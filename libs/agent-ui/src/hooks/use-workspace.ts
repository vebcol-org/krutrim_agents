import { useEffect } from 'react';
import type { Agent, AgentMeta, Chat, Project } from '@krutrim_agent/shared-types';

import {
  createNewAgent,
  createNewChat,
  createNewProject,
  deleteAgentById,
  deleteChatById,
  deleteProjectById,
  fetchWorkspace,
  moveChatToProject,
  openAgent as openAgentThunk,
  renameAgent,
  renameChat,
  renameProject,
  selectChat as selectChatAction,
  setBackendUrl,
  toggleProjectExpanded as toggleProjectExpandedAction,
  type WorkspaceSelection,
} from '../store/workspace-slice';
import { useAppDispatch, useAppSelector } from '../store/hooks';

/**
 * The sidebar tree's data + CRUD, on top of `workspace-slice.ts`. Distinct
 * from `useChat` (`./use-chat.ts`), which owns the *active chat
 * conversation*'s messages — selecting a chat node here dispatches both
 * this hook's `selectChat` (tree highlighting) and, at the call site,
 * `useChat`'s `selectChat`/`openChat` (message loading), since the two
 * slices are deliberately kept decoupled rather than reaching into each other.
 */

export interface UseWorkspaceOptions {
  backendUrl: string;
}

export interface UseWorkspaceResult {
  projects: Project[];
  agentsByProject: Record<string, Agent[]>;
  chatsByProject: Record<string, Chat[]>;
  standaloneChats: Chat[];
  agentProfiles: AgentMeta[];
  expandedProjectIds: string[];
  selection: WorkspaceSelection | null;
  isLoading: boolean;
  error: string | null;
  toggleProjectExpanded: (projectId: string) => void;
  createProject: (title: string) => void;
  renameProjectTitle: (projectId: string, title: string) => void;
  deleteProject: (projectId: string) => void;
  /** `newProjectTitle` set → creates that project first, then the agent inside it (see
   * `NewAgentSheet`'s inline "create new project" flow). */
  createAgent: (params: { projectId: string; newProjectTitle?: string; agentKey: string; displayName: string }) => void;
  renameAgentName: (projectId: string, agentId: string, displayName: string) => void;
  deleteAgent: (projectId: string, agentId: string) => void;
  createChat: (displayName: string, projectId?: string | null) => void;
  renameChatName: (chatId: string, displayName: string) => void;
  deleteChat: (chatId: string) => void;
  moveChat: (chatId: string, projectId: string | null) => void;
  selectChat: (chatId: string) => void;
  openAgent: (agentId: string) => void;
}

export function useWorkspace({ backendUrl }: UseWorkspaceOptions): UseWorkspaceResult {
  const dispatch = useAppDispatch();
  const state = useAppSelector((s) => s.workspace);

  useEffect(() => {
    dispatch(setBackendUrl(backendUrl));
    dispatch(fetchWorkspace());
  }, [dispatch, backendUrl]);

  return {
    projects: state.projects,
    agentsByProject: state.agentsByProject,
    chatsByProject: state.chatsByProject,
    standaloneChats: state.standaloneChats,
    agentProfiles: state.agentProfiles,
    expandedProjectIds: state.expandedProjectIds,
    selection: state.selection,
    isLoading: state.isLoading,
    error: state.error,
    toggleProjectExpanded: (projectId) => dispatch(toggleProjectExpandedAction(projectId)),
    createProject: (title) => {
      dispatch(createNewProject(title));
    },
    renameProjectTitle: (projectId, title) => {
      dispatch(renameProject({ projectId, title }));
    },
    deleteProject: (projectId) => {
      dispatch(deleteProjectById(projectId));
    },
    createAgent: ({ projectId, newProjectTitle, agentKey, displayName }) => {
      if (newProjectTitle) {
        // Create the project first, then the agent inside it — the New Agent
        // sheet's "+ Create new project…" option collapses both steps into
        // one submit for the user, but the backend still needs them in order.
        void dispatch(createNewProject(newProjectTitle))
          .unwrap()
          .then((project) => {
            dispatch(createNewAgent({ projectId: project.project_id, agentKey, displayName }));
          });
        return;
      }
      dispatch(createNewAgent({ projectId, agentKey, displayName }));
    },
    renameAgentName: (projectId, agentId, displayName) => {
      dispatch(renameAgent({ projectId, agentId, displayName }));
    },
    deleteAgent: (projectId, agentId) => {
      dispatch(deleteAgentById({ projectId, agentId }));
    },
    createChat: (displayName, projectId) => {
      dispatch(createNewChat({ displayName, projectId }));
    },
    renameChatName: (chatId, displayName) => {
      dispatch(renameChat({ chatId, displayName }));
    },
    deleteChat: (chatId) => {
      dispatch(deleteChatById(chatId));
    },
    moveChat: (chatId, projectId) => {
      dispatch(moveChatToProject({ chatId, projectId }));
    },
    selectChat: (chatId) => {
      dispatch(selectChatAction(chatId));
    },
    openAgent: (agentId) => {
      dispatch(openAgentThunk(agentId));
    },
  };
}
