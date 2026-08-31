# syntax=docker/dockerfile:1
# services/krutrim_agent_celery — the Celery worker (RAG document ingestion +
# embeddings precompute).
#
#   base ─→ builder ─┬─→ dev    developer loop: source bind-mounted, a tuned
#                    │          watchfiles reloader wraps the worker
#                    └─→ prod   safety first: fresh base, non-root, immutable
#                               ← default
#
# ─────────────────────────────────────────────────────────────────────────────
#  TORCH_BACKEND = cpu | gpu   (build arg — applies to BOTH dev and prod)
# ─────────────────────────────────────────────────────────────────────────────
#   Selects the PyTorch wheel index krutrim-agent-doc (docling OCR/layout)
#   resolves from. Unlike backend, this Dockerfile ALWAYS forwards the value
#   (`--extra cpu` / `--extra gpu`) because krutrim-agent-doc needs the index
#   pinned even for cpu.
#   cpu  (default)  torch/torchvision CPU wheels (~5GB of nvidia-* libs
#                   skipped) + faiss-cpu.
#   gpu             CUDA torch wheels + faiss-gpu-cu12 (via krutrim-agent-rag[gpu]).
#                   CUDA linux/amd64 host only; compose needs a device
#                   reservation (see docker-compose*.yml).
#
#     docker build -f docker/celery.Dockerfile --target prod \
#       --build-arg TORCH_BACKEND=gpu -t krutrim_agent-celery backend
#
# ─────────────────────────────────────────────────────────────────────────────
#  Vector store = faisslite | qdrant   (NOT a build-time choice — runtime
#  VECTOR_STORE_BACKEND + COMPOSE_PROFILES=qdrant; see backend.Dockerfile)
# ─────────────────────────────────────────────────────────────────────────────
#
# Build context is backend/ (the uv workspace root).

ARG TORCH_BACKEND=cpu


# ── base ───────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# git: `uv sync` clones faisslite. Runtime doesn't need it — hence `prod`
# starts from a clean python image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /usr/local/bin/

# See backend.Dockerfile for why the venv lives outside /app.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app


# ── builder ────────────────────────────────────────────────────────────────
FROM base AS builder
ARG TORCH_BACKEND

# Manifests only first — keep the slow dependency layer cache-stable.
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

# Third-party deps only. Scoped to --package so `--extra` resolves exactly
# krutrim-agent-celery's closure for the chosen wheel index.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package krutrim-agent-celery --extra ${TORCH_BACKEND}

COPY . .

# Fast: only builds/links the local workspace packages against real source.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package krutrim-agent-celery --extra ${TORCH_BACKEND}


# ── dev ────────────────────────────────────────────────────────────────────
# Source is bind-mounted by docker-compose.dev.yml → no rebuild on a code edit.
#
# Celery has no built-in reloader and a full worker restart is expensive here
# (torch/docling import on boot). So this is NOT a naive "restart on every
# save": watchfiles' default 1.6s debounce coalesces a burst of writes, the
# watched paths are scoped to the worker's OWN packages (a krutrim_agent_backend
# edit never bounces it), --sigint-timeout lets a running task finish its warm
# shutdown before SIGKILL, --grace-period skips the slow first boot, and
# --concurrency=1 keeps each restart cheap.
#
# Still too disruptive? Override `command:` in docker-compose.dev.yml with the
# plain worker and restart it by hand when you change task code.
FROM builder AS dev
ARG TORCH_BACKEND

# Re-sync WITH the dev group, plus watchfiles — celery's closure doesn't
# include it (backend gets it transitively via uvicorn[standard]).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --package krutrim-agent-celery --extra ${TORCH_BACKEND} \
    && uv pip install watchfiles

# WATCHFILES_FORCE_POLLING is set from the compose env on macOS/Windows.
CMD ["watchfiles", "--target-type", "command", "--filter", "python", \
     "--sigint-timeout", "30", "--grace-period", "10", \
     "celery -A krutrim_agent_celery.app worker --beat --loglevel=info --concurrency=1", \
     "/app/services/krutrim_agent_celery", "/app/libs"]


# ── prod ───────────────────────────────────────────────────────────────────
# Safety first: clean base, non-root, immutable.
FROM python:3.11-slim AS prod

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# See backend.Dockerfile: image runs as this unprivileged user.
RUN groupadd --system app \
    && useradd --system --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app
COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /app /app
USER app

STOPSIGNAL SIGTERM

# `celery inspect ping` round-trips through the broker to this worker — real
# liveness, not just "process exists". Long start-period for the torch/docling
# first import.
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s --retries=3 \
    CMD ["celery", "-A", "krutrim_agent_celery.app", "inspect", "ping", "-t", "8"]

# --beat runs the scheduler in-process — fine for a single-node deployment
# (see krutrim_agent_celery/app.py). Split into a separate `celery ... beat`
# container only when scaling workers independently of the schedule.
CMD ["celery", "-A", "krutrim_agent_celery.app", "worker", "--beat", "--loglevel=info"]
