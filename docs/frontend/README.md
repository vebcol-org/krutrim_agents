# Frontend developer docs

Deep-dive, per-package documentation for the Nx-managed frontend (`apps/web`, `apps/desktop`, `libs/agent-ui`, `libs/agent-renderers`, `libs/ui`, `libs/shared-types`, `libs/tauri-utils`). For backend docs see [`backend/docs/README.md`](../../backend/docs/README.md).

> Keep these in sync: whenever you change a file in one of the packages below, update its doc in the same change — see [`AGENTS.md`](../../AGENTS.md#after-making-a-code-change).

## ⚠️ Read this first — the docs vs. the code

The root [`README.md`](../../README.md), [`docs/app-flow.md`](../app-flow.md), and `.architecture/agui-message-flow.md` describe an older, single-flat-project AG-UI frontend design (`AgentApp`, a `?agent=<key>` URL param, `project_type` filtering). **That design has been superseded.** The frontend now implements a `Project -> (Agent | Chat) -> Session` hierarchy (see [`backend/docs/libs/krutrim_agent_management.md`](../../backend/docs/libs/krutrim_agent_management.md) for the backend model this mirrors) with **two real, live conversation flows side by side**:

| Flow | Backend route | Frontend hook | Center-pane component |
|---|---|---|---|
| Plain `Chat` | `POST /api/chat` (one-shot REST) | `useChat` | `ChatThread` |
| Live `Agent` | `POST /agents/{agent_id}` (AG-UI SSE stream) | `useAgentChat`, wraps `@ag-ui/client`'s `HttpAgent` | `AgentThread` |

Both are real and wired up today — see [`agent-ui.md`](agent-ui.md#two-conversation-flows-two-hooks-two-center-pane-components) for the full comparison. `@ag-ui/client`/`@ag-ui/core` are no longer dead weight.

**What's still genuinely unwired/dormant:**
- [`libs/agent-renderers`](agent-renderers.md) is now wired in — `libs/agent-ui`'s `OutputPanel` calls `getAgentRenderer(agentKey)` and renders the result once an assistant reply is available (see [`agent-ui.md`](agent-ui.md#componentsagentoutput-paneltsx--no-longer-a-placeholder)). `AgentMessageBubble`'s conversational message list still renders text content only, but the canvas/output side no longer does.
- `libs/agent-ui`'s `SettingsPanel` (talks to `/api/providers/{agent_key}`, the per-role provider config editor) is exported but **not rendered** by `Agent` — `agent.tsx` only ever renders `SandboxSettingsPanel`.
- `AGENT_QUERY_PARAM`/`DEFAULT_AGENT_KEY` (`shared-types`) are unused leftovers from the old `?agent=<key>` URL-param design — agent selection now happens through the New Agent creation flow (pick a project + `agent_key`), not a URL param.
- An Agent-owned session's conversation history has no REST route to fetch before a live run starts — see the "known accepted gap" in [`agent-ui.md`](agent-ui.md#two-conversation-flows-two-hooks-two-center-pane-components).

This doc set documents **what actually ships** as the primary content, and calls out anything still dormant explicitly wherever relevant, rather than describing dead code as if it were live.

## Package map

```
apps/
  web/              Vite + React + TS — browser frontend, served at :4200
  desktop/           Tauri (Rust shell, does nothing but wrap a webview) + same React renderer, :4300 dev
libs/
  agent-ui/          The actual product shell: workspace tree (Project→Agent|Chat→Session),
                      plain Chat flow + live Agent (AG-UI) flow, Settings/SandboxSettings
                      panels, SSE status hook                                    → agent-ui.md
  agent-renderers/    Canvas renderer registry — wired in via agent-ui's OutputPanel → agent-renderers.md
  ui/                 Generic UI primitives (shadcn/radix-style) + theme         → ui.md
  shared-types/       Hand-synced TS mirror of backend Pydantic models           → shared-types.md
  tauri-utils/        isTauriRuntime() — desktop/web branching helper, unused    → tauri-utils.md
```

Per-package docs: [`apps-web.md`](apps-web.md), [`apps-desktop.md`](apps-desktop.md), [`agent-ui.md`](agent-ui.md), [`agent-renderers.md`](agent-renderers.md), [`ui.md`](ui.md), [`shared-types.md`](shared-types.md), [`tauri-utils.md`](tauri-utils.md).

## Lifecycle: page load → workspace tree → conversation → response

### 1. Page load
`apps/web/src/main.tsx` mounts `<App />` (`apps/web/src/app/app.tsx`), which wraps a single-route `<BrowserRouter>` (`"/"` → `<Agent backendUrl={...}>`) — `backendUrl` comes from `import.meta.env['VITE_BACKEND_URL']`, falling back to `shared-types`' `DEFAULT_BACKEND_URL`. `apps/desktop` does the identical thing inline in one file (`src/renderer/main.tsx`) instead of splitting into `app.tsx`. See [`apps-web.md`](apps-web.md) / [`apps-desktop.md`](apps-desktop.md).

### 2. `Agent` mounts, workspace tree loads
`Agent` ([`agent-ui.md`](agent-ui.md#agenttsx)) sets up its own Redux `<Provider>` and `<ThemeProvider>`, then renders `AgentLayout`, which calls both `useWorkspace({ backendUrl })` (loads the `Project -> (Agent | Chat)` tree — `GET /api/projects`, then each project's agents/chats — into `workspace-slice`) and `useChat({ backendUrl })` (the plain-chat flow's own state, `chat-slice`). `HistoryRail` renders the tree from `useWorkspace`'s result plus a `NewMenu` (New Chat / New Agent / New Project).

### 3. Selecting or creating something in the tree
Clicking a Chat or Agent row (or creating one via `NewChatSheet`/`NewAgentSheet`/`NewProjectSheet`) sets `workspace-slice`'s `selection` discriminated union (`{kind:'chat', chatId, sessionId}` or `{kind:'agent', agentId, sessionId}`). `AgentLayout` reads `selection.kind` to decide whether the center pane renders `ChatThread` or `AgentThread`.

### 4a. Plain Chat: user sends a message
`Composer` → `sendMessage(text)` → the Redux `postMessage` thunk → `POST /api/chat` with `{message, chat_id, session_id}`. The user's message is pushed into Redux state **optimistically**. If no `chat_id`/`session_id` existed yet, the backend auto-creates both and returns their real ids. The reply (`{chat_id, session_id, message: {role: "assistant", content}}`) lands as a single unit — **no token-by-token streaming**, matching the backend's non-streaming JSON response (see [`backend/docs/services/krutrim_agent_backend.md#chat_routespy`](../../backend/docs/services/krutrim_agent_backend.md#chat_routespy--the-plain-non-agentic-flow)).

### 4b. Live Agent: user sends a message
`Composer` → `sendMessage(text)` → `useAgentChat`'s `sendMessage`, which calls `@ag-ui/client`'s `HttpAgent.addMessage()` (optimistic local echo) then `.runAgent()` against `POST /agents/{agent_id}?session_id=...`. The reply streams in over SSE and **does** update token-by-token — `AgentMessageList` re-renders on every `onMessagesChanged` firing as the assistant message's `content` grows. See [`agent-ui.md`](agent-ui.md#two-conversation-flows-two-hooks-two-center-pane-components) for how conversation continuity (`threadId: sessionId`) works across separate page loads.

### 5. Sandbox status (unrelated to which flow, still live either way)
`SandboxStatus` subscribes via `useSseStatus` to `GET {backendUrl}/api/status/containers/{ownerId}` — a real `EventSource`/SSE connection. It reflects a session's Docker sandbox container lifecycle (`starting`→`running`→`idle`→`tearing_down`→`stopped`), for either a Chat's or an Agent's session — see [`agent-ui.md`](agent-ui.md#sandbox-statustsx--use-sse-statusts).

### 6. Canvas/output render (Live Agent flow only)
As the assistant reply streams in (step 4b), `AgentLayout` derives a `RenderContentPayload` from the same live message list via `deriveRenderPayload` (the last assistant message's text, wrapped as markdown), and passes it to `OutputPanel` alongside `agentKey` and the run's `trace: TraceStep[]`. `OutputPanel` renders it via `getAgentRenderer(agentKey)` — the `research` profile gets the full markdown-spec renderer (TOC, math, trace panel); every other profile still gets `DefaultRenderer`/`TradingRenderer`/etc., unchanged. See [`agent-ui.md`](agent-ui.md) and [`agent-renderers.md`](agent-renderers.md).

### What's not part of this lifecycle (but exists, dormant)
- Reopening a past Agent session shows an empty thread until the next message — see the accepted gap noted in [`agent-ui.md`](agent-ui.md).
- `SettingsPanel` (per-role provider config) is built and exported but not rendered anywhere in `Agent`.

## Building, running, testing

- `pnpm run web` — `nx serve web` (Vite dev server, port 4200)
- `pnpm run desktop` — `nx serve desktop` (`tauri dev`, Rust toolchain required)
- `pnpm run build` — `nx run-many -t build` (every project with a `build` target)
- `pnpm run lint` — `nx run-many -t lint` (ESLint, `backend/**` excluded from this config entirely)
- `pnpm run test` — `nx run-many -t test` (Vitest; `apps/web` has `--coverage` wired via `coverage-v8`, other `libs/*` have no `test` target yet — add a Vitest config like `apps/web/vite.config.mts`'s embedded block before expecting one)

`apps/web/project.json` and most `libs/*/project.json` declare empty `targets: {}` — `build`/`serve`/`lint`/`test` are all **plugin-inferred** by Nx (`@nx/vite`, `@nx/eslint`, `@nx/vitest` in `nx.json`) from the presence of `vite.config.mts` / eslint / vitest config, not hand-declared. `apps/desktop/project.json` is the exception — it declares explicit `build`/`serve`/`package` targets since Tauri isn't Vite-plugin-inferrable; `build` is deliberately kept Rust-free (renderer only) so `nx run-many -t build` doesn't require the Rust toolchain.
