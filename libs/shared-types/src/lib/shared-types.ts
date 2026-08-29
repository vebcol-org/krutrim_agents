// Mirrors backend/libs/krutrim_agent_management/src/krutrim_agent_management/models.py and
// backend/services/krutrim_agent_backend's route request/response shapes.
// Kept in sync by hand for v1 — see agents.profile.AgentProfile and
// agents.providers.base for the agent-profile/provider side.

/** Backend route prefix for the AG-UI endpoint, e.g. `${backendUrl}${AGENT_ENDPOINT_PREFIX}/${agentId}`. */
export const AGENT_ENDPOINT_PREFIX = '/agents';
export const DEFAULT_BACKEND_URL = 'http://localhost:8000';

/** Which agent type is active — read from this query param, e.g. `?agent=research`. */
export const AGENT_QUERY_PARAM = 'agent';
export const DEFAULT_AGENT_KEY = 'research';

/** Metadata for one registered agent profile — mirrors `GET /api/agents`. Not the same
 * thing as an `Agent` instance (below) — a profile is the code-level type; an `Agent` is
 * a named, project-scoped instance running one. */
export interface AgentMeta {
  key: string;
  display_name: string;
  description: string;
  roles: string[];
}

export const PROVIDER_KEYS = ['openrouter', 'ollama'] as const;
export type ProviderKey = (typeof PROVIDER_KEYS)[number];

export interface BaseModelSettings {
  provider: ProviderKey;
  model: string;
  temperature: number;
  max_tokens: number | null;
  top_p: number | null;
  timeout: number | null;
}

export interface OpenRouterModelSettings extends BaseModelSettings {
  provider: 'openrouter';
  api_key_env: string;
  base_url: string;
  site_url: string | null;
  app_name: string;
}

export interface OllamaModelSettings extends BaseModelSettings {
  provider: 'ollama';
  base_url: string;
  num_ctx: number | null;
  keep_alive: string | null;
}

export type ModelSettings = OpenRouterModelSettings | OllamaModelSettings;

/** A given agent's roles are dynamic (declared by its profile), not a fixed set. */
export type ProviderSettingsByRole = Record<string, ModelSettings>;

export interface UpdateSettingsResponse {
  settings: ModelSettings;
  note: string;
}

/**
 * The shapes the *default* canvas renderer understands. A custom
 * per-agent renderer (see `@krutrim_agent/agent-renderers`) can ignore
 * `kind` entirely and interpret `content` however it wants — this is a
 * hint, not a contract every renderer must honor.
 */
export const CONTENT_KINDS = ['markdown', 'chart', 'news'] as const;
export type ContentKind = (typeof CONTENT_KINDS)[number];

/** Payload the shared `render_content` frontend action receives from any agent. */
export interface RenderContentPayload {
  kind: ContentKind | (string & {});
  title: string;
  content: string;
}

/** `kind="chart"` payload shape (JSON-encoded in `RenderContentPayload.content`). */
export interface ChartContent {
  labels: string[];
  series: { name: string; values: number[] }[];
}

/** `kind="news"` payload shape (JSON-encoded in `RenderContentPayload.content`). */
export interface NewsContent {
  items: { headline: string; source: string; summary: string; url?: string }[];
}

// -- Hierarchy: Project -> (Agent | Chat) -> Session — mirrors
// `krutrim_agent_management.models`. A `Project` is a named container; an `Agent`
// always belongs to exactly one project (a named instance of a registered
// profile — multiple `Agent`s can share the same `agent_key`); a `Chat` is
// optionally scoped to a project (`project_id` may be `null` — a standalone
// chat) and can be moved in/out of one later. `SessionInfo` always belongs
// to exactly one `Agent` or `Chat` (`owner_type`/`owner_id`), never directly
// to a `Project`.

/**
 * Sandbox sharing policy — mirrors `krutrim_agent_management.models.SharingScope`.
 * Does NOT merge containers: "session-shared"/"project-shared" only grant
 * the cross-agent `message_agent` tool between still-separate containers,
 * and only ever between `Agent`-owned sessions. See `attached_to_session_id`
 * on `SessionInfo` for the one mechanism that *does* reuse a literal container.
 */
export const SHARING_SCOPES = ['isolated', 'session-shared', 'project-shared'] as const;
export type SharingScope = (typeof SHARING_SCOPES)[number];

/** Which entity a `SessionInfo` belongs to. */
export type OwnerType = 'agent' | 'chat';

/** Mirrors `krutrim_agent_management.models.Project`. No longer carries `project_type`/
 * `provider`/`model` — those live on its `Agent`/`Chat` children now. */
export interface Project {
  project_id: string;
  project_title: string;
  project_information: string;
  created_at: string;
  updated_at: string;
  /** Default sharing policy inherited by every Agent/Chat under this project. */
  sandbox_sharing: SharingScope;
  sandbox_idle_timeout_seconds: number | null;
  sandbox_resource_overrides: Record<string, number> | null;
}

/** Mirrors `krutrim_agent_management.models.Agent` — a named instance of a registered profile,
 * always inside exactly one project. Moving one between projects isn't supported yet. */
export interface Agent {
  agent_id: string;
  project_id: string;
  /** Which registered profile this instance runs — see `AgentMeta.key` / `GET /api/agents`. */
  agent_key: string;
  display_name: string;
  created_at: string;
  updated_at: string;
  /** `null` means "inherit the project's default" — a different default than `Project`/`SessionInfo`. */
  sandbox_sharing: SharingScope | null;
  sandbox_idle_timeout_seconds: number | null;
  sandbox_resource_overrides: Record<string, number> | null;
}

/** Mirrors `krutrim_agent_management.models.Chat` — a lightweight, non-agentic chat container.
 * `project_id` is optional; a standalone chat has no meaningful sandbox policy until
 * it's moved into a project. */
export interface Chat {
  chat_id: string;
  project_id: string | null;
  display_name: string;
  provider: string;
  model: string;
  created_at: string;
  updated_at: string;
  sandbox_sharing: SharingScope | null;
  sandbox_idle_timeout_seconds: number | null;
  sandbox_resource_overrides: Record<string, number> | null;
}

/** Mirrors `krutrim_agent_management.models.SessionInfo`. Sessions are addressed by `session_id`
 * alone (globally unique) — `project_id` here is denormalized from the owner for
 * convenience, not part of the session's identity. */
export interface SessionInfo {
  session_id: string;
  owner_type: OwnerType;
  /** `Agent.agent_id` when `owner_type === 'agent'`, `Chat.chat_id` when `'chat'`. */
  owner_id: string;
  project_id: string | null;
  /** User-set name; `null` means unnamed — callers show a positional fallback (e.g. "Session 2"). */
  display_name: string | null;
  created_at: string;
  updated_at: string;
  sandbox_sharing: SharingScope;
  attached_to_session_id: string | null;
  linked_session_ids: string[];
}

// -- Request bodies -----------------------------------------------------
// Every `Update*`/`*PolicyUpdate` type follows the same partial-update
// convention: an omitted (or `null`) field is left unchanged server-side.

/** Body for `POST /api/projects`. */
export interface CreateProjectRequest {
  project_title: string;
  project_information?: string;
}

/** Body for `PUT /api/projects/{project_id}`. */
export interface UpdateProjectRequest {
  project_title?: string | null;
  project_information?: string | null;
}

/** Body for `PUT /api/projects/{project_id}/sandbox-policy`. */
export interface ProjectSandboxPolicyUpdate {
  sharing?: SharingScope | null;
  idle_timeout_seconds?: number | null;
  resource_overrides?: Record<string, number> | null;
}

/** Body for `POST /api/projects/{project_id}/agents`. */
export interface CreateAgentRequest {
  agent_key: string;
  display_name: string;
}

/** Body for `PUT /api/projects/{project_id}/agents/{agent_id}`. */
export interface UpdateAgentRequest {
  display_name?: string | null;
}

/** Body for `PUT /api/projects/{project_id}/agents/{agent_id}/sandbox-policy`. */
export interface AgentSandboxPolicyUpdate {
  sharing?: SharingScope | null;
  idle_timeout_seconds?: number | null;
  resource_overrides?: Record<string, number> | null;
}

/** Body for `POST /api/chats`. `project_id` omitted/`null` creates a standalone chat. */
export interface CreateChatRequest {
  display_name: string;
  project_id?: string | null;
  provider?: string | null;
  model?: string | null;
}

/** Body for `PUT /api/chats/{chat_id}`. */
export interface UpdateChatRequest {
  display_name?: string | null;
}

/** Body for `POST /api/chats/{chat_id}/move`. `project_id: null` detaches back to standalone. */
export interface MoveChatRequest {
  project_id: string | null;
}

/** Body for `PUT /api/chats/{chat_id}/sandbox-policy`. Stored regardless of whether the
 * chat currently has a `project_id`, but only takes effect once one is set. */
export interface ChatSandboxPolicyUpdate {
  sharing?: SharingScope | null;
  idle_timeout_seconds?: number | null;
  resource_overrides?: Record<string, number> | null;
}

/** Body for `PUT /api/sessions/{session_id}`. */
export interface UpdateSessionRequest {
  display_name?: string | null;
}

/** Body for `PUT /api/sessions/{session_id}/sandbox-policy`. There is currently no way to
 * clear an existing `attached_to_session_id` back to "not attached" via this route. */
export interface SessionSandboxPolicyUpdate {
  sharing?: SharingScope | null;
  attached_to_session_id?: string | null;
  linked_session_ids?: string[] | null;
}

/** Body for `POST /api/sessions/{session_id}/embed`. */
export interface EmbedRequest {
  source_paths?: string[] | null;
}

export interface EmbedResponse {
  status: 'queued';
  task_id: string;
  job_id: string;
  file_count: number;
}

/** Body for `POST /api/sessions/{session_id}/rag/text` — raw-text RAG ingestion
 * (v1 scope: text only; a `.txt` file's contents are read client-side and sent
 * through this same endpoint, no separate binary upload route exists). */
export interface RagTextRequest {
  text: string;
  title?: string | null;
}

export interface RagTextResponse {
  status: 'queued';
  task_id: string;
  /** Per-document, unlike `EmbedResponse.job_id` — `{session_id}:rag:{document_id}`. */
  job_id: string;
  document_id: string;
}

/** One row from `GET /api/sessions/{session_id}/rag/documents` — a document that
 * has been (or is being) ingested into this session's RAG index. Backs the
 * composer's persistent attachment bar. */
export interface RagDocument {
  document_id: string;
  title: string;
  /** Original upload filename; `null` for pasted text. */
  filename: string | null;
  source_path: string;
  kind: 'file' | 'text';
  created_at: string;
}

export interface RagDocumentsResponse {
  documents: RagDocument[];
}

/**
 * SSE payload shape from `GET /api/status/containers/{owner_id}` — mirrors
 * `krutrim_agent_sandbox.status_channel.publish_container_status`'s JSON. `extra`
 * fields (e.g. `ref_count`) vary by transition; only `status` is guaranteed.
 */
export interface ContainerStatusEvent {
  status: 'starting' | 'running' | 'idle' | 'tearing_down' | 'stopped' | (string & {});
  ref_count?: number;
}

/** SSE payload shape from `GET /api/status/jobs/{job_id}` — mirrors `publish_job_progress`. */
export interface JobProgressEvent {
  processed: number;
  total: number;
}


export interface RagIngestJobProgressEvent {
  stage: 'extracting' | 'chunking' | 'embedding' | 'indexing' | 'error';
  processed?: number;
  total?: number;
  error?: string;
}

/** One entry from `GET /api/models` — mirrors `krutrim_agent_backend.chat.catalog.ChatModelOption`. */
export interface ChatModelOption {
  provider: string;
  model: string;
  display_name: string;
}

/** One turn's worth of chat history, as returned by `GET /api/sessions/{id}/messages`.
 * `POST /api/chat` itself is now an AG-UI SSE stream (`@ag-ui/client`), not JSON —
 * see `libs/agent-ui/src/hooks/use-chat-stream.ts`. */
export interface ChatApiMessage {
  role: 'user' | 'assistant';
  content: string;
}
