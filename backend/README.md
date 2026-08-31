# Backend

FastAPI + LangGraph/deepagents backend for the agent platform. A `uv` workspace (not a single package): shared libraries under `libs/`, deployable services under `services/`, plus `harness/` (content data) and `tests/`.

## Directory structure

```
backend/
├── pyproject.toml            # uv workspace root — members: libs/*, services/*
├── uv.lock
├── .env                        # symlink -> ../.env (one shared file, see repo root)
│
├── libs/                       # importable libraries (no entrypoints of their own)
│   ├── krutrim_agent_management/       # storage, provider config, embeddings, blobstore
│   │   └── src/krutrim_agent_management/
│   ├── krutrim_agent_sandbox/           # session-scoped filesystem sandbox registry + job-status channel
│   │   └── src/krutrim_agent_sandbox/
│   └── krutrim_agents/                  # agent profile content (research/experiment)
│       └── src/krutrim_agents/
│
├── services/                   # deployable processes
│   ├── krutrim_agent_backend/           # the FastAPI app
│   │   └── src/krutrim_agent_backend/
│   │       ├── main.py          # entrypoint: `uv run uvicorn krutrim_agent_backend.main:app`
│   │       ├── api/              # routes (agents, chat, projects, sessions, settings, status, health)
│   │       ├── chat/
│   │       └── celery_client.py # enqueues tasks owned by krutrim_agent_celery
│   └── krutrim_agent_celery/             # Celery worker process
│       └── src/krutrim_agent_celery/
│           ├── app.py            # Celery app instance
│           └── tasks/            # process_rag_document, precompute_embeddings
│
├── harness/                    # content data, checked into the repo
│   ├── prompts/<agent_key>/     # system prompts per agent/role
│   ├── skills/<agent_key>/      # Claude-Code-style SKILL.md files
│   ├── memory/<agent_key>/      # durable per-agent memory (AGENTS.md)
│   ├── memory/settings.json     # per-(agent_key, role) provider config, gitignored
│   ├── memory/runs/<agent_key>/ # gitignored JSONL run transcripts
│   └── evals/                   # standalone eval runner + datasets
│
└── tests/                      # pytest suite, spans all workspace packages
```

## Prerequisites

- Python via [uv](https://docs.astral.sh/uv/) (`brew install uv`) — uv manages its own Python 3.11

## Setup

```bash
cd backend
uv sync
```

Env vars live in one shared file at the repo root (`cp .env.example .env` from there, then fill in `OPENROUTER_API_KEY`) — `backend/.env` is a committed symlink pointing at it, so `uv run`/pydantic-settings pick it up with no extra setup.

## Running it

### 1. FastAPI backend

```bash
cd backend
uv run uvicorn krutrim_agent_backend.main:app --reload --port 8000
```

### 2. Redis (required for Celery)

Celery's broker/result-backend. Only needed for RAG document ingestion / embedding precompute.

```bash
docker compose -f ../docker/docker-compose.yml up redis
```

### 3. Celery worker

Run on the host (not containerized), pointed at the Redis instance above:

```bash
cd backend
uv run celery -A krutrim_agent_celery.app worker --loglevel=info
```

The app runs fine without Redis/Celery — you just lose background RAG ingestion.


## Testing

```bash
cd backend
uv run pytest
```

## Key env vars (see the repo root's `.env.example`)

- `OPENROUTER_API_KEY` — required for the OpenRouter provider
- `KRUTRIM_AGENT_HOST` / `KRUTRIM_AGENT_PORT` — FastAPI bind address (default `0.0.0.0:8000`)
- `KRUTRIM_AGENT_REDIS_URL` — Celery broker/result-backend (default `redis://localhost:6379/0`)
- `KRUTRIM_AGENT_EVAL_RECORD_FULL_PAYLOADS` — capture full tool args + result previews in the per-run JSONL transcript
- `KRUTRIM_AGENT_DEV_MODE` / `DEV_MODE` — gates local-only tooling (Langfuse tracing)
