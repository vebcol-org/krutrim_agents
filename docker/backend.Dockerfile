# syntax=docker/dockerfile:1
# services/krutrim_agent_backend — the FastAPI app.
#
#   base ─→ builder ─┬─→ dev    developer loop: source is bind-mounted, uvicorn
#                    │          --reload restarts on save, NO image rebuild
#                    └─→ prod   safety first: fresh base, non-root, immutable,
#                               only the resolved venv + app source  ← default
#
# ─────────────────────────────────────────────────────────────────────────────
#  TORCH_BACKEND = cpu | gpu   (build arg — applies to BOTH dev and prod,
#                               since each is FROM builder which reads it)
# ─────────────────────────────────────────────────────────────────────────────
#   cpu  (default)  faiss-cpu only (already bundled with faisslite).
#   gpu             also faiss-gpu-cu12, via faisslite[gpu]
#                   (krutrim-agents[gpu] → krutrim-agent-rag[gpu]).
#                   Only meaningful on a CUDA linux/amd64 host, and compose
#                   still needs a device reservation — see the commented
#                   `deploy:` block in docker-compose*.yml.
#
#     # one-off
#     docker build -f docker/backend.Dockerfile --target prod \
#       --build-arg TORCH_BACKEND=gpu -t krutrim_agent-backend backend
#     # via compose: set TORCH_BACKEND=gpu in .env (dev: .env.dev)
#
# ─────────────────────────────────────────────────────────────────────────────
#  Vector store = faisslite | qdrant   (NOT a build-time choice)
# ─────────────────────────────────────────────────────────────────────────────
#   Both `faisslite` and `qdrant-client` are unconditional deps of
#   krutrim-agent-rag, so every image can talk to either. Pick at RUNTIME with
#   VECTOR_STORE_BACKEND, and bring the qdrant service up with
#   COMPOSE_PROFILES=qdrant. No rebuild to switch.
#
# Build context is backend/ (the uv workspace root).

ARG TORCH_BACKEND=cpu


# ── base ───────────────────────────────────────────────────────────────────
# python + uv + git + shared env. Never run directly.
FROM python:3.11-slim AS base

# git: `uv sync` clones faisslite (git+https dependency of krutrim-agent-rag).
# The runtime never needs it — that's why `prod` starts from a clean python
# image rather than this one.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /usr/local/bin/

# UV_PROJECT_ENVIRONMENT pins the venv OUTSIDE /app, so docker-compose.dev.yml
# can bind-mount host source over /app without burying the installed packages
# (and without exposing the host's own ./.venv). compile-bytecode trades a
# little build time for faster cold starts; link-mode=copy silences the
# hardlink warning across the cache mount; python-downloads=never keeps uv on
# the image's own interpreter.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app


# ── builder ────────────────────────────────────────────────────────────────
# The full dependency install into /opt/venv. The slow layer is cached on the
# manifests alone — a source-only edit never re-runs it.
FROM base AS builder
ARG TORCH_BACKEND

# Manifests only first: `COPY . .` before `uv sync` would cache-bust the
# dependency layer on every source edit.
COPY pyproject.toml uv.lock ./
COPY libs/krutrim_agent_celery_core/pyproject.toml libs/krutrim_agent_celery_core/
COPY libs/krutrim_agent_doc/pyproject.toml libs/krutrim_agent_doc/
COPY libs/krutrim_agent_extensions/pyproject.toml libs/krutrim_agent_extensions/
COPY libs/krutrim_agent_management/pyproject.toml libs/krutrim_agent_management/
COPY libs/krutrim_agent_rag/pyproject.toml libs/krutrim_agent_rag/
COPY libs/krutrim_agent_sandbox/pyproject.toml libs/krutrim_agent_sandbox/
COPY libs/krutrim_agent_utils/pyproject.toml libs/krutrim_agent_utils/
COPY libs/krutrim_agents_core/pyproject.toml libs/krutrim_agents_core/
COPY libs/krutrim_agents/pyproject.toml libs/krutrim_agents/
COPY services/krutrim_agent_backend/pyproject.toml services/krutrim_agent_backend/
COPY services/krutrim_agent_celery/pyproject.toml services/krutrim_agent_celery/

# Third-party deps only (the slow part: langchain/langgraph/faiss/…). Scoped
# to --package so `--extra gpu` can't leak into unrelated workspace members
# (e.g. krutrim-agent-doc's cu124 torch, which has no linux/arm64 wheels).
# krutrim-agent-backend has no "cpu" extra — faiss-cpu is already the default —
# so gpu is the only value that adds a flag.
RUN --mount=type=cache,target=/root/.cache/uv \
    EXTRA=$([ "$TORCH_BACKEND" = "gpu" ] && echo "--extra gpu" || true); \
    uv sync --frozen --no-dev --no-install-workspace --package krutrim-agent-backend $EXTRA

COPY . .

# Fast: third-party deps are already in place, this only builds/links the
# local workspace packages against the real source.
RUN --mount=type=cache,target=/root/.cache/uv \
    EXTRA=$([ "$TORCH_BACKEND" = "gpu" ] && echo "--extra gpu" || true); \
    uv sync --frozen --no-dev --package krutrim-agent-backend $EXTRA


# ── dev ────────────────────────────────────────────────────────────────────
# A real dev server. docker-compose.dev.yml bind-mounts ../backend:/app, so a
# host edit IS the same file in the container — uvicorn --reload (watchfiles,
# from uvicorn[standard]) re-spawns the app process on save. Nothing here is
# baked for keeps; only a pyproject.toml / uv.lock change needs `--build`.
FROM builder AS dev
ARG TORCH_BACKEND

# Re-sync WITH the dev group (pytest, httpx, …) so the suite / a REPL can run
# against live code inside the container.
RUN --mount=type=cache,target=/root/.cache/uv \
    EXTRA=$([ "$TORCH_BACKEND" = "gpu" ] && echo "--extra gpu" || true); \
    uv sync --frozen --package krutrim-agent-backend $EXTRA

EXPOSE 8000

# --reload-dir is scoped to the code trees, NOT /app: the app writes run
# transcripts under /app/harness/memory at runtime, and watching that would
# cause a reload loop. WATCHFILES_FORCE_POLLING is set from the compose env on
# macOS/Windows, where bind-mount inotify events don't cross the Docker VM.
CMD ["uvicorn", "krutrim_agent_backend.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--reload", "--reload-dir", "/app/services", "--reload-dir", "/app/libs"]


# ── prod ───────────────────────────────────────────────────────────────────
# Safety first: clean base (no uv, no git, no build caches, no compilers),
# non-root, immutable — no source is mounted in, a code change means a rebuild.
FROM python:3.11-slim AS prod

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Unprivileged runtime user — the image runs as it in every stack.
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /app /app
USER app

EXPOSE 8000
STOPSIGNAL SIGINT

# stdlib only, so the runtime image needs nothing extra installed. Hits the
# real router (krutrim_agent_backend/api/health.py → GET /api/health).
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"]

CMD ["uvicorn", "krutrim_agent_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
