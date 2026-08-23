import type { ModelSettings, ProviderSettingsByRole, UpdateSettingsResponse } from '@krutrim_agent/shared-types';

import { apiGet, apiPut } from '../utils/http-client';
import { providerSettingsByRoleSchema, updateSettingsResponseSchema } from './schemas';

/** `GET /api/providers/{agentKey}` — every declared role's current settings for one agent profile. */
export function fetchProviderSettings(backendUrl: string, agentKey: string): Promise<ProviderSettingsByRole> {
  return apiGet(`${backendUrl}/api/providers/${agentKey}`, providerSettingsByRoleSchema);
}

/** `PUT /api/providers/{agentKey}/{role}` — takes effect on the next backend restart, not live. */
export function updateProviderSettings(
  backendUrl: string,
  agentKey: string,
  role: string,
  next: ModelSettings,
): Promise<UpdateSettingsResponse> {
  return apiPut(`${backendUrl}/api/providers/${agentKey}/${role}`, updateSettingsResponseSchema, next);
}
