import { useEffect, useRef } from 'react';
import { cn } from '@krutrim_agent/ui';
import { Brain, ChevronRight, Loader2 } from 'lucide-react';

import type { ReasoningEntry } from '../../hooks/use-agent-stream';

export interface ThinkingDisclosureProps {
  reasoning: ReasoningEntry;
}

/**
 * The collapsible "thinking" panel shown above an assistant bubble whenever the
 * model streamed reasoning tokens for that turn. **Open by default** (both chat
 * and agents) — the reader gets the chain of thought unless they choose to fold
 * it away. A plain `<details>` for a zero-dependency toggle; auto-scrolls its
 * body while tokens stream in.
 */
export function ThinkingDisclosure({ reasoning }: ThinkingDisclosureProps) {
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (reasoning.running && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [reasoning.text, reasoning.running]);

  const seconds =
    reasoning.endedAt && reasoning.startedAt
      ? Math.max(1, Math.round((reasoning.endedAt - reasoning.startedAt) / 1000))
      : null;

  return (
    <details open className="group mb-1.5 w-full rounded-md border border-border/70 bg-muted/30 text-xs">
      <summary
        className={cn(
          'flex cursor-pointer list-none items-center gap-1.5 px-2.5 py-1.5 font-medium text-muted-foreground',
          'hover:text-foreground',
        )}
      >
        <ChevronRight className="size-3.5 shrink-0 transition-transform group-open:rotate-90" />
        {reasoning.running ? <Loader2 className="size-3.5 shrink-0 animate-spin" /> : <Brain className="size-3.5 shrink-0" />}
        <span>{reasoning.running ? 'Thinking…' : seconds ? `Thought for ${seconds}s` : 'Thought process'}</span>
      </summary>
      <div
        ref={bodyRef}
        className="max-h-56 overflow-y-auto whitespace-pre-wrap border-t border-border/70 px-2.5 py-2 font-mono text-[0.7rem] leading-5 text-muted-foreground"
      >
        {reasoning.text || (reasoning.running ? '…' : '')}
      </div>
    </details>
  );
}
