# `libs/shared-types`

Nx library `shared-types` (import as `@krutrim_agent/shared-types`). A **hand-synced** (not codegen'd) TypeScript mirror of the backend's Pydantic models. Everything lives in one file: [`libs/shared-types/src/lib/shared-types.ts`](../../libs/shared-types/src/lib/shared-types.ts) (203 lines). The file itself documents the split between the AG-UI flow's types (currently unconsumed by frontend code — see the [reality-check](README.md#️-read-this-first--the-docs-vs-the-code)) and the `chat` project type's types (what `libs/agent-ui` actually uses today).

> **Keep this in sync by hand.** If you change a Pydantic model in `krutrim_agent_management.models` or an API response shape in `krutrim_agent_backend/api/*`, update the matching type here in the same change — nothing enforces this automatically.

## Constants

| Constant | Value | Used by |
|---|---|---|
| `AGENT_ENDPOINT_PREFIX` | `'/agents'` | AG-UI flow (unconsumed today) |
| `DEFAULT_BACKEND_URL` | `'http://localhost:8000'` | `apps/web`/`apps/desktop` fallback for `VITE_BACKEND_URL` |
| `AGENT_QUERY_PARAM` | `'agent'` | AG-UI flow (unconsumed — nothing reads `?agent=` today) |
| `DEFAULT_AGENT_KEY` | `'research'` | AG-UI flow (unconsumed) |
| `PROVIDER_KEYS` | `['openrouter', 'ollama'] as const` | `SettingsPanel` |
| `CONTENT_KINDS` | `['markdown', 'chart', 'news'] as const` | `agent-renderers` |
| `CHAT_PROJECT_TYPE` | `'chat'` | `chat-slice.ts` — "the only `project_type` wired up today" |
| `SHARING_SCOPES` | `['isolated', 'session-shared', 'project-shared'] as const` | `SandboxSettingsPanel` |

## AG-UI flow types (mirrors `agents`/`krutrim_agent_backend`'s AG-UI route)

- `AgentMeta { key, display_name, description, roles: string[] }` — mirrors `GET /api/agents`.
- `ProviderKey = (typeof PROVIDER_KEYS)[number]`
- `BaseModelSettings { provider, model, temperature, max_tokens, top_p, timeout }`
- `OpenRouterModelSettings extends BaseModelSettings { provider: 'openrouter'; api_key_env; base_url; site_url; app_name }`
- `OllamaModelSettings extends BaseModelSettings { provider: 'ollama'; base_url; num_ctx; keep_alive }`
- `ModelSettings = OpenRouterModelSettings | OllamaModelSettings` — discriminated union on `provider`, mirrors [`krutrim_agents_core.md`'s `ModelSettings`](../../backend/docs/libs/krutrim_agents_core.md#4-providers--llm-provider-abstraction)
- `ProviderSettingsByRole = Record<string, ModelSettings>`
- `UpdateSettingsResponse { settings: ModelSettings; note: string }`
- `ContentKind = (typeof CONTENT_KINDS)[number]`
- `RenderContentPayload { kind: ContentKind | (string & {}); title: string; content: string }` — the `render_content` tool's argument shape
- `ChartContent { labels: string[]; series: { name: string; values: number[] }[] }` — consumed by `agent-renderers`' `ChartView`
- `NewsContent { items: { headline; source; summary; url? }[] }` — consumed by `agent-renderers`' `NewsView`

## `chat` project type types (what `libs/agent-ui` actually uses)

- `Project { project_id, project_title, project_information, project_type, provider, model, created_at, updated_at, sandbox_sharing, sandbox_idle_timeout_seconds, sandbox_resource_overrides }` — mirrors [`krutrim_agent_management.models.Project`](../../backend/docs/libs/krutrim_agent_management.md#3-modelspy--domain-models)
- `SharingScope = (typeof SHARING_SCOPES)[number]`
- `SessionInfo { session_id, project_id, created_at, updated_at, sandbox_sharing, attached_to_session_id, linked_session_ids }` — mirrors `krutrim_agent_management.models.SessionInfo`
- `ProjectSandboxPolicyUpdate { sharing?; idle_timeout_seconds?; resource_overrides? }`
- `SessionSandboxPolicyUpdate { sharing?; attached_to_session_id?; linked_session_ids? }`
- `EmbedRequest { source_paths?: string[] | null }`
- `EmbedResponse { status: 'queued'; task_id; job_id; file_count }`
- `RagTextRequest { text: string; title?: string | null }` — body for `POST /api/sessions/{id}/rag/text` (v1 scope: text only — a `.txt` file's contents are read client-side and sent through this same request shape)
- `RagTextResponse { status: 'queued'; task_id; job_id; document_id }` — `job_id` is per-document (`{session_id}:rag:{document_id}`), unlike `EmbedResponse.job_id`
- `ContainerStatusEvent { status: 'starting'|'running'|'idle'|'tearing_down'|'stopped'|(string & {}); ref_count? }` — the shape `useSseStatus`/`SandboxStatus` (in `agent-ui`) parse SSE payloads into
- `JobProgressEvent { processed: number; total: number }`
- `RagIngestJobProgressEvent { stage: 'extracting'|'chunking'|'embedding'|'indexing'; processed: number; total: number }` — same channel/route as `JobProgressEvent` (`GET /api/status/jobs/{job_id}`), for a `process_rag_document` job; distinguished by the extra `stage` field
- `ChatModelOption { provider; model; display_name }` — mirrors `krutrim_agent_backend.chat.catalog.ChatModelOption`
- `ChatApiMessage { role: 'user'|'assistant'; content: string }`
- `SendChatMessageRequest { message; project_id?; session_id?; project_title?; project_type?; provider?; model? }`
- `SendChatMessageResponse { project_id; session_id; message: ChatApiMessage }`

## When to update this file

Any time a backend Pydantic model or API response shape changes in a way that affects the frontend: `krutrim_agent_management.models` (`Project`/`SessionInfo`/`ContainerRecord`), `krutrim_agents_core.providers.base.ModelSettings` and its subclasses, `krutrim_agent_backend`'s route response bodies, or `chat.catalog.ChatModelOption`. See the corresponding backend docs ([`krutrim_agent_management.md`](../../backend/docs/libs/krutrim_agent_management.md), [`krutrim_agents_core.md`](../../backend/docs/libs/krutrim_agents_core.md), [`krutrim_agent_backend.md`](../../backend/docs/services/krutrim_agent_backend.md)) for the current source-of-truth shapes.
