# syntax=docker/dockerfile:1
# services/krutrim_agent_celery — the Celery worker/beat process (idle-container
# reaper + embeddings precompute). Same sibling-container relationship to
# the host Docker engine as backend.Dockerfile: it tears down
# krutrim-agent-sandbox-* containers via the mounted /var/run/docker.sock.
#
# Build context is backend/ (the uv workspace root):
#   docker build --secret id=github_token,src=docker/.secrets/github_token \
#     -f docker/celery.Dockerfile -t krutrim_agent-celery backend
#
# The secret is a GitHub token with read access to the private faisslite
# repo — mounted only for the one `uv sync` layer below, never written into
# any image layer. See ../docker/README.md for setup.

FROM python:3.11-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /usr/local/bin/

WORKDIR /app
COPY . .

# --no-dev drops pytest/dev tooling and the sibling krutrim-agent-backend package
# (fastapi, uvicorn, ...) that the worker doesn't need at runtime.
RUN --mount=type=secret,id=github_token,required=true \
    git config --global credential.helper \
      '!f() { echo "username=x-access-token"; echo "password=$(cat /run/secrets/github_token)"; }; f' \
    && uv sync --frozen --no-dev --package krutrim-agent-celery \
    && git config --global --unset credential.helper

FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"

# --beat runs the scheduler in the same process — fine for a single-node
# deployment (see krutrim_agent_celery/app.py's docstring). Split into a separate
# `celery ... beat` container later only if you need to scale workers
# independently of the schedule.
CMD ["celery", "-A", "krutrim_agent_celery.app", "worker", "--beat", "--loglevel=info"]
