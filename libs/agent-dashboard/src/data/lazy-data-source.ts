import { useCallback, useEffect, useRef, useState } from 'react';
import type { ActiveFilters, DataRow } from '../types';

export interface DataLoaderParams {
  offset: number;
  limit: number;
  filters: ActiveFilters;
}

export interface DataLoaderResult {
  rows: DataRow[];
  hasMore: boolean;
  total?: number;
}

/**
 * Fetches one chunk of rows for a DataSource. Not part of the schema — a
 * runtime extension point so a workbook can ship a DataSource with `data: []`
 * (or a small first page) and have the rest streamed in on demand. See
 * docs/agent-dashboard/data-loading.md.
 */
export type DataLoader = (params: DataLoaderParams) => Promise<DataLoaderResult>;

export interface LazyDataSourceState {
  rows: DataRow[];
  isLoading: boolean;
  hasMore: boolean;
  error: Error | null;
  total?: number;
  loadedCount: number;
  /** Manually fetch the next chunk (used by the table chart's "Load more"). No-op if already loading, no loader, or exhausted. */
  loadMore: () => void;
}

export interface UseLazyDataSourceOptions {
  initialRows: DataRow[];
  loader?: DataLoader;
  chunkSize?: number;
  activeFilters: ActiveFilters;
  /** true (default) = keep fetching chunks automatically until exhausted, for charts that need the full series to render meaningfully. false = only fetch on explicit loadMore() (used by the table chart). */
  autoFetchAll?: boolean;
}

/**
 * Manages chunked loading for one DataSource. When no `loader` is supplied,
 * this is a pass-through over `initialRows` — the static-schema case behaves
 * exactly as before, unchanged.
 */
export function useLazyDataSource(options: UseLazyDataSourceOptions): LazyDataSourceState {
  const { initialRows, loader, chunkSize = 200, activeFilters, autoFetchAll = true } = options;

  const [rows, setRows] = useState<DataRow[]>(initialRows);
  const [isLoading, setIsLoading] = useState(false);
  const [hasMore, setHasMore] = useState(Boolean(loader));
  const [error, setError] = useState<Error | null>(null);
  const [total, setTotal] = useState<number | undefined>(undefined);

  const offsetRef = useRef(initialRows.length);
  const cancelledRef = useRef(false);
  const loadingRef = useRef(false);
  const filtersKey = JSON.stringify(activeFilters);

  const fetchNext = useCallback(() => {
    if (!loader || cancelledRef.current || loadingRef.current) return;
    loadingRef.current = true;
    setIsLoading(true);
    void (async () => {
      try {
        const result = await loader({ offset: offsetRef.current, limit: chunkSize, filters: activeFilters });
        if (cancelledRef.current) return;
        offsetRef.current += result.rows.length;
        setRows((prev) => [...prev, ...result.rows]);
        setHasMore(result.hasMore);
        setTotal(result.total);
      } catch (err) {
        if (!cancelledRef.current) setError(err instanceof Error ? err : new Error(String(err)));
      } finally {
        loadingRef.current = false;
        if (!cancelledRef.current) setIsLoading(false);
      }
    })();
  }, [loader, chunkSize, activeFilters]);

  // Reset and refetch the first chunk whenever the loader or active filters change.
  useEffect(() => {
    cancelledRef.current = false;
    loadingRef.current = false;
    offsetRef.current = initialRows.length;
    setRows(initialRows);
    setError(null);
    setHasMore(Boolean(loader));
    setTotal(undefined);
    if (loader) fetchNext();
    return () => {
      cancelledRef.current = true;
    };
  }, [loader, filtersKey]);

  // Progressive background loading for visual/aggregate charts: keep pulling
  // chunks as each one lands, until exhausted.
  useEffect(() => {
    if (autoFetchAll && loader && hasMore && !isLoading && !error) {
      fetchNext();
    }
  }, [autoFetchAll, loader, hasMore, isLoading, error, rows.length]);

  return {
    rows,
    isLoading,
    hasMore,
    error,
    total,
    loadedCount: rows.length,
    loadMore: fetchNext,
  };
}
