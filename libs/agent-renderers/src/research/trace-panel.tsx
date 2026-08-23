import { Timeline, type TimelineItemData } from '@krutrim_agent/ui';

import type { TraceStep } from '../types';

const KIND_LABEL: Record<TraceStep['kind'], string> = {
  tool_call: 'Tool',
  step: 'Step',
  reasoning: 'Thinking',
};

/** `rag_tool` calls get a distinct prefix from other tools (`web_search`,
 * `fetch_url`) so a reader can spot "the agent checked your uploaded
 * context" versus "the agent searched the web" at a glance. */
function describeStep(step: TraceStep): string {
  const prefix = step.kind === 'tool_call' && step.label === 'rag_tool' ? 'RAG' : KIND_LABEL[step.kind];
  const suffix = step.status === 'started' ? '…' : '';
  return `${prefix}: ${step.label}${suffix}`;
}

function toTimelineItem(step: TraceStep): TimelineItemData {
  return {
    id: step.id,
    label: describeStep(step),
    detail: step.detail,
    status: step.status === 'finished' ? 'done' : 'active',
  };
}

export interface TracePanelProps {
  trace: TraceStep[];
}

/** The "agent thinking" panel: renders the live step/tool-call/reasoning
 * trace from `useAgentChat`'s `trace` array (see that hook's docstring) —
 * independent of the chat message list, so it shows activity the filtered
 * `AgentMessageList` never surfaces (tool/system messages). Renders nothing
 * once there's nothing to show, so an idle canvas isn't cluttered with an
 * empty panel. */
export function TracePanel({ trace }: TracePanelProps) {
  if (trace.length === 0) return null;

  return (
    <details className="mb-4 rounded border border-border bg-muted/30 px-3 py-2" open>
      <summary className="cursor-pointer font-mono text-xs uppercase tracking-widest text-muted-foreground">
        Agent activity
      </summary>
      <div className="mt-2">
        <Timeline items={trace.map(toTimelineItem)} />
      </div>
    </details>
  );
}
