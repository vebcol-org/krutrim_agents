# `krutrim_agent_backend` (backend/services/krutrim_agent_backend)

Package name: **`krutrim-agent-backend`** (`backend/services/krutrim_agent_backend/pyproject.toml`). The FastAPI app — the only HTTP surface of the platform. Depends on `krutrim-agent-management`, `krutrim-agent-sandbox`, `krutrim-agents` (which pulls in `krutrim-agents-core` transitively), and [`krutrim-agent-extensions`](../libs/krutrim_agent_extensions.md) (the security-hook middleware/registry). Run via `uv run uvicorn krutrim_agent_backend.main:app --reload --port 8000` from `backend/`.

Routes are organized around the `Project -> (Agent | Chat) -> Session` hierarchy (see [`libs/krutrim_agent_management.md`](../libs/krutrim_agent_management.md#hierarchy-project---agent--chat---session)):

```
krutrim_agent_backend/
├── main.py                create_app() — lifespan startup/shutdown, CORS, extension middleware, router mounting
├── bootstrap.py             build_app_state()/install_app_state() — reusable app.state construction
├── logging_config.py          thin shim → krutrim_agent_management.logging_config.configure_logging("server")
├── celery_client.py             minimal Celery client — enqueues tasks krutrim_agent_celery owns, by name
├── api/
│   ├── agent_run.py            POST /agents/{agent_id} — the AG-UI streaming route (agent-instance scoped)
│   ├── system_routes.py         GET /api/system/extensions — active edition/hooks/storage-backend/sandbox-runtime
│   ├── chat_routes.py           POST /api/chat — the plain, non-agentic chat flow (Chat-entity scoped)
│   ├── projects_routes.py        /api/projects/* CRUD + sandbox policy (explicit create — auto-creates a default Chat)
│   ├── agent_instances_routes.py  /api/projects/{id}/agents/* CRUD + sandbox policy + owned-session create/list
│   ├── chats_routes.py             /api/chats/* CRUD + move + sandbox policy + owned-session create/list
│   ├── sessions_routes.py           /api/sessions/{id}/* — get/rename/delete/messages/sandbox-policy/embed/rag-text/rag-file (session_id alone; delete cascades the vector index)
│   ├── settings_routes.py            /api/providers/* — per-(agent_key,role) provider settings CRUD
│   ├── agents_routes.py               GET /api/agents — lists registered *profiles* (not instances — see agent_instances_routes.py)
│   ├── models_routes.py                GET /api/models — chat model catalog
│   ├── status_routes.py                 /api/status/* — SSE over Redis pub/sub
│   ├── health.py                         GET /api/health
│   └── error_handlers.py                  exception → JSON response mapping
└── chat/
    ├── graph.py                hand-assembled ReAct graph (before_agent → model [→ tools] loop) with a pluggable middleware stack; backs the plain chat flow
    ├── catalog.py                 fixed model catalog for the chat project type
    ├── messages.py                  dict ↔ LangChain BaseMessage conversion
    └── usage.py                      per-turn/cumulative token usage accumulation
```

## 1. `main.py` + `bootstrap.py` — app startup

[`main.py`](../../services/krutrim_agent_backend/src/krutrim_agent_backend/main.py), [`bootstrap.py`](../../services/krutrim_agent_backend/src/krutrim_agent_backend/bootstrap.py)

`configure_logging()` (→ `krutrim_agent_management.logging_config.configure_logging("server")`) runs at **module import time**, before `create_app()`/`lifespan()`. `main.py` also does `import krutrim_agent_rag.cleanup` for its side effect — registering the session-delete hook that drops a session's vector index (Qdrant collection / FAISS dir) whenever its chat or session is deleted.

**`bootstrap.build_app_state(settings) -> AppState`** — extracted out of `lifespan()` so a *second* FastAPI app (e.g. a separate deployment wrapping this same platform with its own extra routes/middleware) can get the exact same startup wiring without re-deriving it:
1. `provider_store = ProviderStore(settings.provider_settings_path)`
2. `storage = create_storage(settings)` — pluggable, see [`krutrim_agent_management.md`](../libs/krutrim_agent_management.md)
3. `sandbox_registry = SandboxRegistry(store=storage, policy_factory=lambda _owner_id: SandboxPolicy(image=settings.sandbox_image), pubsub=RedisPubSubBackend(settings.redis_url))`
4. Returns an `AppState` dataclass bundling the three. `bootstrap.install_app_state(app, state)` sets `app.state.{provider_store, storage, sandbox_registry}` from it.

**`lifespan(app)`** (`@asynccontextmanager`) — now just: `state = await build_app_state(settings)`, `install_app_state(app, state)`, `yield`, then on shutdown (`finally`) `state.sandbox_registry.close_all()`. `app.state.{provider_store, storage, sandbox_registry}` are set **only** inside `lifespan` — they don't exist at `create_app()` time, only once the app has actually started.

**`create_app()`**:
1. `run_startup_selfcheck(settings)` (from [`krutrim_agent_extensions`](../libs/krutrim_agent_extensions.md)) — **before** the `FastAPI(...)` instance is even constructed. Fails CLOSED: raises `RuntimeError` (so `app = create_app()` at module import time fails, and `uvicorn krutrim_agent_backend.main:app` never starts) if `settings.edition == "extended"` but no real `RequestAuthenticator` was registered.
2. `FastAPI(title="Krutrim Agent Backend", lifespan=lifespan)`
3. `CORSMiddleware` — `allow_origins=settings.cors_origins`, `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`.
4. `ExtensionMiddleware` (from `krutrim_agent_extensions`) — resolves `request.state.principal`/`request.state.visible_agent_keys` for every request via whatever hooks are registered (all no-op by default, so this is a pure pass-through for community). See [`krutrim_agent_extensions.md`](../libs/krutrim_agent_extensions.md).
5. `register_exception_handlers(app)` (*)
6. Routers mounted in order: `health_router`, `agents_router`, `settings_router`, `projects_router`, `agent_instances_router`, `chats_router`, `sessions_router`, `chat_router`, `models_router`, `status_router`, `system_router`
7. `mount_agent_run_endpoint(app)` — `/agents/{agent_id}` and `/agents/{agent_id}/health` mounted **directly on `app`** (not via `APIRouter`)
8. Returns `app`. Module-level `app = create_app()` is uvicorn's entrypoint (`krutrim_agent_backend.main:app`).

## 2. API routes

### `agent_run.py` — the AG-UI streaming route

`AGENT_RUN_PATH_PREFIX = "/agents"`. Inlines the ~15 lines `ag_ui_langgraph.add_langgraph_fastapi_endpoint` does internally (that helper only supports one fixed agent per call) — one parameterized handler covers every `Agent` instance regardless of which profile it runs.

**`POST /agents/{agent_id}`** — body: `RunAgentInput` (AG-UI protocol: `threadId`, `messages`, `tools`); query param: `session_id?`. **`agent_id` is an `Agent` instance id** (`POST /api/projects/{id}/agents`, see below) — **not** a profile key. A project can hold multiple instances of the same profile (e.g. two `agent_key="research"` agents with different names), so the profile key alone can no longer identify which one a run targets.

1. `storage.get_agent(agent_id)` — 404 if unknown.
2. `_check_agent_key_visible(request, agent.agent_key)` — 404 (not 403, so an invisible agent looks like it doesn't exist, same as an unknown `agent_id`) if `request.state.visible_agent_keys` (set by `ExtensionMiddleware`) is non-`None` and doesn't include this profile's key. `None` (community default) means no restriction.
3. `get_profile(agent.agent_key)` — resolves which registered profile this instance runs; 404 if the profile itself is somehow unregistered.
4. Session resolution: `session_id` omitted → `storage.create_session("agent", agent.agent_id)`; given → `storage.get_session(session_id)`, then validated to actually belong to this agent (`session.owner_type == "agent" and session.owner_id == agent.agent_id`, else 400).
5. Inside the streaming generator:
   - `handle = await sandbox_registry.get_or_create(session.session_id)` — **unconditional, runs before the graph even starts**, so a brand-new session on this route always spins up a sandbox container even if the model never calls `execute`.
   - Opens a durable per-session `AsyncSqliteSaver` at `sessions/{id}/langgraph_checkpoint.sqlite`.
   - `find_eligible_peers(storage, agent.project_id, session)` — if any, builds a `message_agent_tool(...)` and passes it as `extra_tools`.
   - `graph = build_agent(profile, provider_store, handle.backend, checkpointer=checkpointer, extra_tools=extra_tools)` — built **fresh, inside the streaming call, every request** (not a startup-time pool).
   - `request_agent = LangGraphAgent(name=agent.agent_key, graph=graph, description=profile.description)`; `async for event in request_agent.run(input_data): yield encoder.encode(event)`.
   - On any exception mid-stream: since headers are already sent, it can't become a clean HTTP error — instead yields a `RunErrorEvent` so the frontend sees a real message.
   - `finally: sandbox_registry.release(handle.owner_id)` — always runs, even on error.

**`GET /agents/{agent_id}/health`** → `AgentRunHealthResponse`: `{"status": "ok", "agent": {"id": agent_id, "agent_key": ...}}`; 404 if unknown or not visible (same `_check_agent_key_visible` gate).

For the full event-by-event AG-UI trace (frontend tool bridging, `render_content` closing the loop, etc.), see [`docs/app-flow.md`](../../../docs/app-flow.md) — **but note**: as of the current frontend audit, the frontend side of this flow (`AgentApp`, `useAgentChat`, `@ag-ui/client`) is **not actually wired into `apps/web`/`apps/desktop`** today; only the backend half described here is live, and its exact wiring will need to change to be agent-instance-aware rather than profile-key-aware once that frontend work happens. See [`docs/frontend/README.md`](../../../docs/frontend/README.md) for the current frontend reality.

### `chat_routes.py` — the plain, non-agentic flow

`POST /api/chat`, body `ChatMessageRequest {message, chat_id?, session_id?, project_id?, chat_title?, provider?, model?}` → `SendChatMessageResponse {chat_id, session_id, message: {role: "assistant", content}}` (`message` is a `ChatApiMessage`, shared with `GET /api/sessions/{id}/messages`). Single request/response JSON — **no streaming, no tools, no subagents, no sandbox**.

1. Chat resolution: `chat_id` given → `storage.get_chat(chat_id)` (404 if unknown); omitted → validates `provider`/`model` against `CHAT_MODEL_CATALOG` (400 if unknown/unsupported, defaulting to `DEFAULT_CHAT_MODEL`) and creates a new `Chat` — **`project_id`, if given, scopes it to that project on creation; otherwise it's standalone**, matching the original pre-`Chat`-entity behavior.
2. Session resolution: `session_id` omitted → `storage.create_session("chat", chat.chat_id)`; given → `storage.get_session(session_id)`, validated to belong to this chat (else 400).
3. Checkpointer: opens a durable per-session `AsyncSqliteSaver` at `sessions/{session_id}/langgraph_checkpoint.sqlite` (`CHECKPOINT_FILENAME`), keyed by `thread_id == session_id`. History is **LangGraph's** now — the call passes only the new `HumanMessage`; the checkpointer replays prior state and appends. (The old `storage.read_checkpoint`/`checkpointer.json` JSON round-trip is gone from this route.)
4. `build_chat_model({"provider": chat.provider, "model": chat.model})` (via `krutrim_agents_core.providers.registry` — the same choke point every other model goes through), then `build_chat_graph(model, system_prompt=load_prompt("chat", "main"), checkpointer=checkpointer, middleware=middleware)`. `middleware` holds a single `RagInjectionMiddleware()` **iff `settings.rag_injection_enabled`** (`KRUTRIM_AGENT_RAG_INJECTION_ENABLED`) — it retrieves top-k context for the latest user turn from this session's vector index and prepends it to the system prompt, no visible tool call. `graph.ainvoke({"messages": [HumanMessage(...)]}, config={"configurable": {"thread_id": session_id}})` — the `thread_id` config is what the middleware reads to resolve the session.
5. Persistence: history is in the sqlite checkpoint (step 3). Token usage is still folded into `usage.json` per turn via `chat.usage.accumulate_usage`, keyed by `session_id`.
6. Response: `{chat_id, session_id, message}` — **note the field rename from the old `{project_id, session_id, message}` shape**; any frontend code expecting `project_id` here needs updating (tracked as part of the still-pending frontend phase of this hierarchy work).

Every step logs at INFO (chat/session resolved, reply produced) or DEBUG (prior message count, user text preview, usage totals) via `loguru` — see §5.

### `projects_routes.py` — `/api/projects`

**Now has an explicit create route** (previously creation was implicit-only, a side effect of the first chat message) — `Project` no longer carries `project_type`/`provider`/`model`, so there's no longer a "first message" that could infer those.

| Route | Purpose |
|---|---|
| `POST /api/projects` | body `CreateProjectRequest {project_title, project_information?}` → creates the project **and** one default `Chat` inside it (`display_name="General"`, using `DEFAULT_CHAT_MODEL`) — see the hierarchy plan for why every project gets a default chat |
| `GET /api/projects` | list all |
| `GET /api/projects/{id}` | one project; 404 |
| `PUT /api/projects/{id}` | body `UpdateProjectRequest {project_title?, project_information?}`, unset fields unchanged |
| `DELETE /api/projects/{id}` | 404 if missing; cascades every `Agent`/`Chat` (and transitively their `Session`s) in the project |
| `PUT /api/projects/{id}/sandbox-policy` | body `ProjectSandboxPolicyUpdate {sharing?, idle_timeout_seconds?, resource_overrides?}`, unset fields unchanged — this is now the **default** every `Agent`/`Chat` in the project inherits |

### `agent_instances_routes.py` — `/api/projects/{project_id}/agents` (new)

Not to be confused with `agents_routes.py` (`GET /api/agents`, which lists registered *profiles* — `research`/`trading`/`sales`). This manages **instances** of those profiles, always nested under a project.

| Route | Purpose |
|---|---|
| `POST .../agents` | body `CreateAgentRequest {agent_key, display_name}` — `agent_key` validated against `krutrim_agents_core.registry.get_profile` (400 if unknown); 404 if the project is unknown |
| `GET .../agents` | list agents in this project |
| `GET .../agents/{agent_id}` | one agent; 404 if unknown or not in this project |
| `PUT .../agents/{agent_id}` | body `UpdateAgentRequest {display_name?}` — rename |
| `DELETE .../agents/{agent_id}` | cascades this agent's sessions |
| `PUT .../agents/{agent_id}/sandbox-policy` | body `AgentSandboxPolicyUpdate {sharing?, idle_timeout_seconds?, resource_overrides?}` — governs this agent's cross-agent-messaging eligibility with sibling agents (see [`libs/krutrim_agents.md`](../libs/krutrim_agents.md#7-cross_agentpy--synchronous-agent-to-agent-messaging)) |
| `POST .../agents/{agent_id}/sessions` | creates a session owned by this agent |
| `GET .../agents/{agent_id}/sessions` | lists this agent's sessions |

### `chats_routes.py` — `/api/chats` (new)

`Chat.project_id` is optional — a standalone chat (`project_id=None`) behaves like the original plain-chat flow; moving one in/out of a project is explicit.

| Route | Purpose |
|---|---|
| `POST /api/chats` | body `CreateChatRequest {display_name, project_id?, provider?, model?}` — same model validation as `/api/chat`'s implicit-create path |
| `GET /api/chats?project_id=<id>` | that project's chats; **omitting `project_id` lists standalone chats**, not "all chats" (matches `Storage.list_chats`'s semantics) |
| `GET /api/chats/{chat_id}` | one chat; 404 |
| `PUT /api/chats/{chat_id}` | body `UpdateChatRequest {display_name?}` — rename |
| `DELETE /api/chats/{chat_id}` | cascades this chat's sessions **and their vector indexes** — each session's FAISS dir / Qdrant collection is dropped via the `krutrim_agent_rag.cleanup` session-delete hook (`KRUTRIM_AGENT_VECTOR_STORE_BACKEND`) |
| `POST /api/chats/{chat_id}/move` | body `MoveChatRequest {project_id: str \| None}` — sets or (passing `null`) clears the chat's project |
| `PUT /api/chats/{chat_id}/sandbox-policy` | body `ChatSandboxPolicyUpdate {sharing?, idle_timeout_seconds?, resource_overrides?}` — stored regardless of `project_id`, only takes effect once one is set |
| `POST /api/chats/{chat_id}/sessions` | creates a session owned by this chat |
| `GET /api/chats/{chat_id}/sessions` | lists this chat's sessions |

### `sessions_routes.py` — `/api/sessions` (session_id-scoped)

Sessions are globally unique (`session_id` alone, no owner prefix needed to address one) — creating/listing is owner-scoped (see the two route files above); everything else lives here.

| Route | Purpose |
|---|---|
| `GET /api/sessions/{id}` | one session; 404 |
| `PUT /api/sessions/{id}` | body `UpdateSessionRequest {display_name?}` — rename |
| `DELETE /api/sessions/{id}` | 404 |
| `GET /api/sessions/{id}/messages` | `{"messages": [...]}` read from the session's `langgraph_checkpoint.sqlite` (`build_chat_graph(object(), checkpointer=...)` → `aget_state` — the model is never invoked on a read), converted via `from_lc_messages`; `[]` if the session has never been messaged. Used to reload a past conversation. |
| `PUT /api/sessions/{id}/sandbox-policy` | body `SessionSandboxPolicyUpdate {sharing?, attached_to_session_id?, linked_session_ids?}`. Validates: attach target must share this session's `project_id` (both non-null), no self-attach, no chained attaches (can't attach to a session that's itself attached), can't become an attach target while others already depend on this session — all 400 on violation. **No way to clear `attached_to_session_id` back to `None` via this route** (documented gap). |
| `POST /api/sessions/{id}/embed` | body `EmbedRequest {source_paths?: list[str] \| None}` → `EmbedResponse {"status": "queued", "task_id", "job_id", "file_count"}`. If `source_paths` omitted, uses the full persisted workspace mirror. Dispatches `celery_client.send_task("krutrim_agent_celery.precompute_embeddings", args=[session_id, source_paths])`. `job_id = f"{session_id}:embed"` — session ids are globally unique, so no project qualifier is needed (this changed from the old `f"{project_id}:{session_id}:embed"` shape). Constructed the same way the Celery task constructs it itself, so the caller can subscribe to `GET /api/status/jobs/{job_id}` immediately, without waiting on Celery's result backend. |
| `POST /api/sessions/{id}/rag/text` | body `RagTextRequest {text, title?}` → `RagTextResponse {"status": "queued", "task_id", "job_id", "document_id"}`. Empty/whitespace-only `text` → 400. Writes the text via the already-existing `Storage.sync_workspace_from_container(session_id, [(f"_rag_uploads/{document_id}.txt", text.encode())])` — no new `Storage` method needed. Dispatches `celery_client.send_task("krutrim_agent_celery.process_rag_document", args=[session_id, document_id, source_path, title])`, `title` defaulting to `document_id` if omitted. `job_id = f"{session_id}:rag:{document_id}"` — **per-document**, unlike `/embed`'s single per-session job id, since a session can ingest multiple RAG documents over time, each with its own progress stream. Pasted/`.txt`-read-client-side text only — see `/rag/file` for real binary uploads. |
| `POST /api/sessions/{id}/rag/file` | Multipart `UploadFile` + optional `title` form field → `RagTextResponse`, same shape as `/rag/text`. The counterpart for real document uploads (PDF, DOCX, anything [`krutrim_agent_doc`](../libs/krutrim_agent_doc.md)'s parser registry supports), not just pasted text. Rejects an empty file (400) or one over 25MB (413). Preserves the upload's file extension when writing to the workspace mirror (`_rag_uploads/{document_id}{suffix}`, unlike `/rag/text`'s hardcoded `.txt`) so `process_rag_document`'s Celery task can dispatch to the right parser by suffix. Dispatches the same `krutrim_agent_celery.process_rag_document` task and job-id scheme as `/rag/text` — ingestion is unified once content is on disk, regardless of which route wrote it. |

### `settings_routes.py` — `/api/providers`

Backs the per-`(agent_key, role)` provider/model config editor — unaffected by the hierarchy change; still keyed by profile type (`agent_key`), shared across every `Agent` instance running that profile. **Changes take effect only after a backend restart** — compiled graphs aren't hot-reloaded.

| Route | Purpose |
|---|---|
| `GET /api/providers/meta` | `{"providers": known_providers()}` |
| `GET /api/providers/{agent_key}` | `dict[role, settings]`; 404 unknown agent |
| `GET /api/providers/{agent_key}/{role}` | one role's settings; 404/400 |
| `PUT /api/providers/{agent_key}/{role}` | body: raw partial `ModelSettings` dict → `{"settings", "note": RESTART_NOTE}` |
| `POST /api/providers/{agent_key}/{role}/reset` | resets to profile default, same response shape |

### `agents_routes.py` / `models_routes.py` / `health.py`

- `GET /api/agents` → `list[{key, display_name, description, roles}]` from `krutrim_agents_core.registry.all_profiles()`, filtered by `request.state.visible_agent_keys` when non-`None` (community default is `None` — unfiltered, identical to before `krutrim_agent_extensions` existed) — lists registered **profiles** (research/trading/sales), not `Agent` instances. Instances live under `/api/projects/{id}/agents` (`agent_instances_routes.py`).
- `GET /api/models` → `list[{provider, model, display_name}]` from `chat.catalog.CHAT_MODEL_CATALOG` — models for `Chat`s.
- `GET /api/health` → `{"status": "ok"}`.

### `system_routes.py` — `GET /api/system/extensions`

Read-only status report — never raises on edition drift (that's `krutrim_agent_extensions.selfcheck.run_startup_selfcheck`'s job, run once at `create_app()` time). Returns `{"edition", "hooks": {hook_name: implementation_class_name}, "storage_backend", "sandbox_runtime"}`. Nothing sensitive in the payload (implementation class names and config strings, no secrets), so it's ungated — same posture as `/api/health`/`/api/agents`. What an external monitor, or a future frontend self-check, polls to catch a hook (or storage backend, or sandbox runtime) silently reverting to its community default after a bad deploy/config change.

### `status_routes.py` — SSE over Redis pub/sub

Published by `krutrim_agent_celery` workers and `SandboxRegistry`; both routes share `_sse_stream(channel)`, which opens its **own** `redis.asyncio.Redis.from_url(...)` client + pubsub per request (not a pooled/shared client), subscribes, iterates `pubsub.listen()`, yields `data: {text}\n\n` per message, and unsubscribes/closes in `finally`. Uses `redis.asyncio` directly rather than the `PubSubBackend` ABC (that ABC is publish-only; subscribing is a genuinely long-lived loop). Unaffected by the hierarchy change — `owner_id`/`job_id` were already opaque strings to this module.

| Route | Purpose |
|---|---|
| `GET /api/status/containers/{owner_id}` | subscribes to `sandbox:container:{owner_id}` |
| `GET /api/status/jobs/{job_id}` | subscribes to `sandbox:job:{job_id}` |

## 3. `chat/` subpackage

- **`catalog.py`** — `ChatModelOption(provider, model, display_name)` (frozen dataclass); `CHAT_MODEL_CATALOG` currently has **one entry**: `openrouter` / `deepseek/deepseek-v4-flash` / `"DeepSeek V4 Flash (OpenRouter)"`; `DEFAULT_CHAT_MODEL = CHAT_MODEL_CATALOG[0]`; `is_known_chat_model(provider, model)`.
- **`graph.py`** — `build_chat_graph(model, tools=None, *, system_prompt=None, system_prompt_fn=None, middleware=None, checkpointer=None, ...) -> CompiledStateGraph`: a hand-assembled ReAct graph with the same param names as `deepagents.create_deep_agent`. Nodes: `before_agent` (runs middleware `before_agent` hooks), `model` (`before_model` hooks → composed `wrap_model_call` chain → `after_model` hooks), and — only if any tools are present — `tools` (`ToolNode` with a composed `wrap_tool_call` chain). `START → before_agent → model`; with tools, a conditional edge routes `model → tools → model` until no tool calls, else `→ END`. The `chat` flow passes **no tools** and one optional `RagInjectionMiddleware`. A `checkpointer` (the per-session `AsyncSqliteSaver`) is now passed in by `chat_routes.py` — LangGraph owns history. `build_chat_graph(object(), checkpointer=...)` compiles fine for a pure `aget_state` read.
- **`messages.py`** — `to_lc_messages(raw)` (dict → `AIMessage`/`HumanMessage` by `role`), `from_lc_messages(messages)` (reverse), `derive_title(message, max_len=60)` (whitespace-collapsed, truncated, `"Untitled chat"` fallback).
- **`usage.py`** — `accumulate_usage(existing, reply: AIMessage)`: pulls `reply.usage_metadata` (`input_tokens`/`output_tokens`/`total_tokens`), sums into `existing["totals"]`, appends a per-turn record to `existing["turns"]`.

## 4. `celery_client.py`

```python
celery_client = Celery(
    "krutrim_agent_backend", broker=settings.redis_url, backend=settings.redis_url
)
```

A minimal client so `krutrim_agent_backend` can `send_task()` by name across the process boundary without importing `krutrim_agent_celery`'s heavier deps (docker, deepagents, numpy, langchain_ollama). See [`services/krutrim_agent_celery.md`](krutrim_agent_celery.md#decoupling-from-krutrim_agent_backend).

## 5. `logging_config.py`

A one-line shim: `configure_logging() → krutrim_agent_management.logging_config.configure_logging("server")`. The actual loguru wiring lives in [`krutrim_agent_management`](../libs/krutrim_agent_management.md#logging) so the Celery worker (`krutrim_agent_celery.app`, component `"worker"`) shares the exact same config and `KRUTRIM_AGENT_LOG_*` knobs. Server logs land in `<KRUTRIM_AGENT_LOG_DIR>/server/server.log` (default `~/.krutrim_agent/logs/server/server.log`); periodic rotation (`KRUTRIM_AGENT_LOG_ROTATION`, default `"1 day"`), `KRUTRIM_AGENT_LOG_RETENTION` default `"14 days"`. Console = `INFO`, file = `INFO`, both forced to `DEBUG` when `DEV_MODE=true` (or set `KRUTRIM_AGENT_LOG_LEVEL=DEBUG` in `.env.dev`). stdlib logs (uvicorn/httpx/...) are intercepted into the same sinks. `diagnose=False` on the file sink is deliberate — loguru's diagnose mode dumps local variables into tracebacks, which would leak provider API keys sitting in locals inside `providers/*.py`.

## 6. `api/error_handlers.py`

`register_exception_handlers(app)` — 4 handlers:

| Exception | Response |
|---|---|
| `HTTPException` | passthrough status/detail/headers; `logger.warning` |
| `ProviderConfigError` (krutrim_agents_core.providers.base) | 400, `logger.error` |
| `openai.APIStatusError` (auth/rate-limit/bad-request from the LLM provider) | 502 (`"Model provider request failed (...)"`), `logger.error` |
| any other `Exception` | 500 (`"Internal server error (...)"`), `logger.exception` (full traceback logged) |

Without these, e.g. a bad `OPENROUTER_API_KEY` would bubble up through uvicorn as a raw traceback/bare 500 instead of a clean 400/502.

## 7. Env vars / config consumed

`krutrim_agent_backend` has **no direct `os.environ`/`os.getenv` calls** — everything goes through the shared `krutrim_agent_management.config.settings` singleton: `provider_settings_path`, `sandbox_image`, `redis_url`, `cors_origins`, `dev_mode` (log-only), `host`/`port` (uvicorn run args in `__init__.py`). No service-specific env prefix exists for `krutrim_agent_backend` itself — see [`libs/krutrim_agent_management.md`](../libs/krutrim_agent_management.md#4-configpy--appsettingssettings) for the full field list.

## Migrating existing local data

If `~/.krutrim_agent` (or your configured `STORAGE_ROOT`) predates this route/model restructuring, run the one-time migration script before starting the backend — see [`libs/krutrim_agent_management.md#8-migrating-an-existing-storage_root`](../libs/krutrim_agent_management.md#8-migrating-an-existing-storage_root).

## Dependencies

[`pyproject.toml`](../../services/krutrim_agent_backend/pyproject.toml) — package `krutrim-agent-backend`: `ag-ui-langgraph`, `ag-ui-protocol`, `langgraph`, `langgraph-checkpoint-sqlite`, `langchain`, `fastapi`, `uvicorn[standard]`, `pydantic`, `openai`, `loguru`, `celery[redis]` (deliberately **not** a dependency on `krutrim-agent-celery` itself — just used for `send_task`), plus workspace `krutrim-agent-management`, `krutrim-agent-sandbox`, `krutrim-agent-rag` (chat RAG-injection middleware + the session-delete vector-store cleanup hook), `agents`, `krutrim-agent-extensions`. `[project.scripts] krutrim-agent-backend = "krutrim_agent_backend:main"` runs uvicorn with `reload=True`.
