import { ChartView } from './chart-view';
import { NewsView } from './news-view';
import { ProseMarkdown } from './prose';
import type { AgentRendererProps } from '../types';

/**
 * The built-in renderer, used whenever an agent hasn't registered its own
 * (see `registry.ts`) — so a brand-new agent profile renders sensibly with
 * zero frontend work. Switches on `kind`; unrecognized kinds fall back to
 * markdown so nothing silently breaks.
 */
export function DefaultRenderer({ payload }: AgentRendererProps) {
  return (
    <div className="mx-auto max-w-3xl px-6 py-8 lg:px-8">
      <header className="mb-6 border-b border-border pb-4">
        <span className="mb-1 block font-mono text-xs uppercase tracking-widest text-primary">{payload.kind}</span>
        <h2 className="font-mono text-xl font-semibold text-foreground">{payload.title}</h2>
      </header>
      {payload.kind === 'chart' ? (
        <ChartView content={payload.content} />
      ) : payload.kind === 'news' ? (
        <NewsView content={payload.content} />
      ) : (
        <ProseMarkdown content={payload.content} />
      )}
    </div>
  );
}
