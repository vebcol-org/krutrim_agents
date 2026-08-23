import type { CandlestickData, HistogramData, LineData, SeriesMarkerPrice, Time } from 'lightweight-charts';
import type { Chart, DataRow } from '../../types';
import type { ThemeTokens } from '../../theme';
import { computeEMA, computeMACD, computeRSI, computeSMA } from './indicators';
import { num, toUnixSeconds } from './trading-utils';

export interface PriceLineSpec {
  price: number;
  color: string;
  title?: string;
}

export interface OverlayLineSpec {
  id: string;
  color: string;
  data: LineData<Time>[];
}

export interface TradingPaneSpec {
  id: string;
  /** Relative size vs. the price pane (stretch factor 1) — see IPaneApi.setStretchFactor. */
  stretchFactor: number;
  lines: OverlayLineSpec[];
  histogram?: { data: HistogramData<Time>[] };
  priceLines?: PriceLineSpec[];
}

export interface TrendlineSpec {
  color: string;
  /** Exactly 2 points. */
  points: LineData<Time>[];
}

/**
 * Everything a candlestick chart needs to draw, fully resolved from a
 * DataRow[] + Chart + ThemeTokens — no `lightweight-charts` API calls happen
 * here. `use-lightweight-chart.ts` is the "how to draw it" layer that
 * consumes this; this is the "what to draw" layer, kept pure and
 * independently testable.
 */
export interface TradingSeriesConfig {
  candlestick: CandlestickData<Time>[];
  volume?: HistogramData<Time>[];
  /** sma/ema (default pane), drawn directly on the price pane. */
  overlayLines: OverlayLineSpec[];
  /** rsi/macd (and any sma/ema explicitly marked `pane: 'separate'`), each its own synced sub-pane. */
  panes: TradingPaneSpec[];
  /** horizontalLine / fibRetracement annotations, drawn on the price pane. */
  priceLines: PriceLineSpec[];
  /** trendline annotations, drawn on the price pane. */
  trendlines: TrendlineSpec[];
  /** label annotations, drawn on the price pane via createSeriesMarkers. */
  markers: SeriesMarkerPrice<Time>[];
}

const DEFAULT_FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];
const EMPTY_CONFIG: TradingSeriesConfig = { candlestick: [], overlayLines: [], panes: [], priceLines: [], trendlines: [], markers: [] };

function formatFibTitle(label: string | undefined, level: number): string {
  const pct = `${Math.round(level * 1000) / 10}%`;
  return label ? `${label} ${pct}` : pct;
}

export function buildTradingSeriesConfig(rows: DataRow[], chart: Chart, themeTokens: ThemeTokens): TradingSeriesConfig {
  const { x: timeField, open, high, low, close, volume: volumeField } = chart.encoding;
  if (!timeField || !open || !high || !low || !close) return EMPTY_CONFIG;

  const sortedRows = [...rows].sort(
    (a, b) => Number(toUnixSeconds(a[timeField])) - Number(toUnixSeconds(b[timeField])),
  );
  const times: Time[] = sortedRows.map((r) => toUnixSeconds(r[timeField]));

  const candlestick: CandlestickData<Time>[] = sortedRows.map((r, i) => ({
    time: times[i],
    open: num(r[open]),
    high: num(r[high]),
    low: num(r[low]),
    close: num(r[close]),
  }));

  const volume: HistogramData<Time>[] | undefined = volumeField
    ? sortedRows.map((r, i) => ({
        time: times[i],
        value: num(r[volumeField]),
        color: num(r[close]) >= num(r[open]) ? themeTokens.up : themeTokens.down,
      }))
    : undefined;

  const overlayLines: OverlayLineSpec[] = [];
  const panes: TradingPaneSpec[] = [];
  let colorCursor = 0;
  const nextColor = () => themeTokens.series[colorCursor++ % themeTokens.series.length];

  for (const spec of chart.indicators ?? []) {
    const sourceField = spec.field ?? close;
    const sourceValues = sortedRows.map((r) => num(r[sourceField]));
    const color = spec.color ?? nextColor();

    if (spec.type === 'sma' || spec.type === 'ema') {
      const period = spec.period ?? 20;
      const computed = spec.type === 'sma' ? computeSMA(sourceValues, period) : computeEMA(sourceValues, period);
      const line: OverlayLineSpec = {
        id: spec.label ?? `${spec.type}-${period}`,
        color,
        data: computed.map((c) => ({ time: times[c.index], value: c.value })),
      };
      if (spec.pane === 'separate') panes.push({ id: line.id, stretchFactor: 0.35, lines: [line] });
      else overlayLines.push(line);
      continue;
    }

    if (spec.type === 'rsi') {
      const period = spec.period ?? 14;
      const computed = computeRSI(sourceValues, period);
      panes.push({
        id: spec.label ?? `rsi-${period}`,
        stretchFactor: 0.35,
        lines: [{ id: 'rsi', color, data: computed.map((c) => ({ time: times[c.index], value: c.value })) }],
        priceLines: [
          { price: 70, color: themeTokens.down, title: 'Overbought' },
          { price: 30, color: themeTokens.up, title: 'Oversold' },
        ],
      });
      continue;
    }

    if (spec.type === 'macd') {
      const fastPeriod = spec.fastPeriod ?? 12;
      const slowPeriod = spec.slowPeriod ?? 26;
      const signalPeriod = spec.signalPeriod ?? 9;
      const { macd, signal, histogram } = computeMACD(sourceValues, fastPeriod, slowPeriod, signalPeriod);
      panes.push({
        id: spec.label ?? 'macd',
        stretchFactor: 0.4,
        lines: [
          { id: 'macd', color, data: macd.map((m) => ({ time: times[m.index], value: m.value })) },
          { id: 'signal', color: themeTokens.accent, data: signal.map((s) => ({ time: times[s.index], value: s.value })) },
        ],
        histogram: {
          data: histogram.map((h) => ({
            time: times[h.index],
            value: h.value,
            color: h.value >= 0 ? themeTokens.up : themeTokens.down,
          })),
        },
      });
    }
  }

  const priceLines: PriceLineSpec[] = [];
  const trendlines: TrendlineSpec[] = [];
  const markers: SeriesMarkerPrice<Time>[] = [];

  for (const annotation of chart.annotations ?? []) {
    const color = annotation.color ?? themeTokens.accent;

    if (annotation.type === 'trendline') {
      if (annotation.points.length !== 2) continue;
      trendlines.push({ color, points: annotation.points.map((p) => ({ time: toUnixSeconds(p.time), value: p.value })) });
      continue;
    }

    if (annotation.type === 'horizontalLine') {
      if (annotation.points.length < 1) continue;
      priceLines.push({ price: annotation.points[0].value, color, title: annotation.label });
      continue;
    }

    if (annotation.type === 'fibRetracement') {
      if (annotation.points.length !== 2) continue;
      const [a, b] = annotation.points;
      for (const level of annotation.levels ?? DEFAULT_FIB_LEVELS) {
        priceLines.push({ price: a.value + (b.value - a.value) * level, color, title: formatFibTitle(annotation.label, level) });
      }
      continue;
    }

    if (annotation.type === 'label') {
      if (annotation.points.length < 1) continue;
      const point = annotation.points[0];
      markers.push({
        time: toUnixSeconds(point.time),
        position: 'atPriceMiddle',
        price: point.value,
        shape: 'circle',
        color,
        text: annotation.label,
      });
    }
  }

  return { candlestick, volume, overlayLines, panes, priceLines, trendlines, markers };
}
