# Customization

Every extension point in this package follows the same rule: **register globally, or override per-instance — never edit the built-in.**

## Replacing a built-in chart type, globally

```ts
import { registerChartRenderer, type ChartComponentProps } from '@krutrim_agent/agent-dashboard';

function MyBarChart({ chart, rows, isLoading }: ChartComponentProps) {
  // rows are already filtered + aggregated per chart.encoding — see architecture.md
  return <MyOwnBarLib data={rows} xKey={chart.encoding.x} yKey={chart.encoding.y} loading={isLoading} />;
}

registerChartRenderer('bar', MyBarChart); // affects every <AgentDashboard> in the app from here on
```

`ChartComponentProps`:

```ts
interface ChartComponentProps {
  chart: Chart;
  rows: DataRow[];
  isLoading: boolean;
  loadedCount: number;
  total?: number;
  hasMore: boolean;
  onLoadMore: () => void; // wire this to a "load more" affordance if you want one — see data-loading.md
  themeTokens: ThemeTokens;
  echartsThemeName: string; // pass straight to echarts.init(el, echartsThemeName) if building your own ECharts-backed type
}
```

## Overriding for a single dashboard instance

```tsx
<AgentDashboard workbook={workbook} chartRenderers={{ bar: MyBarChart, table: MyFancyTable }} />
```

This layers on top of the global registry inside `DashboardProvider` (`getChartComponent` checks the instance override first, falls back to the registry) — it never mutates `registerChartRenderer`'s state, so other dashboards on the same page keep the default.

## Adding a chart type this package doesn't ship

Same mechanism — `registerChartRenderer('my_custom_type' as ChartType, MyComponent)` works even for a `type` string outside the built-in 16, as long as your workbook's `Chart.type` uses that same string. (TypeScript will complain about the cast since `ChartType` is a closed union — that's expected; widen your own local type if you do this regularly.)

## Filters — same pattern

```ts
import { registerFilterRenderer, type FilterComponentProps } from '@krutrim_agent/agent-dashboard';

function RangeSlider({ filter, value, onChange }: FilterComponentProps) {
  const [min, max] = (value as [number, number]) ?? [0, 100];
  return <MyDualHandleSlider min={min} max={max} onChange={([lo, hi]) => onChange([lo, hi])} />;
}

registerFilterRenderer('range', RangeSlider);
// or per-instance: <AgentDashboard filterRenderers={{ range: RangeSlider }} />
```

## GeoJSON maps for `geo_choropleth`

Boundary data isn't bundled (it's large and app-specific). Register it once at startup:

```ts
import { registerGeoMap, DEFAULT_GEO_MAP_NAME } from '@krutrim_agent/agent-dashboard';
import worldGeoJson from './world.geo.json';

registerGeoMap(DEFAULT_GEO_MAP_NAME, worldGeoJson); // 'world' — the name the built-in geo_choropleth component looks for
```

Need a different map (e.g. US states) for a specific chart instead of the global default? Register it under its own name and swap in a small custom component via `chartRenderers`:

```tsx
registerGeoMap('us-states', usStatesGeoJson);

function UsStatesChoropleth({ chart, rows, echartsThemeName }: ChartComponentProps) {
  const option = buildGeoChoroplethOption(rows, chart.encoding, 'us-states'); // exported for exactly this
  return <EChartsBase option={option} themeName={echartsThemeName} />; // both exported from the package
}

<AgentDashboard chartRenderers={{ geo_choropleth: UsStatesChoropleth }} />
```

## `renderHeader` / `renderEmpty`

```tsx
<AgentDashboard
  workbook={workbook}
  renderHeader={(wb) => <h1>{wb.title}</h1>}
  renderEmpty={() => <p>This dashboard has no data yet.</p>}
/>
```

`renderHeader` renders above the filter bar/page tabs; `renderEmpty` replaces the entire dashboard body when `workbook.pages` or `workbook.charts` is empty.

## Reading dashboard state from a custom component

Any component rendered inside `<AgentDashboard>` (a custom chart/filter, or something you put in `renderHeader`) can call `useDashboard()` to reach the workbook, active filters, theme tokens, or registries directly — see `api.md`.
