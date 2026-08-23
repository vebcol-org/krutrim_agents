# `krutrim_agents_core` (backend/libs/krutrim_agents_core)

Package name: **`krutrim-agents-core`** (`backend/libs/krutrim_agents_core/pyproject.toml`), imported as `krutrim_agents_core`. The agent *engine*: profile discovery/registration, the deepagents graph builder, LLM provider abstraction, the cross-agent messaging bridge, and harness content loaders. Depends on the internal workspace packages `krutrim-agent-management` and `krutrim-agent-sandbox`.

**Dependency direction**: `krutrim_agents_core` never imports agent *content* — it owns the `AgentProfile` contract and discovers implementations of it by dotted package name (`settings.agent_profile_sources`, default `["krutrim_agents.profiles"]`), never by importing a specific profile module. The content package ([`krutrim_agents`](krutrim_agents.md)) imports `krutrim_agents_core`, not the other way around — this is what lets a second, privately-distributed profile package (e.g. a proprietary catalog) register itself purely via config, with zero edits here.

```
krutrim_agents_core/
├── builder.py          build_agent() — the one place a deepagents graph is assembled
├── profile.py           AgentProfile / RoleDefaults dataclasses — the plugin contract
├── registry.py           auto-discovery from settings.agent_profile_sources, register_profile/all_profiles/get_profile
├── tools/                 web_search (configurable provider), fetch_url, get_current_date/time/datetime — see §5
│   ├── websearch/            duckduckgo.py, tavily.py, registry.py (provider selection)
│   ├── fetch.py
│   └── datetime_tools.py
├── frontend_tools.py      FrontendToolBridgeMiddleware — makes render_content callable by the model
├── cross_agent.py         message_agent tool — synchronous agent-to-agent messaging
├── observability.py       Langfuse tracing (dev-mode only), wired into providers/registry.py
├── providers/
│   ├── base.py             ModelSettings / Provider ABCs, ProviderConfigError
│   ├── openrouter.py        OpenRouterModelSettings / OpenRouterProvider
│   ├── ollama.py             OllamaModelSettings / OllamaProvider
│   ├── registry.py            provider dispatch + build_chat_model() (every chat model goes through here)
│   └── store.py                ProviderStore — persists per-(agent_key, role) settings
└── harness/
    ├── prompts.py           load_prompt(agent_key, name) — cached .md reader
    ├── readonly_backend.py    ReadOnlyFilesystemBackend — write/edit/delete always fail
    └── runs.py                RunLogger — JSONL transcripts (defined, NOT wired into the live path — see below)
```

Profile content itself (`research`/`trading`/`sales`/`experiment`) lives in the separate [`krutrim_agents`](krutrim_agents.md) package, not here.

**`react_agent.py` — removed.** The from-scratch ReAct graph blueprint that used to live here (a second, hand-rolled way to compile a deep agent, alongside this file's `build_agent`/`create_deep_agent` path) was relocated into `krutrim_agents/profiles/research/agent.py` as `create_research_agent` — it's no longer a dormant reference blueprint, it's the actual compiled graph the `research` profile runs via `AgentProfile.graph_pattern` (see [`krutrim_agents.md`](krutrim_agents.md#the-research-profile)). The design-doc content that used to live at `krutrim_agents_core_react_agent.md` moved with it — see that file for what's current.

## 1. `build_agent()` — the graph assembler

[`builder.py`](../../libs/krutrim_agents_core/src/krutrim_agents_core/builder.py)

```python
def build_agent(
    profile: AgentProfile,
    store: ProviderStore,
    sandbox: BaseSandbox,
    checkpointer: BaseCheckpointSaver | None = None,
    extra_tools: list[BaseTool] | None = None,
) -> CompiledStateGraph
```

This is the **one** place a deepagents graph gets assembled — it never imports a specific profile module. Steps:

1. Builds a `CompositeBackend(default=sandbox, routes={...})`:
   - `default=sandbox` — everything not matched by a route (in particular `/workspace` and the `execute` tool) goes to the per-session Docker sandbox.
   - `"/skills/common/"` → `ReadOnlyFilesystemBackend` rooted at `settings.common_skills_dir`
   - `f"/skills/{profile.key}/"` → `ReadOnlyFilesystemBackend` rooted at `settings.agent_skills_dir(profile.key)`
   - `"/memory/"` → `ReadOnlyFilesystemBackend` rooted at `settings.agent_memory_dir(profile.key)`
   - These three routes scope a profile to its own skills/memory — one profile can't resolve a path into another's.
2. Calls `deepagents.create_deep_agent(...)`:
   - `model=build_chat_model(store.get(profile.key, "main"))` — resolves the `"main"` role from `ProviderStore`.
   - `tools=[*profile.tools(), *(extra_tools or [])]`
   - `system_prompt=profile.main_system_prompt`
   - `subagents=profile.subagents(store)`
   - `skills=list(profile.skills_sources)`, `memory=list(profile.memory_sources)`
   - `backend=` the `CompositeBackend` above
   - `middleware=[FrontendToolBridgeMiddleware()]`
   - `checkpointer=checkpointer or InMemorySaver()` — real callers ([`api/agent_run.py`](../services/krutrim_agent_backend.md#agent_runpy)) always pass a durable per-session `AsyncSqliteSaver`; `InMemorySaver()` is only a fallback so the graph still compiles for callers (tests) that don't need persistence.
   - `name=profile.key`

**Why read-only enforcement lives at the backend layer, not deepagents' `permissions` system**: deepagents' `permissions` rules are enforced at the tool layer, but the sandboxed `execute` tool is a shell — a model could `execute("rm harness/memory/foo.md")` and permission rules would never see it. `ReadOnlyFilesystemBackend` enforces read-only-ness at the thing every filesystem tool eventually calls through, so it can't be bypassed by picking a different tool.

`extra_tools` is where the cross-agent `message_agent` tool gets grafted in — only when the session's sharing policy makes at least one peer reachable (*).

## 2. `AgentProfile` / `RoleDefaults` — the plugin contract

[`profile.py`](../../libs/krutrim_agents_core/src/krutrim_agents_core/profile.py)

**`RoleDefaults`** (frozen dataclass) — one role's default provider/model, used to seed `ProviderStore`:

| Field | Type | Purpose |
|---|---|---|
| `provider` | `str` | `"openrouter"` / `"ollama"` |
| `model` | `str` | model id string |
| `temperature` | `float = 0.3` | default sampling temp |
| `max_tokens` | `int \| None = None` | default token cap |

**`AgentProfile`** (frozen dataclass) — the plugin contract:

| Field | Type | Purpose |
|---|---|---|
| `key` | `str` | must match `^[a-z0-9_-]+$`; this is the `agent_key` an `Agent` instance references (`Agent.agent_key`, see [`krutrim_agent_management.md`](krutrim_agent_management.md#hierarchy-project---agent--chat---session)), and appears in `/api/providers/<key>/...`. The AG-UI run route (`POST /agents/{agent_id}`) is keyed by **instance** id, not this profile key directly — see [`services/krutrim_agent_backend.md`](../services/krutrim_agent_backend.md#agent_runpy--the-ag-ui-streaming-route). |
| `display_name` | `str` | human-readable name |
| `description` | `str` | human-readable description |
| `roles` | `Sequence[str]` | role names this profile defines — validated against by `ProviderStore.get`/`set` |
| `default_models` | `dict[str, RoleDefaults]` | per-role default, seeds `ProviderStore` |
| `main_system_prompt` | `str` | top-level agent's system prompt, usually `load_prompt(key, "main")` |
| `skills_sources` | `Sequence[str]` | deepagents `skills=` paths (e.g. `/skills/common/`, `/skills/<key>/`) |
| `memory_sources` | `Sequence[str] = ()` | deepagents `memory=` paths (e.g. `/memory/AGENTS.md`) |
| `tools_factory` | `Callable[[], list[BaseTool]] \| None` | zero-arg factory for the main agent's tools |
| `subagents_factory` | `Callable[[ProviderStore], list[SubAgent]] \| None` | factory (takes `ProviderStore` so subagents resolve their own models) |
| `graph_pattern` | `Callable[[DeepAgentContext], CompiledStateGraph] \| None` | opt-in override of the graph topology `build_agent` compiles — see below |

Methods: `.tools()` calls `tools_factory()` or `[]`; `.subagents(store)` calls `subagents_factory(store)` or `[]`.

**`graph_pattern`** (default `None`): `build_agent` always assembles a `DeepAgentContext` (model, tools, system_prompt, subagents, skills, memory, backend, middleware, checkpointer, name — everything `create_deep_agent` would need). With no `graph_pattern`, it calls `context.react_agent()`, which is exactly the old unconditional `create_deep_agent(...)` call — zero behavior change for every profile that doesn't set this. A profile that needs a different top-level topology (planner/worker, supervisor, reflection loop — `create_deep_agent`'s graph shape is fixed and has no such parameter) sets `graph_pattern` to a callable that receives the `DeepAgentContext` and returns its own compiled `StateGraph`, calling `context.react_agent()` wherever it wants a fully-wired deep-agent node/tool instead of hand-rolling filesystem/subagent/skills/memory wiring itself. **`research` is the one profile that actually does this today** — see [`krutrim_agents.md`](krutrim_agents.md#the-research-profile) and [the from-scratch graph builder's design doc](krutrim_agents_core_react_agent.md) for a hand-rolled alternative to `context.react_agent()` when you don't want the `deepagents`/`create_agent` dependency at all.

`AgentProfile` itself has no registration logic — each profile module builds one and calls `register_profile(...)` at **module import time** (see [`krutrim_agents.md`](krutrim_agents.md)).

## 3. `registry.py` — configurable-source auto-discovery

[`registry.py`](../../libs/krutrim_agents_core/src/krutrim_agents_core/registry.py) — a thin, profile-specific wrapper around [`krutrim_agent_utils.PluginRegistry`](krutrim_agent_utils.md#1-plugin_registrypy--pluginregistryt) (`PluginRegistry(kind="agent")`, keyed by `profile.key`).

- `register_profile(profile)` — `_registry.register(profile.key, profile)`; raises `ValueError` if `profile.key` is already registered.
- `_discover()` — `_registry.discover_packages(settings.agent_profile_sources)` (`krutrim_agent_management.config.AppSettings`, default `["krutrim_agents.profiles"]`); for each dotted **package** name, imports it and `pkgutil.iter_modules()`s over its `__path__`, importing every submodule found. Importing a profile module executes its module-level `register_profile(AgentProfile(...))` call as a side effect. **This file never changes when a profile is added, removed, or an entirely new profile *source* is added** — the source list is config, not code. Community ships with exactly one source (`krutrim_agents.profiles`, the OSS content package); a private deployment adds a second source to `agent_profile_sources` to register proprietary profiles alongside it. `krutrim_agent_management`'s pluggable storage/vector-store backends and `krutrim_agent_sandbox`'s pluggable runtime selection reuse the same `PluginRegistry` primitive, just with `discover_modules()` instead (one implementation per module, not a package of many — see [`krutrim_agent_utils.md`](krutrim_agent_utils.md)).
- `all_profiles() -> dict[str, AgentProfile]` — calls `_discover()`, returns `_registry.all()`.
- `get_profile(key) -> AgentProfile` — calls `_discover()`, returns `_registry.get(key)` (raises `KeyError`, with the sorted list of known keys, if unregistered).

Both `all_profiles()`/`get_profile()` call `_discover()` on every invocation — cheap since re-importing an already-imported module is a `sys.modules` no-op, but it does mean discovery runs on every call, not once at startup.

## 4. `providers/` — LLM provider abstraction

### `base.py`
- `ProviderConfigError(RuntimeError)` — raised when a provider can't build a chat model (e.g. missing API key). Mapped to HTTP 400 by [`krutrim_agent_backend`'s error handlers](services/krutrim_agent_backend.md#6-apierror_handlerspy).
- `ModelSettings(BaseModel)` — common fields: `provider`, `model`, `temperature: float = 0.3`, `max_tokens: int | None`, `top_p: float | None`, `timeout: float | None`.
- `Provider(ABC)` — `key: str`; abstract `build_chat_model(settings) -> BaseChatModel`.

### `openrouter.py`
- `OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"`
- `OpenRouterModelSettings`: `provider: Literal["openrouter"]`, `model: str = "deepseek/deepseek-v4-flash-0731"`, `api_key_env: str = "OPENROUTER_API_KEY"` (the **env var name**, never the key itself), `base_url`, `site_url: str | None`, `app_name: str = "krutrim-agent"`.
- `OpenRouterProvider.build_chat_model`: reads `os.environ.get(settings.api_key_env)`, raises `ProviderConfigError` if unset; builds `default_headers` (`X-Title`, optional `HTTP-Referer`); returns `ChatOpenAI(...)`.

### `ollama.py`
- `OllamaModelSettings`: `provider: Literal["ollama"]`, `model: str = "llama3.1"`, `base_url: str = "http://localhost:11434"`, `num_ctx: int | None`, `keep_alive: str | None`.
- `OllamaProvider.build_chat_model` returns `ChatOllama(...)`. **Note**: does not pass `max_tokens`/`top_p`/`timeout` from the base `ModelSettings` through to `ChatOllama` — those fields are accepted but silently ignored for the Ollama provider.

### `registry.py` — the one choke point every chat model goes through
- `_SETTINGS_CLASSES` / `_PROVIDERS` — static dicts (`{"openrouter": ..., "ollama": ...}`), no auto-discovery like profiles have. Add a new provider by subclassing `ModelSettings`/`Provider` and registering here.
- `known_providers() -> list[str]`
- `parse_model_settings(data: dict) -> ModelSettings` — dispatches on `data["provider"]`, raises `ValueError` if unknown.
- `build_chat_model(data: dict | ModelSettings) -> BaseChatModel` — parses if needed, dispatches to the provider, then attaches Langfuse tracing if `get_langfuse_handler()` (*) returns a handler. **Every** chat model in the app — every deepagents profile role and the plain `chat` graph — is constructed through this function, so Langfuse tracing is global for free.

### `store.py` — `ProviderStore`
Persists one named `ModelSettings` per `(agent_key, role)` as a plain JSON file at `settings.provider_settings_path` (= `harness/memory/settings.json`, gitignored — local config, not source), shaped `{agent_key: {role: settings_dict}}`.

- **Thread-safety**: a single `threading.Lock()` per instance guards every read-modify-write.
- **Atomic writes**: writes to a `.json.tmp` sibling then `Path.replace()` (atomic rename).
- **Seeding / merging new agents**: on construction, if the file doesn't exist it's seeded from `_default_config()` (built from every registered profile's `default_models`); if it exists, `_merge_new_agents()` adds any profile key missing from the file **without touching existing keys** — a newly-registered profile is picked up automatically on next backend start, user edits to existing agents are never clobbered.
- **API**: `get_all(agent_key)`, `get(agent_key, role)` (raises `KeyError` if unset, `ValueError` if `role` isn't in `profile.roles`), `set(agent_key, role, data)` (validates the same way, persists), `reset(agent_key, role=None)`.
- Never stores API keys — only the env-var name to read them from.

`ProviderStore` is instantiated once in `krutrim_agent_backend`'s `lifespan()` and threaded through `build_agent()`, `AgentProfile.subagents(store)`, and the cross-agent messaging functions.

## 5. `tools/` — general-purpose tools

[`tools/`](../../libs/krutrim_agents_core/src/krutrim_agents_core/tools/) — code execution/file I/O are **not** here; deepagents auto-provisions `execute`/`ls`/`read_file`/`write_file`/`edit_file`/`glob`/`grep` from the sandbox backend. Was a single flat `tools.py` module; split into a package once a second web-search provider (Tavily) needed to sit alongside DuckDuckGo. `tools/__init__.py` re-exports the exact same names the old flat module did (`web_search`, `fetch_url`, `get_current_date/time/datetime`) — no profile's `from krutrim_agents_core.tools import ...` needed to change.

Constants: `MAX_SEARCH_RESULTS = 6` (per provider), `MAX_FETCH_CHARS = 8_000`, `FETCH_TIMEOUT_SECONDS = 15`.

| Tool | Behavior |
|---|---|
| `get_current_date(timezone=None)` | `YYYY-MM-DD`; catches bad timezone → `"Error: unknown timezone '<tz>'"` |
| `get_current_time(timezone=None)` | `HH:MM:SS`, same error handling |
| `get_current_datetime(timezone=None)` | full ISO 8601 with UTC offset, same error handling |
| `web_search(query)` (async) | Resolves to whichever provider `settings.web_search_provider` names (default `"duckduckgo"`) — see below. Import it as `web_search` to get the configured default, or `krutrim_agents_core.tools.websearch.{duckduckgo_search, tavily_search}` to pin one explicitly. |
| `fetch_url(url)` (async) | `httpx.AsyncClient` GET, 15s timeout, `User-Agent: Mozilla/5.0 (krutrim-agent)`; HTML → text via `html2text` (`ignore_images=True`, `body_width=0`); truncated to 8000 chars with a `"[Truncated...]"` suffix; any exception → `"Error: could not fetch '<url>' (...)."` |

### `tools/websearch/` — pluggable search provider

- **`duckduckgo.py`** — `duckduckgo_search(query)`: `ddgs.DDGS().text(query, max_results=6)` off-thread via `asyncio.to_thread`; broad except → `"Error: web search failed (...)."`, no results → `"No results found."`. Zero-config, no API key.
- **`tavily.py`** — `tavily_search(query)`: hand-written `@tool` against `tavily-python`'s `AsyncTavilyClient` directly (not `langchain-tavily`'s `TavilySearch` class), formatted into the same numbered `title/href/body`-shaped text `duckduckgo_search` produces, so the model sees a consistent shape regardless of provider. Reads `TAVILY_API_KEY` from the environment; returns a tool-visible error string (not an exception) if the key is unset or the request fails.
- **`registry.py`** — `SEARCH_PROVIDERS = {"duckduckgo": duckduckgo_search, "tavily": tavily_search}`; `get_web_search_tool(provider=None)` resolves `provider` or falls back to `settings.web_search_provider` (`krutrim_agent_management.config.AppSettings`, `KRUTRIM_AGENT_WEB_SEARCH_PROVIDER` env var, default `"duckduckgo"`); an unrecognized provider name falls back to DuckDuckGo rather than raising. `tools/websearch/__init__.py`'s `web_search = get_web_search_tool()` is resolved once at import time — the configured provider is fixed for the process lifetime, same as every other env-driven setting here.

Every tool in this package surfaces failures as tool-visible error strings rather than raising — the model sees the failure and can react, the graph doesn't crash.

## 6. `frontend_tools.py` — `FrontendToolBridgeMiddleware`

[`frontend_tools.py`](../../libs/krutrim_agents_core/src/krutrim_agents_core/frontend_tools.py) — a trimmed port of `copilotkit.CopilotKitMiddleware`'s hooks, reading `state["tools"]` (populated by `ag_ui_langgraph`'s default state merge from `RunAgentInput.tools`) instead of CopilotKit's own state shape.

This is what makes a frontend-only tool (e.g. `render_content` — see [the AG-UI flow doc](../../docs/app-flow.md)) usable inside the LangGraph loop even though nothing on the server implements it:

1. **`wrap_model_call`/`awrap_model_call`** — merges `state["tools"]` into the model's bound tool list, so the LLM can see and call frontend tools at all.
2. **`after_model`/`aafter_model`** — if the last `AIMessage`'s tool calls include any frontend-tool names, strips them out of the message (saving them in `intercepted_tool_calls`/`original_ai_message_id` state) **before** LangGraph's `ToolNode` would try (and fail) to execute a tool with no backend implementation. The turn then ends naturally.
3. **`after_agent`/`aafter_agent`** — once the run is over, restores the stripped calls onto the final message, purely so they still stream to the client as ordinary `TOOL_CALL_*` AG-UI events.

## 7. `cross_agent.py` — synchronous agent-to-agent messaging

[`cross_agent.py`](../../libs/krutrim_agents_core/src/krutrim_agents_core/cross_agent.py) — lets the agent in one session message the agent in another session **in the same project**, synchronously, and get a real reply. Not a shared filesystem — sessions keep separate sandboxes the whole time (contrast with `SessionInfo.attached_to_session_id`, which does share a container; see [`krutrim_agent_sandbox.md`](krutrim_agent_sandbox.md)).

**Agent-owned sessions only.** Both sides of an exchange must be sessions owned by an `Agent` (never a `Chat` — see [`krutrim_agent_management.md`](krutrim_agent_management.md#hierarchy-project---agent--chat---session)); a `Chat` reaching into a sibling `Agent` is a real, separate feature (the plain `chat` graph has no tool-injection framework today) that isn't built. `_check_eligible` enforces this directly — not just via `find_eligible_peers`'s filtering — since `message_agent`'s `container_id` argument is LLM-supplied and not guaranteed to come from the peer list it was offered. It also now checks both sessions share the same (non-null) `project_id`, since sessions are looked up globally by id rather than scoped to a caller-supplied `project_id`.

`MAX_CROSS_AGENT_CALL_DEPTH = 3` — hard cap on chain length, independent of cycle detection.

- **`_check_eligible(caller, target) -> bool`** — eligible iff both are `owner_type == "agent"`, both share the same non-null `project_id`, and either both `sandbox_sharing == "project-shared"`, or both `"session-shared"` AND mutually listed in each other's `linked_session_ids`. One-sided sharing is never eligible.
- **`find_eligible_peers(store, project_id, session) -> list[str]`** — `[]` immediately if `session.sandbox_sharing == "isolated"`; otherwise gathers every session owned by any `Agent` in the project (`store.list_agents(project_id)` then `store.list_sessions("agent", agent_id)` per agent) and filters via `_check_eligible`. This is a graph-build-time convenience for deciding whether to grant the tool at all — `invoke_agent_turn` re-checks eligibility per actual call regardless.
- **`invoke_agent_turn(...)`** (async, returns a plain string always — success or failure, since it's a tool return value):
  1. Self-message guard, cycle detection (`target_session_id in call_chain`), depth limit (`len(call_chain) >= 3`).
  2. Looks up both `SessionInfo`s by id alone (`store.get_session(session_id)`, no `project_id` needed), re-checks eligibility for this specific pair.
  3. Resolves the target's owning `Agent` (`store.get_agent(target.owner_id)`) and its profile via `get_profile(target_agent.agent_key)` — **not** a project-wide type, since a project can now hold multiple differently-typed agents.
  4. `next_call_chain = [*call_chain, caller_session_id]`.
  5. `sandbox_registry.get_or_create(target_session_id)` — spins up the target's sandbox if idle.
  6. Opens the **target's own durable checkpointer** (`sessions/{target}/langgraph_checkpoint.sqlite`) — the same file its normal AG-UI requests use, so the exchange shows up in that session's history next time its human owner resumes it.
  7. Recursively resolves the target's own eligible peers, so a `message_agent` tool propagates to the target too (with the incremented `call_chain`) if it has peers.
  8. Builds the target's graph via `build_agent(...)`, wraps the message as `HumanMessage(content=message, name=f"peer_agent:{caller_session_id}")`.
  9. `asyncio.wait_for(graph.ainvoke(...), timeout=settings.cross_agent_call_timeout_seconds)` (default 60s) — on timeout, returns an error string, not an exception.
  10. `finally: sandbox_registry.release(handle.owner_id)` — always runs.
- **`message_agent_tool(...)`** — builds and returns a fresh `@tool async def message_agent(container_id, message) -> str` closure **bound to one calling session's identity and call chain**, constructed fresh per graph-build (never shared across sessions, so closure state can't leak). Delegates to `invoke_agent_turn`.

Wired in by [`api/agent_run.py`](services/krutrim_agent_backend.md#agent_runpy): calls `find_eligible_peers` at graph-build time; if any peers exist, builds a `message_agent_tool(...)` and passes it into `build_agent(..., extra_tools=[...])`.

## 8. `harness/` — prompt/skill/memory loaders

[`harness/`](../../libs/krutrim_agents_core/src/krutrim_agents_core/harness/)

- **`prompts.py`** — `load_prompt(agent_key, name)`: reads `harness/prompts/<agent_key>/<name>.md`, raises `FileNotFoundError` if missing, `.strip()`s the content. **`@lru_cache(maxsize=None)`** — cached forever per process. Editing a prompt `.md` file has no effect on a running process until restart.
- **`readonly_backend.py`** — `ReadOnlyFilesystemBackend(FilesystemBackend)`: overrides `write`/`edit`/`delete` to unconditionally return an error result (`"Permission denied: this path is a read-only harness directory."`); read operations (`ls`/`read_file`/`glob`/`grep`) are inherited unchanged. Used to mount `/skills/*`/`/memory/` in `builder.py`'s `CompositeBackend`.
- **`runs.py`** — `RunLogger(agent_key, thread_id)`: appends JSONL records (`{"ts", "agent", "thread_id", "type", **payload}`) to `harness/memory/runs/<agent_key>/<thread_id>.jsonl` under a per-instance lock. **Defined but confirmed NOT wired into the live request path** — nothing in `krutrim_agent_backend` or the eval runner currently instantiates it. It's scaffolding for observability/eval-feeding, not dead code exactly, but not called from anywhere today. If you wire it up, remove this callout.

Skills (`harness/skills/`) and long-term memory (`harness/memory/<agent_key>/AGENTS.md`) need **no loader in this package at all** — deepagents' own `SkillsMiddleware`/`MemoryMiddleware` read them directly through the `CompositeBackend` routes set up in `builder.py`.

## 9. `observability.py` — Langfuse tracing (dev-mode only)

[`observability.py`](../../libs/krutrim_agents_core/src/krutrim_agents_core/observability.py) — `get_langfuse_handler()` (`@lru_cache(maxsize=1)`): returns `None` immediately unless `settings.dev_mode` is truthy; returns `None` with a warning if dev-mode is on but `langfuse_public_key`/`langfuse_secret_key` aren't both set; otherwise lazily constructs a `Langfuse` client and returns a `CallbackHandler`. Wired into `providers/registry.py::build_chat_model`, so it traces every chat model in the app without any per-route wiring — explicitly a local dev aid, not meant for production traffic by default.

## Dependencies

[`pyproject.toml`](../../libs/krutrim_agents_core/pyproject.toml) — package `krutrim-agents-core`: `deepagents`, `langgraph`, `langgraph-checkpoint-sqlite`, `langchain`, `langchain-openai`, `langchain-ollama`, `ddgs`, `tavily-python`, `html2text`, `httpx`, `loguru`, `langfuse`, plus internal workspace deps `krutrim-agent-management`, `krutrim-agent-sandbox`, `krutrim-agent-utils`.

## Live call graph (production)

`api/agent_run.py` → `find_eligible_peers` (`cross_agent.py`) → maybe `message_agent_tool` (`cross_agent.py`) → `build_agent` (`builder.py`) → `create_deep_agent` (deepagents), or — for the `research` profile — `krutrim_agents.profiles.research.agent.create_research_agent` via its `graph_pattern`, with the profile resolved via `krutrim_agents_core.registry.get_profile`.

Relevant tests: `backend/tests/test_cross_agent.py`, `test_graph_smoke.py`, `test_agent_run.py`, `test_providers.py`, `test_agent_registry.py`. Standalone eval runner: `backend/harness/evals/runner.py` (`uv run python harness/evals/runner.py <agent_key>` — needs real API/Ollama access, not part of `pytest`).
