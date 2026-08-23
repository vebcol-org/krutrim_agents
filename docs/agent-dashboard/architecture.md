# Architecture

## The pipeline, end to end

```
<AgentDashboard workbook>
  └─ DashboardProvider              (context/dashboard-context.tsx)
       │  owns: activeFilters, theme tokens, dataLoaders, per-instance registry overrides
       ├─ FilterBar                 (filters/filter-bar.tsx)
       │    renders one control per workbook.filters[], via filter-registry
       ├─ PageTabs                  (layout/page-tabs.tsx)
       │    tab per workbook.pages[] (hidden for a single page)
       └─ DashboardGrid             (layout/dashboard-grid.tsx)
            CSS Grid from the active page's layout[]
            └─ ChartRenderer × N    (charts/chart-renderer.tsx)   — one per layout item
                 1. look up chart.dataSourceId in workbook.dataSources
                 2. useLazyDataSource  → chunked rows if a loader is registered, else pass-through
                 3. resolveChartRows  → apply matching Filters, then aggregate per encoding
                 4. look up chart.type in chart-registry → render that component with the resolved rows
```

Every arrow above is a real module boundary — `resolveChartRows`, `useLazyDataSource`, and the registries are all exported from the package root specifically so they're independently testable and reusable if an app wants to build its own layout around the same pieces (see `api.md`).

## Why a registry, not a switch statement

`chart-registry.ts` and `filter-registry.ts` are both `Map<Type, Component>` behind `register*`/`get*` functions, not a big `switch (chart.type)` inside `ChartRenderer`. Two reasons:

1. **The user's own requirement**: "customize from application, and if we don't, use default." A `switch` can't be partially overridden from outside the file; a registry can — `registerChartRenderer('bar', MyBarComponent)` replaces the built-in globally, or `<AgentDashboard chartRenderers={{ bar: MyBarComponent }}>` overrides it for one dashboard instance only (layered on top of the registry in `DashboardProvider`, never mutating it — see `dashboard-context.tsx`'s `getChartComponent`).
2. **Unknown types degrade gracefully**: `getChartRenderer(type)` returning `undefined` renders a clear "no renderer registered" message instead of a compile-time exhaustiveness error, which matters if a workbook ever adds a `type` this version of the package doesn't know about yet.

`registerBuiltinCharts()`/`registerBuiltinFilters()` (`charts/register-builtins.ts`, `filters/register-builtins.ts`) populate the registries with every built-in on first import of `agent-dashboard.tsx` — idempotent, so importing the package multiple times or in tests never double-registers.

## Why two chart engines

- **Apache ECharts** renders 13 of the 16 types (bar/line/area/scatter/pie/heatmap/boxplot/radar/funnel/sankey/network_graph/geo_choropleth/gauge) — one library, one theme system, one lifecycle hook (`use-echarts-instance.ts`) reused by every type via `createEChartsChart` (`charts/echarts/create-echarts-chart.tsx`), which just wraps an `(rows, encoding) -> EChartsOption` pure function as a full `ChartComponent`. Adding a 14th ECharts type is "write one option-builder function, one one-line file."
- **`lightweight-charts`** (TradingView's own open-source, Apache-2.0 charting library — not the commercial "TradingView Charting Library", which isn't npm-installable) renders `candlestick` alone. OHLC financial charts have enough TradingView-specific UX conventions (crosshair, price scale, time scale) that reimplementing them on ECharts' generic candlestick series would be a worse trading experience for no real benefit, so it gets its own small lifecycle hook (`charts/trading/use-lightweight-chart.ts`).
- **`table`** and **`kpi`** need no chart engine at all — plain HTML/CSS, since a sortable table and a big-number card don't benefit from a canvas renderer.

## Data pipeline details

- **Filtering** (`data/apply-filters.ts`): a `Filter` only narrows rows for the `DataSource` it names (`filter.dataSourceId`) and only for charts it targets (`appliesTo: ['*']` or an exact chart id) — see `filters.md`.
- **Aggregation** (`data/aggregate.ts`): groups by `[encoding.x, encoding.color]` (whichever are present) and reduces `encoding.y ?? encoding.value` via `encoding.aggregate`. `aggregate: 'none'` (or omitted) is a deliberate no-op — the schema's own doc comment says the agent may have already pre-aggregated the data, and `boxplot` specifically needs raw (non-aggregated) rows to compute its five-number summary itself.
- **Lazy loading** (`data/lazy-data-source.ts`): see `data-loading.md` for the full design — the short version is `resolveChartRows`'s `overrideRows` parameter lets `ChartRenderer` swap in progressively-fetched rows in place of `dataSource.data` without either module knowing about the other's existence.

## Layout model

`layout/dashboard-grid.tsx` is intentionally **static** in the drag/resize sense — CSS Grid computed from `page.layout[].{x,y,w,h}` (12 columns, per the schema's react-grid-layout convention), no drag/resize. The schema's shape is compatible with a future drag-and-drop editor, but rendering (this package's whole job right now) doesn't need one, and pulling in `react-grid-layout` as a runtime dependency for a feature nobody asked for would be exactly the kind of premature abstraction worth avoiding.

### Responsive layout

The grid itself *is* responsive, via plain CSS — no JS resize listeners. `DashboardGrid` precomputes, per layout item, the CSS custom properties three media-query tiers in `theme.css` (`.kdash-grid`/`.kdash-grid-item`) switch between:

| Viewport | Columns | What changes |
|---|---|---|
| `>1024px` (desktop) | 12 | The schema's native layout, unchanged. |
| `641–1024px` (tablet) | 6 | `x`/`w` proportionally rescaled onto 6 columns via `layout/scale-span.ts`'s `scaleSpan` (e.g. two items at `x:0,w:6`/`x:6,w:6` become `x:0,w:3`/`x:3,w:3` — still side by side, still non-overlapping). |
| `<=640px` (phone) | 1 | Every item spans the full width; `x` becomes meaningless so it's dropped, but `h` (row units) is kept via `grid-row: auto / span var(--kdash-item-h)`, so a chart that needed more vertical room still gets it. Items are pre-sorted by `(y, x)` in `DashboardGrid` so single-column stacking order matches the intended reading order regardless of the original grid coordinates. |

Doing the column-count math (`scaleSpan`) once per item in JS, then handing the *result* to CSS as custom properties, is the split that makes this both testable (`scaleSpan` is a pure function, unit-tested directly) and genuinely CSS-driven (the breakpoint switch itself — which tier is active — is a browser media query, not a `matchMedia` listener re-rendering React).

## Theming model

Fully self-contained — this package does **not** depend on `@krutrim_agent/ui`, since it has to work as a standalone library before any integration into the app happens. See `theming.md`.
