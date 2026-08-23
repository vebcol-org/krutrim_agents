import type { SendChatMessageRequest, SendChatMessageResponse } from '@krutrim_agent/shared-types';

import { apiPost } from '../utils/http-client';
import { sendChatMessageResponseSchema } from './schemas';

/** `POST /api/chat` — the plain, non-agentic chat flow. Auto-creates the Chat/session on first
 * call (optionally scoped to a project via `project_id`, only consulted when `chat_id` is omitted). */
export function sendChatMessage(backendUrl: string, body: SendChatMessageRequest): Promise<SendChatMessageResponse> {
  return apiPost(`${backendUrl}/api/chat`, sendChatMessageResponseSchema, body);
}
