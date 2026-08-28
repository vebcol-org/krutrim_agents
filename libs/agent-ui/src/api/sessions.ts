import type {
  ChatApiMessage,
  EmbedRequest,
  EmbedResponse,
  RagDocument,
  RagTextResponse,
  SessionInfo,
  SessionSandboxPolicyUpdate,
  UpdateSessionRequest,
} from '@krutrim_agent/shared-types';

import { apiDelete, apiGet, apiPost, apiPostForm, apiPut } from '../utils/http-client';
import {
  embedResponseSchema,
  ragDocumentsResponseSchema,
  ragTextResponseSchema,
  sessionInfoSchema,
  sessionMessagesResponseSchema,
} from './schemas';

/** `GET /api/sessions/{sessionId}` — sessions are addressed by id alone (globally unique). */
export function fetchSession(backendUrl: string, sessionId: string): Promise<SessionInfo> {
  return apiGet(`${backendUrl}/api/sessions/${sessionId}`, sessionInfoSchema);
}

/** `PUT /api/sessions/{sessionId}` — rename. */
export function updateSession(
  backendUrl: string,
  sessionId: string,
  body: UpdateSessionRequest,
): Promise<SessionInfo> {
  return apiPut(`${backendUrl}/api/sessions/${sessionId}`, sessionInfoSchema, body);
}

/** `DELETE /api/sessions/{sessionId}` */
export function deleteSession(backendUrl: string, sessionId: string): Promise<void> {
  return apiDelete(`${backendUrl}/api/sessions/${sessionId}`);
}

/** `GET /api/sessions/{sessionId}/messages` — used to reload a past conversation. Only ever
 * populated for `Chat`-owned sessions today; an `Agent`-owned session's real history lives in
 * its LangGraph checkpoint, which has no REST route exposing it yet (see the hierarchy plan). */
export async function fetchSessionMessages(backendUrl: string, sessionId: string): Promise<ChatApiMessage[]> {
  const data = await apiGet(`${backendUrl}/api/sessions/${sessionId}/messages`, sessionMessagesResponseSchema);
  return data.messages;
}

/** `PUT /api/sessions/{sessionId}/sandbox-policy` */
export function updateSessionSandboxPolicy(
  backendUrl: string,
  sessionId: string,
  update: SessionSandboxPolicyUpdate,
): Promise<SessionInfo> {
  return apiPut(`${backendUrl}/api/sessions/${sessionId}/sandbox-policy`, sessionInfoSchema, update);
}

/** `POST /api/sessions/{sessionId}/embed` — dispatches the embedding precompute job. */
export function triggerEmbed(backendUrl: string, sessionId: string, body: EmbedRequest): Promise<EmbedResponse> {
  return apiPost(`${backendUrl}/api/sessions/${sessionId}/embed`, embedResponseSchema, body);
}

/** `POST /api/sessions/{sessionId}/rag/file` — real (binary-capable) document
 * upload: PDF, DOCX, and anything else `krutrim_agent_doc`'s parser registry
 * supports, not just plain text. Response shape is identical to `/rag/text`'s. */
export function submitRagFile(
  backendUrl: string,
  sessionId: string,
  file: File,
  title?: string | null,
): Promise<RagTextResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (title) formData.append('title', title);
  return apiPostForm(`${backendUrl}/api/sessions/${sessionId}/rag/file`, ragTextResponseSchema, formData);
}

/** `GET /api/sessions/{sessionId}/rag/documents` — every document ingested into
 * this session's RAG index, oldest first. Feeds the persistent attachment bar. */
export async function fetchSessionRagDocuments(backendUrl: string, sessionId: string): Promise<RagDocument[]> {
  const data = await apiGet(`${backendUrl}/api/sessions/${sessionId}/rag/documents`, ragDocumentsResponseSchema);
  return data.documents;
}

/** `DELETE /api/sessions/{sessionId}/rag/documents/{documentId}` — removes the
 * document from the session manifest (indexed vectors are swept on session delete). */
export function deleteSessionRagDocument(backendUrl: string, sessionId: string, documentId: string): Promise<void> {
  return apiDelete(`${backendUrl}/api/sessions/${sessionId}/rag/documents/${documentId}`);
}
