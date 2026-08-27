import { createAsyncThunk, createSlice, type PayloadAction } from '@reduxjs/toolkit';
import type { ChatApiMessage, SessionInfo } from '@krutrim_agent/shared-types';

import { createChat, createChatSession, fetchChatSessions, fetchSessionMessages, sendChatMessage } from '../api';
import { ApiError } from '../utils/http-client';
import type { RootState } from './store';

/**
 * The **active chat conversation** — messages, sessions of the currently
 * open chat, and the send/open flow. Chat *listing* (the sidebar tree) is
 * `workspace-slice.ts`'s job, not this one; the two are deliberately
 * decoupled (see that file's docstring) rather than one slice owning both.
 */

export interface ChatState {
  backendUrl: string;
  sessions: SessionInfo[];
  activeChatId: string | null;
  activeSessionId: string | null;
  messages: ChatApiMessage[];
  isLoading: boolean;
  isSending: boolean;
  error: string | null;
}

const initialState: ChatState = {
  backendUrl: '',
  sessions: [],
  activeChatId: null,
  activeSessionId: null,
  messages: [],
  isLoading: false,
  isSending: false,
  error: null,
};

function sortByCreatedAtAsc(sessions: SessionInfo[]): SessionInfo[] {
  return [...sessions].sort((a, b) => a.created_at.localeCompare(b.created_at));
}

/**
 * Turns a thrown error into a user-displayable string: an `ApiError`'s
 * backend-provided `detail` when available (including `ApiSchemaError`,
 * which is an `Error` subclass carrying a precise "the backend response
 * didn't match what we expected" message — see `../utils/http-client.ts`),
 * else a generic fallback.
 */
function describeError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return fallback;
}

interface OpenChatResult {
  chatId: string;
  sessions: SessionInfo[];
  sessionId: string | null;
  messages: ChatApiMessage[];
}

/** Selects a chat, opening its first (oldest) session if one exists — mirrors backend lazy session creation. */
export const openChat = createAsyncThunk<OpenChatResult, string, { state: RootState; rejectValue: string }>(
  'chat/openChat',
  async (chatId, { getState, rejectWithValue }) => {
    const { backendUrl } = getState().chat;
    try {
      const sessionList = await fetchChatSessions(backendUrl, chatId);
      const ordered = sortByCreatedAtAsc(sessionList);
      if (ordered.length === 0) {
        return { chatId, sessions: ordered, sessionId: null, messages: [] };
      }
      const sessionId = ordered[0].session_id;
      const messages = await fetchSessionMessages(backendUrl, sessionId);
      return { chatId, sessions: ordered, sessionId, messages };
    } catch (err) {
      return rejectWithValue(describeError(err, 'Failed to open chat.'));
    }
  },
);

interface OpenSessionResult {
  sessionId: string;
  messages: ChatApiMessage[];
}

export const openSession = createAsyncThunk<OpenSessionResult, string, { state: RootState; rejectValue: string }>(
  'chat/openSession',
  async (sessionId, { getState, rejectWithValue }) => {
    const { activeChatId, backendUrl } = getState().chat;
    if (!activeChatId) return rejectWithValue('No active chat.');
    try {
      const messages = await fetchSessionMessages(backendUrl, sessionId);
      return { sessionId, messages };
    } catch (err) {
      return rejectWithValue(describeError(err, 'Failed to open session.'));
    }
  },
);

interface PostMessageResult {
  message: ChatApiMessage;
  chatId: string;
  sessionId: string;
  sessions?: SessionInfo[];
}

export const postMessage = createAsyncThunk<PostMessageResult, string, { state: RootState; rejectValue: string }>(
  'chat/postMessage',
  async (trimmed, { getState, rejectWithValue }) => {
    const { backendUrl, activeChatId, activeSessionId } = getState().chat;
    try {
      const response = await sendChatMessage(backendUrl, {
        message: trimmed,
        chat_id: activeChatId,
        session_id: activeSessionId,
      });

      const chatChanged = response.chat_id !== activeChatId;
      const sessionChanged = response.session_id !== activeSessionId;
      // Note: if `chatChanged` (a brand-new chat was implicitly created by
      // sending a message with no chat pre-selected), the sidebar tree
      // (`workspace-slice.ts`) won't know about it until its next
      // `fetchWorkspace()` — the two slices are deliberately decoupled, so
      // this slice doesn't reach into that one to refresh it. A known,
      // tolerable gap for this pass, same as other documented ones in
      // this codebase (e.g. `SandboxSettingsPanel` not refreshing its
      // parent's list after a save).

      let sessions: SessionInfo[] | undefined;
      if (chatChanged || sessionChanged) {
        sessions = sortByCreatedAtAsc(await fetchChatSessions(backendUrl, response.chat_id));
      }

      return {
        message: response.message,
        chatId: response.chat_id,
        sessionId: response.session_id,
        sessions,
      };
    } catch (err) {
      return rejectWithValue(describeError(err, 'Failed to send message.'));
    }
  },
);

interface EnsureSessionResult {
  chatId: string;
  sessionId: string;
  /** Present only when this call had to create the session (and possibly the
   * chat) — lets the reducer fold the new session into `sessions`. */
  session?: SessionInfo;
}

/**
 * Guarantees the active chat has a real `session_id`, creating one (and, if
 * nothing is selected yet, the chat itself) on demand. Used by the composer
 * before a file attachment: RAG ingestion is a `POST /api/sessions/{id}/rag/file`
 * call, so it can't run against the backend's usual lazy-on-first-message
 * session. A no-op when a session already exists.
 *
 * Like `postMessage`, when this implicitly creates a chat the sidebar tree
 * (`workspace-slice.ts`) won't know about it until its next `fetchWorkspace()`
 * — the two slices stay decoupled; a tolerable, already-documented gap.
 */
export const ensureChatSession = createAsyncThunk<
  EnsureSessionResult,
  void,
  { state: RootState; rejectValue: string }
>('chat/ensureChatSession', async (_arg, { getState, rejectWithValue }) => {
  const { backendUrl, activeChatId, activeSessionId } = getState().chat;
  if (activeSessionId && activeChatId) {
    return { chatId: activeChatId, sessionId: activeSessionId };
  }
  try {
    let chatId = activeChatId;
    if (!chatId) {
      const chat = await createChat(backendUrl, { display_name: 'New chat', project_id: null });
      chatId = chat.chat_id;
    }
    const session = await createChatSession(backendUrl, chatId);
    return { chatId, sessionId: session.session_id, session };
  } catch (err) {
    return rejectWithValue(describeError(err, 'Failed to start a session.'));
  }
});

const chatSlice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    setBackendUrl(state, action: PayloadAction<string>) {
      state.backendUrl = action.payload;
    },
    startNewChat(state) {
      state.activeChatId = null;
      state.activeSessionId = null;
      state.sessions = [];
      state.messages = [];
      state.error = null;
    },
    startNewSession(state) {
      if (!state.activeChatId) return;
      state.activeSessionId = null;
      state.messages = [];
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(openChat.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(openChat.fulfilled, (state, action) => {
        state.isLoading = false;
        state.activeChatId = action.payload.chatId;
        state.sessions = action.payload.sessions;
        state.activeSessionId = action.payload.sessionId;
        state.messages = action.payload.messages;
      })
      .addCase(openChat.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload ?? action.error.message ?? 'Failed to open chat.';
      })

      .addCase(openSession.pending, (state, action) => {
        state.isLoading = true;
        state.error = null;
        state.activeSessionId = action.meta.arg;
      })
      .addCase(openSession.fulfilled, (state, action) => {
        state.isLoading = false;
        state.messages = action.payload.messages;
      })
      .addCase(openSession.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload ?? action.error.message ?? 'Failed to open session.';
      })

      .addCase(postMessage.pending, (state, action) => {
        state.isSending = true;
        state.error = null;
        state.messages.push({ role: 'user', content: action.meta.arg });
      })
      .addCase(postMessage.fulfilled, (state, action) => {
        state.isSending = false;
        state.messages.push(action.payload.message);
        state.activeChatId = action.payload.chatId;
        state.activeSessionId = action.payload.sessionId;
        if (action.payload.sessions) state.sessions = action.payload.sessions;
      })
      .addCase(postMessage.rejected, (state, action) => {
        state.isSending = false;
        state.error = action.payload ?? action.error.message ?? 'Failed to send message.';
      })

      .addCase(ensureChatSession.fulfilled, (state, action) => {
        state.activeChatId = action.payload.chatId;
        state.activeSessionId = action.payload.sessionId;
        if (action.payload.session && !state.sessions.some((s) => s.session_id === action.payload.sessionId)) {
          state.sessions = sortByCreatedAtAsc([...state.sessions, action.payload.session]);
        }
      })
      .addCase(ensureChatSession.rejected, (state, action) => {
        state.error = action.payload ?? action.error.message ?? 'Failed to start a session.';
      });
  },
});

export const { setBackendUrl, startNewChat, startNewSession } = chatSlice.actions;
export default chatSlice.reducer;
