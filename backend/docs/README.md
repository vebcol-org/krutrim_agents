# Backend developer docs

Deep-dive, per-package documentation for the `backend/` uv workspace. For setup/run commands see [`backend/README.md`](../README.md); for the end-to-end request trace see [`docs/app-flow.md`](../../docs/app-flow.md). This tree exists so a developer can open one file and get everything they need to know about a specific package, instead of re-deriving it from source.

> Keep these in sync: whenever you change a file in one of the packages below, update its doc in the same change. See [`AGENTS.md`](../../AGENTS.md#after-making-a-code-change).

## Workspace layout

`backend/` is a [uv workspace](https://docs.astral.sh/uv/concepts/projects/workspaces/) (`backend/pyproject.toml`, `members = ["libs/*", "services/*"]`), not one package — ten independently-versioned packages sharing one venv:

```
backend/
├── libs/                     importable libraries, no entrypoints of their own
│   ├── krutrim_agent_utils/           plug-in registry + atomic-write helpers, zero deps → docs: libs/krutrim_agent_utils.md
│   ├── krutrim_agent_management/       storage, config, models, embeddings I/O (pluggable) → docs: libs/krutrim_agent_management.md
│   ├── krutrim_agent_sandbox/           Docker sandbox backend, policy, registry (pluggable runtime) → docs: libs/krutrim_agent_sandbox.md
│   ├── krutrim_agents_core/              discovery, graph builder, providers, tools → docs: libs/krutrim_agents_core.md
│   ├── krutrim_agents/            profile content (research/trading/sales)   → docs: libs/krutrim_agents.md
│   ├── krutrim_agent_celery_core/          reusable Celery app construction          → docs: libs/krutrim_agent_celery_core.md
│   └── krutrim_agent_extensions/            security-hook middleware + registry       → docs: libs/krutrim_agent_extensions.md
├── services/                 deployable processes
│   ├── krutrim_agent_backend/         the FastAPI app                          → docs: services/krutrim_agent_backend.md
│   └── krutrim_agent_celery/          Celery worker/beat process                → docs: services/krutrim_agent_celery.md
├── harness/                  content data (prompts/skills/memory), not code
└── tests/                    pytest suite spanning all ten packages
```

## Package dependency graph

```
krutrim_agent_utils        (NO internal deps at all — the actual foundation: PluginRegistry, atomic-write helpers)
      ▲
      │
krutrim_agent_management     (depends on krutrim_agent_utils — Storage/BlobStore/VectorStore ABCs + pluggable-backend factories)
      ▲
      │
krutrim_agent_sandbox          (depends on krutrim_agent_management + krutrim_agent_utils — pluggable sandbox-runtime factory)
      ▲                │
      │                ├──────────────────────┬───────────────────────┐
krutrim_agents_core             krutrim_agent_celery_core       krutrim_agent_extensions        │
(+ krutrim_agent_sandbox,       (Celery app factory,    (security-hook          │
 krutrim_agent_utils —          depends on              middleware/registry,    │
 discovery, builder,    krutrim_agent_management +      depends on              │
 providers, tools)      krutrim_agent_utils only)       krutrim_agent_management +      │
      ▲                       ▲                 krutrim_agent_utils)            │
      │                       │                       ▲                 │
krutrim_agents              krutrim_agent_celery                  │                 │
(profile content,       (community's own              │                 │
 depends on              two tasks, depends            │                 │
 krutrim_agents_core only)       on krutrim_agent_celery_core)          │                 │
      ▲                                                  │                 │
      └──────────────────────────────────────────────────┴─────────────────┘
                                    │
                              krutrim_agent_backend
                    (the FastAPI app — depends on krutrim_agents_core,
                     krutrim_agents, krutrim_agent_extensions, krutrim_agent_management,
                     krutrim_agent_sandbox)
```

`krutrim_agent_backend` and `krutrim_agent_celery` talk to each other only through Redis (`krutrim_agent_backend`'s [`celery_client.py`](../services/krutrim_agent_backend/src/krutrim_agent_backend/celery_client.py) enqueues tasks by registered name string, never importing `krutrim_agent_celery`'s code) — see [`services/krutrim_agent_celery.md`](services/krutrim_agent_celery.md#decoupling-from-krutrim_agent_backend).

## The recurring shape: pluggable-by-config, not pluggable-by-code-edit

Four different things in this workspace are selected via a settings field naming a key, resolved against an `krutrim_agent_utils.PluginRegistry` populated from a configurable list of dotted module paths — the same pattern applied four times, not four different mechanisms:

| What | Selector setting | Sources setting | Default |
|---|---|---|---|
| Agent profile content | (all discovered, no single "active" one) | `agent_profile_sources` | `["krutrim_agents.profiles"]` |
| Storage backend | `storage_backend` | `storage_backend_sources` | `"local"` / `["krutrim_agent_management.local"]` |
| Vector-store backend | `vector_store_backend` | `vector_store_backend_sources` | `"faisslite"` / `["krutrim_agent_management.embeddings"]` |
| Sandbox runtime | `sandbox_runtime` | `sandbox_runtime_sources` | `"docker"` / `["krutrim_agent_sandbox.docker_backend"]` |
| Security-extension hooks | (all three hook slots, pre-seeded with no-ops) | `extension_sources` | `[]` |

A private deployment extends any of these by shipping its own module (registering itself under a new key, or — for extension hooks — replacing a no-op default) and adding it to the relevant `*_sources` list. **No package in this list is ever edited to support that.**

## One thing every package shares: `krutrim_agent_management.config.settings`

A single `AppSettings` singleton (env prefix `KRUTRIM_AGENT_`, `.env` at the repo root via symlinks) supplies every filesystem path (harness dirs, storage root), the Redis URL, sandbox image/runtime, cross-agent call timeout, and every `*_backend`/`*_sources` pair from the table above. See [`libs/krutrim_agent_management.md`](libs/krutrim_agent_management.md#4-configpy--appsettingssettings) for the full field list. `krutrim_agent_celery` additionally has its own `celery_settings` under a **different** prefix (`KRUTRIM_AGENT_CELERY_`) — see [`services/krutrim_agent_celery.md`](services/krutrim_agent_celery.md#2-configpy--celery_settings).

## Docs index

| Doc | Covers |
|---|---|
| [`libs/krutrim_agent_utils.md`](libs/krutrim_agent_utils.md) | `PluginRegistry[T]` (keyed registry + dotted-module discovery, `discover_packages`/`discover_modules`), `atomic_write_bytes`/`atomic_write_json` |
| [`libs/krutrim_agent_management.md`](libs/krutrim_agent_management.md) | `Storage`/`BlobStore`/`VectorStore` ABCs + `LocalStorage`/`LocalBlobStore`/`FaissliteVectorStore`, pluggable-backend factories, on-disk layout, Pydantic models, `AppSettings` |
| [`libs/krutrim_agent_sandbox.md`](libs/krutrim_agent_sandbox.md) | `DockerSandboxBackend`, `SandboxPolicy`, `SandboxRegistry`, pluggable sandbox-runtime factory, Redis status pub/sub, sandbox exceptions |
| [`libs/krutrim_agents_core.md`](libs/krutrim_agents_core.md) | Profile discovery (`registry.py`, configurable `agent_profile_sources`), `build_agent()`, providers (OpenRouter/Ollama), `ProviderStore`, tools (`web_search`/`fetch_url`), the frontend-tool bridge middleware, cross-agent messaging, harness loaders |
| [`libs/krutrim_agents.md`](libs/krutrim_agents.md) | Agent profile content only (research/trading/sales/experiment) — prompts, roles, tool wiring per agent type |
| [`libs/krutrim_agent_celery_core.md`](libs/krutrim_agent_celery_core.md) | `build_celery_app()` — reusable broker/backend/timezone/beat-schedule wiring |
| [`libs/krutrim_agent_extensions.md`](libs/krutrim_agent_extensions.md) | Security-hook contracts (`RequestAuthenticator`/`AgentVisibilityPolicy`/`AuditSink`), `ExtensionMiddleware`, the fail-closed startup self-check |
| [`services/krutrim_agent_backend.md`](services/krutrim_agent_backend.md) | FastAPI app startup (`main.py` + `bootstrap.py`), every API route, the plain-`chat` graph, logging, error handling |
| [`services/krutrim_agent_celery.md`](services/krutrim_agent_celery.md) | Celery app/config, the idle-container reaper task, the embedding precompute task |
