import { useEffect } from 'react';
import type { ChatApiMessage, SessionInfo } from '@krutrim_agent/shared-types';

import {
  ensureChatSession,
  openChat,
  openSession,
  postMessage,
  setBackendUrl,
  startNewChat,
  startNewSession,
} from '../store/chat-slice';
import { useAppDispatch, useAppSelector } from '../store/hooks';

/**
 * The **active chat conversation** — messages, sessions, and the send flow
 * for whichever chat is currently open (see `../store/chat-slice.ts`). Does
 * *not* list chats — that's `useWorkspace` (`./use-workspace.ts`), which
 * drives the sidebar tree. Selecting a chat node dispatches both: this
 * hook's `selectChat` (loads messages) and `useWorkspace`'s `selectChat`
 * (tree highlighting) — see `history-rail.tsx`.
 */

export interface UseChatOptions {
  backendUrl: string;
}

export interface UseChatResult {
  sessions: SessionInfo[];
  activeChatId: string | null;
  activeSessionId: string | null;
  messages: ChatApiMessage[];
  isLoading: boolean;
  isSending: boolean;
  error: string | null;
  startNewChat: () => void;
  startNewSession: () => void;
  selectChat: (chatId: string) => void;
  selectSession: (sessionId: string) => void;
  sendMessage: (text: string) => void;
  /** Resolves to a guaranteed `session_id` for the active chat, creating the
   * session (and the chat, if none is selected) on demand — see
   * `ensureChatSession`. Returns `null` if creation failed. */
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
    messages: state.messages,
    isLoading: state.isLoading,
    isSending: state.isSending,
    error: state.error,
    startNewChat: () => dispatch(startNewChat()),
    startNewSession: () => dispatch(startNewSession()),
    selectChat: (chatId: string) => {
      dispatch(openChat(chatId));
    },
    selectSession: (sessionId: string) => {
      if (!state.activeChatId) return;
      dispatch(openSession(sessionId));
    },
    sendMessage: (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || state.isSending) return;
      dispatch(postMessage(trimmed));
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
