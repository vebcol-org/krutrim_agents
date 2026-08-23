import { z } from 'zod';
import type {
  Chat,
  ChatSandboxPolicyUpdate,
  CreateChatRequest,
  MoveChatRequest,
  SessionInfo,
  UpdateChatRequest,
} from '@krutrim_agent/shared-types';

import { apiDelete, apiGet, apiPost, apiPut } from '../utils/http-client';
import { chatSchema, sessionInfoSchema } from './schemas';

/** `POST /api/chats` — `project_id` omitted/`null` creates a standalone chat. */
export function createChat(backendUrl: string, body: CreateChatRequest): Promise<Chat> {
  return apiPost(`${backendUrl}/api/chats`, chatSchema, body);
}

/** `GET /api/chats?project_id=<id>` — that project's chats; omitting `projectId` lists
 * **standalone** chats, not "every chat" (matches the backend's `Storage.list_chats` semantics). */
export function fetchChats(backendUrl: string, projectId?: string | null): Promise<Chat[]> {
  const url = new URL(`${backendUrl}/api/chats`);
  if (projectId) url.searchParams.set('project_id', projectId);
  return apiGet(url.toString(), z.array(chatSchema));
}

/** `GET /api/chats/{chatId}` */
export function fetchChat(backendUrl: string, chatId: string): Promise<Chat> {
  return apiGet(`${backendUrl}/api/chats/${chatId}`, chatSchema);
}

/** `PUT /api/chats/{chatId}` — rename. */
export function updateChat(backendUrl: string, chatId: string, body: UpdateChatRequest): Promise<Chat> {
  return apiPut(`${backendUrl}/api/chats/${chatId}`, chatSchema, body);
}

/** `DELETE /api/chats/{chatId}` — cascades this chat's sessions. */
export function deleteChat(backendUrl: string, chatId: string): Promise<void> {
  return apiDelete(`${backendUrl}/api/chats/${chatId}`);
}

/** `POST /api/chats/{chatId}/move` — sets or (passing `project_id: null`) clears the chat's project. */
export function moveChat(backendUrl: string, chatId: string, body: MoveChatRequest): Promise<Chat> {
  return apiPost(`${backendUrl}/api/chats/${chatId}/move`, chatSchema, body);
}

/** `PUT /api/chats/{chatId}/sandbox-policy` — only takes effect once the chat has a `project_id`. */
export function updateChatSandboxPolicy(
  backendUrl: string,
  chatId: string,
  update: ChatSandboxPolicyUpdate,
): Promise<Chat> {
  return apiPut(`${backendUrl}/api/chats/${chatId}/sandbox-policy`, chatSchema, update);
}

/** `POST /api/chats/{chatId}/sessions` — creates a session owned by this chat. */
export function createChatSession(backendUrl: string, chatId: string): Promise<SessionInfo> {
  return apiPost(`${backendUrl}/api/chats/${chatId}/sessions`, sessionInfoSchema, undefined);
}

/** `GET /api/chats/{chatId}/sessions` — this chat's sessions. */
export function fetchChatSessions(backendUrl: string, chatId: string): Promise<SessionInfo[]> {
  return apiGet(`${backendUrl}/api/chats/${chatId}/sessions`, z.array(sessionInfoSchema));
}
