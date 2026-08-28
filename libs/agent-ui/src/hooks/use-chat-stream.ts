import { useCallback, useMemo, useRef } from 'react';
import type { Message } from '@ag-ui/client';
import type { ChatApiMessage } from '@krutrim_agent/shared-types';

import { syncResolvedChat } from '../store/chat-slice';
import { fetchWorkspace } from '../store/workspace-slice';
import { useAppDispatch, useAppSelector } from '../store/hooks';
import {
  useAgentStream,
  type ReasoningEntry,
  type RunStats,
} from './use-agent-stream';

/**
 * The live send/stream for the plain **Chat** flow — `POST /api/chat`, now an
 * AG-UI SSE stream (same protocol as `/agents/{id}`, see `use-agent-chat.ts`).
 * Sits on the shared `useAgentStream` core and bridges it to `chat-slice`:
 *
 * - the chat/session identity rides in each run's `forwardedProps`; when the
 *   backend creates either on the fly it announces the ids in a `chat_session`
 *   `CUSTOM` event, which we stash and apply on `RUN_FINISHED` (applying mid-run
 *   would rebuild the `HttpAgent` and drop the stream).
 * - the internal `HttpAgent` is seeded with the loaded history (`s.chat.messages`)
 *   so the live message list is always the full conversation, not just this turn.
 */

export interface UseChatStreamResult {
  /** The full conversation for the open chat: seeded history + live turn(s). */
  messages: Message[];
  reasoningByMessageId: Record<string, ReasoningEntry>;
  runStats: RunStats | null;
  isRunning: boolean;
  error: string | null;
  sendMessage: (text: string) => void;
}

function toAguiMessage(message: ChatApiMessage, index: number): Message {
  return { id: `history-${index}`, role: message.role, content: message.content };
}

export function useChatStream({ backendUrl }: { backendUrl: string }): UseChatStreamResult {
  const dispatch = useAppDispatch();
  const { activeChatId, activeSessionId, historySessionId, messages: history, newChatNonce } = useAppSelector(
    (s) => s.chat,
  );

  // Resolved-but-not-yet-applied ids from the current run's `chat_session` event.
  const pendingResolveRef = useRef<{ chatId: string; sessionId: string } | null>(null);

  const url = `${backendUrl}/api/chat`;
  // Identity the HttpAgent is memoised on — any change starts a fresh, re-seeded
  // conversation. Keyed on `historySessionId` (not `activeSessionId`) so the
  // agent only rebuilds once `history` is the loaded history *for that session* —
  // rebuilding on the switcher's optimistic `activeSessionId` would re-seed the
  // new agent with the previous session's messages. Without a session yet (new
  // chat, or a new session on an existing chat) the bumped nonce keeps
  // successive "new…" clicks distinct.
  const conversationKey = historySessionId ?? `${activeChatId ?? 'none'}-new-${newChatNonce}`;

  const seededMessages = useMemo(() => history.map(toAguiMessage), [history]);

  // Identity sent with every run — the session id is `historySessionId`, i.e. the
  // one the internal HttpAgent is actually bound to (see `conversationKey`).
  const forwardedProps = useMemo(
    () => ({
      ...(activeChatId ? { chat_id: activeChatId } : {}),
      ...(historySessionId ? { session_id: historySessionId } : {}),
    }),
    [activeChatId, historySessionId],
  );

  const onCustomEvent = useCallback((name: string, value: unknown) => {
    if (name !== 'chat_session' || !value || typeof value !== 'object') return;
    const { chat_id, session_id } = value as { chat_id?: string; session_id?: string };
    if (chat_id && session_id) pendingResolveRef.current = { chatId: chat_id, sessionId: session_id };
  }, []);

  const onRunFinished = useCallback(() => {
    const pending = pendingResolveRef.current;
    pendingResolveRef.current = null;
    if (!pending) return;
    if (pending.sessionId === activeSessionId && pending.chatId === activeChatId) return;

    // One dispatch adopts the new ids AND loads the now-persisted history +
    // session list together (`syncResolvedChat.fulfilled`). Doing it in a single
    // step means the `HttpAgent` only rebuilds once the history it should be
    // re-seeded with is already in the store.
    void dispatch(syncResolvedChat(pending));
    if (pending.chatId !== activeChatId) void dispatch(fetchWorkspace());
  }, [dispatch, activeChatId, activeSessionId]);

  const stream = useAgentStream({
    url,
    threadId: conversationKey,
    initialMessages: seededMessages,
    forwardedProps,
    onCustomEvent,
    onRunFinished,
  });

  const sendMessage = useCallback(
    (text: string) => {
      pendingResolveRef.current = null;
      stream.sendMessage(text);
    },
    [stream],
  );

  return {
    messages: stream.messages,
    reasoningByMessageId: stream.reasoningByMessageId,
    runStats: stream.runStats,
    isRunning: stream.isRunning,
    error: stream.error,
    sendMessage,
  };
}
