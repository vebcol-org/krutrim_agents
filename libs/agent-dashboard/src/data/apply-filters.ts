import type { ActiveFilters, DataRow, Filter, FilterValue } from '../types';

/** Whether a single row satisfies one active filter value, per the filter's `type`. */
export function rowMatchesFilter(row: DataRow, filter: Filter, value: FilterValue | undefined): boolean {
  if (value === undefined || value === null) return true;
  const cell = row[filter.field];

  switch (filter.type) {
    case 'categorical': {
      const selected = value as string[];
      if (!Array.isArray(selected) || selected.length === 0) return true;
      return selected.includes(String(cell));
    }
    case 'range': {
      const [min, max] = value as [number, number];
      const num = typeof cell === 'number' ? cell : Number(cell);
      return Number.isNaN(num) ? false : num >= min && num <= max;
    }
    case 'dateRange': {
      const [start, end] = value as [string, string];
      const t = new Date(String(cell)).getTime();
      const s = new Date(start).getTime();
      const e = new Date(end).getTime();
      return Number.isNaN(t) ? false : t >= s && t <= e;
    }
    case 'boolean':
      return Boolean(cell) === (value as boolean);
    case 'search': {
      const query = String(value).trim().toLowerCase();
      if (!query) return true;
      return String(cell ?? '').toLowerCase().includes(query);
    }
    default:
      return true;
  }
}

/**
 * Filters `rows` (already scoped to one DataSource) down to only the
 * `Filter`s relevant to it, per `appliesTo` (`'*'` or this exact chartId).
 */
export function applyFiltersToDataSource(
  rows: DataRow[],
  dataSourceId: string,
  filters: Filter[],
  activeFilters: ActiveFilters,
  chartId: string,
): DataRow[] {
  const relevant = filters.filter(
    (f) => f.dataSourceId === dataSourceId && (f.appliesTo.includes('*') || f.appliesTo.includes(chartId)),
  );
  if (relevant.length === 0) return rows;
  return rows.filter((row) => relevant.every((f) => rowMatchesFilter(row, f, activeFilters[f.id])));
}
