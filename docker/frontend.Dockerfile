# apps/web — the Vite/React frontend, built to static files and served by
# nginx. Talks to krutrim_agent_backend straight over AG-UI (HTTP/SSE) from the
# *browser*, so VITE_BACKEND_URL must be a URL the browser can reach (e.g.
# http://localhost:8000, assuming docker-compose.yml publishes the backend's
# port to the host) — never the internal compose service name, since the
# browser runs outside the compose network.
#
# Build context is the repo root (this is an Nx/pnpm monorepo — apps/web
# depends on libs/ui, libs/agent-ui, libs/agent-renderers, etc.):
#   docker build -f docker/frontend.Dockerfile \
#     --build-arg VITE_BACKEND_URL=http://localhost:8000 \
#     -t krutrim_agent-frontend .

FROM node:22-slim AS builder

RUN corepack enable

WORKDIR /app
COPY . .

RUN pnpm install --frozen-lockfile

ARG VITE_BACKEND_URL=http://localhost:8000
ENV VITE_BACKEND_URL=${VITE_BACKEND_URL}

RUN pnpm exec nx build web

FROM nginx:1.27-alpine

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist/apps/web /usr/share/nginx/html

EXPOSE 80
