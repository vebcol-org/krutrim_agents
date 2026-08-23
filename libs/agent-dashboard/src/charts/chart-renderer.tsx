import { useMemo } from 'react';
import type { Chart } from '../types';
import { useDashboard } from '../context/use-dashboard';
import { resolveChartRows } from '../data/resolve-data';
import { useLazyDataSource } from '../data/lazy-data-source';
import { ErrorState } from './chart-states';

export interface ChartRendererProps {
  chart: Chart;
}

/**
 * One chart's full pipeline: resolve its DataSource, wire lazy loading (a
 * no-op pass-through when no loader is registered for it), resolve rows
 * through the active filters + aggregation, then hand off to whatever
 * component is registered for `chart.type` (built-in or overridden — see
 * chart-registry.ts).
 */
export function ChartRenderer({ chart }: ChartRendererProps) {
  const { workbook, activeFilters, dataLoaders, chunkSize, getChartComponent, themeTokens, echartsThemeName } = useDashboard();
  const dataSource = workbook.dataSources.find((ds) => ds.id === chart.dataSourceId);
  const loader = dataLoaders[chart.dataSourceId];

  const lazy = useLazyDataSource({
    initialRows: dataSource?.data ?? [],
    loader,
    chunkSize,
    activeFilters,
    autoFetchAll: chart.type !== 'table',
  });

  const rows = useMemo(
    () => resolveChartRows(workbook, chart, activeFilters, lazy.rows),
    [workbook, chart, activeFilters, lazy.rows],
  );

  const Component = getChartComponent(chart.type);

  return (
    <div className="kdash-panel">
      {chart.title && <div className="kdash-panel-title">{chart.title}</div>}
      <div className="kdash-panel-body">
        {!dataSource ? (
          <ErrorState message={`Unknown dataSourceId "${chart.dataSourceId}"`} />
        ) : lazy.error ? (
          <ErrorState message={lazy.error.message} />
        ) : !Component ? (
          <ErrorState message={`No renderer registered for chart type "${chart.type}"`} />
        ) : (
          <Component
            chart={chart}
            rows={rows}
            isLoading={lazy.isLoading}
            loadedCount={lazy.loadedCount}
            total={lazy.total}
            hasMore={lazy.hasMore}
            onLoadMore={lazy.loadMore}
            themeTokens={themeTokens}
            echartsThemeName={echartsThemeName}
          />
        )}
      </div>
    </div>
  );
}
