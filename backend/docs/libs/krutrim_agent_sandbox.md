# `krutrim_agent_sandbox` (backend/libs/krutrim_agent_sandbox)

Package name: **`krutrim-agent-sandbox`** (`backend/libs/krutrim_agent_sandbox/pyproject.toml`). The Docker sandbox: `DockerSandboxBackend`, `SandboxPolicy`, `SandboxRegistry`, and Redis-backed live status pub/sub. Depends on `krutrim-agent-management` (`Storage`/config types) and [`krutrim_agent_utils`](krutrim_agent_utils.md) (the `PluginRegistry` backing `factory.py`'s runtime selection). For the *why* behind these design decisions (one container per session by default, explicit attach, the reattach-by-name bug, etc.) see `.architecture/sandbox-design.md` (tracked design notes — per `AGENTS.md`'s edit policy, only update on explicit user request).

```
krutrim_agent_sandbox/
├── docker_backend.py    DockerSandboxBackend — execute/upload_files/download_files/id; self-registers "docker"
├── factory.py             create_sandbox_backend() — registry-based runtime selection ("docker" today)
├── policy.py               SandboxPolicy — fixed, server-side resource/security limits
├── registry.py              SandboxRegistry — owner-scoped get_or_create/release, hot-reload
├── status_channel.py         Redis pub/sub for live container/job status
└── exceptions.py               SandboxError, SandboxStartError
```

## 1. `DockerSandboxBackend`

[`docker_backend.py`](../../libs/krutrim_agent_sandbox/src/krutrim_agent_sandbox/docker_backend.py) — subclasses deepagents' `BaseSandbox`. Only `execute`, `upload_files`, `download_files`, `id` are implemented; `ls`/`read_file`/`write_file`/`edit_file`/`grep`/`glob` are **derived** by `BaseSandbox` from those four — no separate code path per filesystem tool that could diverge from "runs inside the container." One container is started lazily per instance and kept running for the process lifetime (not per call), keyed by `owner_id`.

**Constructor**: `__init__(policy: SandboxPolicy | None = None, owner_id: str | None = None, client: docker.DockerClient | None = None)`.

**`id`** → `f"docker-{owner_id}"`. **`last_active_at`** → monotonic timestamp of the last successful `execute()`, what the reaper reads for staleness. **`touch()`** resets it.

**`hydrate(files)`** — ensures a container is running then re-uploads a previously-persisted workspace via `upload_files`. Idempotent. Called by `SandboxRegistry.get_or_create` to resume a session whose container was reaped.

**`_reattach_or_remove_stale(name)`** — looks up an existing Docker container already named `name` (from a different process, or this process after losing track of it): if found and `status == "running"`, returns it for reuse; if found but not running (a stale leftover from a crash that never called `close()`), force-removes it so the name can be reclaimed; if not found, returns `None`.

**`_ensure_container()`** (locked):
1. If already tracked and reloadable as `"running"`, return immediately.
2. Compute `container_name = f"krutrim_agent-sandbox-{owner_id}"`.
3. Try `_reattach_or_remove_stale` first.
4. Otherwise `containers.run(...)` with:
   - `command=["sleep", "infinity"]`, `detach=True`, `name=container_name`
   - `network_disabled=(policy.network == "none")`
   - `mem_limit=f"{memory_mb}m"`, `nano_cpus`, `pids_limit`
   - `read_only=True` — immutable rootfs
   - `tmpfs={"/tmp": f"size={tmp_tmpfs_mb}m,uid=1000,gid=1000,mode=1777", "/workspace": f"size={workspace_tmpfs_mb}m,uid=1000,gid=1000,mode=1777"}` — **explicit `uid=1000,gid=1000,mode=1777`** is required: Docker defaults tmpfs mounts to root ownership, and the container runs as non-root `sandbox` (uid 1000), so without this the non-root user can't write to its own working directory.
   - `working_dir="/workspace"`, `user="sandbox"`, `cap_drop=["ALL"]`, `security_opt=["no-new-privileges"]`, `auto_remove=False`
5. Any failure → `SandboxStartError`, chained from the original exception.

**`execute(command, *, timeout=None)`**:
- Wraps: `timeout -k 2 {effective_timeout} sh -c {shlex.quote(command)}` — SIGKILL 2s after SIGTERM for a command ignoring the first signal.
- Runs via `container.exec_run(["/bin/sh", "-lc", wrapped], workdir="/workspace")`.
- Any exception from `exec_run` → returned as `ExecuteResponse(output="Error executing command in sandbox: ...", exit_code=1)`, never raised — tool-visible, doesn't crash the graph.
- On success, calls `touch()` — **resets the idle clock regardless of the command's own exit code** (a timeout is still "activity").
- Truncates output past `policy.max_output_bytes`, appending `"[Output truncated by sandbox policy.]"`.
- Exit code `124` (the `timeout` coreutil's own signal) gets a `"Error: command timed out after {N}s.\n"` prefix so the agent sees *why* it failed, not a bare exit code.

**`upload_files(files: list[tuple[str, bytes]])`** / **`download_files(paths)`** — base64-over-`execute()` pipe, **not** Docker's native `put_archive`/`get_archive`: Docker refuses `put_archive` on a container with `read_only=True`, even targeting a writable tmpfs mount — the check happens at the container level before Docker looks at what's mounted where. Upload: `mkdir -p {parent} && printf '%s' {b64} | base64 -d > {path}`. Download: `base64 {path}`, decoded client-side. Both are **partial-success** — one file's failure returns an error for that file only, doesn't abort the batch. Upload's parent-dir computation explicitly checks for `"/" in path` rather than relying on `rsplit`'s no-separator behavior — a bare filename like `"result.txt"` (the common shape once hot-reload started passing workspace-mirror-relative keys) has no parent, and `path.rsplit("/", 1)[0]` on a no-separator string returns the whole string, not `""`, so a plain `or "/"` fallback wouldn't catch it.

**`close()`** — force-removes the tracked container (best-effort), clears the reference. Called on app/session shutdown.

## 2. `factory.py`

`create_sandbox_backend(owner_id, policy=None, *, client=None, runtime=None) -> BaseSandbox` — the single place deciding which sandbox runtime backs a given `owner_id`. `SandboxRegistry` always calls this instead of constructing `DockerSandboxBackend` directly. `effective_runtime = runtime or settings.sandbox_runtime`, resolved against an `krutrim_agent_utils.PluginRegistry` discovered from `settings.sandbox_runtime_sources` (default `["krutrim_agent_sandbox.docker_backend"]`, whose import self-registers `"docker"` via `register_sandbox_runtime("docker", ...)`). A future runtime (Podman, Firecracker, a remote sandbox API) registers itself under its own module and gets added to that sources list — **no edit to this file**, same plug-in shape as `krutrim_agents_core.registry`'s profile discovery. `client` (a `docker.DockerClient` override, test-injection plumbing) is Docker-specific and handled as a special case here rather than forcing every future runtime's registered factory to accept a Docker-shaped param; every registered runtime factory otherwise has the uniform signature `(owner_id, policy) -> BaseSandbox`. Only `"docker"` is implemented today; an unregistered runtime name raises `KeyError` (from the registry), not `ValueError`.

## 3. `SandboxPolicy`

[`policy.py`](../../libs/krutrim_agent_sandbox/src/krutrim_agent_sandbox/policy.py) — fixed, server-side, constructed once from app config and handed to `DockerSandboxBackend`; **never** built from model/tool-call input, since the `execute` tool only ever exposes a `command: str` — there's no code path for the agent to loosen any of this.

| Field | Default | Meaning |
|---|---|---|
| `image` | `"krutrim_agent-sandbox:latest"` | |
| `timeout_seconds` | `30` | hard wall-clock limit per `execute()` call |
| `memory_mb` | `512` | |
| `nano_cpus` | `1_000_000_000` (1 core) | |
| `pids_limit` | `128` | |
| `network` | `"none"` (only value) | no egress at all in v1 |
| `workspace_tmpfs_mb` | `256` | in-memory `/workspace`, no host bind mount |
| `tmp_tmpfs_mb` | `64` | |
| `max_output_bytes` | `200_000` | per-command output cap, excess truncated not dropped |

A human operator *can* loosen this per-project via `Project.sandbox_resource_overrides` (Settings API, `PUT /api/projects/{id}/sandbox-policy`) — a different, legitimate control plane from "the agent can never loosen its own policy." `policy_factory` resolves `SandboxPolicy` per-owner at container-creation time (not a single fixed instance built once at startup), so overrides take effect without a backend restart.

## 4. `SandboxRegistry`

[`registry.py`](../../libs/krutrim_agent_sandbox/src/krutrim_agent_sandbox/registry.py) — the **one** entry point anything (the AG-UI agent-run path, cross-agent messaging) calls before touching a sandbox. Nothing else should construct a sandbox backend directly.

```python
class SandboxRegistry:
    def __init__(
        self,
        store: Storage,
        policy_factory=None,
        backend_factory=None,
        pubsub: PubSubBackend | None = None,
    ): ...
    async def resolve_owner_id(self, session_id: str) -> tuple[str, str]: ...
    async def get_or_create(self, session_id: str) -> AttachHandle: ...
    async def release(self, owner_id: str) -> None: ...
    def local_backend(self, owner_id: str) -> BaseSandbox | None: ...
    def close_all(self) -> None: ...
```

Takes a bare `session_id`, not a `(project_id, session_id)` pair — sessions are keyed globally now (`Storage.get_session(session_id)`, see [`krutrim_agent_management.md`](krutrim_agent_management.md#1-storage-abc)), so a session id alone is enough to look one up regardless of whether its owner is an `Agent` or a project-less `Chat`.

- **`resolve_owner_id`**: (1) if `SessionInfo.attached_to_session_id` is set, this session's sandbox actions resolve to that *other* session's container — literally the same container, same filesystem, concurrent `execute()` calls included (safe — `container.exec_run()` is an independent per-call request the Docker daemon serializes/interleaves at the OS-process level; `DockerSandboxBackend`'s own lock only ever guards `_ensure_container()`, never `execute()` itself). (2) Otherwise the session is its own owner — isolated, the default. **`sandbox_sharing` never affects which container a session's `execute()` hits** — it only gates the cross-agent `message_agent` tool (see [`krutrim_agents_core.md`](krutrim_agents_core.md#7-cross_agentpy--synchronous-agent-to-agent-messaging)). Sharing does not mean merging.

  Invariants enforced at the route layer (not here): no self-attach, no chained attaches (a session can't attach to a session that's itself attached to something), a session can't become an attach target while others already depend on it.

- **`get_or_create(session_id)`**:
  1. Resolve `owner_id`/`owner_kind`.
  2. If a `ContainerRecord` exists and `status != "stopped"`: reattach the in-process backend if this process doesn't have it cached (process may have restarted while the container kept running), increment `ref_count`, set `status="running"`, bump `last_active_at`, publish status, return.
  3. Otherwise (missing or `status == "stopped"`) — **hot-reload**: publish `"starting"`, build a fresh backend via the factory, pull the session's persisted workspace mirror (`store.read_workspace_files`/`read_workspace_file`, both `session_id`-only now), `backend.hydrate(files)`, write a new `ContainerRecord` (`ref_count=1`, `project_id` taken from the resolved owner session — may be `None` for a project-less chat), publish `"running"`.
  4. Returns `AttachHandle(backend, owner_id)`.
- **`release(owner_id)`**: decrements `ref_count` (floored at 0); when it hits exactly 0, sets `status="idle"` — this is what makes `"idle"` a real, meaningfully-assigned state (it existed in the type early on but was dead before this). Always called in the request handler's `finally`, even on error.
- **`close_all()`**: best-effort teardown of every backend this process started, called on app shutdown — not the reaper's job, just "don't leak running containers on exit."

**Concurrency note**: `ContainerRecord.ref_count` (incremented on `get_or_create`, decremented on `release`) exists specifically so the idle reaper never tears down a container that's genuinely in use, regardless of how idle it looks by `last_active_at` alone.

**What's deliberately not solved**: two sessions attached to the same container concurrently writing the *same file path* race exactly like two shells in one box — last write wins. Coordinate via distinct subdirectories.

## 5. `status_channel.py` — live status pub/sub

[`status_channel.py`](../../libs/krutrim_agent_sandbox/src/krutrim_agent_sandbox/status_channel.py)

- Channels: `CONTAINER_STATUS_CHANNEL = "sandbox:container:{owner_id}"`, `JOB_STATUS_CHANNEL = "sandbox:job:{job_id}"`.
- `PubSubBackend(ABC)` — one method, `publish(channel, message)`. `RedisPubSubBackend` is the only implementation (`redis.Redis.from_url(...).publish(...)`) — a single synchronous fire-and-forget command, not a long-lived loop. Kept behind an ABC specifically so a future broker swap doesn't touch any publish call site.
- `publish_container_status(pubsub, owner_id, status, **extra)` — JSON `{"status": ..., **extra}` on the container channel. Called from `SandboxRegistry._publish` at `"starting"`, `"running"` (with `ref_count`), and whatever status `release()` sets (typically `"idle"`).
- `publish_job_progress(pubsub, job_id, processed, total)` — JSON `{"processed", "total"}` on the job channel, used by `krutrim_agent_celery`'s `precompute_embeddings` task.
- `publish_job_stage_progress(pubsub, job_id, stage, processed, total)` — sibling to `publish_job_progress`, adding a `stage` field (JSON `{"stage", "processed", "total"}`) for multi-stage jobs that don't have a natural "N of M" unit; used by `krutrim_agent_celery`'s `process_rag_document` task (`extracting`/`chunking`/`embedding`/`indexing`). Publishes to the same `JOB_STATUS_CHANNEL`/job_id — no separate SSE route needed, since `GET /api/status/jobs/{id}` forwards whatever JSON shape is published verbatim.
- Every publish call site is wrapped to swallow its own exceptions — a Redis hiccup must never fail a real sandbox or reap operation.
- The **subscribing** side (`krutrim_agent_backend`'s `GET /api/status/containers/{owner_id}` / `/api/status/jobs/{job_id}` SSE routes) uses `redis.asyncio` directly rather than this ABC, since subscribing is a genuinely long-lived async operation — a different shape than a single `publish()` call. See [`services/krutrim_agent_backend.md`](../services/krutrim_agent_backend.md#status_routespy).

## 6. `exceptions.py`

Two classes, both trivial (docstring-only): `SandboxError(Exception)` (base class), `SandboxStartError(SandboxError)` (raised in `_ensure_container()` when `containers.run(...)` fails for any reason — image pull failure, daemon unreachable, resource limits rejected, name collision, etc. — chained via `from exc`). `factory.py`'s unknown-runtime case raises a plain `KeyError` (from the `PluginRegistry` lookup), not a custom sandbox exception.

## Container lifecycle, end to end

```
"starting" → "running" → "idle" → "tearing_down" → "stopped"
```

- `SandboxRegistry.get_or_create`/`release` only ever adjust `ref_count`/`last_active_at`/`status` — they never actually remove a container.
- `krutrim_agent_celery`'s `reap_idle_containers` beat task is the **only** thing that removes a container for being idle: it downloads `/workspace` and persists it to the session's storage mirror *before* teardown, so a later `get_or_create` for the same owner hot-reloads transparently. See [`services/krutrim_agent_celery.md`](../services/krutrim_agent_celery.md#3-tasksreap_idle_containerspy).
- A record stuck at `"tearing_down"` from a crashed prior reaper run gets retried on the next pass — the reaper's scan doesn't filter by status at all, only by `ref_count`/idle-time.

## Dependencies

[`pyproject.toml`](../../libs/krutrim_agent_sandbox/pyproject.toml) — package `krutrim-agent-sandbox`: `deepagents` (for `BaseSandbox`/`ExecuteResponse`/`FileUploadResponse`/`FileDownloadResponse`), `docker` (docker-py SDK), `pydantic`, `redis`, plus internal workspace deps `krutrim-agent-management` and `krutrim-agent-utils`.

Relevant tests: `backend/tests/test_sandbox.py`, `test_sandbox_registry.py`, `test_sandbox_policy_routes.py`, `test_reaper.py`, `test_status_channel.py`, `test_container_attach.py`, `test_hot_reload.py`.
