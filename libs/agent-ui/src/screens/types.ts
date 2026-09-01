import type { ComponentType } from 'react';
import type { Message } from '@ag-ui/client';
import type { Agent, Chat, SessionInfo, RenderContentPayload } from '@krutrim_agent/shared-types';

import type { ReasoningEntry } from '../hooks/use-agent-stream';

/**
 * The **screen framework**. A "screen" is the whole centre + output composition
 * for one thing the shell can have open: the `home` view, the plain `chat`
 * view, or an agent type (`research`, ...). `AgentLayout` owns the frame
 * (history rail, panels, all the hook state) and just resolves
 * `getScreen(key)` to decide what fills the middle and right columns.
 *
 * Adding a screen = a folder under `screens/<key>/` exporting an
 * `AgentScreenModule`, plus one `registerScreen(...)` line in `screens/index.ts`.
 * External repos can call `registerScreen` too (the types are re-exported from
 * the package root).
 */

/** One step / tool-call / reasoning-chunk from a live AG-UI run — produced by
 * `useAgentStream` from the low-level event stream (not the `messages` array),
 * consumed by `AgentActivity` and rebuilt from the checkpoint on reload. */
export interface TraceStep {
  id: string;
  kind: 'tool_call' | 'step' | 'reasoning';
  label: string;
  detail?: string;
  status: 'started' | 'finished';
  timestamp: number;
}

/**
 * How one raw assistant turn is divided between the two columns:
 * - `narration` — working text for the middle "work log" (`''` = none);
 * - `output` — the finished deliverable for the output panel, or `null` when
 *   the turn hasn't produced one yet (still streaming / stopped early).
 *
 * What counts as narration vs. output is screen-specific (e.g. `research`
 * splits on a `===FINAL_REPORT===` marker), so a screen registers its own
 * `turnSplitter`; the default treats the whole turn as output.
 */
export interface AssistantTurnView {
  narration: string;
  output: RenderContentPayload | null;
}

export interface TurnSplitContext {
  /** The run ended normally — not still streaming, not stopped by the user. */
  finished: boolean;
  /** The agent instance's display name — used as the output payload's title. */
  title: string;
}

/** Pure text → `AssistantTurnView`. No `@ag-ui/client` deps: the shell flattens
 *  the message and picks the latest assistant turn, then calls this with the string. */
export type AgentTurnSplitter = (text: string, ctx: TurnSplitContext) => AssistantTurnView;

export interface AgentRendererProps {
  payload: RenderContentPayload;
  /** `undefined` for a renderer used outside a live agent run context. */
  trace?: TraceStep[];
}

/** The output-panel content component for a screen — full creative control. */
export type AgentRendererComponent = ComponentType<AgentRendererProps>;

/**
 * Everything `AgentLayout` hands a screen's `Center`. The shell owns all the
 * hook state; each screen reads the slice it needs:
 * - `home` uses nothing;
 * - `chat` uses `chat`;
 * - agent-type screens use `agent`.
 * The unused slice is simply `undefined` for a given screen.
 */
export interface AgentScreenContext {
  backendUrl: string;
  onOpenSandboxSettings: () => void;
  onOpenModelSettings: () => void;

  /** Set for an agent-type screen (the live AG-UI stream). */
  agent?: {
    agent: Agent;
    sessionId: string | null;
    messages: Message[];
    trace: TraceStep[];
    /** Pre-`===FINAL_REPORT===` working text for the middle column. */
    narration: string;
    isRunning: boolean;
    error: string | null;
    interrupted: boolean;
    sendMessage: (text: string) => void;
    onStop: () => void;
  };

  /** Set for the built-in `chat` screen (the REST chat flow). */
  chat?: {
    activeChat: Chat | null;
    sessions: SessionInfo[];
    activeSessionId: string | null;
    historySessionId: string | null;
    messages: Message[];
    reasoningByMessageId: Record<string, ReasoningEntry>;
    isLoading: boolean;
    isSending: boolean;
    error: string | null;
    onSelectSession: (sessionId: string) => void;
    onNewSession: () => void;
    onSend: (text: string) => void;
    onEnsureSession: () => Promise<string | null>;
  };
}

/**
 * The plugin unit. A screen owns the centre pane (`Center`) and optionally the
 * output panel (`OutputRenderer`) and the work-log/output split (`turnSplitter`);
 * the two optionals fall back to the `default` behaviour.
 */
export interface AgentScreenModule {
  /** Registry key: an `agent_key` (`research`, ...) or a built-in (`home` / `chat` / `default`). */
  key: string;
  /** Human label — menus and the output-panel header. */
  displayName: string;
  /** The centre pane. */
  Center: ComponentType<AgentScreenContext>;
  /** Right-column content renderer; falls back to `DefaultRenderer`. */
  OutputRenderer?: AgentRendererComponent;
  /** Work-log vs. finished-output split; falls back to `defaultSplitTurn`. */
  turnSplitter?: AgentTurnSplitter;
}
