# `libs/agent-ui`

Nx library `agent-ui` (import as `@krutrim_agent/agent-ui`). **This is the actual product** — the 3-pane shell (workspace tree / conversation / output), its Redux state layer, and the settings/status side panels. Consumed by both `apps/web` and `apps/desktop` identically. See the [frontend README's reality-check](README.md#️-read-this-first--the-docs-vs-the-code) before assuming this matches older docs.

See [`AGENTS.md`](../../AGENTS.md#after-making-a-code-change) for why this doc gets updated in the same change as the code.

```
libs/agent-ui/src/
├── index.ts                    public exports: Agent, SettingsPanel, SandboxStatus, SandboxSettingsPanel
├── api/                        every backend endpoint call this package makes, one file per resource
│   ├── schemas.ts                 zod schemas mirroring shared-types, .strict() — see "API validation" below
│   ├── projects.ts                 fetchProjects, createProject, updateProjectSandboxPolicy, deleteProject
│   ├── agents.ts                    fetchAgents, createAgent, updateAgent, deleteAgent,
│   │                                 updateAgentSandboxPolicy, fetchAgentSessions, createAgentSession
│   ├── chats.ts                      fetchChats, createChat, updateChat, deleteChat, moveChat,
│   │                                  updateChatSandboxPolicy, fetchChatSessions, createChatSession
│   ├── sessions.ts                    fetchSession, updateSession, deleteSession, fetchSessionMessages,
│   │                                   updateSessionSandboxPolicy, triggerEmbed, submitRagText —
│   │                                    all keyed by session_id alone
│   ├── chat.ts                         sendChatMessage — the plain REST `chat` flow only
│   ├── providers.ts                     fetchProviderSettings, updateProviderSettings
│   └── index.ts                          barrel (internal use — not re-exported from the package root)
├── utils/
│   ├── http-client.ts             apiGet/apiPost/apiPut/apiDelete + ApiError/ApiSchemaError — validating fetch wrapper
│   ├── clamp.ts                     clamp(value, min, max)
│   ├── render-payload.ts             deriveRenderPayload(messages, agentDisplayName) — last assistant message → RenderContentPayload
│   └── index.ts
├── hooks/
│   ├── use-chat.ts                useChat — the plain REST `chat` flow, thin hook over `chat-slice`
│   ├── use-workspace.ts             useWorkspace — loads/manages the Project→(Agent|Chat)→Session tree,
│   │                                 thin hook over `workspace-slice`
│   ├── use-agent-chat.ts             useAgentChat — the live AG-UI streaming client for one Agent session,
│   │                                  now also accumulates trace: TraceStep[]
│   ├── use-sse-status.ts              useSseStatus<T> — generic EventSource subscription hook
│   └── index.ts
├── components/
│   ├── agent/                     the 3-pane shell + the plain-chat flow, one component per file
│   │   ├── agent.tsx                 Agent (public) — Redux Provider + ThemeProvider wrapper
│   │   ├── agent-layout.tsx           AgentLayout — 3-column layout, local UI state, ChatThread/AgentThread switch
│   │   ├── history-rail.tsx            HistoryRail — left pane: NewMenu + Project→(Agent|Chat)→Session tree
│   │   ├── new-menu.tsx                 NewMenu — "New" dropdown (New Chat / New Agent / New Project)
│   │   ├── project-tree-node.tsx         ProjectTreeNode — one project row, expands to its agents/chats
│   │   ├── agent-tree-node.tsx            AgentTreeNode — one agent row within a project
│   │   ├── chat-tree-node.tsx              ChatTreeNode — one chat row (project-scoped or standalone)
│   │   ├── chat-thread.tsx                  ChatThread — center pane for the plain `chat` flow
│   │   ├── message-list.tsx                  MessageList — scrollable history for ChatThread
│   │   ├── message-bubble.tsx                 MessageBubble — one `ChatApiMessage`
│   │   ├── composer.tsx                        Composer — the input box, shared by ChatThread and AgentThread
│   │   ├── session-switcher.tsx                 SessionSwitcher — session <Select>
│   │   ├── resize-handle.tsx                     ResizeHandle — output-pane drag handle
│   │   ├── output-panel.tsx                       OutputPanel — right pane, renders the active profile's registered
│   │   │                                            renderer via getAgentRenderer once agentKey+payload are set
│   │   ├── rag-upload-sheet.tsx                     RagUploadSheet — "Add research information": pasted text /
│   │   │                                             .txt upload, POSTs to submitRagText, live stage progress via SSE
│   │   └── index.ts                                exports only Agent/AgentProps — see "Barrel policy" below
│   ├── agent-thread/                center pane for the live Agent (AG-UI streaming) flow
│   │   ├── agent-thread.tsx            AgentThread — header (+ RAG upload trigger, gated to `research`) +
│   │   │                                AgentMessageList + Composer, driven by props (useAgentChat lifted to AgentLayout)
│   │   ├── agent-message-list.tsx       AgentMessageList — scrollable AG-UI Message[] history, auto-scroll
│   │   ├── agent-message-bubble.tsx      AgentMessageBubble — one AG-UI Message (text content only)
│   │   └── index.ts
│   ├── creation-sheets/             the four "New"/"Move" modal forms, Sheet-based
│   │   ├── new-project-sheet.tsx       NewProjectSheet — name only
│   │   ├── new-chat-sheet.tsx           NewChatSheet — name + optional project
│   │   ├── new-agent-sheet.tsx           NewAgentSheet — project (existing or inline-created) + name + agent_key
│   │   ├── move-chat-sheet.tsx            MoveChatSheet — move a chat into/out of a project
│   │   └── index.ts
│   ├── settings-panel/             SettingsPanel — per-role provider config editor (exported, NOT rendered by Agent)
│   │   ├── settings-panel.tsx
│   │   ├── role-editor.tsx           RoleEditor (internal — not exported from the barrel)
│   │   └── index.ts
│   ├── sandbox-settings-panel/       SandboxSettingsPanel — sharing/attach policy editor (IS rendered by Agent)
│   │   ├── sandbox-settings-panel.tsx   picks which sections to render based on the selected target
│   │   ├── agent-policy-section.tsx
│   │   ├── chat-policy-section.tsx       gated on chat.project_id != null
│   │   ├── session-policy-section.tsx
│   │   └── index.ts
│   └── sandbox-status/                SandboxStatus — live container status badge
│       ├── sandbox-status.tsx
│       └── index.ts
└── store/
    ├── store.ts                    configureStore({ chat: chatReducer, workspace: workspaceReducer })
    ├── hooks.ts                     useAppDispatch/useAppSelector — kept beside the store (Redux convention),
    │                                 distinct from the feature-level hooks/ folder above
    ├── chat-slice.ts                 the plain `chat` flow's message state — Chat-entity-keyed, calls ../api/*
    └── workspace-slice.ts             the sidebar tree's data: projects, per-project agents/chats,
                                        standaloneChats, expandedProjectIds, and the `selection` discriminated union
```

## The hierarchy this UI implements

`Project -> (Agent | Chat) -> Session`, matching the backend (`backend/docs/libs/krutrim_agent_management.md`):

- **Project** — a named container. Optional; a Chat can exist standalone.
- **Agent** — always lives inside a Project. Has an `agent_key` (a registered profile, e.g. `experiment`, `research`) and talks over the live AG-UI streaming protocol (`POST /agents/{agent_id}`).
- **Chat** — the plain REST flow (`POST /api/chat`). Optionally scoped to a Project; movable between projects/standalone via `MoveChatSheet`.
- **Session** — the smallest unit of conversation for both Agent and Chat. Each has its own sandbox policy.

`workspace-slice.ts`'s `selection` field (`{kind:'chat', chatId, sessionId} | {kind:'agent', agentId, sessionId} | null`) is what `AgentLayout` reads to decide whether to render `ChatThread` or `AgentThread` in the center pane, and what `SandboxSettingsPanel` reads to decide which policy sections apply.

## Two conversation flows, two hooks, two center-pane components

This package genuinely has two separate chat implementations, not one shared abstraction — they talk to different backend protocols with different data shapes, so forcing a shared component would fight both:

| | Plain `chat` flow | Live `Agent` flow |
|---|---|---|
| Backend route | `POST /api/chat` (one-shot REST) | `POST /agents/{agent_id}` (AG-UI SSE stream) |
| Hook | `useChat` (`hooks/use-chat.ts`) | `useAgentChat` (`hooks/use-agent-chat.ts`) — called from `AgentLayout`, not `AgentThread` (see below) |
| Message type | `ChatApiMessage` (`shared-types`) | `Message` (`@ag-ui/client`/`@ag-ui/core`) |
| Center-pane component | `ChatThread` (`components/agent/`) | `AgentThread` (`components/agent-thread/`) — takes `messages`/`isRunning`/`error`/`sendMessage` as props |
| History on reopen | `GET /api/sessions/{id}/messages` | **No route exists yet** — see gap below |

**`useAgentChat`** (`hooks/use-agent-chat.ts`) constructs one `@ag-ui/client` `HttpAgent` per `(backendUrl, agentId, sessionId)` via `useMemo`, pointed at `${backendUrl}/agents/${agentId}?session_id=...`, with `threadId: sessionId`. Two behaviors here were confirmed empirically against a running backend (not just read off `.d.ts` files), and both are load-bearing:

- `threadId: sessionId` is what makes the backend's per-session LangGraph checkpoint resume correctly — a *new* `HttpAgent` instance, with no local message history, correctly recalls context from a prior run against the same session.
- `agent.subscribe({ onMessagesChanged })` is what fires on every message-list mutation, including the incremental content growth of a streaming assistant reply (`""` → `"h"` → `"hello"` → ...) — this is the hook's actual "live token-by-token updates" mechanism, not `onEvent`/`onTextMessageContentEvent`.

`sendMessage(text)` calls `agent.addMessage(...)` (optimistic local echo) then `agent.runAgent()`; `isRunning`/`error` are plain local state set around that call.

**`useAgentChat` now also returns `trace: TraceStep[]`** (the type is imported from `@krutrim_agent/agent-renderers`, not declared in this package — see [`agent-renderers.md`](agent-renderers.md#typests) for why it lives on that side). It subscribes to several more `@ag-ui/client` events beyond `onMessagesChanged`/`onRunErrorEvent`: `onStepStartedEvent`/`onStepFinishedEvent`, `onToolCallStartEvent`/`onToolCallArgsEvent`/`onToolCallEndEvent`, and `onReasoningMessageStartEvent`/`...ContentEvent`/`...EndEvent` — a second, independent view of the same run (step/tool-call/reasoning events from the lower-level `@ag-ui/core` stream) that `onMessagesChanged` alone never surfaces, since tool/system messages are intentionally absent from `messages` (see `agent-message-list.tsx`). `trace` resets to `[]` on every session change, same as `messages`/`error`. Built for the research renderer's trace panel (task below), but generic enough for any profile.

**`useAgentChat` moved from `AgentThread` to `AgentLayout`** (lifted). `AgentThread` no longer calls the hook itself — it takes `messages`/`isRunning`/`error`/`sendMessage` as props, so its sibling `OutputPanel` (also rendered by `AgentLayout`) can read the exact same live message list to derive its own canvas payload (see `utils/render-payload.ts` below), without a second independent subscription to the same AG-UI run.

**Known accepted gap**: `GET /api/sessions/{id}/messages` only ever returns data for Chat-owned sessions (it reads `Storage.read_checkpoint`, a plain JSON blob only the `chat` graph writes). An Agent-owned session's real history lives in its LangGraph `AsyncSqliteSaver` file, which has no REST route exposing it today. Practical effect: reopening a past Agent session shows an empty `AgentThread` until the next message is sent — the model still has full context internally (LangGraph reloads it via `thread_id`), so replies stay coherent; the history just isn't rendered on load. A `GET /agents/{agent_id}/sessions/{id}/history` route would be the natural fix if this turns out to matter in practice.

`AgentMessageBubble` itself still renders text content only — but the assistant's rendered *output* (as opposed to the conversational bubble) now does go somewhere: see `OutputPanel` below, which is `libs/agent-renderers`'s first real consumer.

## `utils/render-payload.ts`

`deriveRenderPayload(messages: Message[], agentDisplayName: string) -> RenderContentPayload | null` — finds the last `assistant`-role message in the live AG-UI list, extracts its text via `messageText` (from `use-agent-chat.ts`), and wraps it as `{ kind: 'markdown', title: agentDisplayName, content: text }`. Hardcodes `'markdown'` rather than inspecting content to guess a kind, since every agent profile's output today is markdown per `backend/harness/prompts/format/markdown/markdown-spec.md` (tables/math/images are embedded *within* the markdown, not surfaced as a separate `chart`/`news` kind). Returns `null` while there's no assistant output yet, so `OutputPanel` keeps its placeholder. Called from `AgentLayout`, once, over the same `agentChat.messages` list `AgentThread` renders.

## `components/agent/output-panel.tsx` — no longer a placeholder

`OutputPanel` now takes `agentKey: string | null`, `payload: RenderContentPayload | null`, and `trace?: TraceStep[]` as props. When both `agentKey` and `payload` are present, it calls `getAgentRenderer(agentKey)` (from `@krutrim_agent/agent-renderers`, a new dependency for this package — the first real consumer of `getAgentRenderer` anywhere in the codebase) and renders the result, passing `payload`/`trace` through. Falls back to the old placeholder text (different copy depending on whether an agent is even selected) when either is missing — e.g. no assistant reply yet, or the plain `chat` flow (no `agentKey`) is active.

## `components/agent/rag-upload-sheet.tsx` — `RagUploadSheet`

"Add research information": a pasted-text textarea plus a `.txt` file picker (read client-side via the File API — v1 RAG ingestion is text-only, no binary upload endpoint, so both inputs feed the same request). Submits via the new `submitRagText` API function (`api/sessions.ts`), then polls live stage progress (`extracting → chunking → embedding → indexing`) via `useSseStatus<RagIngestJobProgressEvent>` against `GET /api/status/jobs/{job_id}`.

Triggered from a new button in `AgentThread`'s header (`BookOpen` icon from `lucide-react`), gated to `agent.agent_key === 'research'` only via a `RAG_ENABLED_AGENT_KEYS` set in `agent-thread.tsx` — update that set (and this doc) together if RAG ingestion becomes available to more profiles.

**Lives in `agent-ui`, not `agent-renderers/src/research/`**, despite being research-specific UI today — because it needs `submitRagText`/`useSseStatus`, both owned by `agent-ui`'s own `api`/`hooks`, and `agent-renderers` cannot depend on `agent-ui` (the dependency direction is the other way: `agent-ui` already depends on `agent-renderers` for `getAgentRenderer`, so a reverse dependency here would be circular). The backend route itself is a plain session-level endpoint, not research-specific, so gating which profile sees the trigger is the only actually research-specific piece, and that gate lives in `agent-thread.tsx`, not in this component.

## API validation — how a backend contract change gets caught

Every network call in this package goes through `utils/http-client.ts`'s `apiRequest()` (via `apiGet`/`apiPost`/`apiPut`/`apiDelete`), which does two things after `fetch()` resolves:

1. **Non-2xx → `ApiError`.** Carries `status` and `detail` (the backend's FastAPI-style `{"detail": "..."}` body when present, else the raw status line).
2. **2xx but body doesn't match the expected zod schema → `ApiSchemaError`.** Every schema in `api/schemas.ts` is `.strict()` — an object with an unexpected extra field fails validation, not just a missing/mismatched one. `ApiSchemaError.issues` is the full list of zod issues (path + message), and its `.message` renders them inline.

**Why this matters for backend changes**: if `krutrim_agent_backend` renames a field, adds a new one to a response, or changes a type, the old flat `fetch(...).then((r) => r.json())` pattern would silently pass whatever JSON came back straight into Redux state or component props — a missing field just becomes `undefined` somewhere downstream, often nowhere near where the actual problem is. With this wrapper, the exact same change throws `ApiSchemaError` at the call site, with a message naming the field and what didn't match — so a backend/frontend contract drift is a loud, specific, immediate error instead of a silent bug hunt.

Each schema is also a **compile-time** check: it's assigned to a `z.ZodType<T>`-typed const where `T` is the corresponding hand-written interface from `@krutrim_agent/shared-types` (e.g. `export const projectSchema: z.ZodType<Project> = z.object({...}).strict();`). If a schema's shape doesn't structurally match the interface it claims to validate, the assignment itself fails to typecheck — see the comment at the top of `api/schemas.ts` for the one exception (the `ModelSettings` discriminated union's variants can't carry that annotation individually without breaking `z.discriminatedUnion`'s narrowing; the check happens at the union level instead).

**SSE status events are the deliberate exception.** `containerStatusEventSchema` (used by `useSseStatus`/`SandboxStatus`) is *not* `.strict()`, and a validation failure there is swallowed (keeps the last-known-good value) rather than thrown — a live status stream should degrade gracefully on one malformed frame, not tear down the whole subscription. That's a different failure mode than a one-shot REST call, where throwing immediately is the right behavior. See the comment on `containerStatusEventSchema` in `api/schemas.ts`.

**AG-UI streaming is a separate exception, deliberately outside this validation layer.** `useAgentChat` talks to `POST /agents/{agent_id}` through `@ag-ui/client`'s `HttpAgent`, not through `utils/http-client.ts` — the AG-UI protocol has its own event/message schema owned by `@ag-ui/core`, so there's nothing for this package's zod schemas to validate there.

## Barrel policy — what's actually exported where

Two different kinds of `index.ts` exist in this tree, and they mean different things:

- **`api/index.ts`, `utils/index.ts`, `hooks/index.ts`** — full `export *` barrels, meant for imports *within* this package (e.g. `components/agent/agent-layout.tsx` does `import { useChat, useWorkspace } from '../../hooks'`).
- **`components/<feature>/index.ts`** — a curated re-export of only that feature's intended public surface (e.g. `components/agent/index.ts` exports only `Agent`/`AgentProps`; `components/agent-thread/`, `components/creation-sheets/` etc. export their full internal surface since they're consumed directly by sibling components within this package, not re-exported from the package root).

The package root `src/index.ts` re-exports exactly the same four things it always has (`Agent`, `SettingsPanel`, `SandboxStatus`, `SandboxSettingsPanel`, plus their prop types) — **the public API surface is unchanged**. `api/`, `utils/`, `hooks/`, `agent-thread/`, and `creation-sheets/` are not exported from the package root; they're internal to this package today. If another package ever needs one of these directly, add it to `src/index.ts` deliberately rather than blanket-exporting.

## `components/settings-panel/` and `components/sandbox-settings-panel/`

- `settings-panel.tsx` (state + fetch/save orchestration, via `api/providers.ts`) + `role-editor.tsx` (one role's form, unexported).
- `sandbox-settings-panel.tsx` picks which of `agent-policy-section.tsx` / `chat-policy-section.tsx` / `session-policy-section.tsx` to render based on the selected target (`SandboxSettingsTarget`) — all three are presentational, controlled by props, no `fetch` of their own. `chat-policy-section` only renders when the chat has a `project_id`.

Both container components catch `ApiError` specifically (showing `err.detail`) instead of parsing `res.json()` inline.

## `components/sandbox-status/`

Unchanged behavior; `sandbox-status.tsx` imports `useSseStatus` from `../../hooks`.

## Dependencies worth knowing

**`zod`** (root `package.json`) — the runtime schema library backing `api/schemas.ts` and `utils/http-client.ts`. **`@radix-ui/react-dropdown-menu`** (new, backs `libs/ui`'s `DropdownMenu`, used by `NewMenu`). `@reduxjs/toolkit` + `react-redux` back the store; `@radix-ui/react-*` (via `libs/ui`) back `Select`/`Sheet`/`ScrollArea`/`DropdownMenu`. **`@ag-ui/client`/`@ag-ui/core`** — previously listed but unused; now the live streaming client backing `useAgentChat`. **`@krutrim_agent/agent-renderers`** — new dependency, first pulled in by `OutputPanel`'s `getAgentRenderer` call (see above); previously nothing in the codebase imported this package at all.

Same caveat as before: `HistoryRail`'s user block ("Vishesh Panchal" / `visheshpanchal145@gmail.com`) is a **literal string in the component**, not derived from any auth system.
