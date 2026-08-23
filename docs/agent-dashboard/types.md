# Types

All exported from `src/types.ts` and re-exported at the package root. This is a 1:1 mirror of the `AgentDashboardWorkbook` JSON Schema you were given, with `map_interactive` and its `lat`/`lng` encoding channels removed — see the root [`README.md`](README.md#whats-different-from-the-schema-you-were-given).

## `AgentDashboardWorkbook`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `workbookId` | `string` | yes | Unique id for this dashboard instance. |
| `agentType` | `'research' \| 'sales' \| 'trading'` | yes | Which agent produced it. Cosmetic only — doesn't change rendering logic. |
| `schemaVersion` | `number` | no | Which contract revision this payload matches. Absent = implicitly version 1 (every payload predating this field). Not something you set on a hand-written workbook — see [`schema-versioning.md`](schema-versioning.md). |
| `title` | `string` | no | Shown by `renderHeader`, if you supply one — `<AgentDashboard>` itself doesn't render a title bar. |
| `generatedAt` | `string` (ISO datetime) | no | Not read by this package; carried through for host apps that want it. |
| `dataSources` | `DataSource[]` | yes, min 1 | All datasets referenced by `charts[].dataSourceId`. |
| `filters` | `Filter[]` | no | Global filter controls. |
| `charts` | `Chart[]` | yes, min 1 | All chart definitions. |
| `pages` | `Page[]` | yes, min 1 | Dashboard tabs/screens. |

## `DataSource`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | `string` | yes | Referenced by `Chart.dataSourceId` and `Filter.dataSourceId`. |
| `label` | `string` | no | Human-readable name (not currently rendered anywhere by this package — reserved for a future data-source picker UI). |
| `fields` | `Field[]` | yes, min 1 | Schema of every column in `data`. |
| `data` | `DataRow[]` | yes | Rows; may be `[]` if a `DataLoader` is registered for this id — see `data-loading.md`. |

`DataRow = Record<string, string \| number \| boolean \| null \| undefined>` — kept flat/primitive per the schema's own instruction ("no nested objects/arrays inside a row").

## `Field`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `name` | `string` | yes | Column key, exactly as it appears in each `data` row. |
| `role` | `'dimension' \| 'measure'` | yes | `dimension` = categorical/groupable (region, symbol, status). `measure` = numeric/aggregatable (revenue, pnl, count). Informational in this package — nothing currently gates an encoding channel by role, but it's exposed for a future chart-suggestion UI. |
| `dataType` | `'string' \| 'number' \| 'boolean' \| 'date' \| 'datetime'` | yes | Primitive type of the value. |
| `description` | `string` | no | Free-text; not rendered anywhere yet. |

## `Filter`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | `string` | yes | Keys `activeFilters`/`ActiveFilters`. |
| `label` | `string` | no | Shown next to the control in `FilterBar`; falls back to `field`. |
| `field` | `string` | yes | Which `Field.name` in its `DataSource` this filters on. |
| `dataSourceId` | `string` | yes | Which `DataSource` this filter's `field` belongs to. |
| `type` | see below | yes | Which control renders and how `value`/`defaultValue` are shaped. |
| `defaultValue` | see below | no | Applied once on first render if the dashboard is self-managing its filter state (see `filters.md`). |
| `appliesTo` | `string[]` | yes | Chart ids this filter narrows. `['*']` = every chart reading the same `dataSourceId`. |

`Filter.type` / `FilterValue` shapes:

| `type` | `defaultValue` / active value shape | Control |
|---|---|---|
| `categorical` | `string[]` (empty array = no filtering) | multi-select |
| `range` | `[number, number]` | two number inputs |
| `dateRange` | `[string, string]` (ISO dates) | two date inputs |
| `boolean` | `boolean` | checkbox |
| `search` | `string` | text input, case-insensitive substring match |

## `Chart`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | `string` | yes | Referenced by `Page.layout[].chartId` and `Filter.appliesTo`. |
| `title` | `string` | no | Rendered as the panel header in `ChartRenderer`. |
| `dataSourceId` | `string` | yes | Which `DataSource` this chart reads. |
| `type` | `ChartType` (16 values — see `chart-types.md`) | yes | Which component renders it. |
| `encoding` | `Encoding` | yes | Maps field names to visual channels — see below. |
| `indicators` | `IndicatorSpec[]` | no | `candlestick` only. Moving averages/oscillators — see `chart-types.md#candlestick-volume-indicators-and-annotations`. |
| `annotations` | `Annotation[]` | no | `candlestick` only. Agent-authored trendlines/price levels/markers — see the same section. |

## `Encoding`

Every channel is optional; which ones matter depends on `Chart.type` — see `chart-types.md` for the per-type table. Full list:

| Channel | Meaning |
|---|---|
| `x` | Category/x-axis field (also used as the primary group-by dimension for aggregation). |
| `y` | Value/y-axis field. |
| `color` | Secondary group-by dimension (multi-series bar/line, radar series, heatmap intensity fallback). |
| `size` | Point/node size (scatter, network_graph edge weight). |
| `value` | Single-number field (kpi, gauge, pie/funnel/geo_choropleth value). |
| `target` | Goal/reference value (kpi delta, gauge scale). |
| `aggregate` | `'sum' \| 'avg' \| 'count' \| 'min' \| 'max' \| 'none'` — `'none'` (default) means the agent already pre-aggregated the rows. |
| `open`/`high`/`low`/`close` | OHLC fields for `candlestick`. |
| `source`/`target_node` | Edge endpoints for `sankey`/`network_graph` (named `target_node`, not `target`, to avoid clashing with the goal-line channel above). |
| `region` | Region-code field for `geo_choropleth`. |
| `volume` | Volume field for `candlestick` (rendered as a histogram under the price pane). |

## `IndicatorSpec` (`candlestick` only)

| Field | Type | Required | Meaning |
|---|---|---|---|
| `type` | `'sma' \| 'ema' \| 'rsi' \| 'macd'` | yes | Which indicator to compute. |
| `field` | `string` | no | Source field. Defaults to `encoding.close`. |
| `period` | `number` | no | Window for `sma`/`ema`/`rsi`. Defaults: sma/ema 20, rsi 14. Ignored for `macd`. |
| `fastPeriod`/`slowPeriod`/`signalPeriod` | `number` | no | `macd` only. Default 12/26/9. |
| `color` | `string` | no | Defaults to the next color in the theme's series palette. |
| `pane` | `'overlay' \| 'separate'` | no | `sma`/`ema` default `'overlay'` (price pane); `rsi`/`macd` are always their own pane regardless of this field. |
| `label` | `string` | no | Used as the pane/line id and reference-line titles where applicable. |

## `Annotation` (`candlestick` only)

| Field | Type | Required | Meaning |
|---|---|---|---|
| `type` | `'trendline' \| 'horizontalLine' \| 'fibRetracement' \| 'label'` | yes | Which shape to draw. |
| `points` | `AnnotationPoint[]` (`{time, value}`) | yes | Count depends on `type` — see `chart-types.md`. |
| `color` | `string` | no | Defaults to the theme's accent color. |
| `label` | `string` | no | Marker text (`label` type) or price-line title (`horizontalLine`/`fibRetracement`). |
| `levels` | `number[]` | no | `fibRetracement` only. Defaults to `[0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]`. |

## `Page` / `LayoutItem`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `Page.id` | `string` | yes | Tab id. |
| `Page.name` | `string` | yes | Tab label. |
| `Page.layout` | `LayoutItem[]` | yes | Grid placement for this page's charts. |
| `LayoutItem.chartId` | `string` | yes | Must match a `Chart.id`. |
| `LayoutItem.x`/`y` | `number` | yes | Column/row start (0-indexed, 12-column grid). |
| `LayoutItem.w`/`h` | `number` | yes | Width/height in grid units. |
