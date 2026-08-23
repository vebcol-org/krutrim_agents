import { getAgentRenderer, type TraceStep } from '@krutrim_agent/agent-renderers';
import type { RenderContentPayload } from '@krutrim_agent/shared-types';
import { Button } from '@krutrim_agent/ui';
import { PanelRightClose, PanelRightOpen } from 'lucide-react';

export interface OutputPanelProps {
  collapsed: boolean;
  onToggle: () => void;
  width: number;
  /** Which registered profile's renderer to use — `null` for the plain
   * `chat` flow (no agent selected), which keeps the placeholder below. */
  agentKey: string | null;
  /** `null` while there's no assistant output yet (see `deriveRenderPayload`). */
  payload: RenderContentPayload | null;
  trace?: TraceStep[];
}

export function OutputPanel({ collapsed, onToggle, width, agentKey, payload, trace }: OutputPanelProps) {
  if (collapsed) {
    return (
      <aside className="flex w-12 shrink-0 flex-col items-center border-l border-border bg-card py-3">
        <Button variant="ghost" size="icon" onClick={onToggle} aria-label="Show output panel">
          <PanelRightOpen className="size-4" />
        </Button>
      </aside>
    );
  }

  const Renderer = agentKey ? getAgentRenderer(agentKey) : null;

  return (
    <aside className="flex shrink-0 flex-col border-l border-border bg-card" style={{ width }}>
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <span className="font-mono text-xs tracking-widest text-border">OUTPUT</span>
        <Button variant="ghost" size="icon" onClick={onToggle} aria-label="Hide output panel">
          <PanelRightClose className="size-4" />
        </Button>
      </header>

      {Renderer && payload ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <Renderer payload={payload} trace={trace} />
        </div>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center text-muted-foreground">
          <p>
            {agentKey
              ? 'No output yet — ask a question to see the agent’s response here.'
              : 'Basic chat has no canvas output — this panel is here for agent types that render content.'}
          </p>
        </div>
      )}
    </aside>
  );
}
