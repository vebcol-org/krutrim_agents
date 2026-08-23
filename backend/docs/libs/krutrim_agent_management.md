# `krutrim_agent_management` (backend/libs/krutrim_agent_management)

Package name: **`krutrim-agent-management`** (`backend/libs/krutrim_agent_management/pyproject.toml`). Depends only on [`krutrim_agent_utils`](krutrim_agent_utils.md) (the plug-in registry + atomic-write helpers) — otherwise the foundation package, no other internal workspace dependencies. Owns storage (`Storage` ABC + `LocalStorage`, selected pluggably via `storage_factory.py`), the shared `AppSettings` config singleton, the Pydantic domain models (`Project`, `Agent`, `Chat`, `SessionInfo`, `ContainerRecord`), and the `BlobStore` abstraction. Depended on by `krutrim_agent_sandbox`, `krutrim_agent_celery_core`, `krutrim_agent_extensions`, `krutrim_agents_core`, and `krutrim_agent_rag`.

> **Embedding-index I/O moved out.** The `VectorStore` ABC + `FaissliteVectorStore` (formerly this package's `embeddings.py`) and `vector_store_factory.py` now live in [`krutrim_agent_rag`](krutrim_agent_rag.md) — a clean cutover, no shim left behind here. See that doc for embedding-index I/O, chunking, retrieval, and the RAG tool/middleware.

**Backend selection is pluggable, the contracts aren't new.** `Storage` and `BlobStore` were already full ABCs with one implementation each; what's new is that *which implementation gets constructed* is no longer hardcoded — `storage_factory.create_storage(settings)` resolves a name (`settings.storage_backend`) against a `krutrim_agent_utils.PluginRegistry`, populated from a configurable list of dotted module paths (`settings.storage_backend_sources`) — same shape as `krutrim_agents_core.registry`'s profile discovery, and the same shape `krutrim_agent_rag.vector_store_factory.create_vector_store(...)` uses for `settings.vector_store_backend`/`vector_store_backend_sources`. A Postgres- or Qdrant-backed implementation registers itself under its own module and gets added to the relevant sources list, with zero edits to this package.

> **`ProviderStore` is NOT in this package.** It's defined in `backend/libs/krutrim_agents_core/src/krutrim_agents_core/providers/store.py` even though its on-disk path (`settings.provider_settings_path`) is exposed from this package's `AppSettings`. See [`libs/krutrim_agents_core.md`](krutrim_agents_core.md#4-providers--llm-provider-abstraction).

## Hierarchy: `Project -> (Agent | Chat) -> Session`

This replaced an earlier flat model (`Project` had a fixed `project_type`/`provider`/`model`, and `Session`s hung directly off it) so that one project can hold multiple, independently-typed units of work — e.g. a "Company Business Analysis" and a "Company Finance Analysis" agent (both `agent_key="research"`, different names/sessions/policy) plus an ad-hoc `Chat` for quick questions, all in one project.

```
Project                                   (top-level container)
 ├── Chat[]        (optional — project_id may be None, a standalone chat)
 │     └── Session[]
 └── Agent[]       (requires a project — a named instance of a registered profile)
       └── Session[]
```

- **`Project`** no longer carries `project_type`/`provider`/`model` — those live on its children now. It only carries the default sandbox policy its children inherit.
- **`Agent`** always belongs to exactly one project. `agent_key` is which registered profile it runs (`krutrim_agents_core.registry.get_profile`); multiple `Agent` rows can share the same `agent_key`. Moving an `Agent` between projects isn't supported yet.
- **`Chat`** is a lightweight, non-agentic chat container — `project_id` is nullable (a standalone chat behaves like the original plain-chat flow) and can be set/cleared later via `move_chat`.
- **`Session`** is the smallest unit and is keyed by `session_id` **alone** (globally unique) — not by a `(project_id, session_id)` pair, since a `Chat`'s sessions may have no project at all. `owner_type`/`owner_id` say which `Agent` or `Chat` it belongs to; `project_id` is denormalized onto it purely for convenience (cascade/filtering), not identity.

```
krutrim_agent_management/
├── base.py               Storage ABC — the storage-agnostic contract every caller uses
├── local.py                LocalStorage — the only implementation today, SQLite + flat files; self-registers "local"
├── storage_factory.py        create_storage(settings) — resolves settings.storage_backend against a PluginRegistry
├── models.py                   Project, Agent, Chat, SessionInfo, ContainerRecord, SharingScope, OwnerType
├── config.py                     AppSettings / settings singleton
├── blobstore.py                    BlobStore ABC + LocalBlobStore (atomic tmp-file writes, via krutrim_agent_utils)
└── paths.py                          default_storage_root() — ~/.krutrim_agent
```

A one-time migration script converts an old-shape `STORAGE_ROOT` to this one — see [§8](#8-migrating-an-existing-storage_root).

## 1. `Storage` ABC

[`base.py`](../../libs/krutrim_agent_management/src/krutrim_agent_management/base.py) — the storage-agnostic contract. Only `LocalStorage` implements it today; swapping in a remote-backed implementation later needs no caller changes — and, since `storage_factory.create_storage(settings)` is now how every caller (`krutrim_agent_backend`'s `bootstrap.py`, both `krutrim_agent_celery` tasks) constructs its `Storage` instance rather than calling `LocalStorage()` directly, that swap is a config change (`settings.storage_backend` + `storage_backend_sources`), not a code change in any of those callers.

| Group | Methods |
|---|---|
| Projects | `create_project(title, information="")`, `get_project(id)` (raises `KeyError`), `list_projects()`, `update_project(id, *, title=None, information=None)` (partial), `delete_project(id)` (cascades every `Agent`/`Chat`, and transitively their `Session`s, plus memory/cache) |
| Agents | `create_agent(project_id, agent_key, display_name)`, `get_agent(id)`, `list_agents(project_id)`, `update_agent(id, *, display_name=None)` (rename), `delete_agent(id)` (cascades its sessions), `update_agent_sandbox_policy(id, *, sharing=None, idle_timeout_seconds=None, resource_overrides=None)` |
| Chats | `create_chat(display_name, provider, model, project_id=None)`, `get_chat(id)`, `list_chats(project_id=None)` (`None` lists **standalone** chats, not "all"), `update_chat(id, *, display_name=None)`, `move_chat(id, *, project_id)` (sets or, passing `None`, clears the chat's project), `delete_chat(id)` (cascades its sessions), `update_chat_sandbox_policy(id, ...)` (stored regardless of `project_id`, only takes effect once one is set) |
| Sandbox policy (project default) | `update_project_sandbox_policy(id, *, sharing=None, idle_timeout_seconds=None, resource_overrides=None)` — **note**: no sentinel to explicitly reset a value back to "unset"/inherit-default once set — a known, tracked gap, not solved speculatively (see the hierarchy plan) |
| Agent memory | `read_memory(project_id) -> str` (`""` if none), `write_memory(project_id, content)` — `projects/{id}/MEMORY.md`, still project-scoped |
| Sessions | `create_session(owner_type, owner_id)` (raises `KeyError` if the owner is unknown; resolves `project_id` from the owner), `get_session(session_id)` (raises `KeyError`), `list_sessions(owner_type, owner_id)`, `update_session(id, *, display_name=None)` (rename), `delete_session(id)` |
| Checkpointer | `read_checkpoint(session_id) -> dict \| None`, `write_checkpoint(session_id, data)` — `sessions/{id}/checkpointer.json`, the plain-chat message history (distinct from LangGraph's own SQLite checkpoints) |
| Usage | `read_usage(session_id)`, `write_usage(session_id, data)` — `sessions/{id}/usage.json` |
| Cache | `cache_get(project_id, namespace, key) -> Any \| None`, `cache_set(...)` — generic MCP/RAG/tool-result caching, **still project-scoped** (unaffected by the hierarchy change) |
| Sandbox containers | `get_container(owner_id) -> ContainerRecord \| None`, `upsert_container(record)`, `list_containers(*, status=None)` (used by the idle reaper), `delete_container(owner_id)` — keyed by `owner_id` (usually a `session_id`), independent of the project/agent/chat hierarchy so the reaper can scan across all owners in one query |
| Workspace mirror | `read_workspace_files(session_id) -> list[str]`, `read_workspace_file(session_id, path) -> bytes \| None`, `sync_workspace_from_container(session_id, files)` — filesystem mirror of a container's `/workspace`, synced on teardown, read on hot-reload |

## 2. `LocalStorage`

[`local.py`](../../libs/krutrim_agent_management/src/krutrim_agent_management/local.py)

**On-disk layout**, under `STORAGE_ROOT` (default `~/.krutrim_agent`, override via `KRUTRIM_AGENT_STORAGE_ROOT`):

```
STORAGE_ROOT/
  project.db                                    -- one row per project
  agents.db                                      -- one row per agent instance (global table, always project-scoped)
  chats.db                                        -- one row per chat (global table, project_id nullable)
  sessions.db                                      -- one row per session (global table, owner_type/owner_id + denormalized project_id)
  containers.db                                     -- one row per sandbox container (any owner_kind) — global
  projects/{project_id}/
    MEMORY.md                                     -- still project-scoped
    cache/{namespace}/{sha256(key)}.json           -- still project-scoped
  sessions/{session_id}/                          -- NOTE: top-level, not nested under projects/{id}/ anymore
    checkpointer.json
    usage.json
    workspace/                                    -- mirror of the container's /workspace
    embeddings/                                    -- faisslite index (index.faiss/config.json/metadata.sqlite3)
```

`agents.db`/`chats.db`/`sessions.db` are **global tables**, not sharded per-project the way the old `session.db` was — the same reason `containers.db` already was global: a `Chat`'s sessions might have no project at all, so per-project sharding isn't always possible, and one global table lets the idle reaper and cross-owner lookups do a single scan. The tradeoff: all session writes now serialize through one lock instead of one-lock-per-project — the same tradeoff `project.db`/`containers.db` already made, acceptable for a local dev-scale backend.

**Two-layer design**: `_LocalStorageImpl` is fully synchronous; the public `LocalStorage` wraps it and dispatches every method via `asyncio.to_thread` — each call runs start-to-finish on one OS thread, so internal cross-calls (e.g. `delete_project` calling `self.list_agents`/`self.delete_agent`) stay self-contained.

**Locking / atomicity**: SQLite connections opened per call; writes serialized via a `threading.Lock` per DB file — one each for `project.db`, `agents.db`, `chats.db`, `sessions.db`, `containers.db`. All non-relational blobs go through `BlobStore.write`, which is atomic (tmp file + `Path.replace`). **Not safe across multiple processes** against the same `STORAGE_ROOT` — no cross-process locking.

**Cascade deletes**: `delete_project` iterates `list_agents`/`list_chats` for that project and calls `delete_agent`/`delete_chat` on each (which themselves cascade their sessions) before removing the project row and directory. `move_chat` also re-stamps `project_id` onto every session the chat already owns, so cascade/filtering stays correct without a join.

**Schemas** (core columns):

```sql
-- project.db
CREATE TABLE projects (
    project_id TEXT PRIMARY KEY, project_title TEXT NOT NULL,
    project_information TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    sandbox_sharing TEXT NOT NULL DEFAULT 'isolated',
    sandbox_idle_timeout_seconds INTEGER, sandbox_resource_overrides TEXT
);

-- agents.db (global)
CREATE TABLE agents (
    agent_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, agent_key TEXT NOT NULL,
    display_name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    sandbox_sharing TEXT, sandbox_idle_timeout_seconds INTEGER, sandbox_resource_overrides TEXT
);

-- chats.db (global)
CREATE TABLE chats (
    chat_id TEXT PRIMARY KEY, project_id TEXT,  -- nullable: standalone chat
    display_name TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    sandbox_sharing TEXT, sandbox_idle_timeout_seconds INTEGER, sandbox_resource_overrides TEXT
);

-- sessions.db (global)
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY, owner_type TEXT NOT NULL, owner_id TEXT NOT NULL,
    project_id TEXT,  -- denormalized, nullable
    display_name TEXT,  -- nullable: "unnamed", caller falls back to a positional label
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    sandbox_sharing TEXT NOT NULL DEFAULT 'isolated',
    attached_to_session_id TEXT, linked_session_ids TEXT NOT NULL DEFAULT '[]'
);

-- containers.db (global, unchanged shape except project_type dropped)
CREATE TABLE containers (
    owner_id TEXT PRIMARY KEY, owner_kind TEXT NOT NULL, project_id TEXT,
    container_name TEXT NOT NULL, docker_container_id TEXT, status TEXT NOT NULL,
    ref_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
    last_active_at TEXT NOT NULL, policy_snapshot TEXT
);
```

`upsert_container` uses `INSERT ... ON CONFLICT(owner_id) DO UPDATE SET ...` — a true upsert keyed on `owner_id`.

Note `agents.sandbox_sharing`/`chats.sandbox_sharing` are nullable with **no** `DEFAULT 'isolated'` — unlike `Project`/`Session`, `None` here means "inherit the project's default," a real, meaningful value distinct from `"isolated"`.

**Blob keys** (passed to `BlobStore`, not raw filesystem paths): `_memory_key(project_id)`, `_checkpoint_key(session_id)`, `_usage_key(session_id)`, `_cache_key(project_id, namespace, key)` (`sha256(key).hexdigest()`-named), `_workspace_prefix(session_id)`.

**`session_dir(session_id)`** — plain path helper, no I/O, exposed on the public `LocalStorage` too (single-argument now — session id alone is enough to locate it); used by callers needing the raw directory (e.g. embeddings dir composition, cross-agent checkpoint paths).

## 3. `models.py` — domain models

[`models.py`](../../libs/krutrim_agent_management/src/krutrim_agent_management/models.py)

`SharingScope = Literal["isolated", "session-shared", "project-shared"]` — **does not control container identity/merging** (that's `SessionInfo.attached_to_session_id`); it only controls whether the cross-agent `message_agent` tool is granted, and only ever between `Agent`-owned sessions (see [`krutrim_agents_core.md`](krutrim_agents_core.md#7-cross_agentpy--synchronous-agent-to-agent-messaging)). `"isolated"` (default) grants to nobody; `"session-shared"` grants between a session and its `linked_session_ids` peers (mutual); `"project-shared"` grants between every `Agent`-owned session in the same project.

`OwnerType = Literal["agent", "chat"]` — which entity a `SessionInfo` belongs to.

**`Project`**: `project_id`, `project_title`, `project_information=""`, `created_at`, `updated_at`, `sandbox_sharing: SharingScope = "isolated"` (default inherited by every `Agent`/`Chat` under it), `sandbox_idle_timeout_seconds: int | None`, `sandbox_resource_overrides: dict[str, int] | None` (human-set overrides — e.g. `memory_mb`, `nano_cpus`, `pids_limit`, `timeout_seconds` — set only via the Settings API, **never** by the agent/LLM).

**`Agent`**: `agent_id`, `project_id` (required), `agent_key` (which registered profile — determines prompts/tools/subagents), `display_name`, `created_at`, `updated_at`, `sandbox_sharing: SharingScope | None = None` (**`None` means "inherit the project's default"** — different default behavior than `Project`/`Session`), `sandbox_idle_timeout_seconds`, `sandbox_resource_overrides` (same override shape as `Project`).

**`Chat`**: `chat_id`, `project_id: str | None = None`, `display_name`, `provider`, `model`, `created_at`, `updated_at`, `sandbox_sharing`/`sandbox_idle_timeout_seconds`/`sandbox_resource_overrides` (same shape as `Agent` — only takes effect once `project_id` is set).

**`SessionInfo`**: `session_id`, `owner_type: OwnerType`, `owner_id` (an `Agent.agent_id` or `Chat.chat_id`), `project_id: str | None` (denormalized from the owner), `display_name: str | None = None` (user-set name; `None` = unnamed, caller shows a positional fallback), `created_at`, `updated_at`, `sandbox_sharing: SharingScope = "isolated"` (overrides the owner's default), `attached_to_session_id: str | None` (explicit ad-hoc container reuse — this session's sandbox *is* the target session's container, independent of `sandbox_sharing`), `linked_session_ids: list[str] = []` (peers reachable via `message_agent` when `sandbox_sharing == "session-shared"`; eligibility is symmetric).

**`ContainerRecord`** — one row per live-or-recently-live container, keyed by `owner_id`. Unchanged from before except `project_type` was **dropped** (it was only ever a snapshot for a "same type" eligibility check that no longer exists now that a project can hold multiple differently-typed `Agent`s — see [`krutrim_agents_core.md`](krutrim_agents_core.md#7-cross_agentpy--synchronous-agent-to-agent-messaging)):

| Field | Notes |
|---|---|
| `owner_id: str` | usually a session id |
| `owner_kind: Literal["session","project","channel"] = "session"` | `"project"` is reserved/unused; `"channel"` is for a future bot integration |
| `project_id: str \| None` | the container's owning project, if any (`None` for a project-less chat's session) |
| `container_name: str` | |
| `docker_container_id: str \| None` | |
| `status: Literal["starting","running","idle","tearing_down","stopped"] = "starting"` | see [`krutrim_agent_sandbox.md`](krutrim_agent_sandbox.md) for the full lifecycle |
| `ref_count: int = 0` | sessions currently attached; the reaper never tears down while `> 0` |
| `created_at`, `last_active_at: str` | `last_active_at` bumped on every successful `execute`/`upload_files`/`download_files` |
| `policy_snapshot: dict[str, int \| str] \| None` | the resolved `SandboxPolicy` the container started with |

## 4. `config.py` — `AppSettings`/`settings`

[`config.py`](../../libs/krutrim_agent_management/src/krutrim_agent_management/config.py) — unaffected by the hierarchy change.

`class AppSettings(BaseSettings)`, `env_prefix="KRUTRIM_AGENT_"`, `env_file=".env"`. `BACKEND_ROOT` is discovered by walking up from this module looking for a `harness/` directory (not a fixed `parents[N]` index). `.env` at `BACKEND_ROOT/.env` is loaded via `load_dotenv` so unprefixed vars (read via plain `os.getenv`) also land in the process env.

| Field | Default | Notes |
|---|---|---|
| `host` | `"0.0.0.0"` | |
| `port` | `8000` | |
| `harness_dir` | `BACKEND_ROOT / "harness"` | |
| `sandbox_image` | `"krutrim_agent-sandbox:latest"` | |
| `sandbox_runtime` | `"docker"` | resolved against a `PluginRegistry` discovered from `sandbox_runtime_sources` — see [`krutrim_agent_sandbox.md`](krutrim_agent_sandbox.md) |
| `sandbox_runtime_sources` | `["krutrim_agent_sandbox.docker_backend"]` | dotted modules, each directly imported |
| `storage_root` | `default_storage_root()` (`~/.krutrim_agent`) | |
| `storage_backend` / `storage_backend_sources` | `"local"` / `["krutrim_agent_management.local"]` | which `Storage` impl `storage_factory.create_storage()` builds |
| `vector_store_backend` / `vector_store_backend_sources` | `"faisslite"` / `["krutrim_agent_rag.embeddings"]` | same shape, for `VectorStore` — see [`krutrim_agent_rag.md`](krutrim_agent_rag.md) |
| `web_search_provider` | `"duckduckgo"` | resolved by `krutrim_agents_core`'s web-search tool registry — see [`krutrim_agents_core.md`](krutrim_agents_core.md) |
| `rag_embedding_model` | `"qwen/qwen3-embedding-8b"` | model id passed to `krutrim_agent_rag.embeddings_provider.default_embed` (OpenRouter) — see [`krutrim_agent_rag.md`](krutrim_agent_rag.md) |
| `edition` | `"community"` | read by `krutrim_agent_extensions.selfcheck` — not itself a feature gate |
| `extension_sources` | `[]` | dotted modules registering real security hooks — see [`krutrim_agent_extensions.md`](krutrim_agent_extensions.md) |
| `cors_origins` | `["http://localhost:4200", "http://localhost:5173", "http://localhost:4300"]` | |
| `redis_url` | built from `REDIS_URL` or `REDIS_USER`/`REDIS_PASSWORD`/`REDIS_HOST`/`REDIS_PORT`/`REDIS_DB`/`REDIS_USE_TLS` | Celery broker/result-backend, live-status pub/sub |
| `cross_agent_call_timeout_seconds` | `60` | distinct from `SandboxPolicy.timeout_seconds` (one shell command) |
| `dev_mode` | from `KRUTRIM_AGENT_DEV_MODE` or unprefixed `DEV_MODE` | gates Langfuse tracing |
| `langfuse_public_key` / `langfuse_secret_key` / `langfuse_host` | unprefixed `LANGFUSE_*` | `LANGFUSE_BASE_URL` takes priority over `LANGFUSE_HOST` |

Path helper properties/methods (derived from `harness_dir`/`memory_dir`, not settings themselves): `skills_dir`, `common_skills_dir`, `agent_skills_dir(agent_key)`, `prompts_dir(folder_name)` (**not** `agent_prompts_dir` — a pre-existing doc/test naming mismatch, fixed in `tests/test_agent_registry.py` during the RAG work), `memory_dir`, `agent_memory_dir(agent_key)`, `evals_dir`, `provider_settings_path` (→ `memory_dir/"settings.json"`, the `ProviderStore` file), `runs_dir` (→ `RunLogger`'s target directory, unused today — see [`krutrim_agents_core.md`](krutrim_agents_core.md#9-harness--promptskillmemory-loaders)).

Module-level singleton: `settings = AppSettings()`.

## 5. `blobstore.py`

`BlobStore(ABC)` — four methods: `read(key) -> bytes | None`, `write(key, data)` (must be atomic), `list(prefix) -> list[str]` (posix-relative), `delete(key)` (no-op if absent). `LocalBlobStore` is the only implementation: `write` uses tmp-file-then-`Path.replace` for atomicity; `list` does `base.rglob("*")` filtered to files, sorted. Every non-relational artifact `LocalStorage` owns (`MEMORY.md`, checkpoints, usage, cache, workspace mirror, embedding indexes) goes through this seam — a future `S3BlobStore` is a drop-in swap.

## 6. `paths.py`

`default_storage_root() -> Path` — `Path.home() / ".krutrim_agent"`, created if missing. Kept separate from `local.py` so `config.py` can import it without pulling in `sqlite3`/`json`.

## 7. Embedding-index I/O — relocated

`embeddings.py` (`VectorStore` ABC + `FaissliteVectorStore`) and `vector_store_factory.py` **no longer live in this package** — both moved to `krutrim_agent_rag`, a clean cutover with no shim left behind here. See [`krutrim_agent_rag.md`](krutrim_agent_rag.md) for embedding-index I/O, chunking, retrieval, and the RAG tool/middleware built on top of it.

## 8. Migrating an existing `STORAGE_ROOT`

If you have local data from before the `Project -> (Agent | Chat) -> Session` hierarchy (a `project.db` whose `projects` table still has `project_type`/`provider`/`model` columns), run the one-time migration script **with the backend and Celery worker both stopped**:

```bash
cd backend && uv run python scripts/migrate_storage_to_hierarchy.py [--storage-root PATH]
```

It wraps every existing project in a new `Chat` (if `project_type == "chat"`) or `Agent` (any other `project_type`, used as the new `agent_key`), moves each project's sessions (preserving `session_id`, so sandbox/checkpoint/usage/workspace references stay valid) from `projects/{project_id}/sessions/{id}/` to the new global `sessions/{id}/`, and rebuilds `project.db` without the dropped columns. Safe to re-run — it detects an already-migrated `project.db` and exits without touching anything. See [`scripts/migrate_storage_to_hierarchy.py`](../../scripts/migrate_storage_to_hierarchy.py)'s own docstring for the exact per-project logic.

## Dependencies

[`pyproject.toml`](../../libs/krutrim_agent_management/pyproject.toml) — package `krutrim-agent-management`: `pydantic`, `pydantic-settings`, `python-dotenv`, plus the internal workspace dep `krutrim-agent-utils` (the `PluginRegistry`/atomic-write helpers `storage_factory.py` and `blobstore.py` build on). **`faisslite` dropped** — it moved with `embeddings.py`/`vector_store_factory.py` to `krutrim_agent_rag` (see [§7](#7-embedding-index-io--relocated)).
