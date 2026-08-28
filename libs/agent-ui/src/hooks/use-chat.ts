import { useEffect } from 'react';
import type { ChatApiMessage, SessionInfo } from '@krutrim_agent/shared-types';

import {
  createNewChatSession,
  ensureChatSession,
  openChat,
  openSession,
  setBackendUrl,
  startNewChat,
} from '../store/chat-slice';
import { useAppDispatch, useAppSelector } from '../store/hooks';

/**
 * The **active chat conversation**'s sessions + loaded history + open/select
 * flow (see `../store/chat-slice.ts`). The live send/stream is `useChatStream`
 * (`./use-chat-stream.ts`); chat *listing* is `useWorkspace`.
 */

export interface UseChatOptions {
  backendUrl: string;
}

export interface UseChatResult {
  sessions: SessionInfo[];
  activeChatId: string | null;
  activeSessionId: string | null;
  /** The session `messages` actually belong to — lags `activeSessionId` during a switch. */
  historySessionId: string | null;
  /** History for `historySessionId` — the live turn from `useChatStream` renders on top. */
  messages: ChatApiMessage[];
  isLoading: boolean;
  error: string | null;
  startNewChat: () => void;
  /** Creates a real session on the active chat and switches to it. */
  startNewSession: () => void;
  selectChat: (chatId: string) => void;
  /** Opens a chat and lands on a specific session — used by the URL sync on a deep link. */
  openChatAt: (chatId: string, sessionId: string | null) => void;
  selectSession: (sessionId: string) => void;
  /** Resolves to a guaranteed `session_id` for the active chat, creating the
   * session (and the chat, if none is selected) on demand. `null` if it failed. */
  ensureSession: () => Promise<string | null>;
}

export function useChat({ backendUrl }: UseChatOptions): UseChatResult {
  const dispatch = useAppDispatch();
  const state = useAppSelector((s) => s.chat);

  useEffect(() => {
    dispatch(setBackendUrl(backendUrl));
  }, [dispatch, backendUrl]);

  return {
    sessions: state.sessions,
    activeChatId: state.activeChatId,
    activeSessionId: state.activeSessionId,
    historySessionId: state.historySessionId,
    messages: state.messages,
    isLoading: state.isLoading,
    error: state.error,
    startNewChat: () => dispatch(startNewChat()),
    startNewSession: () => dispatch(createNewChatSession()),
    selectChat: (chatId: string) => {
      dispatch(openChat({ chatId }));
    },
    openChatAt: (chatId: string, sessionId: string | null) => {
      dispatch(openChat({ chatId, sessionId }));
    },
    selectSession: (sessionId: string) => {
      if (!state.activeChatId) return;
      dispatch(openSession(sessionId));
    },
    ensureSession: async () => {
      if (state.activeSessionId) return state.activeSessionId;
      try {
        const result = await dispatch(ensureChatSession()).unwrap();
        return result.sessionId;
      } catch {
        return null;
      }
    },
  };
}
