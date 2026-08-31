import type { RenderContentPayload } from '@krutrim_agent/shared-types';

/** One step/tool-call/reasoning-chunk from a live AG-UI run — produced by
 * `@krutrim_agent/agent-ui`'s `useAgentChat` (from the low-level `@ag-ui/core`
 * event stream, not the `messages` array, which never carries tool/step
 * events — see that hook's docstring), consumed here so a renderer can show
 * "what the agent is doing" alongside its final answer. Defined in this
 * package (the consumer, via `AgentRendererProps`), not `agent-ui` (the
 * producer), since `agent-ui` already depends on `agent-renderers` and not
 * the other way around. */
export interface TraceStep {
  id: string;
  kind: 'tool_call' | 'step' | 'reasoning';
  label: string;
  detail?: string;
  status: 'started' | 'finished';
  timestamp: number;
}

export interface AgentRendererProps {
  payload: RenderContentPayload;
  /** `undefined` for a renderer used outside a live agent run context. */
  trace?: TraceStep[];
}

/** A per-agent canvas renderer — full creative control over the content area. */
export type AgentRendererComponent = (props: AgentRendererProps) => JSX.Element;

/**
 * How one raw assistant turn is divided between the two views of the shell:
 *
 * - `narration` — working text for the middle "work log" column (`''` = none);
 * - `output` — the finished deliverable for the output panel, or `null` when
 *   the turn hasn't produced one yet (still streaming / stopped early).
 *
 * What counts as "narration" vs "output" is agent-specific — e.g. `research`
 * splits on a `===FINAL_REPORT===` marker — so each agent registers its own
 * splitter in `registry.ts` (`getAgentTurnSplitter`); the default treats the
 * whole turn as output with no narration.
 */
export interface AssistantTurnView {
  narration: string;
  output: RenderContentPayload | null;
}

export interface TurnSplitContext {
  /** The run ended normally — not still streaming, not stopped by the user.
   *  Lets a splitter decide whether a marker-less turn is a finished answer or
   *  just a partial log. */
  finished: boolean;
  /** The agent instance's display name — used as the output payload's title. */
  title: string;
}

/** Pure text → `AssistantTurnView`. No `@ag-ui/client` / `agent-ui` deps: the
 *  shell flattens the message and picks the latest assistant turn, then calls
 *  this with the plain string. */
export type AgentTurnSplitter = (text: string, ctx: TurnSplitContext) => AssistantTurnView;
