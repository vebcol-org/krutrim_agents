/**
 * TypeScript mirror of the AgentDashboardWorkbook JSON Schema, with one
 * deliberate deviation: `map_interactive` (pin/route maps needing lat/lng +
 * an external tile provider) is dropped from `ChartType` and `Encoding`
 * loses `lat`/`lng` accordingly — see docs/agent-dashboard/README.md for why.
 * Everything else is a 1:1 mirror; see docs/agent-dashboard/types.md for the
 * field-by-field writeup.
 */

export type FieldRole = 'dimension' | 'measure';

export type FieldDataType = 'string' | 'number' | 'boolean' | 'date' | 'datetime';

export interface Field {
  name: string;
  role: FieldRole;
  dataType: FieldDataType;
  description?: string;
}

/** A single row of a DataSource. Values are kept primitive, per the schema. */
export type DataRow = Record<string, string | number | boolean | null | undefined>;

export interface DataSource {
  id: string;
  label?: string;
  fields: Field[];
  data: DataRow[];
}

export type FilterType = 'categorical' | 'range' | 'dateRange' | 'boolean' | 'search';

export type FilterValue = string[] | [number, number] | [string, string] | boolean | string | null;

export interface Filter {
  id: string;
  label?: string;
  field: string;
  dataSourceId: string;
  type: FilterType;
  defaultValue?: FilterValue;
  /** Chart ids this filter narrows; `['*']` = every chart reading the same dataSourceId. */
  appliesTo: string[];
}

/** Active filter values keyed by Filter.id, as currently applied by the host/dashboard. */
export type ActiveFilters = Record<string, FilterValue | undefined>;

export type ChartType =
  | 'bar'
  | 'line'
  | 'area'
  | 'scatter'
  | 'pie'
  | 'candlestick'
  | 'heatmap'
  | 'boxplot'
  | 'radar'
  | 'funnel'
  | 'sankey'
  | 'network_graph'
  | 'geo_choropleth'
  | 'table'
  | 'kpi'
  | 'gauge';

export type AggregateFn = 'sum' | 'avg' | 'count' | 'min' | 'max' | 'none';

export interface Encoding {
  x?: string;
  y?: string;
  color?: string;
  size?: string;
  value?: string;
  target?: string;
  aggregate?: AggregateFn;
  open?: string;
  high?: string;
  low?: string;
  close?: string;
  source?: string;
  target_node?: string;
  region?: string;
  /** candlestick only — field for volume bars, rendered under the price pane. */
  volume?: string;
}

/** candlestick only. `sma`/`ema` default to `pane: 'overlay'` (drawn on the price pane); `rsi`/`macd` always get their own synced sub-pane regardless of `pane`. */
export type IndicatorType = 'sma' | 'ema' | 'rsi' | 'macd';

export interface IndicatorSpec {
  type: IndicatorType;
  /** Source field to compute from. Defaults to encoding.close. */
  field?: string;
  /** Window length for sma/ema/rsi. Defaults: sma/ema 20, rsi 14. Ignored for macd. */
  period?: number;
  /** macd only — fast/slow/signal EMA periods. Default 12/26/9. */
  fastPeriod?: number;
  slowPeriod?: number;
  signalPeriod?: number;
  color?: string;
  pane?: 'overlay' | 'separate';
  label?: string;
}

/** candlestick only — agent-authored, declarative chart annotations (not an interactive drawing tool; see docs/agent-dashboard/chart-types.md). */
export type AnnotationType = 'trendline' | 'horizontalLine' | 'fibRetracement' | 'label';

export interface AnnotationPoint {
  /** ISO date/datetime string, or unix seconds. */
  time: string | number;
  /** Price value. */
  value: number;
}

export interface Annotation {
  type: AnnotationType;
  /** trendline: exactly 2 points. horizontalLine: 1 (only `value` matters). fibRetracement: 2 (anchors). label: 1. */
  points: AnnotationPoint[];
  color?: string;
  label?: string;
  /** fibRetracement only. Defaults to the standard [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1] ratio set. */
  levels?: number[];
}

export interface Chart {
  id: string;
  title?: string;
  dataSourceId: string;
  type: ChartType;
  encoding: Encoding;
  /** candlestick only. */
  indicators?: IndicatorSpec[];
  /** candlestick only. */
  annotations?: Annotation[];
}

export interface LayoutItem {
  chartId: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Page {
  id: string;
  name: string;
  layout: LayoutItem[];
}

export type AgentType = 'research';

export interface AgentDashboardWorkbook {
  workbookId: string;
  agentType: AgentType;
  /**
   * Which revision of this contract the payload matches. Absent on payloads
   * predating this field — those are implicitly version 1. Not meant to be
   * set by hand for a hand-written workbook like the ones in
   * docs/agent-dashboard/examples.md; it matters once a producer's stored/
   * cached payloads need migrating forward — see schema-versioning.ts and
   * docs/agent-dashboard/schema-versioning.md.
   */
  schemaVersion?: number;
  title?: string;
  generatedAt?: string;
  dataSources: DataSource[];
  filters?: Filter[];
  charts: Chart[];
  pages: Page[];
}
