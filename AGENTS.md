# AGENTS.md

Instructions for AI coding agents (and a quick orientation for humans) working in this repo. For setup/run commands and the high-level architecture diagram, see [README.md](README.md). For the exact runtime request flow, see [docs/app-flow.md](docs/app-flow.md).

## Project directory architecture

Each entry notes **what it is** and **why it exists as its own package** (the
recurring reason is the core/plugin split — see the section below).

```
apps/
  web/       Vite + React + TS web frontend (:4200) — primary delivery target.
  desktop/   Tauri (Rust shell) hosting the SAME React renderer as web (:4300 dev)
             — native desktop build with no second UI codebase.

backend/            uv workspace. `uv run` anything from here.
  libs/
    krutrim_agents_core/   Core agent runtime: profile model + registry + builder,
                           the provider/model catalog + resolver, cross-agent
                           messaging, harness loaders (prompts/skills), the
                           run-recording backend. WHY: the stable spine every
                           profile builds on — profiles plug in, never edit it.
    krutrim_agents/         Agent profile *content* — one subpackage per agent
                           type under `profiles/<key>/` (prompts, tools, graph
                           wiring). WHY: the plugin side of the split; a new
                           agent is a new folder here, nothing else in backend/.
    krutrim_agent_agui/    In-tree LangGraph→AG-UI SSE translator + plugin hooks.
                           WHY: owned in-repo (not the upstream package) so
                           per-run instrumentation and the interrupt/partial-
                           persist logic can hook the stream.
    krutrim_agent_management/  Pluggable persistence: projects, agents, sessions,
                           agent memory, blob store, result cache. WHY: one
                           `Storage` ABC so the app isn't bound to one datastore.
    krutrim_agent_sandbox/  Sandbox registry + status channel + exceptions
                           (filesystem-scoped run isolation; the old Docker/gRPC
                           layer is removed). WHY: confines agent file I/O to a
                           per-session workspace.
    krutrim_agent_rag/     Vector-store I/O, chunking, embeddings, retrieval, and
                           `rag_tool`. WHY: one RAG stack shared by the FastAPI
                           app and the Celery ingestion worker.
    krutrim_agent_doc/     Document parsing for RAG ingestion (text/markdown +
                           PDF/DOCX via docling). WHY: isolates heavy parser
                           deps behind a registry the Celery task calls.
    krutrim_agent_extensions/  Extension contracts, registry, middleware, self-
                           check. WHY: optional/third-party add-on surface kept
                           out of core.
    krutrim_agent_celery_core/  Celery app factory. WHY: shared config so the
                           backend and the worker build the same client.
    krutrim_agent_utils/   Dependency-free primitives: plugin registry, atomic
                           JSON write. WHY: reused everywhere, must stay light.
  services/
    krutrim_agent_backend/  FastAPI app: AG-UI agent-run streaming, plain chat,
                           project/session/settings CRUD. WHY: the deployable
                           API both frontends talk to.
    krutrim_agent_celery/   Celery worker: RAG ingestion + embedding precompute
                           against the same storage libs. WHY: keeps slow
                           document work off the request path.
  harness/     Content/data, not code: composable system-prompt fragments + the
               markdown export spec, skills, agent memory, eval datasets. WHY:
               editable (and swappable per deployment) without touching code.
  tests/       pytest suite spanning every workspace package.

libs/          Frontend (Nx) packages.
  agent-ui/         Core frontend shell: history rail, chat/agent threads,
                    composer, settings panels, AG-UI client wiring, and the
                    work-log↔output routing. WHY: agent-agnostic — never edited
                    to add an agent.
  agent-renderers/  Per-agent frontend plugin surface: the output-panel renderer
                    registry AND the turn splitter (what counts as work-log
                    narration vs. finished output — e.g. research's
                    `===FINAL_REPORT===` marker). WHY: everything agent-specific
                    on the frontend lives here, so removing an agent is deleting
                    a folder + one registry line.
  shared-types/     Hand-synced TS mirror of backend Pydantic response models.
                    WHY: no codegen; the API contract stays explicit and diffable.
  ui/               Generic shadcn/radix-style primitives. WHY: the design-system
                    layer shared by every frontend surface.
  tauri-utils/      Tauri-runtime detection. WHY: lets the shared renderer branch
                    web vs. desktop at runtime.

docker/          sandbox.Dockerfile (agent execution image) + docker-compose.yml.
docs/            Living documentation (app-flow.md, usage/use-case docs).
.architecture/   Design-decision notes — see below (strict edit policy).
```

Core vs. plugin split (see README.md and `.architecture/core-plugin-architecture.md` for the full writeup): the FastAPI app (`krutrim_agent_backend`), the providers system, the sandbox (`krutrim_agent_sandbox`), harness loaders, `krutrim_agents_core/registry.py`, `krutrim_agents_core/builder.py`, `libs/ui`, and `libs/agent-ui` are **core** — adding a new agent profile never requires editing them. New agent types are added purely under `backend/libs/krutrim_agents/src/krutrim_agents/profiles/<key>/` and (optionally) `libs/agent-renderers/src/<key>/` (its renderer *and* its turn splitter).

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


## Comment 

- Don't add too long comment if it is required long comment then add in docs with all details.