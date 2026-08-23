import { z } from 'zod';
import type {
  CreateProjectRequest,
  Project,
  ProjectSandboxPolicyUpdate,
  UpdateProjectRequest,
} from '@krutrim_agent/shared-types';

import { apiDelete, apiGet, apiPost, apiPut } from '../utils/http-client';
import { projectSchema } from './schemas';

/** `POST /api/projects` — also auto-creates one default "General" Chat inside it (backend-side). */
export function createProject(backendUrl: string, body: CreateProjectRequest): Promise<Project> {
  return apiPost(`${backendUrl}/api/projects`, projectSchema, body);
}

/** `GET /api/projects` — every project. */
export function fetchProjects(backendUrl: string): Promise<Project[]> {
  return apiGet(`${backendUrl}/api/projects`, z.array(projectSchema));
}

/** `PUT /api/projects/{projectId}` — rename/re-describe. */
export function updateProject(backendUrl: string, projectId: string, body: UpdateProjectRequest): Promise<Project> {
  return apiPut(`${backendUrl}/api/projects/${projectId}`, projectSchema, body);
}

/** `DELETE /api/projects/{projectId}` — cascades every Agent/Chat (and their Sessions) in it. */
export function deleteProject(backendUrl: string, projectId: string): Promise<void> {
  return apiDelete(`${backendUrl}/api/projects/${projectId}`);
}

/** `PUT /api/projects/{projectId}/sandbox-policy` — returns the updated project. */
export function updateProjectSandboxPolicy(
  backendUrl: string,
  projectId: string,
  update: ProjectSandboxPolicyUpdate,
): Promise<Project> {
  return apiPut(`${backendUrl}/api/projects/${projectId}/sandbox-policy`, projectSchema, update);
}
