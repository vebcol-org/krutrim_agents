import { createAsyncThunk, createSlice, type PayloadAction } from '@reduxjs/toolkit';
import type { Agent, AgentMeta, Chat, ModelSelection, Project, SessionInfo } from '@krutrim_agent/shared-types';

import {
  createAgent as apiCreateAgent,
  createAgentSession,
  updateAgentModelSettings,
  createChat as apiCreateChat,
  createProject as apiCreateProject,
  deleteAgent as apiDeleteAgent,
  deleteChat as apiDeleteChat,
  deleteProject as apiDeleteProject,
  fetchAgentProfiles,
  fetchAgents,
  fetchAgentSessions,
  fetchChats,
  fetchProjects,
  moveChat as apiMoveChat,
  updateAgent as apiUpdateAgent,
  updateChat as apiUpdateChat,
  updateProject as apiUpdateProject,
} from '../api';
import { ApiError } from '../utils/http-client';
import type { RootState } from './store';

/**
 * What the sidebar tree currently has open in the center pane. `'chat'`
 * selections don't carry a `sessionId` here — the `chat` slice
 * (`./chat-slice.ts`) owns which session of a chat is active, since it's
 * also responsible for loading that session's messages. `'agent'`
 * selections carry their own `sessionId` because nothing else tracks it yet
 * (the AG-UI streaming client that will actually use it is a later pass).
 */
export type WorkspaceSelection =
  | { kind: 'chat'; chatId: string }
  | { kind: 'agent'; agentId: string; sessionId: string | null };

export interface WorkspaceState {
  backendUrl: string;
  projects: Project[];
  agentsByProject: Record<string, Agent[]>;
  chatsByProject: Record<string, Chat[]>;
  standaloneChats: Chat[];
  /** Registered agent *profiles* (research/experiment/...) — populates the New Agent picker. */
  agentProfiles: AgentMeta[];
  expandedProjectIds: string[];
  selection: WorkspaceSelection | null;
  isLoading: boolean;
  /** `false` until the first `fetchWorkspace` settles (either way). Lets URL sync
   * tell "still loading" apart from "loaded, and this agent/chat really is gone"
   * so a deep link isn't bounced to `/` before the workspace data arrives. */
  hasLoaded: boolean;
  error: string | null;
}

const initialState: WorkspaceState = {
  backendUrl: '',
  projects: [],
  agentsByProject: {},
  chatsByProject: {},
  standaloneChats: [],
  agentProfiles: [],
  expandedProjectIds: [],
  selection: null,
  isLoading: false,
  hasLoaded: false,
  error: null,
};

function describeError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error) return err.message;
  return fallback;
}

function sortByCreatedAtAsc(sessions: SessionInfo[]): SessionInfo[] {
  return [...sessions].sort((a, b) => a.created_at.localeCompare(b.created_at));
}

interface WorkspaceSnapshot {
  projects: Project[];
  agentsByProject: Record<string, Agent[]>;
  chatsByProject: Record<string, Chat[]>;
  standaloneChats: Chat[];
  agentProfiles: AgentMeta[];
}

/**
 * Loads the whole tree in one pass: every project, each project's agents +
 * chats, every standalone chat, and the registered agent-profile list.
 * Simple/eager rather than lazily loading per project on expand — fine at
 * the project counts this is meant for; revisit if that stops being true.
 */
export const fetchWorkspace = createAsyncThunk<WorkspaceSnapshot, void, { state: RootState; rejectValue: string }>(
  'workspace/fetchWorkspace',
  async (_, { getState, rejectWithValue }) => {
    const { backendUrl } = getState().workspace;
    try {
      const [projects, standaloneChats, agentProfiles] = await Promise.all([
        fetchProjects(backendUrl),
        fetchChats(backendUrl, null),
        fetchAgentProfiles(backendUrl),
      ]);
      const agentsByProject: Record<string, Agent[]> = {};
      const chatsByProject: Record<string, Chat[]> = {};
      await Promise.all(
        projects.map(async (project) => {
          const [agents, chats] = await Promise.all([
            fetchAgents(backendUrl, project.project_id),
            fetchChats(backendUrl, project.project_id),
          ]);
          agentsByProject[project.project_id] = agents;
          chatsByProject[project.project_id] = chats;
        }),
      );
      return { projects, agentsByProject, chatsByProject, standaloneChats, agentProfiles };
    } catch (err) {
      return rejectWithValue(describeError(err, 'Failed to load the workspace.'));
    }
  },
);

export const createNewProject = createAsyncThunk<Project, string, { state: RootState; rejectValue: string }>(
  'workspace/createNewProject',
  async (title, { getState, dispatch, rejectWithValue }) => {
    const { backendUrl } = getState().workspace;
    try {
      const project = await apiCreateProject(backendUrl, { project_title: title });
      await dispatch(fetchWorkspace());
      return project;
    } catch (err) {
      return rejectWithValue(describeError(err, 'Failed to create project.'));
    }
  },
);

export const renameProject = createAsyncThunk<
  Project,
  { projectId: string; title: string },
  { state: RootState; rejectValue: string }
>('workspace/renameProject', async ({ projectId, title }, { getState, rejectWithValue }) => {
  const { backendUrl } = getState().workspace;
  try {
    return await apiUpdateProject(backendUrl, projectId, { project_title: title });
  } catch (err) {
    return rejectWithValue(describeError(err, 'Failed to rename project.'));
  }
});

export const deleteProjectById = createAsyncThunk<string, string, { state: RootState; rejectValue: string }>(
  'workspace/deleteProjectById',
  async (projectId, { getState, rejectWithValue }) => {
    const { backendUrl } = getState().workspace;
    try {
      await apiDeleteProject(backendUrl, projectId);
      return projectId;
    } catch (err) {
      return rejectWithValue(describeError(err, 'Failed to delete project.'));
    }
  },
);

export const createNewAgent = createAsyncThunk<
  { agent: Agent; sessionId: string },
  { projectId: string; agentKey: string; displayName: string; roleModels?: Record<string, ModelSelection> },
  { state: RootState; rejectValue: string }
>(
  'workspace/createNewAgent',
  async ({ projectId, agentKey, displayName, roleModels }, { getState, rejectWithValue }) => {
    const { backendUrl } = getState().workspace;
    try {
      const agent = await apiCreateAgent(backendUrl, projectId, { agent_key: agentKey, display_name: displayName });
      const session = await createAgentSession(backendUrl, projectId, agent.agent_id);
      // Apply any per-role model picks from the New Agent sheet. Best-effort —
      // a failed model PUT doesn't undo the created agent.
      for (const [role, selection] of Object.entries(roleModels ?? {})) {
        try {
          await updateAgentModelSettings(backendUrl, agent.agent_id, role, selection);
        } catch {
          /* keep going — the agent still uses the profile default for that role */
        }
      }
      return { agent, sessionId: session.session_id };
    } catch (err) {
      return rejectWithValue(describeError(err, 'Failed to create agent.'));
    }
  },
);

export const renameAgent = createAsyncThunk<
  Agent,
  { projectId: string; agentId: string; displayName: string },
  { state: RootState; rejectValue: string }
>('workspace/renameAgent', async ({ projectId, agentId, displayName }, { getState, rejectWithValue }) => {
  const { backendUrl } = getState().workspace;
  try {
    return await apiUpdateAgent(backendUrl, projectId, agentId, { display_name: displayName });
  } catch (err) {
    return rejectWithValue(describeError(err, 'Failed to rename agent.'));
  }
});

export const deleteAgentById = createAsyncThunk<
  { projectId: string; agentId: string },
  { projectId: string; agentId: string },
  { state: RootState; rejectValue: string }
>('workspace/deleteAgentById', async ({ projectId, agentId }, { getState, rejectWithValue }) => {
  const { backendUrl } = getState().workspace;
  try {
    await apiDeleteAgent(backendUrl, projectId, agentId);
    return { projectId, agentId };
  } catch (err) {
    return rejectWithValue(describeError(err, 'Failed to delete agent.'));
  }
});

export const createNewChat = createAsyncThunk<
  Chat,
  { displayName: string; projectId?: string | null },
  { state: RootState; rejectValue: string }
>('workspace/createNewChat', async ({ displayName, projectId }, { getState, rejectWithValue }) => {
  const { backendUrl } = getState().workspace;
  try {
    return await apiCreateChat(backendUrl, { display_name: displayName, project_id: projectId ?? null });
  } catch (err) {
    return rejectWithValue(describeError(err, 'Failed to create chat.'));
  }
});

export const renameChat = createAsyncThunk<
  Chat,
  { chatId: string; displayName: string },
  { state: RootState; rejectValue: string }
>('workspace/renameChat', async ({ chatId, displayName }, { getState, rejectWithValue }) => {
  const { backendUrl } = getState().workspace;
  try {
    return await apiUpdateChat(backendUrl, chatId, { display_name: displayName });
  } catch (err) {
    return rejectWithValue(describeError(err, 'Failed to rename chat.'));
  }
});

export const deleteChatById = createAsyncThunk<string, string, { state: RootState; rejectValue: string }>(
  'workspace/deleteChatById',
  async (chatId, { getState, rejectWithValue }) => {
    const { backendUrl } = getState().workspace;
    try {
      await apiDeleteChat(backendUrl, chatId);
      return chatId;
    } catch (err) {
      return rejectWithValue(describeError(err, 'Failed to delete chat.'));
    }
  },
);

export const moveChatToProject = createAsyncThunk<
  Chat,
  { chatId: string; projectId: string | null },
  { state: RootState; rejectValue: string }
>('workspace/moveChatToProject', async ({ chatId, projectId }, { getState, rejectWithValue }) => {
  const { backendUrl } = getState().workspace;
  try {
    return await apiMoveChat(backendUrl, chatId, { project_id: projectId });
  } catch (err) {
    return rejectWithValue(describeError(err, 'Failed to move chat.'));
  }
});

/** Opens an agent: loads its sessions and resumes one — `sessionId` if that
 * session still exists (a deep link / reload), otherwise the oldest, otherwise a
 * fresh one. Mirrors `chat-slice.ts`'s `openChat`. */
export const openAgent = createAsyncThunk<
  { agentId: string; sessionId: string },
  { agentId: string; sessionId?: string | null },
  { state: RootState; rejectValue: string }
>('workspace/openAgent', async ({ agentId, sessionId }, { getState, rejectWithValue }) => {
  const { backendUrl, projects, agentsByProject } = getState().workspace;
  const projectId = projects.find((p) => agentsByProject[p.project_id]?.some((a) => a.agent_id === agentId))
    ?.project_id;
  if (!projectId) return rejectWithValue('Unknown agent.');
  try {
    const sessions = await fetchAgentSessions(backendUrl, projectId, agentId);
    const ordered = sortByCreatedAtAsc(sessions);
    const wanted = sessionId ? ordered.find((s) => s.session_id === sessionId) : undefined;
    const session = wanted ?? ordered[0] ?? (await createAgentSession(backendUrl, projectId, agentId));
    return { agentId, sessionId: session.session_id };
  } catch (err) {
    return rejectWithValue(describeError(err, 'Failed to open agent.'));
  }
});

const workspaceSlice = createSlice({
  name: 'workspace',
  initialState,
  reducers: {
    setBackendUrl(state, action: PayloadAction<string>) {
      state.backendUrl = action.payload;
    },
    toggleProjectExpanded(state, action: PayloadAction<string>) {
      const idx = state.expandedProjectIds.indexOf(action.payload);
      if (idx === -1) state.expandedProjectIds.push(action.payload);
      else state.expandedProjectIds.splice(idx, 1);
    },
    selectChat(state, action: PayloadAction<string>) {
      state.selection = { kind: 'chat', chatId: action.payload };
    },
    clearSelection(state) {
      state.selection = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchWorkspace.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(fetchWorkspace.fulfilled, (state, action) => {
        state.isLoading = false;
        state.hasLoaded = true;
        state.projects = action.payload.projects;
        state.agentsByProject = action.payload.agentsByProject;
        state.chatsByProject = action.payload.chatsByProject;
        state.standaloneChats = action.payload.standaloneChats;
        state.agentProfiles = action.payload.agentProfiles;
      })
      .addCase(fetchWorkspace.rejected, (state, action) => {
        state.isLoading = false;
        state.hasLoaded = true;
        state.error = action.payload ?? action.error.message ?? 'Failed to load the workspace.';
      })

      .addCase(createNewProject.fulfilled, (state, action) => {
        state.expandedProjectIds.push(action.payload.project_id);
      })
      .addCase(createNewProject.rejected, (state, action) => {
        state.error = action.payload ?? action.error.message ?? 'Failed to create project.';
      })

      .addCase(renameProject.fulfilled, (state, action) => {
        const idx = state.projects.findIndex((p) => p.project_id === action.payload.project_id);
        if (idx !== -1) state.projects[idx] = action.payload;
      })
      .addCase(renameProject.rejected, (state, action) => {
        state.error = action.payload ?? action.error.message ?? 'Failed to rename project.';
      })

      .addCase(deleteProjectById.fulfilled, (state, action) => {
        const projectId = action.payload;
        const removedAgentIds = new Set((state.agentsByProject[projectId] ?? []).map((a) => a.agent_id));
        state.projects = state.projects.filter((p) => p.project_id !== projectId);
        delete state.agentsByProject[projectId];
        delete state.chatsByProject[projectId];
        const selection = state.selection;
        if (selection?.kind === 'agent' && removedAgentIds.has(selection.agentId)) {
          state.selection = null;
        }
      })
      .addCase(deleteProjectById.rejected, (state, action) => {
        state.error = action.payload ?? action.error.message ?? 'Failed to delete project.';
      })

      .addCase(createNewAgent.fulfilled, (state, action) => {
        const { agent, sessionId } = action.payload;
        const list = state.agentsByProject[agent.project_id] ?? [];
        state.agentsByProject[agent.project_id] = [...list, agent];
        state.expandedProjectIds = Array.from(new Set([...state.expandedProjectIds, agent.project_id]));
        state.selection = { kind: 'agent', agentId: agent.agent_id, sessionId };
      })
      .addCase(createNewAgent.rejected, (state, action) => {
        state.error = action.payload ?? action.error.message ?? 'Failed to create agent.';
      })

      .addCase(renameAgent.fulfilled, (state, action) => {
        const list = state.agentsByProject[action.payload.project_id];
        if (!list) return;
        const idx = list.findIndex((a) => a.agent_id === action.payload.agent_id);
        if (idx !== -1) list[idx] = action.payload;
      })
      .addCase(renameAgent.rejected, (state, action) => {
        state.error = action.payload ?? action.error.message ?? 'Failed to rename agent.';
      })

      .addCase(deleteAgentById.fulfilled, (state, action) => {
        const { projectId, agentId } = action.payload;
        const list = state.agentsByProject[projectId];
        if (list) {
          state.agentsByProject[projectId] = list.filter((a) => a.agent_id !== agentId);
        }
        const selection = state.selection;
        if (selection?.kind === 'agent' && selection.agentId === agentId) {
          state.selection = null;
        }
      })
      .addCase(deleteAgentById.rejected, (state, action) => {
        state.error = action.payload ?? action.error.message ?? 'Failed to delete agent.';
      })

      .addCase(createNewChat.fulfilled, (state, action) => {
        const chat = action.payload;
        if (chat.project_id) {
          const list = state.chatsByProject[chat.project_id] ?? [];
          state.chatsByProject[chat.project_id] = [...list, chat];
          state.expandedProjectIds = Array.from(new Set([...state.expandedProjectIds, chat.project_id]));
        } else {
          state.standaloneChats = [...state.standaloneChats, chat];
        }
        state.selection = { kind: 'chat', chatId: chat.chat_id };
      })
      .addCase(createNewChat.rejected, (state, action) => {
        state.error = action.payload ?? action.error.message ?? 'Failed to create chat.';
      })

      .addCase(renameChat.fulfilled, (state, action) => {
        const chat = action.payload;
        if (chat.project_id) {
          const list = state.chatsByProject[chat.project_id];
          const idx = list ? list.findIndex((c) => c.chat_id === chat.chat_id) : -1;
          if (list && idx !== -1) list[idx] = chat;
        } else {
          const idx = state.standaloneChats.findIndex((c) => c.chat_id === chat.chat_id);
          if (idx !== -1) state.standaloneChats[idx] = chat;
        }
      })
      .addCase(renameChat.rejected, (state, action) => {
        state.error = action.payload ?? action.error.message ?? 'Failed to rename chat.';
      })

      .addCase(deleteChatById.fulfilled, (state, action) => {
        const chatId = action.payload;
        state.standaloneChats = state.standaloneChats.filter((c) => c.chat_id !== chatId);
        for (const projectId of Object.keys(state.chatsByProject)) {
          state.chatsByProject[projectId] = state.chatsByProject[projectId].filter((c) => c.chat_id !== chatId);
        }
        const selection = state.selection;
        if (selection?.kind === 'chat' && selection.chatId === chatId) {
          state.selection = null;
        }
      })
      .addCase(deleteChatById.rejected, (state, action) => {
        state.error = action.payload ?? action.error.message ?? 'Failed to delete chat.';
      })

      .addCase(moveChatToProject.fulfilled, (state, action) => {
        const chat = action.payload;
        // Remove from every list it might currently be in, then re-insert
        // wherever it now belongs — simplest correct way to handle both
        // directions (into a project, or back to standalone).
        state.standaloneChats = state.standaloneChats.filter((c) => c.chat_id !== chat.chat_id);
        for (const projectId of Object.keys(state.chatsByProject)) {
          state.chatsByProject[projectId] = state.chatsByProject[projectId].filter((c) => c.chat_id !== chat.chat_id);
        }
        if (chat.project_id) {
          const list = state.chatsByProject[chat.project_id] ?? [];
          state.chatsByProject[chat.project_id] = [...list, chat];
          state.expandedProjectIds = Array.from(new Set([...state.expandedProjectIds, chat.project_id]));
        } else {
          state.standaloneChats = [...state.standaloneChats, chat];
        }
      })
      .addCase(moveChatToProject.rejected, (state, action) => {
        state.error = action.payload ?? action.error.message ?? 'Failed to move chat.';
      })

      .addCase(openAgent.fulfilled, (state, action) => {
        state.selection = { kind: 'agent', agentId: action.payload.agentId, sessionId: action.payload.sessionId };
        state.error = null;
      })
      .addCase(openAgent.rejected, (state, action) => {
        state.error = action.payload ?? action.error.message ?? 'Failed to open agent.';
      });
  },
});

export const { setBackendUrl, toggleProjectExpanded, selectChat, clearSelection } = workspaceSlice.actions;
export default workspaceSlice.reducer;
