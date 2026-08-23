# `krutrim_agent_extensions` (backend/libs/krutrim_agent_extensions)

Package name: **`krutrim-agent-extensions`** (`backend/libs/krutrim_agent_extensions/pyproject.toml`). Security/governance extension points — request authentication, agent-profile visibility, audit logging — as a middleware + registry pair. Community ships all-no-op hooks (matching today's single-user, no-auth model exactly); an extended deployment registers real ones via `settings.extension_sources`, with **zero edits to this package or to `krutrim_agent_backend`'s routes**. This is the actual "middleware architecture" seam for a private repo to plug security behavior into this platform.

```
krutrim_agent_extensions/
├── contracts.py     Principal, AuditEvent + Protocol contracts + shipped NoOp implementations
├── registry.py        register_hook() / get_authenticator() / get_agent_visibility_policy() / get_audit_sink()
├── middleware.py         ExtensionMiddleware — resolves the active hooks for every request
└── selfcheck.py            run_startup_selfcheck() — fails CLOSED if extended edition ships with no real auth
```

## 1. `contracts.py`

[`contracts.py`](../../libs/krutrim_agent_extensions/src/krutrim_agent_extensions/contracts.py)

- **`Principal`** (frozen dataclass) — `id`, `display_name=""`, `metadata={}`. `ANONYMOUS_PRINCIPAL = Principal(id="anonymous", ...)` is the community default every request resolves to.
- **`AuditEvent`** (frozen dataclass) — `principal`, `method`, `path`, `status_code`.
- **`RequestAuthenticator`** (`Protocol`) — `async def authenticate(self, request: Request) -> Principal`.
- **`AgentVisibilityPolicy`** (`Protocol`) — `def visible_agent_keys(self, principal: Principal) -> set[str] | None`. `None` means "no restriction" — every registered agent profile is visible, the community default.
- **`AuditSink`** (`Protocol`) — `async def record(self, event: AuditEvent) -> None`.
- **`NoOpRequestAuthenticator`** / **`NoOpAgentVisibilityPolicy`** / **`NoOpAuditSink`** — the shipped defaults: every request is `ANONYMOUS_PRINCIPAL`, nothing is hidden, nothing is recorded. Together these reproduce today's community behavior exactly.

## 2. `registry.py`

[`registry.py`](../../libs/krutrim_agent_extensions/src/krutrim_agent_extensions/registry.py) — an `krutrim_agent_utils.PluginRegistry` **pre-seeded** with the three no-op defaults above (unlike `krutrim_agents_core.registry`'s profiles or `krutrim_agent_management`'s storage backends, where every key is registered exactly once, every hook name here already has a default — an extension source *replaces* it via `PluginRegistry.register(..., replace=True)`).

- **`register_hook(name, implementation)`** — called by an extension-source module at import time. `name` is one of `"RequestAuthenticator"`, `"AgentVisibilityPolicy"`, `"AuditSink"`.
- **`get_authenticator()`** / **`get_agent_visibility_policy()`** / **`get_audit_sink()`** — each calls `PluginRegistry.discover_modules(settings.extension_sources)` (default `[]` — community registers nothing extra) then returns the currently-registered implementation for that hook.
- **`all_hooks() -> dict[str, object]`** — every hook by name, used by `selfcheck.py` and `GET /api/system/extensions`.

## 3. `middleware.py` — `ExtensionMiddleware`

[`middleware.py`](../../libs/krutrim_agent_extensions/src/krutrim_agent_extensions/middleware.py) — a `starlette.middleware.base.BaseHTTPMiddleware`. Per request: resolves a `Principal` via `RequestAuthenticator.authenticate(request)` → `request.state.principal`; resolves `AgentVisibilityPolicy.visible_agent_keys(principal)` → `request.state.visible_agent_keys`; after the response, fires `AuditSink.record(AuditEvent(...))`. Community's all-no-op hooks make this a pure pass-through — every request gets `ANONYMOUS_PRINCIPAL`, `visible_agent_keys=None` (unfiltered), and the audit event is dropped. `krutrim_agent_backend`'s `agents_routes.py` (`GET /api/agents`) and `agent_run.py` (`POST /agents/{agent_id}`) read `request.state.visible_agent_keys` to filter/gate — see [`services/krutrim_agent_backend.md`](../services/krutrim_agent_backend.md).

## 4. `selfcheck.py` — the fail-closed startup check

[`selfcheck.py`](../../libs/krutrim_agent_extensions/src/krutrim_agent_extensions/selfcheck.py)

```python
def run_startup_selfcheck(settings: AppSettings) -> ExtensionStatus: ...
```

Logs which hooks are active (no-op vs real, by implementation class name) and returns an `ExtensionStatus(edition, hooks)`. **Raises `RuntimeError`** if `settings.edition == "extended"` and `RequestAuthenticator` is still `NoOpRequestAuthenticator` — you cannot accidentally ship an extended deployment with no real authentication in place. Called once, in `krutrim_agent_backend.main.create_app()`, **before** the `FastAPI(...)` instance is even constructed — a failure here means `app = create_app()` at module import time raises, and `uvicorn krutrim_agent_backend.main:app` never starts. Fails CLOSED, not open.

`GET /api/system/extensions` (`krutrim_agent_backend/api/system_routes.py`) reports the same hook status at runtime, without the raising check — a read-only status endpoint any external monitor (or a future frontend self-check) can poll to catch a hook silently reverting to its no-op default after a bad deploy/config change.

## Dependencies

[`pyproject.toml`](../../libs/krutrim_agent_extensions/pyproject.toml) — package `krutrim-agent-extensions`: `starlette` (for `Request`/`BaseHTTPMiddleware`/`Response` — not the full `fastapi`, since that's all this package actually needs), `loguru`, plus workspace `krutrim-agent-management` and `krutrim-agent-utils`.

Relevant tests: `backend/tests/test_extension_registry.py` (default-no-op behavior, override/replace semantics, both startup-selfcheck outcomes).
