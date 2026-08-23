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
