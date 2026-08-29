# Krutrim Agent

A pluggable multi-agent-type platform: a LangGraph + [deepagents](https://docs.langchain.com/oss/python/deepagents/overview) backend (Python) hosting several independent agent "profiles" (research, trading, sales — add more without touching core code), talking directly to a pure-React frontend (web app and Tauri desktop app) over the AG-UI protocol via `@ag-ui/client`'s `HttpAgent` — no intermediary runtime process. Chat lives in a left pane; the agent's finished output renders in a right-hand canvas, using whichever agent type is selected via `?agent=<key>` in the URL.

## Architecture

```
apps/web (Vite+React+TS)     ─┐
                                ├─ @ag-ui/client HttpAgent, one per selected agent_key
apps/desktop (Tauri+Rust+TS) ─┘  (same React renderer as apps/web, wrapped in a
                                  native window by src-tauri/ — no Node "main process")
                                                       │
                                                       │ AG-UI protocol (HTTP/SSE), direct
                                                       ▼
                                    backend/ (FastAPI, Python, uv-managed)
                                      ├─ POST /agents/{agent_key}       → ONE parameterized route
                                      ├─ GET  /api/agents               → lists registered profiles
                                      ├─ /api/providers/{agent_key}     → CRUD for per-role LLM settings
                                      └─ /api/health
                                                       │
                                       krutrim_agents_core/ (libs/krutrim_agents_core)
                                    registry.py auto-discovers krutrim_agents/profiles/{research,trading,sales}/*
                                                       │
                                             ┌─────────┴──────────┐
                                             ▼                    ▼
                                  providers/ (OpenRouter,   harness/ (skills, prompts,
                                  Ollama via LangChain)      evals, memory - per agent_key)
                                                                   │ execute / file ops
                                                                   ▼
                                                One Docker sandbox per agent profile (read-only
                                                rootfs, no network, non-root, resource limits)
```

## The core/plugin split

This is the central design decision — see `.architecture/` (design-decision notes, tracked in the repo) for the full writeup. Short version:

- **Core** (never touched when adding an agent): the FastAPI app, the providers system, the Docker sandbox, the harness loaders, `krutrim_agents_core/registry.py` (auto-discovery), `krutrim_agents_core/builder.py` (generic graph assembly), the shared primitives in `libs/ui`, and the entire frontend shell in `libs/agent-ui` (chat panel, settings panel, URL parsing, canvas shell, the `@ag-ui/client` wiring in `agent-client.ts`).
- **Plugin surface** (what you touch to add a new agent type):
  - Backend: one new folder `backend/libs/krutrim_agents/src/krutrim_agents/profiles/<key>/__init__.py` (declares an `AgentProfile` — prompts, tools, subagents, default models — and self-registers) plus its harness content folders. **Zero edits to existing files** — `registry.py` scans each configured profile-source package's filesystem path at import time.
  - Frontend: one new folder `libs/agent-renderers/src/<key>/renderer.tsx` (a React component that draws that agent's content) plus **one line** in `libs/agent-renderers/src/registry.ts`. Everything in `libs/agent-ui` stays untouched — it only ever calls `getAgentRenderer(agentKey)`, falling back to a built-in markdown/chart/news renderer if a custom one isn't registered.

## Reusable packages — consuming this repo from another codebase

Every backend lib and every reusable frontend lib (never a page/app) is an independently installable package, meant for a separate private repo  to depend on directly — no publishing infrastructure required to start.

**Backend** (`backend/libs/*`, each a real `uv` workspace package): `krutrim_agent_utils`, `krutrim_agent_management`, `krutrim_agent_sandbox`, `krutrim_agents_core`, `krutrim_agents`, `krutrim_agent_celery_core`, `krutrim_agent_extensions`. A consuming repo's own `pyproject.toml` points straight at a subfolder of this repo:

```toml
[tool.uv.sources]
krutrim-agents-core = { git = "https://github.com/<org>/krutrim_community", subdirectory = "backend/libs/krutrim_agents_core" }
```

**Frontend** (`libs/*`, each a real npm package under the `@krutrim_agent/` scope): `@krutrim_agent/ui`, `@krutrim_agent/shared-types`, `@krutrim_agent/agent-renderers`, `@krutrim_agent/agent-ui`, `@krutrim_agent/extensions` (`tauri-utils` stays unpackaged — desktop/Tauri-only). Each has its own `package.json`/`vite.config.mts` producing a real `dist/` (ESM + `.d.ts`); `pnpm nx build <lib>` builds one, `pnpm run build` builds everything. A consuming repo's `package.json` points at a subfolder via pnpm's git-subdirectory support:

```json
"dependencies": {
  "@krutrim_agent/agent-ui": "github:<org>/krutrim_community#path:libs/agent-ui"
}
```

Because `agent-ui`/`agent-renderers` depend on their sibling `@krutrim_agent/*` packages too, add a `pnpm.overrides` block redirecting those to the same git subfolder (there's no registry resolving `@krutrim_agent/*` by version yet):

```json
"pnpm": {
  "overrides": {
    "@krutrim_agent/ui": "github:<org>/krutrim_community#path:libs/ui",
    "@krutrim_agent/shared-types": "github:<org>/krutrim_community#path:libs/shared-types",
    "@krutrim_agent/extensions": "github:<org>/krutrim_community#path:libs/extensions"
  }
}
```

Publishing to a private registry (GitHub Packages / a private PyPI index) removes the need for overrides entirely — a pure upgrade later, not a redesign.

**Tailwind**: `@krutrim_agent/ui`'s `theme.css` ships as raw, unprocessed source (`import "@krutrim_agent/ui/theme.css"` in your own entry CSS) — Tailwind compilation always happens in the *consuming* app, never inside these libraries. Since Tailwind's content-detection never walks into `node_modules`, add your own scan target pointing at the installed packages' built JS:

```css
@import 'tailwindcss';
@import '@krutrim_agent/ui/theme.css';
@source '../node_modules/@krutrim_agent/*/dist/**/*.js';
```

**Extending securely**: `krutrim_agent_extensions` (backend) and `@krutrim_agent/extensions` (frontend) are the seam for everything edition-specific — auth, agent-profile visibility, audit logging. Community ships all-no-op hooks on both sides; a consuming app registers real ones (backend: `settings.extension_sources`; frontend: `<Agent extensions={{ authProvider, visibilityFilter }}>`) without forking anything else. `GET /api/system/extensions` plus the frontend's `<ExtensionSelfCheck backendUrl={...}>` catch drift between what each side thinks is configured — see `backend/docs/libs/krutrim_agent_extensions.md`.

## Prerequisites

- Node 20+, [pnpm](https://pnpm.io) 10+
- Python via [uv](https://docs.astral.sh/uv/) (`brew install uv`) — uv manages its own Python 3.11, your system Python doesn't matter
- Docker Desktop (or another Docker daemon) running — required for the agent sandboxes
- Optional: [Ollama](https://ollama.com) running locally if you want any role on a local model instead of OpenRouter
- Only if you're running the desktop app: a Rust toolchain (`rustup`/`cargo`) plus Tauri's [platform-specific system dependencies](https://v2.tauri.app/start/prerequisites/) (e.g. WebKitGTK on Linux). Not needed for the web app.

## Setup

```bash
pnpm install

cp .env.example .env   # then fill in OPENROUTER_API_KEY — one shared file, see below

cd backend
uv sync
docker build -f ../docker/sandbox.Dockerfile -t krutrim_agent-sandbox:latest .
cd ..
```

`backend/` is a `uv` workspace, not a single package: `libs/{krutrim_agent_management,krutrim_agent_sandbox,krutrim_agents}` (importable libraries) and `services/{krutrim_agent_backend,krutrim_agent_celery}` (the FastAPI app and the idle-container-reaper worker), sharing one venv. `uv sync`/`uv run` from `backend/` operate on the whole workspace.

There's one real env file, at the repo root. `backend/.env` and `apps/web/.env.local` are committed symlinks pointing at it (so is `docker/.env`, for the containerized setup — see `docker/README.md`) — edit values in the root `.env` only, every tool reads the same file through its own symlink.

## Running it

The frontend talks straight to the backend over AG-UI (HTTP/SSE), no runtime hop in between. A Redis instance (`docker compose -f docker/docker-compose.yml up redis`) and the Celery worker are only needed for the idle-container reaper — the app runs fine without them, just without automatic sandbox teardown.

```bash
# 1. Backend (FastAPI)
cd backend && uv run uvicorn krutrim_agent_backend.main:app --reload --port 8000

# 1b. Optional: idle-container reaper worker (needs Redis running)
cd backend && uv run celery -A krutrim_agent_celery.app worker --beat --loglevel=info

# 2a. Web
pnpm run web          # apps/web, http://localhost:4200

# 2b. ...or Desktop (requires the Rust toolchain — see Prerequisites)
pnpm exec nx run desktop:serve   # runs `tauri dev`: starts the Vite renderer, opens a native window
```

Open `http://localhost:4200/?agent=research` (or `trading`, or `sales`) — the URL picks which agent you're talking to; omitting `?agent=` defaults to `research`. The Settings (⚙) button in the chat header edits that agent's per-role provider/model config against `/api/providers/{agent}` — **changes take effect on the next backend restart**, there's no hot-reload of the compiled graphs in this v1.

## Agent profiles shipped in this pass

- **`research`** — general-purpose research: gathers, critiques, and reports on any topic. Roles: `main`, `researcher`, `critic`, `writer`.
- **`trading`** — trading/market research analysis (tickers, sectors, trade ideas). Same four roles; has its own custom canvas renderer (`libs/agent-renderers/src/trading/`) that keeps a persistent "not financial advice" footer and can render numeric series as a chart.
- **`sales`** — prospect research + outreach drafting. Only three roles (`main`, `researcher`, `writer`, no `critic`) — deliberately different from the other two, to prove a profile can shape its own role set.

## LLM providers

Two providers ship out of the box, each with its own Pydantic settings class (`backend/libs/krutrim_agents_core/src/krutrim_agents_core/providers/`):

- **OpenRouter** (`openrouter.py`) — needs `OPENROUTER_API_KEY`; model id is whatever OpenRouter calls it (e.g. `deepseek/deepseek-v4-flash-0731`, `openai/gpt-4.1-mini`).
- **Ollama** (`ollama.py`) — local, no key; needs `ollama serve` running (or the `docker/docker-compose.yml` `ollama` service) and the model pulled (`ollama pull llama3.1`).

Settings are persisted per `(agent_key, role)` in `backend/harness/memory/settings.json` (gitignored), seeded from each profile's own `default_models` — the store itself has no per-agent knowledge and picks up a newly added profile's defaults automatically on the next backend start. Add a new provider by subclassing `ModelSettings`/`Provider` and registering it in `providers/registry.py` (this is core, shared by every agent).

## The sandbox: "won't go beyond the rules"

Every filesystem operation and shell command an agent runs happens inside a locked-down Docker container (`krutrim_agent_sandbox.docker_backend.DockerSandboxBackend`, subclassing deepagents' `BaseSandbox`) — **one container per session by default** (isolated), with opt-in explicit container reuse between sessions and a cross-agent messaging bridge between separate sessions' containers; see `sandbox/registry.py`'s `SandboxRegistry` and the idle-container reaper in `services/krutrim_agent_celery/`:

- **No network** (`network_disabled=True`) — nothing to exfiltrate to or fetch from.
- **Read-only rootfs** — only `/tmp` and `/workspace` are writable, and both are in-memory tmpfs (no host bind mount at all, so the sandbox has zero access to host files).
- **Non-root, capabilities dropped, `no-new-privileges`.**
- **Fixed resource limits** (memory/CPU/pids) and a **hard wall-clock timeout** per command, enforced via `timeout` inside the container.
- The policy (`sandbox/policy.py`) is server-side config — the LLM-facing `execute` tool only ever takes a command string, so there's no code path for the model to loosen any of this.

`backend/harness/skills/{common,<agent_key>}/` and `backend/harness/memory/<agent_key>/` are mounted read-only (`ReadOnlyFilesystemBackend`) alongside the sandbox via a `CompositeBackend`, scoped per agent — a research agent can't read trading's memory, for instance — and the agent can read its own harness content but never write to it, even though it has full read/write inside `/workspace`.

## The harness

- `harness/skills/common/*/SKILL.md` — skills shared by every agent (web research, sandboxed data analysis).
- `harness/skills/<agent_key>/*/SKILL.md` — Claude-Code-style skill files specific to one agent, loaded by deepagents' `SkillsMiddleware`.
- `harness/prompts/<agent_key>/*.md` — system prompts for that agent's main graph and each of its subagents, loaded by `krutrim_agents_core.harness.prompts.load_prompt(agent_key, name)`.
- `harness/evals/datasets/<agent_key>.jsonl` + `evals/runner.py` — a standalone script (not part of `pytest`) that runs each task through that agent's real graph and checks required substrings. Needs real API/Ollama access: `uv run python harness/evals/runner.py <agent_key>`.
- `harness/memory/<agent_key>/AGENTS.md` — durable per-agent memory, loaded into that agent's system prompt. `harness/memory/runs/<agent_key>/` holds gitignored JSONL run transcripts (`krutrim_agents_core.harness.runs.RunLogger`); `harness/memory/settings.json` holds all agents' provider config (gitignored).

## Adding a new agent type

1. `backend/libs/krutrim_agents/src/krutrim_agents/profiles/<key>/__init__.py` — define an `AgentProfile` and call `register_profile(...)`. Copy an existing profile (`sales` is the simplest) as a starting point.
2. `backend/harness/{skills,prompts,memory}/<key>/` — that profile's harness content (at minimum, `memory/<key>/AGENTS.md` and a prompt per declared role).
3. `libs/agent-renderers/src/<key>/renderer.tsx` + one line in `libs/agent-renderers/src/registry.ts` — optional; omit it and the built-in markdown/chart/news renderer is used automatically.
4. Restart the backend and the runtime. Visit `?agent=<key>`.

Nothing else changes — no core file is edited for any of the above.

## Testing

```bash
cd backend && uv run pytest       # providers, sandbox (real Docker containers), agent registry, graph assembly for every profile
pnpm run lint                     # frontend eslint
pnpm run build                    # build every Nx project
```

## Known limitations / not built (v1)

- No network-allowlist egress proxy for the sandbox — it ships network-disabled only.
- The desktop app (`apps/desktop`, shell in `apps/desktop/src-tauri/`) doesn't auto-spawn the backend — it connects to a configurable URL (`VITE_BACKEND_URL`), same as the web app. `src-tauri/icons/icon.png` is a solid-color placeholder (just enough for `cargo check`/`tauri dev` to run) — regenerate a real icon set (`pnpm exec tauri icon <path-to-1024px-png>`) before running `nx run desktop:package` (`tauri build`) to produce an installable bundle.
- `shared-types` is hand-synced against the backend's Pydantic models, not codegen'd.
- Provider settings changes need a backend restart to take effect (no hot-reload of the compiled graphs).
- Real market-data tools (quotes/OHLCV/indicators) aren't wired in — agents have `web_search`/`fetch_url` plus a sandboxed Python/pandas `execute` tool for now; add a dedicated skill + tool when you pick a data source.
- A "coding"/PR-drafting agent type is a natural next profile but deliberately not built here — it needs real git/network/credential access and a human-approval gate before anything irreversible, which is a different (more privileged) sandbox than the one every other profile shares. See `.architecture/` for the design sketch.
