import type { ChartComponentProps } from '../chart-registry';
import { EmptyState } from '../chart-states';

function formatNumber(n: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(n);
}

/** Big-number card, no chart engine. `encoding.target` (optional) renders as a delta line. */
export function KpiChart({ chart, rows }: ChartComponentProps) {
  const valueField = chart.encoding.value ?? chart.encoding.y;
  const targetField = chart.encoding.target;

  if (!valueField || rows.length === 0) return <EmptyState />;

  const value = Number(rows[0][valueField] ?? 0);
  const target = targetField ? Number(rows[0][targetField]) : undefined;
  const delta = target !== undefined && !Number.isNaN(target) ? value - target : undefined;

  return (
    <div className="kdash-kpi">
      <span className="kdash-muted">{chart.title ?? valueField}</span>
      <span className="kdash-kpi-value">{formatNumber(value)}</span>
      {delta !== undefined && (
        <span className={delta >= 0 ? 'kdash-kpi-delta-up' : 'kdash-kpi-delta-down'}>
          {delta >= 0 ? '▲' : '▼'} {formatNumber(Math.abs(delta))} vs target {formatNumber(target as number)}
        </span>
      )}
    </div>
  );
}
