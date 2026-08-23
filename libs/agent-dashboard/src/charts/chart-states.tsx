/** Small shared overlays used by every chart engine (ECharts, lightweight-charts, table, kpi) for the states resolve-data/lazy-data-source can produce. */

export function EmptyState({ message = 'No data.' }: { message?: string }) {
  return <div className="kdash-empty-state kdash-muted">{message}</div>;
}

export function ErrorState({ message }: { message: string }) {
  return <div className="kdash-error-state">{message}</div>;
}

export function LoadingBadge({ loadedCount, total }: { loadedCount: number; total?: number }) {
  return (
    <div
      className="kdash-muted"
      style={{ position: 'absolute', top: 4, right: 8, fontSize: '0.7rem', pointerEvents: 'none' }}
    >
      Loading{total !== undefined ? ` ${loadedCount}/${total}` : `… (${loadedCount} loaded)`}
    </div>
  );
}
