import { describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useLazyDataSource, type DataLoader } from '../../src/data/lazy-data-source';

function makeLoader(pages: Array<{ rows: Array<Record<string, unknown>>; hasMore: boolean; total?: number }>): DataLoader {
  let call = 0;
  return vi.fn(async () => {
    const page = pages[Math.min(call, pages.length - 1)];
    call += 1;
    return page;
  });
}

describe('useLazyDataSource', () => {
  it('is a pass-through over initialRows when no loader is given', () => {
    const { result } = renderHook(() =>
      useLazyDataSource({ initialRows: [{ a: 1 }], activeFilters: {} }),
    );
    expect(result.current.rows).toEqual([{ a: 1 }]);
    expect(result.current.hasMore).toBe(false);
    expect(result.current.isLoading).toBe(false);
  });

  it('auto-fetches all chunks when autoFetchAll is true (the default, for visual charts)', async () => {
    const loader = makeLoader([
      { rows: [{ a: 1 }], hasMore: true },
      { rows: [{ a: 2 }], hasMore: false },
    ]);

    const { result } = renderHook(() => useLazyDataSource({ initialRows: [], loader, activeFilters: {} }));

    await waitFor(() => expect(result.current.hasMore).toBe(false));
    expect(result.current.rows).toEqual([{ a: 1 }, { a: 2 }]);
    expect(loader).toHaveBeenCalledTimes(2);
  });

  it('only fetches on explicit loadMore() when autoFetchAll is false (table behavior)', async () => {
    const loader = makeLoader([
      { rows: [{ a: 1 }], hasMore: true },
      { rows: [{ a: 2 }], hasMore: false },
    ]);

    const { result } = renderHook(() =>
      useLazyDataSource({ initialRows: [], loader, activeFilters: {}, autoFetchAll: false }),
    );

    await waitFor(() => expect(result.current.rows).toEqual([{ a: 1 }]));
    expect(result.current.hasMore).toBe(true);

    act(() => result.current.loadMore());
    await waitFor(() => expect(result.current.rows).toEqual([{ a: 1 }, { a: 2 }]));
    expect(result.current.hasMore).toBe(false);
  });

  it('surfaces loader errors without throwing', async () => {
    const loader: DataLoader = vi.fn().mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useLazyDataSource({ initialRows: [], loader, activeFilters: {} }));

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.message).toBe('network down');
    expect(result.current.isLoading).toBe(false);
  });

  it('resets and refetches the first chunk when activeFilters change', async () => {
    const loader = makeLoader([{ rows: [{ a: 'first' }], hasMore: false }]);
    const { result, rerender } = renderHook(
      ({ filters }) => useLazyDataSource({ initialRows: [], loader, activeFilters: filters }),
      { initialProps: { filters: { region: ['us'] } } },
    );

    await waitFor(() => expect(result.current.rows).toEqual([{ a: 'first' }]));

    rerender({ filters: { region: ['eu'] } });
    await waitFor(() => expect(loader).toHaveBeenCalledTimes(2));
  });
});
