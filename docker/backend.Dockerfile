# syntax=docker/dockerfile:1
# services/krutrim_agent_backend — the FastAPI app.
#
# Talks to the *host* Docker engine via /var/run/docker.sock (mounted in
# docker-compose.yml) to create/tear down krutrim-agent-sandbox-* containers as
# siblings on the same engine — not nested Docker-in-Docker. See
# ../docker/README.md for the full picture.
#
# Build context is backend/ (the uv workspace root):
#   docker build --secret id=github_token,src=docker/.secrets/github_token \
#     -f docker/backend.Dockerfile -t krutrim_agent-backend backend
#
# The secret is a GitHub token with read access to the private faisslite
# repo (a transitive dependency via krutrim-agent-management) — mounted only for
# the one `uv sync` layer below, never written into any image layer or
# baked into git config that persists. See ../docker/README.md for setup.

FROM python:3.11-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /usr/local/bin/

WORKDIR /app
COPY . .

# --no-dev drops the workspace's pytest/dev tooling and the sibling
# krutrim-agent-celery package (deepagents, numpy, langchain-ollama, ...) that
# krutrim-agent-backend doesn't need at runtime — see ../docker/README.md.
RUN --mount=type=secret,id=github_token,required=true \
    git config --global credential.helper \
      '!f() { echo "username=x-access-token"; echo "password=$(cat /run/secrets/github_token)"; }; f' \
    && uv sync --frozen --no-dev --package krutrim-agent-backend \
    && git config --global --unset credential.helper

FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "krutrim_agent_backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
