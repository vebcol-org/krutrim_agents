# syntax=docker/dockerfile:1
# The agent-execution sandbox image.
#
#   base ─→ builder ─→ prod   (default)
#
# Two things run in a container from this image, depending on SandboxPolicy.run_mode:
#
#   run_mode="tool-backend" (default, legacy): the container is started with
#     `sleep infinity` and only the agent's execute/filesystem tool calls are
#     exec'd into it from the host. Needs just coreutils + pandas/numpy for the
#     sandboxed-data-analysis skill.
#
#   run_mode="in-sandbox": the container's own CMD starts the krutrim_agent_grpc
#     AgentRuntime server on a bind-mounted Unix socket, and the WHOLE agent
#     graph runs inside here. Still network_disabled — every LLM call and
#     host-side tool goes back out over the HostBridge socket. Needs the full
#     agent runtime (krutrim-agent-grpc + transitive: krutrim-agents, langgraph,
#     deepagents, …).
#
# Build context is backend/ (the uv workspace root):
#   docker build -f docker/sandbox.Dockerfile -t krutrim_agent-sandbox:latest backend

# ── base ───────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# git: `uv sync` clones faisslite / promptstore (git deps of krutrim-agent-rag
# and krutrim-agents). The runtime never needs it — prod starts from a clean
# python image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git coreutils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /usr/local/bin/

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

# Manifests only first so a source-only edit doesn't cache-bust the slow
# dependency layer.
COPY pyproject.toml uv.lock ./
COPY libs/krutrim_agent_agui/pyproject.toml libs/krutrim_agent_agui/
COPY libs/krutrim_agent_celery_core/pyproject.toml libs/krutrim_agent_celery_core/
COPY libs/krutrim_agent_doc/pyproject.toml libs/krutrim_agent_doc/
COPY libs/krutrim_agent_extensions/pyproject.toml libs/krutrim_agent_extensions/
COPY libs/krutrim_agent_grpc/pyproject.toml libs/krutrim_agent_grpc/
COPY libs/krutrim_agent_management/pyproject.toml libs/krutrim_agent_management/
COPY libs/krutrim_agent_rag/pyproject.toml libs/krutrim_agent_rag/
COPY libs/krutrim_agent_sandbox/pyproject.toml libs/krutrim_agent_sandbox/
COPY libs/krutrim_agent_utils/pyproject.toml libs/krutrim_agent_utils/
COPY libs/krutrim_agents_core/pyproject.toml libs/krutrim_agents_core/
COPY libs/krutrim_agents/pyproject.toml libs/krutrim_agents/
COPY services/krutrim_agent_backend/pyproject.toml services/krutrim_agent_backend/
COPY services/krutrim_agent_celery/pyproject.toml services/krutrim_agent_celery/

# Third-party deps only, scoped to the sandbox runtime package. --no-editable so
# the venv is self-contained and can be copied into the clean prod stage.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --no-install-workspace --package krutrim-agent-grpc

COPY . .

# Build/link the local workspace packages against the real source, plus the two
# libraries the sandboxed-data-analysis skill expects on PATH.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package krutrim-agent-grpc \
    && uv pip install --python /opt/venv/bin/python pandas numpy


# ── prod ───────────────────────────────────────────────────────────────────
# Clean base: no uv, no git, no build caches. Non-root, read-only rootfs at
# runtime (enforced by DockerSandboxBackend, not here).
FROM python:3.11-slim AS prod

RUN apt-get update \
    && apt-get install -y --no-install-recommends coreutils \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin sandbox \
    && mkdir -p /workspace /run/krutrim_agent \
    && chown sandbox:sandbox /workspace /run/krutrim_agent

COPY --from=builder --chown=sandbox:sandbox /opt/venv /opt/venv

# KRUTRIM_AGENT_RUNTIME_IN_SANDBOX flips krutrim_agents_core's provider registry
# + tool shim to their proxy variants (calls home over HostBridge instead of
# reaching the network directly). Harmless in tool-backend mode, where the
# gRPC server is never started.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    KRUTRIM_AGENT_RUNTIME_IN_SANDBOX=1

USER sandbox
WORKDIR /workspace
STOPSIGNAL SIGINT

# The server binds 0.0.0.0:50051 and reads its endpoints from
# /run/krutrim_agent/run.json. --health-check dials 127.0.0.1:50051 and calls
# Health; only meaningful in run_mode="in-sandbox".
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-m", "krutrim_agent_grpc.server", "--health-check"]

CMD ["python", "-m", "krutrim_agent_grpc.server"]
