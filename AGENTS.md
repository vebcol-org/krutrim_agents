# AGENTS.md

Instructions for AI coding agents (and a quick orientation for humans) working in this repo. For setup/run commands and the high-level architecture diagram, see [README.md](README.md). For the exact runtime request flow, see [docs/app-flow.md](docs/app-flow.md).

## Project directory architecture

```
apps/
  web/            Vite + React + TS — primary web frontend (:4200)
  desktop/        Tauri (Rust shell) + same React renderer (:4300 dev)
backend/
  libs/             uv workspace libraries (krutrim_agent_management, krutrim_agent_sandbox, krutrim_agents)
  services/         uv workspace deployables (krutrim_agent_backend — the FastAPI app; krutrim_agent_celery — idle-container reaper)
  harness/          Content data: prompts, skills, memory, eval datasets — not code
  tests/            pytest suite (spans every workspace package — `uv run pytest` from backend/)
libs/
  agent-ui/         Core frontend shell (chat panel, settings panel, AG-UI client wiring) — never touched when adding an agent
  agent-renderers/  Plugin surface for the canvas — per-agent renderer registry
  shared-types/     Hand-synced TS mirror of backend Pydantic models
  ui/               Generic UI primitives (shadcn/radix style)
  tauri-utils/      Tauri-runtime detection helper
docker/             sandbox.Dockerfile (agent execution image) + docker-compose.yml (optional local Ollama)
docs/               Living documentation (app-flow.md, usage/use-case docs)
.architecture/      Design-decision notes — see below
```

Core vs. plugin split (see README.md and `.architecture/core-plugin-architecture.md` for the full writeup): the FastAPI app (`krutrim_agent_backend`), providers system, Docker sandbox (`krutrim_agent_sandbox`), harness loaders, `krutrim_agents_core/registry.py`, `krutrim_agents_core/builder.py`, `libs/ui`, and `libs/agent-ui` are **core** — adding a new agent profile never requires editing them. New agent types are added purely under `backend/libs/krutrim_agents/src/krutrim_agents/profiles/<key>/` and (optionally) `libs/agent-renderers/src/<key>/`.

## Reference `.architecture/` for design context

Before making a non-trivial change to how a component is wired (routing, the sandbox, the provider/model system, the AG-UI message flow, the plugin registry, the desktop shell), read the relevant note in `.architecture/`:

- `agui-message-flow.md` — the exact request/response trace between frontend and backend
- `core-plugin-architecture.md` — the core/plugin boundary and why it's drawn where it is
- `sandbox-design.md` — what the Docker sandbox isolates and why (one container per profile, not per thread or shared)
- `desktop-shell-evolution.md` — why `apps/desktop` is Tauri, not Electron, and what's deliberately left unfinished
- `coding-agent-sketch.md` — a design sketch (not built) for why a future "coding"/PR-drafting agent profile needs a more privileged sandbox than today's profiles share

These notes exist so both AI agents and humans share the same mental model of *why* the system is built this way, not just what the code currently does. Read them for context — but see the strict edit policy below before touching them.

## After making a code change

Follow this sequence for every change:

1. **Run tests** for whatever you touched:
   - Backend: `cd backend && uv run pytest`
   - Frontend: `pnpm run test` (or a targeted `pnpm exec nx run <project>:test` for just the project you touched)

2. **Check coverage on the code you changed** — not repo-wide coverage. The goal is that new/changed code is exercised by a test, not that the whole repo hits some global percentage.
   - Backend: `pytest-cov` isn't in `backend/pyproject.toml` yet. Add it once with `cd backend && uv add --group dev pytest-cov`, then run `uv run pytest --cov=krutrim_agent_management --cov=krutrim_agent_sandbox --cov=krutrim_agents --cov=krutrim_agent_backend --cov=krutrim_agent_celery --cov-report=term-missing` and check the reported lines for the files you edited.
   - Frontend: `apps/web` already has `coverage-v8` wired into its Vitest config (`apps/web/vite.config.mts`) — run `pnpm exec nx run web:test --coverage`. Other `libs/*` projects currently only have a `lint` target, no `test` target — if you add tests to one of them, give it a Vitest `test` config (see `apps/web/vite.config.mts` as a template) before expecting a coverage report.
   - Don't chase 100%; don't retrofit coverage for unrelated pre-existing code in the same file.

3. **Update documentation** once tests pass:
   - Keep [docs/app-flow.md](docs/app-flow.md) in sync with the runtime flow if your change alters it (a new route, a new step in the request trace, a new API endpoint, a changed data-flow).
   - Keep the per-package developer docs current for whatever you touched:
     - Backend: `backend/docs/libs/<package>.md` or `backend/docs/services/<service>.md` for the package/service you changed (new function/route/tool/env var, changed behavior, new file).
     - Frontend: `docs/frontend/<package>.md` (plus `docs/frontend/README.md` if the change affects the overall lifecycle/flow).
   - Add or update a use-case/usage doc under `docs/` for any new or changed user-facing capability.
   - If a change makes any doc's "known gaps"/"not wired up" callouts stale (e.g. you actually wire up something previously flagged as disconnected), update that callout instead of leaving it stale — these docs must reflect what the code actually does, not what an older doc assumed.
   - Do **not** touch `.architecture/` as part of this step — see below.

## `.architecture/` edit policy — do not update automatically

`.architecture/*.md` is a deliberately curated, low-churn set of design notes for understanding *why* the system is architected the way it is — not a changelog, and not something that should drift on every commit.

- Do not update `.architecture/` for routine changes, refactors, or new agent profiles/features that fit within the existing design.
- Only update it when the **user explicitly says the architecture itself changed** and **explicitly asks you to update the `.architecture` docs**.
- Even then, confirm with the user before editing — describe what you intend to change in `.architecture/` and get a go-ahead first. Never edit these files silently as a side effect of another task.

## Comment 

- Don't add too long comment if it is required long comment then add in docs with all details.