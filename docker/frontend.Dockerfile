# syntax=docker/dockerfile:1
# apps/web — the Vite/React frontend (Nx + pnpm monorepo).
#
#   deps ─┬─→ dev     Vite dev server + HMR; source bind-mounted, no rebuild
#         └─→ build ─→ prod   static bundle served by unprivileged nginx  ← default
#
# No TORCH_BACKEND / vector-store switches here — those are backend concerns.
#
# The browser talks to krutrim_agent_backend directly over AG-UI (HTTP/SSE), so
# VITE_BACKEND_URL must be a URL the *browser* can reach (e.g.
# http://localhost:8000) — never an internal compose service name. For `prod`
# it is baked into the bundle at build time (Vite convention); for `dev` it is
# read live from the environment by `vite dev`.
#
# Build context is the repo root.


# ── deps ───────────────────────────────────────────────────────────────────
# pnpm workspace install. Cached on the lockfile + package.json files alone —
# a source-only edit never re-installs. (The pnpm workspace is the repo root +
# libs/*; apps/* have no package.json of their own.)
FROM node:22-slim AS deps

RUN corepack enable
WORKDIR /app
ENV CI=1

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY libs/agent-dashboard/package.json  libs/agent-dashboard/
COPY libs/agent-ui/package.json         libs/agent-ui/
COPY libs/extensions/package.json       libs/extensions/
COPY libs/shared-types/package.json     libs/shared-types/
COPY libs/ui/package.json               libs/ui/

RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile


# ── dev ────────────────────────────────────────────────────────────────────
# docker-compose.dev.yml bind-mounts the repo root over /app (with the
# image's node_modules kept in a named volume), so editing a component on the
# host hot-reloads in the browser with no rebuild. Only a package.json /
# pnpm-lock.yaml change needs `--build` (+ dropping the node_modules volume).
FROM deps AS dev

EXPOSE 4200

# apps/web/vite.config.mts binds host "localhost" — override to 0.0.0.0 so the
# port is reachable from outside the container. CHOKIDAR_USEPOLLING /
# WATCHPACK_POLLING are set from the compose env on macOS/Windows.
CMD ["pnpm", "exec", "nx", "serve", "web", "--host=0.0.0.0", "--port=4200"]


# ── build ──────────────────────────────────────────────────────────────────
# The static production bundle.
FROM deps AS build

COPY . .

ARG VITE_BACKEND_URL=http://localhost:8000
ENV VITE_BACKEND_URL=${VITE_BACKEND_URL}

RUN pnpm exec nx build web


# ── prod ───────────────────────────────────────────────────────────────────
# Safety first: immutable static bundle behind rootless nginx.
# nginx-unprivileged runs as uid 101 and listens on 8080 (no root, no setcap).
# Pair with `read_only: true` + a tmpfs for /tmp,/var/cache/nginx,/var/run in
# compose for a fully immutable runtime.
FROM nginxinc/nginx-unprivileged:1.27-alpine AS prod

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist/apps/web /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=4s --start-period=5s --retries=3 \
    CMD ["wget", "-q", "-O", "-", "http://127.0.0.1:8080/"]
