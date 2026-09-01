import type {
  ModelCard,
  ModelSelection,
  ProviderCard,
  RoleModelSettingsList,
} from '@krutrim_agent/shared-types';

import { apiGet, apiPost, apiPut } from '../utils/http-client';
import {
  modelCatalogResponseSchema,
  providerListResponseSchema,
  roleModelSettingsListSchema,
} from './schemas';

/** `GET /api/providers` — every provider, with `configured` = its API key is set. */
export function fetchProviders(backendUrl: string): Promise<ProviderCard[]> {
  return apiGet(`${backendUrl}/api/providers`, providerListResponseSchema).then((r) => r.providers);
}

/** `GET /api/providers/models` — the model catalog the pickers show (chat-only by default). */
export function fetchModelCatalog(
  backendUrl: string,
  opts: { kind?: 'chat' | 'embedding'; provider?: string } = {},
): Promise<ModelCard[]> {
  const params = new URLSearchParams();
  if (opts.kind) params.set('kind', opts.kind);
  if (opts.provider) params.set('provider', opts.provider);
  const qs = params.toString();
  return apiGet(
    `${backendUrl}/api/providers/models${qs ? `?${qs}` : ''}`,
    modelCatalogResponseSchema,
  ).then((r) => r.models);
}

// ── agent-instance scope ────────────────────────────────────────────────
/** `GET /api/providers/agents/{agentId}` — effective per-role settings for an agent instance. */
export function fetchAgentModelSettings(
  backendUrl: string,
  agentId: string,
): Promise<RoleModelSettingsList> {
  return apiGet(`${backendUrl}/api/providers/agents/${agentId}`, roleModelSettingsListSchema);
}

/** `PUT /api/providers/agents/{agentId}/{role}` — takes effect on the agent's next message. */
export function updateAgentModelSettings(
  backendUrl: string,
  agentId: string,
  role: string,
  selection: ModelSelection,
): Promise<RoleModelSettingsList> {
  return apiPut(
    `${backendUrl}/api/providers/agents/${agentId}/${role}`,
    roleModelSettingsListSchema,
    selection,
  );
}

/** `POST /api/providers/agents/{agentId}/{role}/reset` — drop the agent-level override. */
export function resetAgentModelSettings(
  backendUrl: string,
  agentId: string,
  role: string,
): Promise<RoleModelSettingsList> {
  return apiPost(
    `${backendUrl}/api/providers/agents/${agentId}/${role}/reset`,
    roleModelSettingsListSchema,
    {},
  );
}

// ── session scope (the chat-composer model switcher) ────────────────────
/** `GET /api/providers/sessions/{sessionId}` — effective settings for one conversation. */
export function fetchSessionModelSettings(
  backendUrl: string,
  sessionId: string,
): Promise<RoleModelSettingsList> {
  return apiGet(`${backendUrl}/api/providers/sessions/${sessionId}`, roleModelSettingsListSchema);
}

/** `PUT /api/providers/sessions/{sessionId}/{role}` — per-session override of the agent pick. */
export function updateSessionModelSettings(
  backendUrl: string,
  sessionId: string,
  role: string,
  selection: ModelSelection,
): Promise<RoleModelSettingsList> {
  return apiPut(
    `${backendUrl}/api/providers/sessions/${sessionId}/${role}`,
    roleModelSettingsListSchema,
    selection,
  );
}

/** `POST /api/providers/sessions/{sessionId}/{role}/reset` — fall back to the agent pick. */
export function resetSessionModelSettings(
  backendUrl: string,
  sessionId: string,
  role: string,
): Promise<RoleModelSettingsList> {
  return apiPost(
    `${backendUrl}/api/providers/sessions/${sessionId}/${role}/reset`,
    roleModelSettingsListSchema,
    {},
  );
}
