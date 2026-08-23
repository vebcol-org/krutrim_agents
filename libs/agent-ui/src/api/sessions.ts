import type {
  ChatApiMessage,
  EmbedRequest,
  EmbedResponse,
  RagTextRequest,
  RagTextResponse,
  SessionInfo,
  SessionSandboxPolicyUpdate,
  UpdateSessionRequest,
} from '@krutrim_agent/shared-types';

import { apiDelete, apiGet, apiPost, apiPut } from '../utils/http-client';
import { embedResponseSchema, ragTextResponseSchema, sessionInfoSchema, sessionMessagesResponseSchema } from './schemas';

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

/** `POST /api/sessions/{sessionId}/rag/text` — dispatches RAG ingestion for pasted
 * text, or a `.txt` file's contents read client-side (v1 ingestion is text-only —
 * see `RagTextRequest`). */
export function submitRagText(backendUrl: string, sessionId: string, body: RagTextRequest): Promise<RagTextResponse> {
  return apiPost(`${backendUrl}/api/sessions/${sessionId}/rag/text`, ragTextResponseSchema, body);
}
