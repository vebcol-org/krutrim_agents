import { useMemo, useState } from 'react';
import type { ChartComponentProps } from '../chart-registry';
import { EmptyState } from '../chart-states';
import { useDashboard } from '../../context/use-dashboard';

type SortState = { field: string; direction: 'asc' | 'desc' } | null;

/**
 * Plain sortable HTML table. Unlike the ECharts-backed types, table owns its
 * own "load more" affordance instead of auto-fetching everything — see
 * useLazyDataSource's `autoFetchAll` and docs/agent-dashboard/data-loading.md.
 */
export function TableChart({ chart, rows, isLoading, hasMore, onLoadMore, loadedCount, total }: ChartComponentProps) {
  const { workbook } = useDashboard();
  const [sort, setSort] = useState<SortState>(null);

  const columns = useMemo(() => {
    const dataSource = workbook.dataSources.find((ds) => ds.id === chart.dataSourceId);
    if (dataSource) return dataSource.fields.map((f) => f.name);
    return rows.length > 0 ? Object.keys(rows[0]) : [];
  }, [workbook, chart.dataSourceId, rows]);

  const sortedRows = useMemo(() => {
    if (!sort) return rows;
    const { field, direction } = sort;
    return [...rows].sort((a, b) => {
      const av = a[field] ?? '';
      const bv = b[field] ?? '';
      if (av === bv) return 0;
      const cmp = av < bv ? -1 : 1;
      return direction === 'asc' ? cmp : -cmp;
    });
  }, [rows, sort]);

  const toggleSort = (field: string) => {
    setSort((prev) => (prev?.field === field ? { field, direction: prev.direction === 'asc' ? 'desc' : 'asc' } : { field, direction: 'asc' }));
  };

  if (rows.length === 0 && !isLoading) return <EmptyState />;

  return (
    <div className="kdash-table-wrap">
      <table className="kdash-table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col} onClick={() => toggleSort(col)}>
                {col}
                {sort?.field === col ? (sort.direction === 'asc' ? ' ↑' : ' ↓') : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row, i) => (
            <tr key={i}>
              {columns.map((col) => (
                <td key={col}>{String(row[col] ?? '')}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {hasMore && (
        <button type="button" className="kdash-table-load-more" onClick={onLoadMore} disabled={isLoading}>
          {isLoading ? 'Loading…' : `Load more${total !== undefined ? ` (${loadedCount}/${total})` : ''}`}
        </button>
      )}
    </div>
  );
}
