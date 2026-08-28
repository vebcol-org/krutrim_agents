# App Flow

How a message travels through Krutrim Agent, from the browser to the LLM and back. See the root [README.md](../README.md) for setup/run instructions and the plugin model — this doc focuses on the runtime request flow.

> Naming note: the repo/package name is **krutrim_agent**. "Research" is just one of three shipped agent _profiles_ (`research`, `trading`, `sales`) — the platform itself is agent-type-agnostic.

## 1. System overview

```
apps/web (Vite+React+TS)     ─┐
                                ├─ @ag-ui/client HttpAgent, one per selected agent_key
apps/desktop (Tauri+Rust+TS) ─┘  (same React renderer, wrapped in a native window)
                                                       │
                                                       │ AG-UI protocol (HTTP + SSE), direct — no
                                                       │ intermediary Node runtime process
                                                       ▼
                                    backend/ (FastAPI, Python, uv-managed)
                                      ├─ POST /agents/{agent_key}       → ONE parameterized route (deepagents)
                                      ├─ POST /api/chat                 → basic LangGraph chat loop (*)
                                      ├─ /api/projects, /api/projects/{id}/sessions → CRUD (*)
                                      ├─ GET  /api/models                → chat model catalog (*)
                                      ├─ GET  /api/agents               → lists registered profiles
                                      ├─ /api/providers/{agent_key}     → CRUD for per-role LLM settings
                                      └─ /api/health
                                                       │
                                          krutrim_agents_core/registry.py
                                          auto-discovers profiles/{research,trading,sales}/*
                                                       │
                                             ┌─────────┴──────────┐
                                             ▼                    ▼
                                  providers/ (OpenRouter)   harness/ (skills, prompts,
                                                             evals, memory — per agent_key)
                                                                   │ execute / file ops
                                                                   ▼
                                                One Docker sandbox per agent profile (read-only
                                                rootfs, no network, non-root, resource limits)
```

There is no queue and no worker process — it's a two-process system (one FastAPI process + one frontend dev server) plus one long-lived Docker sandbox container per registered agent profile. There's still no server-side relational database for the AG-UI agent profiles (\*) for its project/session bookkeeping.

## 2. Entry points

| Layer                  | Entry point                                                                                                                                                                                                                                              |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Backend (FastAPI/ASGI) | [`backend/services/krutrim_agent_backend/src/krutrim_agent_backend/main.py`](../backend/services/krutrim_agent_backend/src/krutrim_agent_backend/main.py) — `create_app()`; run via `uv run uvicorn krutrim_agent_backend.main:app --reload --port 8000` |
| Web frontend           | [`apps/web/src/main.tsx`](../apps/web/src/main.tsx) → `apps/web/src/app/app.tsx` → mounts `<AgentApp backendUrl={...} />`                                                                                                                                |
| Desktop frontend       | `apps/desktop/src/renderer/main.tsx` — same `<AgentApp>` pattern, no Node "main process"; the Rust shell (`apps/desktop/src-tauri/src/main.rs`) just wraps the same React renderer in a native window and does **not** auto-spawn the backend            |
| Shared UI shell        | [`libs/agent-ui/src/lib/agent-app.tsx`](../libs/agent-ui/src/lib/agent-app.tsx) (`AgentApp`), [`libs/agent-ui/src/lib/agent-client.ts`](../libs/agent-ui/src/lib/agent-client.ts) (`useAgentChat`, the AG-UI transport)                                  |

## 3. Startup sequence (backend)

`main.py`'s `lifespan()` runs once at process start ([`main.py:22-42`](../backend/services/krutrim_agent_backend/src/krutrim_agent_backend/main.py)):

1. Load `ProviderStore` from `backend/harness/memory/settings.json` (per-`(agent_key, role)` LLM config, gitignored).
2. Spin up **one `DockerSandboxBackend` per registered profile** (`session_id=key`) — not per-thread, not shared across profiles.
3. `all_profiles()` returns whatever `krutrim_agents_core/registry.py` auto-discovered by scanning `krutrim_agents/profiles/*` at import time (each profile package calls `register_profile(...)` on import — no manual wiring).
4. `build_agui_agents(store, sandboxes)` compiles one `deepagents` LangGraph graph per profile via `build_agent()` and wraps each in an AG-UI `LangGraphAgent`.
5. `mount_agent_run_endpoint(app, agents_by_key)` registers the single parameterized route (\*).
6. On shutdown, every sandbox container is closed.

## 4. End-to-end request trace

### Step 1 — Page load

`AgentApp` ([`libs/agent-ui/src/lib/agent-app.tsx`](../libs/agent-ui/src/lib/agent-app.tsx)) reads `?agent=<key>` from the URL (defaults to `research`), then calls `useAgentChat({ agentKey, backendUrl, onRenderContent })`.

### Step 2 — User sends a message

`useAgentChat` ([`libs/agent-ui/src/lib/agent-client.ts:67-70`](../libs/agent-ui/src/lib/agent-client.ts)) builds one `@ag-ui/client` `HttpAgent` pointed at `${backendUrl}/agents/${agentKey}`. `sendMessage()` calls `agent.addMessage({ role: 'user', content })`, then `runTurn()`.

### Step 3 — `runTurn()` calls `agent.runAgent({ tools: [RENDER_CONTENT_TOOL] })`

Every run declares one frontend-only tool, shared across all agent types ([`agent-client.ts:34-50`](../libs/agent-ui/src/lib/agent-client.ts)):

```ts
const RENDER_CONTENT_TOOL = {
  name: 'render_content',
  description:
    '... "markdown" for a report/draft, "chart" for a numeric series, "news" for a list of items ...',
  parameters: { kind, title, content },
};
```

This POSTs a `RunAgentInput` (`threadId`, `messages`, `tools`) to `POST /agents/{agent_key}`.

### Step 4 — Backend receives the request

One parameterized FastAPI route handles every profile ([`backend/services/krutrim_agent_backend/src/krutrim_agent_backend/api/agent_run.py:39-55`](../backend/services/krutrim_agent_backend/src/krutrim_agent_backend/api/agent_run.py)):

```python
@app.post(f"{AGENT_RUN_PATH_PREFIX}/{{agent_key}}")
async def agent_run_endpoint(
    agent_key: str, input_data: RunAgentInput, request: Request
):
    agent = agents_by_key.get(agent_key)
    ...
    request_agent = agent.clone()  # isolated run state per request

    async def event_generator():
        async for event in request_agent.run(input_data):
            yield encoder.encode(event)

    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())
```

Adding a new agent profile never means adding a new route — the same handler picks it up automatically once it's registered.

### Step 5 — The graph runs (agent orchestration)

Built by [`krutrim_agents_core/builder.py:build_agent()`](../backend/libs/krutrim_agents_core/src/krutrim_agents_core/builder.py):

```python
def build_agent(profile, store, sandbox) -> CompiledStateGraph:
    backend = CompositeBackend(
        default=sandbox,  # every filesystem op / shell command → Docker container
        routes={
            "/skills/common/": ReadOnlyFilesystemBackend(...),
            f"/skills/{profile.key}/": ReadOnlyFilesystemBackend(...),
            "/memory/": ReadOnlyFilesystemBackend(...),
        },
    )
    return create_deep_agent(
        model=build_chat_model(store.get(profile.key, "main")),
        tools=profile.tools(),
        system_prompt=profile.main_system_prompt,
        subagents=profile.subagents(store),
        skills=list(profile.skills_sources),
        memory=list(profile.memory_sources),
        backend=backend,
        middleware=[FrontendToolBridgeMiddleware()],
        checkpointer=InMemorySaver(),
        name=profile.key,
    )
```

`create_deep_agent` (from the `deepagents` package) supplies the actual agent loop — planning, tool-calling, subagent delegation via a `task` tool. This repo only supplies the _configuration_: prompts, tools, subagents, sandbox backend, middleware.

Within a run, the **main** role (e.g. `research`'s main model, resolved via `ProviderStore.get(agent_key, "main")`) reasons and may:

- call `web_search` / `fetch_url` directly ([`krutrim_agents_core/tools.py`](../backend/libs/krutrim_agents_core/src/krutrim_agents_core/tools.py)),
- delegate via the `task` tool to a subagent (for `research`: `researcher` → `critic` → `writer`, each its own prompt + model — see [`krutrim_agents/profiles/research/__init__.py`](../backend/libs/krutrim_agents/src/krutrim_agents/profiles/research/__init__.py)),
- call sandboxed file/shell tools (`execute`, `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep` — auto-derived by deepagents from `BaseSandbox`), which run **inside that profile's Docker container**,
- and/or call `render_content` once it has finished output.

`FrontendToolBridgeMiddleware` ([`krutrim_agents_core/frontend_tools.py`](../backend/libs/krutrim_agents_core/src/krutrim_agents_core/frontend_tools.py)) is what makes `render_content` — a tool with no backend implementation — usable inside the LangGraph loop:

1. `wrap_model_call` merges the frontend-declared tools into the model's bound tool list so the LLM can call them at all.
2. `after_model` strips any `render_content` call out of the `AIMessage` before LangGraph's `ToolNode` would try (and fail) to execute it server-side — the turn then ends naturally.
3. `after_agent` restores the call onto the final message purely so it still streams to the client as a normal `TOOL_CALL_*` AG-UI event.

### Step 6 — Streaming back

`ag_ui_langgraph` translates LangGraph events into AG-UI SSE events (`RUN_STARTED`, `TEXT_MESSAGE_CONTENT`, `TOOL_CALL_START/ARGS/END`, `STATE_SNAPSHOT`, `RUN_FINISHED`). The frontend's `HttpAgent` consumes these directly and updates `agent.messages` — this is why chat text streams token-by-token.

### Step 7 — Closing the loop on `render_content`

When `agent.runAgent()` resolves, `runTurn()` ([`agent-client.ts:77-114`](../libs/agent-ui/src/lib/agent-client.ts)) inspects the last assistant message's tool calls for `render_content`. For each one it finds:

1. Parses the JSON args as a `RenderContentPayload`.
2. Calls `onRenderContent(payload)` → `AgentApp` sets `payload` state → the canvas looks up `getAgentRenderer(agentKey)` ([`libs/agent-renderers/src/registry.ts`](../libs/agent-renderers/src/registry.ts)) and renders the right pane (markdown / chart / news, or a profile-specific renderer).
3. Synthesizes a client-side `role: 'tool'` message (no backend round-trip) and recursively calls `runTurn()` again so the model sees its tool call "succeeded" and can finish the turn.

### Sequence diagram

```
Browser (web/desktop renderer)                          Python backend (FastAPI)
     │  HttpAgent, tools=[render_content]                        │
     │──────────────── POST /agents/{agent_key} ────────────►│
     │      RunAgentInput (threadId, messages, tools)             │  clone() the agent, run the graph
     │ ◄──────────────── SSE stream (AG-UI events) ───────────────│
     │  last message has a render_content call →                  │
     │  runs locally: onRenderContent() fills the canvas,          │
     │  runTurn() calls itself → new run with the tool result ────►│
```

### The `research` profile's pipeline specifically

The main system prompt ([`backend/harness/prompts/research/main.md`](../backend/harness/prompts/research/main.md)) instructs the main agent to: delegate to `researcher` (web search/fetch) → delegate to `critic` (reviews the draft) → delegate to `writer` (produces the final markdown per the `report-writing` skill) → call `render_content(kind="markdown")`.

## 4b. The `chat` project type — a simpler, non-agentic flow

Separate from the AG-UI/deepagents flow in §4: `chat` is a plain system-prompt + LLM call, no tools, no subagents, no sandbox, no streaming — one JSON request in, one JSON response out. It exists for cases that don't need the full agent pipeline. Agent types (`research`/`trading`/`sales`) will eventually get a `project_type` here too; only `chat` is wired up so far.

```
POST /api/chat  { message, project_id?, session_id?, project_title?, project_type?, provider?, model? }
```

Handled entirely by [`api/chat_routes.py`](../backend/services/krutrim_agent_backend/src/krutrim_agent_backend/api/chat_routes.py):

1. **Project resolution.** If `project_id` is omitted, a new project is created automatically — `project_type` defaults to `"chat"` (the only supported value today), `provider`/`model` default to the chat catalog's one entry (`openrouter` / `deepseek/deepseek-v4-flash`, see [`chat/catalog.py`](../backend/services/krutrim_agent_backend/src/krutrim_agent_backend/chat/catalog.py)) unless the caller names a different known one, and the title is derived from the first message if not given. If `project_id` is supplied, that project is loaded and must be `project_type == "chat"`.
2. **Session resolution.** Same auto-create-if-omitted pattern, scoped under the resolved project (`Storage.create_session` / `get_session`).
3. **Checkpointer.** A durable per-session `AsyncSqliteSaver` is opened at `sessions/{session_id}/langgraph_checkpoint.sqlite` (keyed by `thread_id == session_id`). History is now **LangGraph's** — the call passes only the new `HumanMessage`; the checkpointer replays prior state and appends. (The old `Storage.read_checkpoint`/`checkpointer.json` round-trip is gone from this route.)
4. **Graph invocation.** [`chat/graph.py:build_chat_graph()`](../backend/services/krutrim_agent_backend/src/krutrim_agent_backend/chat/graph.py) compiles a hand-assembled ReAct graph (`before_agent → model [→ tools]`) with a pluggable middleware stack. The `chat` flow passes no tools and — **iff `KRUTRIM_AGENT_RAG_INJECTION_ENABLED`** — one `RagInjectionMiddleware`, which retrieves top-k context for the latest user turn from this session's vector index and prepends it to the system prompt (loaded from `backend/harness/prompts/chat/main.md`). `graph.ainvoke(..., config={"configurable": {"thread_id": session_id}})`.
5. **Persistence.** History lives in the sqlite checkpoint (step 3). Per-turn + cumulative token usage (from the reply's `usage_metadata`) is still folded into `usage.json` (`chat/usage.py`). Every step logs at INFO/DEBUG via loguru (`~/.krutrim_agent/logs/server/server.log`).
6. **Response.** `{ chat_id, session_id, message: { role: "assistant", content } }`.

RAG end-to-end for chat: upload a document to the session via `POST /api/sessions/{id}/rag/file` (or `/rag/text`) → the Celery `process_rag_document` task extracts/chunks/embeds/indexes it (`~/.krutrim_agent/logs/worker/worker.log`) → the next chat turn on that session retrieves and injects it. Deleting the chat (`DELETE /api/chats/{id}`) cascades its sessions and drops each session's vector index (FAISS dir / Qdrant collection, per `KRUTRIM_AGENT_VECTOR_STORE_BACKEND`) via the `krutrim_agent_rag.cleanup` session-delete hook.

### Storage layout

`Storage` ([`storage/base.py`](../backend/libs/krutrim_agent_management/src/krutrim_agent_management/base.py), implemented by `LocalStorage` in [`storage/local.py`](../backend/libs/krutrim_agent_management/src/krutrim_agent_management/local.py)) is a backend-agnostic persistence contract — swapping in a remote-backed implementation later needs no caller changes. `LocalStorage` keeps everything under an OS-appropriate `STORAGE_ROOT` (`krutrim_agent_management.config.settings.storage_root`, overridable via `KRUTRIM_AGENT_STORAGE_ROOT`):

```
STORAGE_ROOT/
  project.db                                    -- SQLite, one row per project (id, title, information, type, provider, model)
  projects/{project_id}/
    MEMORY.md                                     -- freeform agent memory for that project
    session.db                                     -- SQLite, one row per session
    cache/{namespace}/{sha256(key)}.json           -- generic cache (mcp/rag/tool results)
    sessions/{session_id}/
      langgraph_checkpoint.sqlite                   -- this session's message history (LangGraph AsyncSqliteSaver)
      usage.json                                    -- per-turn + cumulative token usage
      embeddings/                                   -- FAISS vector index (faisslite backend; Qdrant uses a `session_{id}` collection instead)
```

Logs live outside `STORAGE_ROOT` under `KRUTRIM_AGENT_LOG_DIR` (default `~/.krutrim_agent/logs/`), split `server/server.log` (FastAPI) and `worker/worker.log` (Celery) — same loguru config, periodic rotation (`KRUTRIM_AGENT_LOG_ROTATION`, default `1 day`). See [`backend/docs/libs/krutrim_agent_management.md`](../backend/docs/libs/krutrim_agent_management.md#logging).

## 5. Backend API surface

| Route                                                                         | File                                                                                                                   | Purpose                                                                                                            |
| ----------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `POST /agents/{agent_key}`                                                    | [`api/agent_run.py`](../backend/services/krutrim_agent_backend/src/krutrim_agent_backend/api/agent_run.py)             | Streams one AG-UI run for the given profile (\*)                                                                   |
| `GET /agents/{agent_key}/health`                                              | `api/agent_run.py`                                                                                                     | Per-agent health check                                                                                             |
| `GET /api/agents`                                                             | [`api/agents_routes.py`](../backend/services/krutrim_agent_backend/src/krutrim_agent_backend/api/agents_routes.py)     | Lists registered profiles (key, display name, description, roles)                                                  |
| `/api/providers/{agent_key}`                                                  | [`api/settings_routes.py`](../backend/services/krutrim_agent_backend/src/krutrim_agent_backend/api/settings_routes.py) | CRUD for that agent's per-role provider/model settings                                                             |
| `POST /api/chat`                                                              | [`api/chat_routes.py`](../backend/services/krutrim_agent_backend/src/krutrim_agent_backend/api/chat_routes.py)         | Send a chat message; auto-creates the project/session on the first call (\*)                                       |
| `GET/DELETE /api/projects`, `/api/projects/{project_id}`                      | [`api/projects_routes.py`](../backend/services/krutrim_agent_backend/src/krutrim_agent_backend/api/projects_routes.py) | List/read/delete projects — no manual create route, see §4b                                                        |
| `GET/DELETE /api/projects/{project_id}/sessions`, `.../sessions/{session_id}` | [`api/sessions_routes.py`](../backend/services/krutrim_agent_backend/src/krutrim_agent_backend/api/sessions_routes.py) | List/read/delete sessions under a project                                                                          |
| `GET /api/sessions/{session_id}/messages`                                     | `api/sessions_routes.py`                                                                                               | Read-only message history for a session (reads `langgraph_checkpoint.sqlite` via `aget_state`) — used to reload a past conversation in the UI |
| `GET /api/models`                                                             | [`api/models_routes.py`](../backend/services/krutrim_agent_backend/src/krutrim_agent_backend/api/models_routes.py)     | Lists models available for the `chat` project type                                                                 |
| `/api/health`                                                                 | [`api/health.py`](../backend/services/krutrim_agent_backend/src/krutrim_agent_backend/api/health.py)                   | Process-level health check                                                                                         |

Provider settings changes take effect on the **next backend restart** — there's no hot-reload of the compiled graphs in v1.

## 6. The plugin model

**Core** (never touched to add an agent): the FastAPI app, the providers system, the Docker sandbox, the harness loaders, `krutrim_agents_core/registry.py` (auto-discovery), `krutrim_agents_core/builder.py` (generic graph assembly), `libs/ui`, and the entire frontend shell in `libs/agent-ui`.

**To add a new agent profile:**

1. `backend/libs/krutrim_agents/src/krutrim_agents/profiles/<key>/__init__.py` — define an `AgentProfile` (dataclass contract in [`krutrim_agents_core/profile.py`](../backend/libs/krutrim_agents_core/src/krutrim_agents_core/profile.py): `key`, `display_name`, `roles`, `default_models`, `main_system_prompt`, `skills_sources`, `memory_sources`, `tools_factory`, `subagents_factory`) and call `register_profile(...)`.
2. `backend/harness/{skills,prompts,memory}/<key>/` — that profile's harness content (at minimum `memory/<key>/AGENTS.md` and one prompt per declared role).
3. Optionally, `libs/agent-renderers/src/<key>/renderer.tsx` + one line in `libs/agent-renderers/src/registry.ts` — omit it and the built-in markdown/chart/news renderer is used automatically.
4. Restart the backend. Visit `?agent=<key>`.

No core file is edited for any of the above — `registry.py` and `getAgentRenderer()` do the wiring at runtime.

## 7. The sandbox

Every shell command and filesystem operation an agent runs happens inside a locked-down Docker container (`krutrim_agent_sandbox.docker_backend.DockerSandboxBackend`) — **one container per agent profile**, not per conversation thread, kept alive for the process lifetime:

- **No network** (`network_disabled=True`).
- **Read-only rootfs** — only `/tmp` and `/workspace` are writable, both in-memory tmpfs, no host bind mount (zero access to host files).
- **Non-root, capabilities dropped, `no-new-privileges`.**
- **Fixed memory/CPU/pid limits** and a **hard wall-clock timeout** per command.
- Policy lives server-side (`sandbox/policy.py`) — the LLM-facing `execute` tool only ever takes a command string, so there's no path for the model to loosen any of this.

`backend/harness/skills/{common,<agent_key>}/` and `backend/harness/memory/<agent_key>/` are mounted **read-only** alongside the sandbox, scoped per agent (one profile can't read another's memory) via the `CompositeBackend` in `builder.py`.

## 8. Data layer

No vector database, and no relational database for the AG-UI agent profiles (\*).

| What                                                      | Where                                                   | Notes                                                                                                                                                                             |
| --------------------------------------------------------- | ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Per-`(agent_key, role)` provider/model settings           | `backend/harness/memory/settings.json` (gitignored)     | Managed by `ProviderStore` — thread-safe, atomic writes, auto-seeded from each profile's `default_models`, merges in newly-registered profiles without clobbering existing config |
| Durable per-agent memory                                  | `backend/harness/memory/<agent_key>/AGENTS.md`          | Loaded into that agent's system prompt; read-only to the agent itself                                                                                                             |
| Run transcripts                                           | `backend/harness/memory/runs/<agent_key>/` (gitignored) | Written by `RunLogger`, JSONL, for observability/eval feeding                                                                                                                     |
| Conversation state (AG-UI agent profiles)                 | LangGraph `InMemorySaver()` (`builder.py`)              | In-process only — does **not** survive a backend restart                                                                                                                          |
| Chat projects/sessions, memory, checkpoints, usage, cache | `STORAGE_ROOT` (OS-specific per-user data dir, see §4b) | `LocalStorage` — SQLite for project/session rows, atomic JSON/text writes for everything else; **does** survive a backend restart                                                 |
| Sandbox scratch space                                     | `/workspace`, `/tmp` inside each container              | In-memory tmpfs, not persisted anywhere                                                                                                                                           |

## 9. External integrations

**LLM providers** (`backend/libs/krutrim_agents_core/src/krutrim_agents_core/providers/`):

- **OpenRouter** — `ChatOpenAI` against `https://openrouter.ai/api/v1`, needs `OPENROUTER_API_KEY`; default `deepseek/deepseek-v4-flash-0731` for agent profiles, `deepseek/deepseek-v4-flash` for the `chat` project type (\*).
- **Ollama** — `ChatOllama`, local, no key, default `base_url=http://localhost:11434`, default model `llama3.1`.
- Extend by subclassing `ModelSettings`/`Provider` and registering in `providers/registry.py` (core, shared by every profile).

**Web tools** ([`krutrim_agents_core/tools.py`](../backend/libs/krutrim_agents_core/src/krutrim_agents_core/tools.py)):

- `web_search` — DuckDuckGo via the `ddgs` library, no API key.
- `fetch_url` — `httpx` GET + `html2text` conversion, 15s timeout, 8000-char cap.

No vector DB and no dedicated market-data API are wired in yet (a known v1 limitation — see README).

## 10. Shared frontend types

[`libs/shared-types/src/lib/shared-types.ts`](../libs/shared-types/src/lib/shared-types.ts) is a **hand-synced** (not codegen'd) TS mirror of the backend's Pydantic models: `AgentMeta`, `ModelSettings` (OpenRouter/Ollama variants), `RenderContentPayload`, `ChartContent`, `NewsContent`, plus constants `AGENT_ENDPOINT_PREFIX = '/agents'`, `DEFAULT_BACKEND_URL = 'http://localhost:8000'`, `AGENT_QUERY_PARAM = 'agent'`, `DEFAULT_AGENT_KEY = 'research'`. Keep it in sync by hand when backend models change.

## 11. Known v1 limitations

- No network-allowlist egress proxy for the sandbox — it's network-disabled only, not selectively allowlisted.
- The desktop app doesn't auto-spawn the backend; it connects to a configurable `VITE_BACKEND_URL`.
- `shared-types` is hand-synced, not codegen'd — can drift from the backend's actual Pydantic models.
- Provider/model settings changes require a backend restart (no hot-reload of compiled graphs).
- No real market-data tools (quotes/OHLCV/indicators) — agents have `web_search`/`fetch_url` plus a sandboxed Python/pandas `execute` tool.
- A privileged "coding"/PR-drafting agent type (needing real git/network/credential access and a human-approval gate) is deliberately not built — it would need a different, more privileged sandbox than every other profile shares.
