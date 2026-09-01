import type { RenderContentPayload } from '@krutrim_agent/shared-types';
import { Button } from '@krutrim_agent/ui';
import { Loader2, PanelRightClose, PanelRightOpen } from 'lucide-react';

import { getOutputRenderer } from '../../screens/registry';
import type { AgentScreenModule } from '../../screens/types';

export interface OutputPanelProps {
  collapsed: boolean;
  onToggle: () => void;
  width: number;
  /** The active screen — supplies `OutputRenderer` (falls back to the default). */
  screen: AgentScreenModule;
  /** This screen produces canvas output (agent-type screens do; home / chat don't). */
  canvasCapable: boolean;
  /** `null` while there's no finished output yet (see `deriveAssistantTurn`). */
  payload: RenderContentPayload | null;
  /** A run is in flight — shows a "generating" hint instead of the empty state. */
  busy?: boolean;
}

/**
 * The right-hand "output explorer": the screen's finished answer, rendered by
 * its `OutputRenderer` (research → sectioned report + TOC). `AgentLayout` pops
 * this open automatically the moment a run finishes with output; step/tool
 * activity lives in the conversation (`AgentActivity`), not here.
 */
export function OutputPanel({ collapsed, onToggle, width, screen, canvasCapable, payload, busy }: OutputPanelProps) {
  if (collapsed) {
    return (
      <aside className="flex w-12 shrink-0 flex-col items-center gap-2 border-l border-border bg-card py-3">
        <Button variant="ghost" size="icon" onClick={onToggle} aria-label="Show output explorer">
          <PanelRightOpen className="size-4" />
        </Button>
        {busy ? (
          <Loader2 className="size-3.5 animate-spin text-muted-foreground" />
        ) : (
          payload && <span className="size-1.5 rounded-full bg-success" aria-label="Output ready" />
        )}
      </aside>
    );
  }

  const Renderer = canvasCapable ? getOutputRenderer(screen.key) : null;

  return (
    <aside className="flex shrink-0 flex-col border-l border-border bg-card" style={{ width }}>
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex min-w-0 flex-col">
          <span className="font-mono text-xs tracking-widest text-border">OUTPUT EXPLORER</span>
          {payload?.title && (
            <span className="mt-0.5 truncate text-xs text-muted-foreground">{payload.title}</span>
          )}
        </div>
        <Button variant="ghost" size="icon" onClick={onToggle} aria-label="Hide output explorer">
          <PanelRightClose className="size-4" />
        </Button>
      </header>

      {Renderer && payload ? (
        <div className="min-h-0 flex-1 overflow-y-auto">
          <Renderer payload={payload} />
        </div>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center text-muted-foreground">
          {busy ? (
            <>
              <Loader2 className="size-5 animate-spin" />
              <p>Generating the final output…</p>
            </>
          ) : (
            <p>
              {canvasCapable
                ? 'No output yet — ask a question and the agent’s finished answer will appear here.'
                : 'This view has no canvas output — the panel is here for agent types that render content.'}
            </p>
          )}
        </div>
      )}
    </aside>
  );
}
