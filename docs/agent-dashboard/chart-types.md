# Chart types

All 16 `ChartType` values (the schema's 17th, `map_interactive`, is dropped — see the root [`README.md`](README.md)). Built-in components live under `libs/agent-dashboard/src/charts/` and are wired up by `registerBuiltinCharts()`.

| `type` | Engine | Required `encoding` | Optional `encoding` |
|---|---|---|---|
| `bar` | ECharts | `x`, `y` (or `value`) | `color` (multi-series), `aggregate` |
| `line` | ECharts | `x`, `y` | `color`, `aggregate` |
| `area` | ECharts | `x`, `y` | `color`, `aggregate` |
| `scatter` | ECharts | `x`, `y` | `color` (series grouping) |
| `pie` | ECharts | `x` (or `color`), `y` (or `value`) | — |
| `candlestick` | lightweight-charts | `x` (time), `open`, `high`, `low`, `close` | `volume` (histogram under the price pane); `Chart.indicators`/`Chart.annotations` — see below |
| `heatmap` | ECharts | `x`, `y` (both categorical axes), `value` (or `color`, as intensity) | — |
| `boxplot` | ECharts | `x`, `y` (raw, non-aggregated rows — see note below) | — |
| `radar` | ECharts | `x` (indicator name), `y` (or `value`, magnitude) | `color` (one series per compared entity) |
| `funnel` | ECharts | `x` (stage name), `y` (or `value`) | — |
| `sankey` | ECharts | `source`, `target_node` | `value` (or `y`, edge weight — defaults to 1) |
| `network_graph` | ECharts | `source`, `target_node` | `size` (or `value`, edge weight) |
| `geo_choropleth` | ECharts | `region`, `value` (or `y`) | needs a registered GeoJSON — see `customization.md` |
| `table` | plain HTML | — (columns come from the DataSource's `fields`) | — |
| `kpi` | plain HTML | `value` (or `y`) | `target` (renders a delta line) |
| `gauge` | ECharts | `value` (or `y`) | `target` (scales the gauge max) |

## Notes

- **`heatmap`**: unlike most types, both `x` and `y` are treated as categorical axes here (e.g. day-of-week × hour-of-day), not x-axis/measure — the intensity measure is `value` (falling back to `color` if `value` isn't set).
- **`boxplot`**: needs `encoding.aggregate` left as `'none'` (the default) so `resolveChartRows` doesn't collapse rows before the box-plot's own five-number-summary computation runs on the raw per-category values.
- **`radar`**: the schema has no native "multiple measures as axes" shape, so this package's convention is `x` = indicator/axis name, one row per (indicator, entity) pair, `color` = which entity's series a row belongs to.
- **`sankey`**/**`network_graph`**: node names are derived automatically as the distinct union of `source` and `target_node` values — no separate node list needed in the DataSource.
- **`geo_choropleth`**: renders a placeholder message (not a blank chart) until `registerGeoMap('world', geoJson)` has been called — see `customization.md`. GeoJSON boundary data isn't bundled since it's large and app-specific.
- **`candlestick`**: zoom/pan/crosshair are on by default in `lightweight-charts` and explicitly configured (not just left incidental) in `use-lightweight-chart.ts`. See the dedicated section below for volume, indicators, and annotations.

## `candlestick`: volume, indicators, and annotations

A candlestick chart can optionally carry three more pieces, all additive — a plain OHLC chart with none of them behaves exactly as before:

**`encoding.volume`** — a field name for volume bars, rendered as a histogram squeezed under the price pane (its own price scale, not a separate pane), colored per-candle to match up/down.

**`Chart.indicators: IndicatorSpec[]`** — moving averages and oscillators, computed client-side from the resolved rows:

| `type` | Where it renders | Notes |
|---|---|---|
| `sma` / `ema` | Price pane overlay (default), or its own pane if `pane: 'separate'` | `period` defaults to 20. `field` defaults to `encoding.close`. |
| `rsi` | Always its own synced sub-pane | `period` defaults to 14. Comes with 70/30 overbought/oversold reference lines automatically. |
| `macd` | Always its own synced sub-pane | `fastPeriod`/`slowPeriod`/`signalPeriod` default 12/26/9. Renders the MACD line, signal line, and a histogram. |

Every sub-pane indicator (`rsi`, `macd`, or an `sma`/`ema` marked `pane: 'separate'`) lives in its own **pane within the same chart instance** (`lightweight-charts`' multi-pane API) — time-scale and crosshair are shared across all panes automatically, so "price + RSI + volume, linked crosshair" is just a chart with those pieces present, not a separate synced-charts feature.

```ts
indicators: [
  { type: 'sma', period: 20 },
  { type: 'rsi', period: 14 },
  { type: 'macd' },
]
```

**`Chart.annotations: Annotation[]`** — agent-authored, declarative markup on the price pane (not an interactive drawing tool — the workbook's own data says what to draw, the chart just renders it):

| `type` | `points` | Renders as |
|---|---|---|
| `trendline` | exactly 2 | A straight line segment between the two (time, price) points. |
| `horizontalLine` | 1 (only `value` matters) | A full-width reference price line, e.g. support/resistance. |
| `fibRetracement` | exactly 2 (anchors) | One price line per ratio in `levels` (default `[0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]`), interpolated between the two anchor prices. |
| `label` | 1 | A marker at that (time, price) with `label` as its text. |

```ts
annotations: [
  { type: 'trendline', points: [{ time: '2026-01-01', value: 180 }, { time: '2026-02-01', value: 210 }] },
  { type: 'fibRetracement', points: [{ time: '2026-01-01', value: 150 }, { time: '2026-01-15', value: 220 }] },
  { type: 'label', points: [{ time: '2026-01-10', value: 205 }], label: 'Breakout' },
]
```

## Minimal examples

```ts
// bar
{ id: 'c1', dataSourceId: 'ds', type: 'bar', encoding: { x: 'region', y: 'revenue', aggregate: 'sum' } }

// candlestick
{ id: 'c2', dataSourceId: 'ticks', type: 'candlestick', encoding: { x: 'timestamp', open: 'o', high: 'h', low: 'l', close: 'c' } }

// candlestick + volume + RSI + a trendline annotation
{
  id: 'c2b', dataSourceId: 'ticks', type: 'candlestick',
  encoding: { x: 'timestamp', open: 'o', high: 'h', low: 'l', close: 'c', volume: 'v' },
  indicators: [{ type: 'sma', period: 20 }, { type: 'rsi', period: 14 }],
  annotations: [{ type: 'trendline', points: [{ time: '2026-01-01', value: 180 }, { time: '2026-02-01', value: 210 }] }],
}

// sankey
{ id: 'c3', dataSourceId: 'flows', type: 'sankey', encoding: { source: 'from_stage', target_node: 'to_stage', value: 'count' } }

// kpi with a target
{ id: 'c4', dataSourceId: 'summary', type: 'kpi', title: 'Active Users', encoding: { value: 'active_users', target: 'goal' } }
```
