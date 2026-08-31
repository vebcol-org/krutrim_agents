import { defaultSplitTurn } from './default-split';
import { DefaultRenderer } from './default-renderer';
import { ResearchRenderer } from './research/renderer';
import { researchSplitTurn } from './research/split';
import type { AgentRendererComponent, AgentTurnSplitter } from './types';

/**
 * The plugin surface for rendering. To add a new agent's screen: create
 * `<key>/renderer.tsx` and add ONE line here. Everything in
 * `@krutrim_agent/agent-ui` (the core shell) is untouched by this —
 * it only ever calls `getAgentRenderer(agentKey)`.
 */
const RENDERERS: Record<string, AgentRendererComponent> = {
  research: ResearchRenderer,
};

export function getAgentRenderer(agentKey: string): AgentRendererComponent {
  return RENDERERS[agentKey] ?? DefaultRenderer;
}

/**
 * The companion plugin surface for the work-log / output split (see
 * `AgentTurnSplitter`). An agent whose model follows a narration-then-report
 * convention registers a splitter here; everything else uses `defaultSplitTurn`
 * (whole turn = output, no work log). The shell only calls
 * `getAgentTurnSplitter(agentKey)`.
 */
const SPLITTERS: Record<string, AgentTurnSplitter> = {
  research: researchSplitTurn,
};

export function getAgentTurnSplitter(agentKey: string | null): AgentTurnSplitter {
  return (agentKey ? SPLITTERS[agentKey] : undefined) ?? defaultSplitTurn;
}
