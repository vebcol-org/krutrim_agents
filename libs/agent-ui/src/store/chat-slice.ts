import { createAsyncThunk, createSlice, type PayloadAction } from '@reduxjs/toolkit';
import type { ChatApiMessage, SessionInfo } from '@krutrim_agent/shared-types';

import { createChat, createChatSession, fetchChatSessions, fetchSessionMessages } from '../api';
import { ApiError } from '../utils/http-client';
import type { RootState } from './store';

/**
 * The **active chat conversation**'s sessions + loaded history, and the
 * open/select flow. The *live send* is no longer here: `POST /api/chat` is an
 * AG-UI SSE stream consumed by `useChatStream` (`../hooks/use-chat-stream.ts`),
 * which owns the streaming message state and calls back into this slice via
 * `chatSessionResolved` (ids created on the fly) and `openSession` (reload
 * history once a turn completes). Chat *listing* (the sidebar tree) is
 * `workspace-slice.ts`'s job.
 *
 * `activeSessionId` vs `historySessionId`: the switcher updates `activeSessionId`
 * the instant you pick an entry (so the `<Select>` feels responsive), but the
 * message stream + files drawer key off `historySessionId`, which only advances
 * once that session's history has actually loaded. Keeping them separate stops
 * the thread from rendering the *previous* session's messages against the *new*
 * session's file list during the load (the "files and messages don't match"
 * bug).
 */

export interface ChatState {
  backendUrl: string;
  sessions: SessionInfo[];
  activeChatId: string | null;
  /** The session the switcher currently points at — updated immediately on select. */
  activeSessionId: string | null;
  /** The session `messages` actually belong to — advances only once that
   * session's history has loaded. `useChatStream` / `useSessionFiles` key off
   * this so the thread and the file list never show two different sessions. */
  historySessionId: string | null;
  /** History for `historySessionId`, loaded on open — the live turn streams on top of this. */
  messages: ChatApiMessage[];
  isLoading: boolean;
  error: string | null;
  /** Bumped by `startNewChat` / `createNewChatSession` so `useChatStream` can
   * tell two successive "new…" actions apart and rebuild its `HttpAgent`. */
  newChatNonce: number;
}

const initialState: ChatState = {
  backendUrl: '',
  sessions: [],
  activeChatId: null,
  activeSessionId: null,
  historySessionId: null,
  messages: [],
  isLoading: false,
  error: null,
  newChatNonce: 0,
};

/** Oldest → newest. The switcher renders this reversed (newest on top) while
 * still numbering "Session N" by this order, so N stays stable for a session
 * as later ones are added. */
function sortByCreatedAtAsc(sessions: SessionInfo[]): SessionInfo[] {
  return [...sessions].sort((a, b) => a.created_at.localeCompare(b.created_at));
}

/** The session a freshly-opened chat should land on — the newest one. */
function newestSessionId(ordered: SessionInfo[]): string | null {
  return ordered.length ? ordered[ordered.length - 1].session_id : null;
}

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

export interface OpenChatArg {
  chatId: string;
  /** Land on this specific session (e.g. from a deep link) instead of the newest.
   * Ignored if the chat has no such session. */
  sessionId?: string | null;
}

/** Selects a chat, opening the newest session if one exists (or the requested
 * `sessionId`) — mirrors backend lazy session creation when there are none. */
export const openChat = createAsyncThunk<OpenChatResult, OpenChatArg, { state: RootState; rejectValue: string }>(
  'chat/openChat',
  async ({ chatId, sessionId: requested }, { getState, rejectWithValue }) => {
    const { backendUrl } = getState().chat;
    try {
      const sessionList = await fetchChatSessions(backendUrl, chatId);
      const ordered = sortByCreatedAtAsc(sessionList);
      if (ordered.length === 0) {
        return { chatId, sessions: ordered, sessionId: null, messages: [] };
      }
      const sessionId =
        requested && ordered.some((s) => s.session_id === requested)
          ? requested
          : (newestSessionId(ordered) as string);
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

interface SyncResolvedChatResult {
  chatId: string;
  sessionId: string;
  sessions: SessionInfo[];
  messages: ChatApiMessage[];
}

/**
 * Called by `useChatStream` once a streamed turn finishes against a chat/session
 * that was created on the fly: adopts the new ids and pulls the now-persisted
 * history + session list so a later `HttpAgent` rebuild (or navigating away and
 * back) sees the complete conversation.
 */
export const syncResolvedChat = createAsyncThunk<
  SyncResolvedChatResult,
  { chatId: string; sessionId: string },
  { state: RootState; rejectValue: string }
>('chat/syncResolvedChat', async ({ chatId, sessionId }, { getState, rejectWithValue }) => {
  const { backendUrl } = getState().chat;
  try {
    const [messages, sessionList] = await Promise.all([
      fetchSessionMessages(backendUrl, sessionId),
      fetchChatSessions(backendUrl, chatId),
    ]);
    return { chatId, sessionId, sessions: sortByCreatedAtAsc(sessionList), messages };
  } catch (err) {
    return rejectWithValue(describeError(err, 'Failed to sync chat.'));
  }
});

interface CreateSessionResult {
  chatId: string;
  session: SessionInfo;
}

/**
 * The "+" (new session) button: creates a real session on the active chat
 * immediately (`POST /api/chats/{chatId}/sessions`) and switches to it, rather
 * than just blanking the thread and waiting for the first message. Keeps the
 * switcher list and the backend in lock-step.
 */
export const createNewChatSession = createAsyncThunk<
  CreateSessionResult,
  void,
  { state: RootState; rejectValue: string }
>('chat/createNewChatSession', async (_arg, { getState, rejectWithValue }) => {
  const { backendUrl, activeChatId } = getState().chat;
  if (!activeChatId) return rejectWithValue('No active chat.');
  try {
    const session = await createChatSession(backendUrl, activeChatId);
    return { chatId: activeChatId, session };
  } catch (err) {
    return rejectWithValue(describeError(err, 'Failed to create session.'));
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
      state.historySessionId = null;
      state.sessions = [];
      state.messages = [];
      state.error = null;
      state.newChatNonce += 1;
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
        state.historySessionId = action.payload.sessionId;
        state.messages = action.payload.messages;
      })
      .addCase(openChat.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload ?? action.error.message ?? 'Failed to open chat.';
      })

      .addCase(openSession.pending, (state, action) => {
        state.isLoading = true;
        state.error = null;
        // Move the switcher's pointer now; `historySessionId` stays put until
        // the history for `action.meta.arg` has actually loaded (fulfilled).
        state.activeSessionId = action.meta.arg;
      })
      .addCase(openSession.fulfilled, (state, action) => {
        state.isLoading = false;
        state.historySessionId = action.payload.sessionId;
        state.messages = action.payload.messages;
      })
      .addCase(openSession.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload ?? action.error.message ?? 'Failed to open session.';
      })

      .addCase(syncResolvedChat.fulfilled, (state, action) => {
        state.isLoading = false;
        state.activeChatId = action.payload.chatId;
        state.activeSessionId = action.payload.sessionId;
        state.historySessionId = action.payload.sessionId;
        state.sessions = action.payload.sessions;
        state.messages = action.payload.messages;
      })
      .addCase(syncResolvedChat.rejected, (state, action) => {
        state.error = action.payload ?? action.error.message ?? 'Failed to sync chat.';
      })

      .addCase(ensureChatSession.fulfilled, (state, action) => {
        state.activeChatId = action.payload.chatId;
        state.activeSessionId = action.payload.sessionId;
        state.historySessionId = action.payload.sessionId;
        if (action.payload.session && !state.sessions.some((s) => s.session_id === action.payload.sessionId)) {
          state.sessions = sortByCreatedAtAsc([...state.sessions, action.payload.session]);
        }
      })
      .addCase(ensureChatSession.rejected, (state, action) => {
        state.error = action.payload ?? action.error.message ?? 'Failed to start a session.';
      })

      .addCase(createNewChatSession.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(createNewChatSession.fulfilled, (state, action) => {
        state.isLoading = false;
        const { session } = action.payload;
        if (!state.sessions.some((s) => s.session_id === session.session_id)) {
          state.sessions = sortByCreatedAtAsc([...state.sessions, session]);
        }
        state.activeSessionId = session.session_id;
        state.historySessionId = session.session_id;
        state.messages = [];
        state.newChatNonce += 1;
      })
      .addCase(createNewChatSession.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload ?? action.error.message ?? 'Failed to create session.';
      });
  },
});

export const { setBackendUrl, startNewChat } = chatSlice.actions;
export default chatSlice.reducer;
