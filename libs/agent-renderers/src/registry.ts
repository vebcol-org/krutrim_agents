import { DefaultRenderer } from './default-renderer';
import { ResearchRenderer } from './research/renderer';
import { SalesRenderer } from './sales/renderer';
import { TradingRenderer } from './trading/renderer';
import type { AgentRendererComponent } from './types';

/**
 * The plugin surface for rendering. To add a new agent's screen: create
 * `<key>/renderer.tsx` and add ONE line here. Everything in
 * `@krutrim_agent/agent-ui` (the core shell) is untouched by this —
 * it only ever calls `getAgentRenderer(agentKey)`.
 */
const RENDERERS: Record<string, AgentRendererComponent> = {
  research: ResearchRenderer,
  trading: TradingRenderer,
  sales: SalesRenderer,
};

export function getAgentRenderer(agentKey: string): AgentRendererComponent {
  return RENDERERS[agentKey] ?? DefaultRenderer;
}
