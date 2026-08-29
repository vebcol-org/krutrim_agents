import { z } from 'zod';
import type {
  Agent,
  AgentMeta,
  AgentSandboxPolicyUpdate,
  CreateAgentRequest,
  SessionInfo,
  UpdateAgentRequest,
} from '@krutrim_agent/shared-types';

import { apiDelete, apiGet, apiPost, apiPut } from '../utils/http-client';
import { agentMetaSchema, agentSchema, sessionInfoSchema } from './schemas';

/** `GET /api/agents` — every registered agent *profile* (research/...), not
 * project-scoped instances of them (those are the rest of this file). Used to populate the
 * `agent_key` picker when creating a new `Agent` instance. */
export function fetchAgentProfiles(backendUrl: string): Promise<AgentMeta[]> {
  return apiGet(`${backendUrl}/api/agents`, z.array(agentMetaSchema));
}

/** `POST /api/projects/{projectId}/agents` — `agent_key` must be one of `fetchAgentProfiles`'s keys. */
export function createAgent(backendUrl: string, projectId: string, body: CreateAgentRequest): Promise<Agent> {
  return apiPost(`${backendUrl}/api/projects/${projectId}/agents`, agentSchema, body);
}

/** `GET /api/projects/{projectId}/agents` — every agent instance in this project. */
export function fetchAgents(backendUrl: string, projectId: string): Promise<Agent[]> {
  return apiGet(`${backendUrl}/api/projects/${projectId}/agents`, z.array(agentSchema));
}

/** `GET /api/projects/{projectId}/agents/{agentId}` */
export function fetchAgent(backendUrl: string, projectId: string, agentId: string): Promise<Agent> {
  return apiGet(`${backendUrl}/api/projects/${projectId}/agents/${agentId}`, agentSchema);
}

/** `PUT /api/projects/{projectId}/agents/{agentId}` — rename. */
export function updateAgent(
  backendUrl: string,
  projectId: string,
  agentId: string,
  body: UpdateAgentRequest,
): Promise<Agent> {
  return apiPut(`${backendUrl}/api/projects/${projectId}/agents/${agentId}`, agentSchema, body);
}

/** `DELETE /api/projects/{projectId}/agents/{agentId}` — cascades this agent's sessions. */
export function deleteAgent(backendUrl: string, projectId: string, agentId: string): Promise<void> {
  return apiDelete(`${backendUrl}/api/projects/${projectId}/agents/${agentId}`);
}

/** `PUT /api/projects/{projectId}/agents/{agentId}/sandbox-policy` */
export function updateAgentSandboxPolicy(
  backendUrl: string,
  projectId: string,
  agentId: string,
  update: AgentSandboxPolicyUpdate,
): Promise<Agent> {
  return apiPut(`${backendUrl}/api/projects/${projectId}/agents/${agentId}/sandbox-policy`, agentSchema, update);
}

/** `POST /api/projects/{projectId}/agents/{agentId}/sessions` — creates a session owned by this agent. */
export function createAgentSession(backendUrl: string, projectId: string, agentId: string): Promise<SessionInfo> {
  return apiPost(`${backendUrl}/api/projects/${projectId}/agents/${agentId}/sessions`, sessionInfoSchema, undefined);
}

/** `GET /api/projects/{projectId}/agents/{agentId}/sessions` — this agent's sessions. */
export function fetchAgentSessions(
  backendUrl: string,
  projectId: string,
  agentId: string,
): Promise<SessionInfo[]> {
  return apiGet(`${backendUrl}/api/projects/${projectId}/agents/${agentId}/sessions`, z.array(sessionInfoSchema));
}
