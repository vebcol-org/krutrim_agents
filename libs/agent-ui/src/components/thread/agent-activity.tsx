import { useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@krutrim_agent/ui';
import {
  Brain,
  Check,
  ChevronRight,
  Database,
  Globe,
  Loader2,
  Search,
  Waypoints,
  Wrench,
  type LucideIcon,
} from 'lucide-react';

import type { TraceStep } from '../../hooks/use-agent-stream';
import { Markdown } from './markdown';

/**
 * The Claude / ChatGPT-style "what the agent is doing" panel, rendered inline
 * in the conversation just above the assistant's answer. It folds the whole
 * run — reasoning ("Thinking"), tool calls (`web_search` / `fetch_url` /
 * `rag_tool`), and graph steps — into one collapsible block:
 *
 * - while the run is live it stays open and shows a one-line status of the
 *   current activity ("Searching the web…");
 * - each row is itself a `<details>` disclosure whose body is the streamed
 *   reasoning text or the tool's args/result JSON;
 * - once the run ends it collapses to a single "Worked for Ns · N steps"
 *   summary the reader can expand again.
 *
 * Driven entirely by `useAgentStream`'s `trace` array (the low-level AG-UI
 * event stream), so it never touches the `messages` list.
 */

const TOOL_ICON: Record<string, LucideIcon> = {
  web_search: Search,
  fetch_url: Globe,
  rag_tool: Database,
};

const RUNNING_VERB: Record<string, string> = {
  web_search: 'Searching the web',
  fetch_url: 'Reading a page',
  rag_tool: 'Searching your files',
};

function stepIcon(step: TraceStep): LucideIcon {
  if (step.kind === 'reasoning') return Brain;
  if (step.kind === 'step') return Waypoints;
  return TOOL_ICON[step.label] ?? Wrench;
}

function stepTitle(step: TraceStep): string {
  if (step.kind === 'reasoning') return 'Thinking';
  return step.label;
}

/** Short present-tense status for the collapsed header while a step runs. */
function runningLabel(step: TraceStep | undefined): string {
  if (!step) return 'Working…';
  if (step.kind === 'reasoning') return 'Thinking…';
  if (step.kind === 'step') return `${step.label}…`;
  return `${RUNNING_VERB[step.label] ?? step.label}…`;
}

export interface AgentActivityProps {
  trace: TraceStep[];
  isRunning: boolean;
}

export function AgentActivity({ trace, isRunning }: AgentActivityProps) {
  const [open, setOpen] = useState(true);
  const bodyRef = useRef<HTMLDivElement>(null);

  // Open while the run is live; fold to the summary line once it finishes.
  // A later user toggle is respected until the next run starts.
  useEffect(() => {
    setOpen(isRunning);
  }, [isRunning]);

  useEffect(() => {
    if (open && isRunning && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [trace, open, isRunning]);

  const current = useMemo(
    () => [...trace].reverse().find((s) => s.status === 'started'),
    [trace],
  );

  const elapsedS = useMemo(() => {
    if (trace.length === 0) return 0;
    const first = trace[0].timestamp;
    const last = trace.reduce((m, s) => Math.max(m, s.timestamp), first);
    return Math.max(1, Math.round((last - first) / 1000));
  }, [trace]);

  if (trace.length === 0) return null;

  const live = isRunning && !!current;
  const summary = live
    ? runningLabel(current)
    : `Worked for ${elapsedS}s · ${trace.length} step${trace.length === 1 ? '' : 's'}`;

  return (
    <div className="mb-1.5 w-full max-w-[85%] overflow-hidden rounded-md border border-border/70 bg-muted/30 text-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 font-medium text-muted-foreground hover:text-foreground"
      >
        <ChevronRight className={cn('size-3.5 shrink-0 transition-transform', open && 'rotate-90')} />
        {live ? (
          <Loader2 className="size-3.5 shrink-0 animate-spin" />
        ) : (
          <Check className="size-3.5 shrink-0 text-success" />
        )}
        <span className="truncate">{summary}</span>
      </button>

      {open && (
        <div
          ref={bodyRef}
          className="max-h-72 space-y-0.5 overflow-y-auto border-t border-border/70 px-1.5 py-1.5"
        >
          {trace.map((step) => (
            <ActivityRow key={step.id} step={step} />
          ))}
        </div>
      )}
    </div>
  );
}

function ActivityRow({ step }: { step: TraceStep }) {
  const Icon = stepIcon(step);
  const running = step.status === 'started';
  const hasBody = !!step.detail && step.kind !== 'step';

  const head = (
    <>
      <ChevronRight
        className={cn(
          'size-3 shrink-0 transition-transform',
          hasBody ? 'group-open:rotate-90' : 'opacity-0',
        )}
      />
      <Icon className="size-3.5 shrink-0" />
      <span className="truncate font-medium">{stepTitle(step)}</span>
      {running ? (
        <Loader2 className="ml-auto size-3 shrink-0 animate-spin text-muted-foreground" />
      ) : (
        <Check className="ml-auto size-3 shrink-0 text-success" />
      )}
    </>
  );

  if (!hasBody) {
    return (
      <div
        className={cn(
          'flex items-center gap-1.5 rounded px-1.5 py-1 text-muted-foreground',
          step.kind === 'step' && 'text-foreground/70',
        )}
      >
        {head}
      </div>
    );
  }

  return (
    <details className="group rounded" open={running}>
      <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded px-1.5 py-1 text-muted-foreground hover:bg-muted/60 hover:text-foreground">
        {head}
      </summary>
      {step.kind === 'reasoning' ? (
        // The model's thinking is prose — render it as markdown.
        <div className="mx-1.5 mb-1 mt-0.5 max-h-72 overflow-auto rounded bg-muted px-2 py-1.5 text-[0.72rem] text-muted-foreground">
          <Markdown className="text-[0.72rem] leading-[1.15rem]">{step.detail ?? ''}</Markdown>
        </div>
      ) : (
        // Tool args / results — keep verbatim (usually JSON).
        <pre className="mx-1.5 mb-1 mt-0.5 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-muted px-2 py-1.5 font-mono text-[0.68rem] leading-4 text-muted-foreground">
          {step.detail}
        </pre>
      )}
    </details>
  );
}
