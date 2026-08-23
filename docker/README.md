# docker/

Everything needed to run the whole stack — frontend, backend, Celery worker, Redis — on your laptop's Docker engine with one `docker compose up`, instead of starting each piece by hand (`uv run uvicorn ...`, `uv run celery ...`, `pnpm run web`, ...).

## Files in this folder

| File | Builds | Used by |
|---|---|---|
| [`backend.Dockerfile`](./backend.Dockerfile) | `services/krutrim_agent_backend` — the FastAPI app | `docker-compose.yml`'s `backend` service |
| [`celery.Dockerfile`](./celery.Dockerfile) | `services/krutrim_agent_celery` — the Celery worker/beat (idle-container reaper, embeddings precompute) | `docker-compose.yml`'s `celery-worker` service |
| [`frontend.Dockerfile`](./frontend.Dockerfile) | `apps/web` — Vite/React build, served by nginx | `docker-compose.yml`'s `frontend` service |
| [`sandbox.Dockerfile`](./sandbox.Dockerfile) | The locked-down image every **agent sandbox** container runs (no network, read-only rootfs, non-root) | Referenced by name (`krutrim_agent-sandbox:latest`) from backend/celery code — never built *by* compose, see below |
| [`nginx.conf`](./nginx.conf) | Static-file + SPA fallback config for the frontend image | `frontend.Dockerfile` |
| [`docker-compose.yml`](./docker-compose.yml) | Wires all of the above together | You, directly |

## The architecture this sets up

```
Your laptop's Docker engine
├─ frontend        (nginx, static build)          :4200 → browser
├─ backend         (FastAPI)                       :8000 → browser (AG-UI/SSE)
├─ celery-worker   (reaper + embeddings precompute)
├─ redis           (Celery broker/result-backend)  :6379
├─ ollama          (optional, local LLM provider)  :11434
│
└─ krutrim-agent-sandbox-* (one per session, created/torn down BY backend/celery)
```

`backend` and `celery-worker` each get `/var/run/docker.sock` bind-mounted in. When their code (`krutrim_agent_sandbox.docker_backend`, via the `docker` Python SDK) asks Docker to start a sandbox container, it's talking to **this same host engine** — the sandbox container comes up as a *sibling* of `backend`, not nested inside it (no Docker-in-Docker). Run `docker ps` on your host and you'll see `krutrim-agent-sandbox-*` containers listed right alongside `backend`/`celery-worker`/`frontend`/`redis`.

This means mounting the socket effectively gives `backend`/`celery-worker` root-equivalent control over your host's Docker daemon — that's the trade-off for "one command manages everything." It's the same reason the previous, non-containerized setup in the root README ran the backend directly on the host: either way, something needs unrestricted Docker access to create/tear down sandboxes.

## One-time setup

### 1. The sandbox image

The agent sandbox image is **not** built by `docker-compose.yml` — it just has to already exist in your host engine's image store by the name `backend`/`celery-worker` code expects (`KRUTRIM_AGENT_SANDBOX_IMAGE`, default `krutrim_agent-sandbox:latest`), because they reference it by name when asking the host engine to start a container:

```bash
docker build -f docker/sandbox.Dockerfile -t krutrim_agent-sandbox:latest .
```

Rebuild it whenever `sandbox.Dockerfile` changes.

### 2. faisslite over HTTPS (private repo)

`krutrim-agent-management` (used by both `krutrim_agent_backend` and `krutrim_agent_celery`) depends on `faisslite`, hosted at [github.com/visheshpanchal/faisslite](https://github.com/visheshpanchal/faisslite) — a **private** repo. `pyproject.toml`/`uv.lock` already point at it over HTTPS. `uv sync` inside the build needs credentials to clone it — no SSH key is set up on this machine, so instead the build takes a **GitHub token as a BuildKit secret**, mounted only for that one layer and never written into any image layer (see the `RUN --mount=type=secret,...` step in `backend.Dockerfile`/`celery.Dockerfile`).

One-time setup:

1. Create the token file (gitignored — `docker/.secrets/` — never committed):
   ```bash
   mkdir -p docker/.secrets
   gh auth token > docker/.secrets/github_token   # reuses your existing gh CLI login
   chmod 600 docker/.secrets/github_token
   ```
   `gh auth token` reuses whatever broad-scoped session token `gh auth login` set up (scopes: `repo`, `gist`, `read:org`, `workflow`). That's fine to get started, but it's more than this build needs — swap in a [fine-grained PAT](https://github.com/settings/personal-access-tokens/new) scoped to read-only **Contents** on just the `faisslite` repo when you want tighter scoping (same file, same format, just the token string).
2. `docker-compose.yml` already references this file via its top-level `secrets:` block and passes it to `backend`/`celery-worker`'s builds — no extra flags needed for `docker compose build`.
3. Building a single Dockerfile manually (outside compose) needs the flag explicitly:
   ```bash
   docker build --secret id=github_token,src=docker/.secrets/github_token \
     -f docker/backend.Dockerfile -t krutrim_agent-backend backend
   ```

If `docker/.secrets/github_token` doesn't exist, the build fails fast (`required=true` on the secret mount) rather than silently baking in a broken auth state.

### 3. Env vars — one shared `.env`

```bash
cp .env.example .env   # from the repo root — fill in OPENROUTER_API_KEY
```

There's exactly **one** real env file, at the repo root. `backend/.env`, `apps/web/.env.local`, and `docker/.env` are committed *symlinks* pointing at it — so `uv run uvicorn ...` (reads `backend/.env`), `vite dev` (reads `apps/web/.env.local`), and `docker compose` (reads `docker/.env`) all end up reading the exact same file without you maintaining three copies. Edit values in the root `.env` only; the symlinks are structural, not something you recreate per change. A fresh clone already has them (they're just path pointers, no secrets in them) — the only manual step is the `cp .env.example .env` above.

`docker-compose.yml` also loads the root `.env` directly via `env_file` on `backend`/`celery-worker`, and overrides the Redis URL / storage root to the in-network values (the root `.env`'s own `KRUTRIM_AGENT_REDIS_URL` default, when set, is written for running the backend directly on the host, not inside compose).

`REDIS_USER`/`REDIS_PASSWORD` (also in `.env.example`) gate Redis auth for the `redis` service — see "Redis auth" below.

## Running it

```bash
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml up
```

- Frontend: http://localhost:4200
- Backend: http://localhost:8000
- Redis: localhost:6379

No `uv run`, no `pnpm run web`, no separate Celery command — `docker compose up` starts/stops all of it together. `docker compose down` stops everything; add `-v` only if you also want to drop the `redis-data`/`ollama-models` *named volumes* (this does **not** touch your data — see below).

## Persistent data

Two things are bind-mounted from your real home directory / repo, not stored inside the containers, so `docker compose down` / image rebuilds never lose them:

- `${HOME}/.krutrim_agent` → `/data` in `backend` and `celery-worker` — projects, sessions, the sandbox-container registry (`STORAGE_ROOT`, see `krutrim_agent_management/local.py`'s docstring for the full layout).
- `backend/harness/memory` → `/app/harness/memory` — per-agent provider settings (`settings.json`) and run transcripts. Gitignored, written at runtime.

Both processes point at the *same* `STORAGE_ROOT` (matching how the non-Docker dev setup already runs backend + Celery against one shared `~/.krutrim_agent`) — see that module's docstring for the "not safe for concurrent writes across processes" caveat, which is an existing constraint, not something Docker introduces.

## Redis auth

Off by default — leave `REDIS_USER`/`REDIS_PASSWORD` blank in `.env` and `redis` starts with no password, same as before, with its port published straight to your host (`6379:6379`).

Set both to turn it on:

```bash
# in .env
REDIS_USER=default   # Redis's built-in user name — not a placeholder, leave as "default"
REDIS_PASSWORD=some-real-password
```

`docker-compose.yml` threads this two places:
- `redis`'s own `command:` passes `--requirepass ${REDIS_PASSWORD}` (as an array, not a shell string — see the comment in `docker-compose.yml` for why that distinction matters for the blank case).
- `backend`/`celery-worker`'s `KRUTRIM_AGENT_REDIS_URL` only embeds `user:pass@` when `REDIS_PASSWORD` is actually set (`${REDIS_PASSWORD:+...}`) — sending `AUTH` to a `redis-server` that has no password configured is itself a Redis error, so the credentialed and uncredentialed forms of the URL can't be the same string.

This project doesn't set up Redis ACLs (multiple named users with different permissions) — `REDIS_USER` exists so the connection URL has a username segment to put in front of the password (`redis://user:pass@host:port`, the standard Redis URI form), not because there's more than one user configured.

## Frontend build-time URL

`VITE_BACKEND_URL` is baked into the frontend's static JS at *build* time (Vite convention — there's no server to read env vars from at runtime). It must be a URL your **browser** can reach, which is the backend's port published to the host (`http://localhost:8000` by default, sourced from `.env`) — never the internal compose service name `http://backend:8000`, since the browser runs outside the compose network entirely.

To point at a different backend, either change `VITE_BACKEND_URL` in `.env` and rebuild, or override the build arg directly for a one-off:

```bash
docker compose -f docker/docker-compose.yml build \
  --build-arg VITE_BACKEND_URL=https://your-deployed-backend.example.com frontend
```
