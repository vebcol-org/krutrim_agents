# Krutrim Agent

A pluggable, multi-agent-type platform. A LangGraph + [deepagents](https://docs.langchain.com/oss/python/deepagents/overview) backend (Python) hosts independent agent **profiles** — this build's is `research` — and streams to a pure-React frontend (web + Tauri desktop) over the AG-UI protocol via `@ag-ui/client`'s `HttpAgent`, with no runtime process in between. Chat sits in a left pane; the agent's finished deliverable renders in a right-hand canvas. `?agent=<key>` in the URL picks the agent.

## Core / plugin split

The one load-bearing design decision. **Core** is never touched to add an agent: the FastAPI app, the provider system, the sandbox registry, the harness loaders, `krutrim_agents_core`'s `registry.py` (auto-discovery) and `builder.py` (generic graph assembly), `libs/ui`, and the `agent-ui` frame (`components/{shell,thread,panels,sheets}/`, `api/`, `hooks/`, `store/`).

**Adding an agent type** touches only:

- **Backend** — one folder `backend/libs/krutrim_agents/src/krutrim_agents/profiles/<key>/` declaring an `AgentProfile` (prompts, tools, subagents, default models) that self-registers, plus its `harness/{prompts,skills,memory}/<key>/` content. Zero edits to existing files — `registry.py` scans each configured profile package's filesystem path at import.
- **Frontend** — optional: one folder `libs/agent-ui/src/screens/<key>/` exporting an `AgentScreenModule` plus one line in `screens/registry.ts`. Omit it and the `default` screen (shared thread + built-in markdown/chart renderer) is used.

## Features

### Research agent

`main` orchestrator + `researcher` / `critic` / `writer` subagents, each independently model-configurable.

| Feature | Status | Notes |
| --- | --- | --- |
| Web research | Completed | `web_search` (Tavily) + `web_fetch` |
| RAG over session documents | Completed | `rag_tool`, per-session vector store |
| RAG silent-injection mode | Completed | Off by default |
| Subagent delegation | Completed | `researcher` / `critic` / `writer` |
| Filesystem workspace | Completed | `ls` / `read` / `write` / `edit` / `glob` / `grep` |
| Live scratchpad + per-turn dynamic system prompt | Completed | |
| Clarification protocol | Completed | Asks before diving in on an ambiguous request |
| Skills + per-agent memory | Completed | Loaded from `harness/` |
| Context management (`trim` / `summarize`) | Completed | Off by default |
| Run-transcript recording | Completed | For eval / replay |

### Platform

| Feature | Status | Notes |
| --- | --- | --- |
| LLM provider: OpenRouter | Completed | |
| LLM provider: others | Not built | Provider registry supports it |
| Web search: Tavily | Completed | |
| Web search: other providers | Not built | |
| RAG vector store: faisslite / Qdrant | Completed | faisslite is the default (embedded) |
| RAG retrieval: `vector_only` | Completed | |
| RAG retrieval: hybrid / BM25 / rerank | Not built | |
| Document parsing: text / markdown / PDF / DOCX | Completed | PDF / DOCX via docling |
| Async RAG ingestion | Completed | Celery worker |
| Frontend: web + Tauri desktop | Completed | One React renderer |
| Plain non-agentic chat screen | Completed | `/api/chat` |
| Live provider / model settings | Partial | Change needs a backend restart |
| Sandbox: per-session filesystem workspace | Completed | |
| Sandbox: container / network / resource isolation | Not built | Current backend is a placeholder |
| Domain tools (market data, quotes / OHLCV, …) | Not built | |
| `shared-types` codegen from Pydantic models | Not built | Hand-synced |
| Desktop: auto-spawn backend + real app icon | Not built | |
| Dataset-driven eval runner | Not built | Transcript recording only |
| More agent profiles (trading / sales) | Not built | |
| Coding / PR-drafting agent | Not built | Deliberate — needs a privileged sandbox + human-approval gate |

## Prerequisites

- Node 20+, [pnpm](https://pnpm.io) 10+
- Python via [uv](https://docs.astral.sh/uv/) (`brew install uv`) — uv manages its own Python 3.11; your system Python doesn't matter
- An `OPENROUTER_API_KEY` (LLM + RAG embeddings) and a `TAVILY_API_KEY` (web search)
- Optional: Docker — only for the full `docker/` compose stack, or a standalone Redis (Celery / RAG ingestion) or Qdrant
- Desktop app only: a Rust toolchain (`rustup`/`cargo`) plus Tauri's [system dependencies](https://v2.tauri.app/start/prerequisites/)

## Setup

```bash
pnpm install
cp .env.example .env      # fill in OPENROUTER_API_KEY and TAVILY_API_KEY
cd backend && uv sync && cd ..
```

`backend/` is one `uv` workspace — the libs, the FastAPI service, and the Celery worker share a single venv; run `uv run` from `backend/`. There's one real `.env` at the repo root; `backend/.env`, `apps/web/.env.local`, and `docker/.env` are committed symlinks to it — edit the root file only.

## Running it

```bash
# Backend (FastAPI) — the frontend talks to it directly over AG-UI, no runtime hop
cd backend && uv run uvicorn krutrim_agent_backend.main:app --reload --port 8000

# Frontend — web
pnpm run web                       # apps/web → http://localhost:4200
# ...or desktop (needs the Rust toolchain)
pnpm exec nx run desktop:serve     # runs `tauri dev`

# Optional — RAG document ingestion + embedding precompute (needs Redis)
docker compose -f docker/docker-compose.yml up redis
cd backend && uv run krutrim-agent-worker
```

Open `http://localhost:4200/?agent=research` (omitting `?agent=` lands on `home`). The whole stack also runs via `docker/docker-compose.yml` — see `docker/README.md`.

## Adding a new agent type

1. `backend/libs/krutrim_agents/src/krutrim_agents/profiles/<key>/__init__.py` — define an `AgentProfile` and call `register_profile(...)`. Copy `research` as a starting point.
2. `backend/harness/{prompts,skills,memory}/<key>/` — at minimum `memory/<key>/AGENTS.md` and a prompt per declared role.
3. *(optional)* `libs/agent-ui/src/screens/<key>/` + one line in `screens/registry.ts` — skip it to use the `default` screen.
4. Restart the backend. Visit `?agent=<key>`.

No core file changes for any of the above.

## Testing

```bash
cd backend && uv run pytest    # providers, registry, graph assembly, AG-UI translator, chat, doc parsers, cross-agent
pnpm run lint                  # frontend eslint
pnpm run build                 # build every Nx project
```

## Consuming the packages elsewhere

Every `backend/libs/*` (`uv` workspace package) and every reusable `libs/*` frontend package (`@krutrim_agent/` scope) is independently installable — a separate private repo can depend on a subfolder of this repo directly, no publishing infrastructure required:

```toml
# consuming pyproject.toml
[tool.uv.sources]
krutrim-agents-core = { git = "https://github.com/<org>/krutrim_community", subdirectory = "backend/libs/krutrim_agents_core" }
```

```json
// consuming package.json — agent-ui pulls its @krutrim_agent/* siblings, so redirect those too
"dependencies": { "@krutrim_agent/agent-ui": "github:<org>/krutrim_community#path:libs/agent-ui" },
"pnpm": { "overrides": {
  "@krutrim_agent/ui": "github:<org>/krutrim_community#path:libs/ui",
  "@krutrim_agent/shared-types": "github:<org>/krutrim_community#path:libs/shared-types"
}}
```

Tailwind compilation always happens in the consuming app: `import '@krutrim_agent/ui/theme.css'` in your entry CSS and add `@source '../node_modules/@krutrim_agent/*/dist/**/*.js';` so its content scan reaches the installed packages.

`krutrim_agent_extensions` (backend) and `@krutrim_agent/extensions` (frontend) are the seam for edition-specific add-ons — auth, agent-profile visibility, audit logging. Community ships all-no-op hooks; a consuming app registers real ones via `settings.extension_sources` / `<Agent extensions={{ ... }}>` without forking anything else.
