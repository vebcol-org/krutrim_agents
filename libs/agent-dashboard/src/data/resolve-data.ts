import type { ActiveFilters, AgentDashboardWorkbook, Chart, DataRow } from '../types';
import { applyFiltersToDataSource } from './apply-filters';
import { aggregateRows } from './aggregate';

/**
 * The full data pipeline for one chart: look up its DataSource (or use
 * `overrideRows`, which lazy loading passes in place of the static
 * `dataSource.data`), apply the filters that target it, then aggregate per
 * `chart.encoding`. Grouping key is `[x, color]` (whichever are present) —
 * covers plain, grouped, and stacked chart shapes without per-type branching.
 */
export function resolveChartRows(
  workbook: AgentDashboardWorkbook,
  chart: Chart,
  activeFilters: ActiveFilters = {},
  overrideRows?: DataRow[],
): DataRow[] {
  const dataSource = workbook.dataSources.find((ds) => ds.id === chart.dataSourceId);
  const rows = overrideRows ?? dataSource?.data ?? [];

  const filtered = applyFiltersToDataSource(rows, chart.dataSourceId, workbook.filters ?? [], activeFilters, chart.id);

  const groupFields = [chart.encoding.x, chart.encoding.color].filter((f): f is string => Boolean(f));
  const valueField = chart.encoding.y ?? chart.encoding.value;

  return aggregateRows(filtered, groupFields, valueField, chart.encoding.aggregate);
}
