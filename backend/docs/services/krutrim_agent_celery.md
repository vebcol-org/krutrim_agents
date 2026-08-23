# `krutrim_agent_celery` (backend/services/krutrim_agent_celery)

Package name: **`krutrim-agent-celery`** (`backend/services/krutrim_agent_celery/pyproject.toml`). The Celery worker/beat process. Depends on `krutrim-agent-management` + `krutrim-agent-sandbox` + [`krutrim-agent-celery-core`](../libs/krutrim_agent_celery_core.md) + [`krutrim-agent-rag`](../libs/krutrim_agent_rag.md) **only** — deliberately **not** on `krutrim-agents` or `krutrim-agent-backend`, so the worker never pulls in the full deepagents/LangGraph agent-graph stack just to reap containers or embed text. `krutrim_agent_rag` itself only depends on `krutrim_agent_management` (see that doc), preserving this boundary — though it does bring in `langchain-openai` (for OpenRouter embeddings, see [§4](#4-tasksprecompute_embeddingspy)), a change from when this worker used `langchain-ollama` and no LLM-adjacent package at all. Run via `uv run celery -A krutrim_agent_celery.app worker --beat --loglevel=info` from `backend/`.

**No chat message ever touches Celery.** It runs two background jobs, fully decoupled from the request path — see [`docs/app-flow.md`](../../../docs/app-flow.md) for how this fits into the overall request flow. The app works fine without Redis/Celery running; you just lose automatic sandbox teardown.

```
krutrim_agent_celery/
├── app.py               Celery app instance via krutrim_agent_celery_core.build_celery_app(), beat schedule, task registration
├── config.py              celery_settings — KRUTRIM_AGENT_CELERY_-prefixed env vars
└── tasks/
    ├── reap_idle_containers.py    beat-scheduled — tears down idle sandbox containers
    ├── precompute_embeddings.py     on-demand — chunks + embeds workspace files
    └── process_rag_document.py        on-demand — chunks + embeds a single user-submitted RAG document
```

## Decoupling from `krutrim_agent_backend`

`krutrim_agent_backend` and `krutrim_agent_celery` never import each other. `krutrim_agent_backend`'s [`celery_client.py`](krutrim_agent_backend.md#4-celery_clientpy) is a minimal `Celery(...)` instance pointed at the same Redis URL, used only to `send_task("krutrim_agent_celery.<task_name>", args=[...])` by the task's registered name string — it never imports `krutrim_agent_celery`'s code, so the FastAPI process doesn't pay for `docker`/`numpy`/`langchain_openai` just to enqueue a job. Conversely `krutrim_agent_celery` never imports `krutrim-agents` (the LangGraph/deepagents LLM stack) — it only needs `krutrim-agent-sandbox` (to reconstruct a `DockerSandboxBackend` for teardown), `krutrim-agent-management` (`Storage`, config), and `krutrim-agent-rag` (chunking/embedding for its two ingestion tasks).

## 1. `app.py`

```python
celery_app = build_celery_app(
    "krutrim_agent_celery",
    beat_schedule={
        "reap-idle-containers": {
            "task": "krutrim_agent_celery.reap_idle_containers",
            "schedule": celery_settings.beat_interval_seconds,
        },
    },
)

from krutrim_agent_celery.tasks import reap_idle_containers as _reap_idle_containers
from krutrim_agent_celery.tasks import precompute_embeddings as _precompute_embeddings
from krutrim_agent_celery.tasks import process_rag_document as _process_rag_document
```

`build_celery_app` (`krutrim_agent_celery_core.factory` — see [`libs/krutrim_agent_celery_core.md`](../libs/krutrim_agent_celery_core.md)) does the generic `Celery(name, broker=settings.redis_url, backend=settings.redis_url)` + `conf.timezone`/`conf.beat_schedule` wiring, shared with any other Celery service in this workspace; this module supplies its own name, beat schedule, and task list — the community-specific part. Both broker and result-backend point at Redis — the only pub/sub-style implementation in this codebase today. Only `reap_idle_containers` is on the beat schedule; `precompute_embeddings` is dispatched on-demand from `krutrim_agent_backend`, never scheduled.

The two task-module imports **must stay after** `celery_app = build_celery_app(...)` — they're side-effect-only (registering the `@celery_app.task`-decorated functions against this app instance), and each task module does `from krutrim_agent_celery.app import celery_app`, which only resolves once that assignment has completed (a circular import otherwise — see `krutrim_agent_celery_core.factory`'s docstring for why `build_celery_app` deliberately doesn't import task modules itself).

`--beat` runs the scheduler in the same process as the worker — fine for a single-node dev/deploy; a future RabbitMQ migration only means changing `redis_url`'s scheme/host here (and separately swapping `krutrim_agent_sandbox.status_channel`'s implementation), neither touches task code.

## 2. `config.py` — `celery_settings`

`class CelerySettings(BaseSettings)`, **`env_prefix="KRUTRIM_AGENT_CELERY_"`** — deliberately a *different* prefix than the shared `KRUTRIM_AGENT_` used by `krutrim_agent_management.config.AppSettings`, anticipating this service's eventual extraction into its own deployable package.

| Field | Env var | Default | Meaning |
|---|---|---|---|
| `idle_timeout_seconds` | `KRUTRIM_AGENT_CELERY_IDLE_TIMEOUT_SECONDS` | `600` | default staleness threshold before an unreferenced container is torn down; overridden per-project by `project.sandbox_idle_timeout_seconds` when set |
| `beat_interval_seconds` | `KRUTRIM_AGENT_CELERY_BEAT_INTERVAL_SECONDS` | `60` | how often beat fires the reaper task — a distinct concept from `idle_timeout_seconds` |

## 3. `tasks/reap_idle_containers.py`

[`reap_idle_containers.py`](../../services/krutrim_agent_celery/src/krutrim_agent_celery/tasks/reap_idle_containers.py) — the background half of sandbox lifecycle management. Entirely separate from the request path: `SandboxRegistry.get_or_create`/`release` only ever adjust `ref_count`/`last_active_at`/`status`; **this task is the only thing that actually removes a container** for being idle.

- **`_LIST_WORKSPACE_FILES_CMD`** — a `python3 -c "..."` one-liner that `os.walk`s `/workspace` inside the container, printing one absolute path per line. Plain Python rather than `find`, since the sandbox image guarantees Python but not `findutils`.
- **`_download_workspace_files(backend)`**: runs the listing command; `exit_code != 0` → `[]` (best-effort, never crashes the reaper); strips to workspace-relative paths; calls `backend.download_files(...)`, filters out any per-file errors. **Known limitation**: the listing output is subject to the sandbox policy's `max_output_bytes` truncation — a very large workspace could silently be cut off.
- **`_publish_safe(pubsub, owner_id, status)`** — swallows all exceptions; a Redis hiccup must never fail a real teardown.
- **`_resolve_idle_timeout(store, record, default_timeout)`** — `record.project_id is None` → `default_timeout`; otherwise fetches the project and returns `project.sandbox_idle_timeout_seconds` if set, else `default_timeout`.
- **`reap_idle_containers_once(store, *, idle_timeout_seconds, backend_factory=create_sandbox_backend, pubsub=None) -> dict`** — the testable core (all deps injectable):
  1. Iterates **every** record from `store.list_containers()` — no status filter (a stuck `"tearing_down"` from a crashed prior run gets retried too).
  2. Skips `owner_kind == "channel"` unconditionally (static, future bot integrations, never reaped).
  3. Skips `ref_count > 0` (actively attached — never torn down mid-use).
  4. Skips if `(now - last_active_at).total_seconds() < effective_timeout`.
  5. Otherwise reaps: marks `status="tearing_down"`, publishes it, reconstructs the container's `SandboxPolicy` from `record.policy_snapshot` (or default), builds a fresh backend via `backend_factory`.
     - `try`: downloads workspace files; if any, `store.sync_workspace_from_container(record.owner_id, files)` — **the "persist workspace before teardown" step** (session-id-only call now — `sync_workspace_from_container` no longer needs `project_id` since sessions are keyed globally, see [`libs/krutrim_agent_management.md`](../libs/krutrim_agent_management.md#1-storage-abc)). (Note: an explicitly-attached session sharing this container isn't synced into its own separate mirror here — a documented gap, since `owner_id` for the kinds this reaper handles is always a session id.)
     - Calls `backend.close()`.
     - `finally`: `store.delete_container(record.owner_id)` + publish `"stopped"` — **teardown happens even if the download/sync step raised**.
  6. Returns `{"reaped": [owner_id, ...]}`.
- **`reap_idle_containers()`** — the `@celery_app.task(name="krutrim_agent_celery.reap_idle_containers")` wrapper: `asyncio.run(reap_idle_containers_once(create_storage(settings), idle_timeout_seconds=celery_settings.idle_timeout_seconds, pubsub=RedisPubSubBackend(settings.redis_url)))`.

See [`libs/krutrim_agent_sandbox.md`](../libs/krutrim_agent_sandbox.md#container-lifecycle-end-to-end) for how this fits the full container status lifecycle.

## 4. `tasks/precompute_embeddings.py`

[`precompute_embeddings.py`](../../services/krutrim_agent_celery/src/krutrim_agent_celery/tasks/precompute_embeddings.py) — chunks a session's source files, embeds them, adds vectors to that session's `faisslite` index, giving RAG-style recall for documents too large to paste into a prompt.

**Trigger**: `POST /api/sessions/{session_id}/embed` (see [`services/krutrim_agent_backend.md`](krutrim_agent_backend.md#sessions_routespy--apisessions-session_id-scoped)) — never scheduled.

- `chunk_text`/`CHUNK_SIZE`/`CHUNK_OVERLAP` **moved** to [`krutrim_agent_rag.chunking`](../libs/krutrim_agent_rag.md#chunkingpy) — this module re-exports all three (`from krutrim_agent_celery.tasks.precompute_embeddings import chunk_text` still works) purely for backward-compat import; the real definition, and the one `process_rag_document.py` (below) also uses, lives in `krutrim_agent_rag`.
- **`_default_embed(texts)`** — **switched from local Ollama to OpenRouter**: was `langchain_ollama.OllamaEmbeddings(model="nomic-embed-text")` (no API key needed), now `krutrim_agent_rag.embeddings_provider.default_embed` (OpenRouter via `langchain_openai.OpenAIEmbeddings`). **Behavior change**: `/embed` now requires `OPENROUTER_API_KEY` where it previously needed no key at all. Reason: one session's FAISS index must use one consistent embedding model regardless of which ingestion path wrote to it — see [`krutrim_agent_rag.md`](../libs/krutrim_agent_rag.md#embeddings_providerpy) for the full "why not Ollama" rationale, which applies equally to `process_rag_document.py`'s embedder.
- **`precompute_embeddings_once(store, *, session_id, source_paths, embed_fn=_default_embed, on_progress=None) -> dict`** — testable core (no `project_id` param — sessions are keyed globally now):
  - For each `path` in `source_paths`: reads from the session's **persisted workspace mirror** (`store.read_workspace_file(session_id, path)`, not a live container); missing content is skipped, not an error; chunks the text (tolerating non-UTF-8 bytes via `errors="replace"` — arbitrary workspace files aren't guaranteed clean text); embeds; on first successful embedding batch, opens (or creates) the index via `open_index(embeddings_dir, dim=vectors.shape[1])` where `embeddings_dir = store.session_dir(session_id) / "embeddings"`; `index.add(vectors, source=path, texts=chunks)`.
  - Calls `on_progress(processed, total)` after every file, regardless of whether it had content.
  - `index.save()` if anything was added.
  - Returns `{"files_processed": total, "chunks_added": chunks_added}`.
- **`precompute_embeddings(session_id, source_paths)`** — the `@celery_app.task(name="krutrim_agent_celery.precompute_embeddings")` wrapper: `job_id = f"{session_id}:embed"` (dropped the old `project_id` prefix — session ids are globally unique, so no qualifier is needed; matches what the `/embed` route constructs independently, so the caller can subscribe to `GET /api/status/jobs/{job_id}` without round-tripping Celery's result backend); `on_progress` publishes via `publish_job_progress` (best-effort, swallows exceptions); assumes one embed job per session at a time is sufficient for this first pass.

## 5. `tasks/process_rag_document.py`

[`process_rag_document.py`](../../services/krutrim_agent_celery/src/krutrim_agent_celery/tasks/process_rag_document.py) — ingests a single document a user submitted via pasted text or a client-side-read `.txt` file (see [`services/krutrim_agent_backend.md`](krutrim_agent_backend.md#sessions_routespy--apisessions-session_id-scoped)'s `POST /{session_id}/rag/text`) into that session's faisslite index. Same testable-core-plus-thin-wrapper shape as `precompute_embeddings.py`, sharing its chunker and embedder (both from `krutrim_agent_rag`) but reporting **stage-level** progress instead of a bare processed/total count, since one document's ingestion doesn't have a natural "N of M" unit the way precompute's multi-file loop does.

**Trigger**: `POST /api/sessions/{session_id}/rag/text` — never scheduled.

- Stages: `extracting` → `chunking` → `embedding` → `indexing`, each reported via **`publish_job_stage_progress`** — a new function in `krutrim_agent_sandbox/status_channel.py`, sibling to the existing `publish_job_progress`, adding a `stage` field alongside `processed`/`total`. Publishes to the same `JOB_STATUS_CHANNEL`/job_id shape — **no new SSE route needed**, `GET /api/status/jobs/{id}` already forwards whatever JSON is published verbatim.
- **v1 rejects non-UTF-8 content as an error result** (`{"status": "error", "error": "..."}`) rather than tolerating it via `errors="replace"` like `precompute_embeddings_once` does — a document a user explicitly submitted through the text-ingestion flow should always decode cleanly, so a decode failure signals something genuinely wrong, not an arbitrary-file edge case.
- **`process_rag_document_once(store, *, session_id, document_id, source_path, title=None, embed_fn=default_embed, on_progress=None) -> dict`** — testable core: reads `source_path` from the session's workspace mirror (written by the route just before dispatch), decodes strictly as UTF-8, chunks, embeds, opens/creates the index the same way `precompute_embeddings_once` does, adds the vectors, saves. Returns `{"status": "ok", "document_id", "title", "chunks_added"}` on success (`title` defaults to `document_id` if the route didn't supply one), or `{"status": "error", "error": "..."}` if the source content is missing or not valid UTF-8.
- **`process_rag_document(session_id, document_id, source_path, title=None)`** — the `@celery_app.task(name="krutrim_agent_celery.process_rag_document")` wrapper: `job_id = f"{session_id}:rag:{document_id}"` — **per-document**, unlike `/embed`'s single per-session job id, since a session can ingest multiple RAG documents over time; `on_progress` publishes via `publish_job_stage_progress` (best-effort, swallows exceptions).

## Dependencies

[`pyproject.toml`](../../services/krutrim_agent_celery/pyproject.toml) — package `krutrim-agent-celery`: `celery[redis]`, `deepagents` (for the `BaseSandbox` type used when reconstructing a backend for teardown), `numpy`, plus workspace `krutrim-agent-management`, `krutrim-agent-sandbox`, `krutrim-agent-celery-core`, and **`krutrim-agent-rag`** (chunking + the OpenRouter embedder shared by both ingestion tasks). **`langchain-ollama` dropped** — no ingestion path uses local Ollama anymore. **No `krutrim-agents` or `krutrim-agent-backend` dependency** — `krutrim_agent_rag` only depends on `krutrim_agent_management`, so this boundary is preserved even with the new RAG-library dependency. No `[project.scripts]` entry — run via the `celery` CLI directly, not a custom entrypoint.

Relevant tests: `backend/tests/test_reaper.py`, `test_precompute_embeddings.py`, `test_embeddings.py`, `test_process_rag_document.py`.
