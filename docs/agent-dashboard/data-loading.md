# Lazy / chunked data loading

## The problem this solves

The schema's `DataSource.data` is a plain, fully-materialized array — fine for a workbook with a few hundred rows, not fine for one backed by millions of ticks or a huge trade log. Loading everything up front before the dashboard can render anything defeats the point of a fast first paint.

## The design

This is a **runtime extension, not a schema change** — a `DataSource` can legitimately ship with `data: []` (or just a first page), and a `DataLoader` you register fills in the rest on demand:

```ts
type DataLoader = (params: {
  offset: number;
  limit: number;
  filters: ActiveFilters; // so your API can push filtering server-side instead of over-fetching
}) => Promise<{
  rows: DataRow[];
  hasMore: boolean;
  total?: number; // optional — powers a "120/50,000 loaded" progress readout
}>;
```

```tsx
<AgentDashboard
  workbook={workbook}
  dataLoaders={{
    trades_by_symbol: async ({ offset, limit, filters }) => {
      const res = await fetch(`/api/trades?offset=${offset}&limit=${limit}&region=${filters['region-filter'] ?? ''}`);
      const page = await res.json();
      return { rows: page.items, hasMore: page.hasMore, total: page.total };
    },
  }}
  chunkSize={200}
/>
```

No loader registered for a `DataSource` id, or `data` already fully populated? Nothing changes — the static-schema case behaves exactly as it always did. This is the "if we don't customize, use default" path.

## What happens per chart, by category

`ChartRenderer` (`charts/chart-renderer.tsx`) wires every chart through `useLazyDataSource` (`data/lazy-data-source.ts`) with `autoFetchAll: chart.type !== 'table'`:

- **Every chart type except `table`** (bar, line, candlestick, kpi, …): chunks are fetched automatically and continuously in the background — as each one lands, it's merged into the working row set and the chart re-renders, "filling in" progressively — until `hasMore` is `false`. This suits chart types that need the (eventual) full series to render meaningfully.
- **`table`**: fetches only the first chunk automatically, then exposes a "Load more" button (`charts/table/table-chart.tsx`) tied to `loadMore()`. Tables can represent far more rows than you'd want to blindly pull in full, so the default here is user-paced instead of eager.

## Filter changes reset the load

Changing `activeFilters` resets `useLazyDataSource`'s internal offset/rows and refetches page one against the new filter values (see the `filtersKey` effect dependency in `lazy-data-source.ts`) — the loader's `filters` param is meant for exactly this, so your backend can do the filtering instead of the client discarding rows that don't match.

## Loading/error state

`ChartComponentProps` (passed to every chart component, built-in or custom) carries `isLoading`, `hasMore`, `loadedCount`, `total`, and `onLoadMore` — the shared `LoadingBadge`/`ErrorState`/`EmptyState` components (`charts/chart-states.tsx`) use these for a small "Loading… (140 loaded)" overlay and error messaging, and any custom chart component gets the same props for free.
