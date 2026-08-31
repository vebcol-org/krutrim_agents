import type { ChartContent } from '@krutrim_agent/shared-types';

const PALETTE = ['var(--color-primary)', 'var(--color-success)', 'var(--color-destructive)', 'var(--color-muted-foreground)'];

/**
 * Minimal, dependency-free bar chart (plain divs sized by percentage height,
 * no SVG/charting library). Deliberately simple: swap in a real charting
 * library (recharts, visx, ...) here if a renderer needs more than grouped
 * bars.
 */
export function ChartView({ content }: { content: string }) {
  let data: ChartContent;
  try {
    data = JSON.parse(content);
  } catch {
    return <p className="text-sm text-muted-foreground">Couldn't parse chart data.</p>;
  }
  if (!data.labels?.length || !data.series?.length) {
    return <p className="text-sm text-muted-foreground">No chart data.</p>;
  }

  const max = Math.max(1, ...data.series.flatMap((s) => s.values.map((v) => Math.abs(v))));

  return (
    <div>
      {data.series.length > 1 && (
        <div className="mb-3 flex flex-wrap gap-4">
          {data.series.map((s, i) => (
            <span key={s.name} className="flex items-center gap-1.5 font-mono text-xs text-muted-foreground">
              <span className="size-2.5 rounded-sm" style={{ background: PALETTE[i % PALETTE.length] }} />
              {s.name}
            </span>
          ))}
        </div>
      )}
      <div className="flex h-56 items-end gap-6 border-b border-border px-2 pt-4">
        {data.labels.map((label, labelIndex) => (
          <div key={label} className="flex h-full flex-1 items-end gap-2">
            {data.series.map((s, seriesIndex) => {
              const value = s.values[labelIndex] ?? 0;
              const heightPct = Math.max(1, (Math.abs(value) / max) * 100);
              return (
                <div key={s.name} className="flex h-full min-w-0 flex-1 flex-col items-center justify-end">
                  <span className="mb-1 whitespace-nowrap font-mono text-[0.68rem] text-muted-foreground">{value}</span>
                  <div
                    className="w-full min-h-[2px] rounded-t-sm"
                    style={{ height: `${heightPct}%`, background: PALETTE[seriesIndex % PALETTE.length] }}
                  />
                </div>
              );
            })}
          </div>
        ))}
      </div>
      <div className="mt-2 flex gap-6">
        {data.labels.map((label) => (
          <span key={label} className="flex-1 truncate text-center font-mono text-xs text-muted-foreground">
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}
