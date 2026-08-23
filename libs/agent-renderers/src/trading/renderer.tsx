import { Badge } from '@krutrim_agent/ui';

import { ChartView } from '../chart-view';
import { NewsView } from '../news-view';
import { ProseMarkdown } from '../prose';
import type { AgentRendererProps } from '../types';

/**
 * A genuinely custom screen (not just the default renderer re-exported):
 * a persistent "not financial advice" footer on every render, regardless of
 * `kind`, plus a badge naming the content shape. Still composes the shared
 * `ChartView`/`NewsView` for chart/news kinds rather than reimplementing them.
 */
export function TradingRenderer({ payload }: AgentRendererProps) {
  return (
    <div className="mx-auto flex max-w-3xl flex-col px-6 py-8 lg:px-8">
      <header className="mb-6 flex items-start justify-between gap-4 border-b border-border pb-4">
        <div>
          <span className="mb-1 block font-mono text-xs uppercase tracking-widest text-primary">Trading Analysis</span>
          <h2 className="font-mono text-xl font-semibold text-foreground">{payload.title}</h2>
        </div>
        <Badge>{payload.kind}</Badge>
      </header>

      {payload.kind === 'chart' ? (
        <ChartView content={payload.content} />
      ) : payload.kind === 'news' ? (
        <NewsView content={payload.content} />
      ) : (
        <ProseMarkdown content={payload.content} />
      )}

      <footer className="mt-8 border-t border-dashed border-border pt-3 font-mono text-xs uppercase tracking-wide text-destructive">
        Not financial advice — informational only.
      </footer>
    </div>
  );
}
