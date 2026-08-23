import { describe, expect, it } from 'vitest';
import { buildTradingSeriesConfig } from '../../../src/charts/trading/build-trading-config';
import { DEFAULT_LIGHT_THEME } from '../../../src/theme';
import type { Chart, DataRow } from '../../../src/types';

function makeRows(count: number): DataRow[] {
  return Array.from({ length: count }, (_, i) => {
    const day = String(i + 1).padStart(2, '0');
    const base = 100 + i;
    const isUp = i % 2 === 0;
    return {
      ts: `2026-01-${day}`,
      open: base,
      high: base + 2,
      low: base - 2,
      close: isUp ? base + 1 : base - 1,
      vol: 1000 + i,
    };
  });
}

function baseChart(overrides: Partial<Chart> = {}): Chart {
  return {
    id: 'candles',
    dataSourceId: 'ticks',
    type: 'candlestick',
    encoding: { x: 'ts', open: 'open', high: 'high', low: 'low', close: 'close' },
    ...overrides,
  };
}

describe('buildTradingSeriesConfig', () => {
  it('returns candlestick data and empty everything-else for a plain OHLC chart', () => {
    const rows = makeRows(5);
    const config = buildTradingSeriesConfig(rows, baseChart(), DEFAULT_LIGHT_THEME);

    expect(config.candlestick).toHaveLength(5);
    expect(config.candlestick[0]).toMatchObject({ open: 100, high: 102, low: 98, close: 101 });
    expect(config.volume).toBeUndefined();
    expect(config.overlayLines).toEqual([]);
    expect(config.panes).toEqual([]);
    expect(config.priceLines).toEqual([]);
    expect(config.trendlines).toEqual([]);
    expect(config.markers).toEqual([]);
  });

  it('returns an empty config when a required OHLC encoding field is missing', () => {
    const chart = baseChart({ encoding: { x: 'ts', open: 'open', high: 'high', low: 'low' } }); // no close
    expect(buildTradingSeriesConfig(makeRows(3), chart, DEFAULT_LIGHT_THEME).candlestick).toEqual([]);
  });

  it('builds a volume histogram colored by candle direction when encoding.volume is set', () => {
    const chart = baseChart({ encoding: { x: 'ts', open: 'open', high: 'high', low: 'low', close: 'close', volume: 'vol' } });
    const config = buildTradingSeriesConfig(makeRows(4), chart, DEFAULT_LIGHT_THEME);

    expect(config.volume).toHaveLength(4);
    expect(config.volume?.[0]).toMatchObject({ value: 1000, color: DEFAULT_LIGHT_THEME.up }); // i=0 is up
    expect(config.volume?.[1]).toMatchObject({ value: 1001, color: DEFAULT_LIGHT_THEME.down }); // i=1 is down
  });

  it('sma/ema default to an overlay line on the price pane', () => {
    const chart = baseChart({ indicators: [{ type: 'sma', period: 3 }] });
    const config = buildTradingSeriesConfig(makeRows(10), chart, DEFAULT_LIGHT_THEME);

    expect(config.panes).toEqual([]);
    expect(config.overlayLines).toHaveLength(1);
    expect(config.overlayLines[0].id).toBe('sma-3');
    expect(config.overlayLines[0].data.length).toBe(8); // 10 rows - (period-1) warm-up
  });

  it('an sma/ema explicitly marked pane:"separate" gets its own pane instead of overlaying', () => {
    const chart = baseChart({ indicators: [{ type: 'ema', period: 3, pane: 'separate' }] });
    const config = buildTradingSeriesConfig(makeRows(10), chart, DEFAULT_LIGHT_THEME);

    expect(config.overlayLines).toEqual([]);
    expect(config.panes).toHaveLength(1);
    expect(config.panes[0].lines).toHaveLength(1);
  });

  it('rsi always gets its own pane with 70/30 reference price lines', () => {
    const chart = baseChart({ indicators: [{ type: 'rsi', period: 5 }] });
    const config = buildTradingSeriesConfig(makeRows(20), chart, DEFAULT_LIGHT_THEME);

    expect(config.panes).toHaveLength(1);
    const [pane] = config.panes;
    expect(pane.lines).toHaveLength(1);
    expect(pane.priceLines).toEqual([
      { price: 70, color: DEFAULT_LIGHT_THEME.down, title: 'Overbought' },
      { price: 30, color: DEFAULT_LIGHT_THEME.up, title: 'Oversold' },
    ]);
  });

  it('macd produces a pane with macd+signal lines and a histogram', () => {
    const chart = baseChart({ indicators: [{ type: 'macd' }] });
    const config = buildTradingSeriesConfig(makeRows(60), chart, DEFAULT_LIGHT_THEME);

    expect(config.panes).toHaveLength(1);
    const [pane] = config.panes;
    expect(pane.lines).toHaveLength(2);
    expect(pane.histogram?.data.length).toBeGreaterThan(0);
  });

  it('multiple separate-pane indicators each get their own pane entry', () => {
    const chart = baseChart({ indicators: [{ type: 'rsi', period: 5 }, { type: 'macd' }] });
    const config = buildTradingSeriesConfig(makeRows(60), chart, DEFAULT_LIGHT_THEME);
    expect(config.panes).toHaveLength(2);
  });

  it('a trendline annotation passes its 2 points through with a resolved color', () => {
    const chart = baseChart({
      annotations: [{ type: 'trendline', points: [{ time: '2026-01-01', value: 100 }, { time: '2026-01-05', value: 110 }] }],
    });
    const config = buildTradingSeriesConfig(makeRows(5), chart, DEFAULT_LIGHT_THEME);

    expect(config.trendlines).toHaveLength(1);
    expect(config.trendlines[0].points).toHaveLength(2);
    expect(config.trendlines[0].points[0].value).toBe(100);
    expect(config.trendlines[0].color).toBe(DEFAULT_LIGHT_THEME.accent);
  });

  it('skips a trendline annotation that does not have exactly 2 points', () => {
    const chart = baseChart({ annotations: [{ type: 'trendline', points: [{ time: '2026-01-01', value: 100 }] }] });
    expect(buildTradingSeriesConfig(makeRows(5), chart, DEFAULT_LIGHT_THEME).trendlines).toEqual([]);
  });

  it('a horizontalLine annotation becomes a single price line at its value', () => {
    const chart = baseChart({ annotations: [{ type: 'horizontalLine', points: [{ time: '2026-01-01', value: 150 }], label: 'Resistance' }] });
    const config = buildTradingSeriesConfig(makeRows(5), chart, DEFAULT_LIGHT_THEME);
    expect(config.priceLines).toEqual([{ price: 150, color: DEFAULT_LIGHT_THEME.accent, title: 'Resistance' }]);
  });

  it('a fibRetracement annotation expands to the default 7 levels between its two anchors', () => {
    const chart = baseChart({
      annotations: [{ type: 'fibRetracement', points: [{ time: '2026-01-01', value: 100 }, { time: '2026-01-10', value: 200 }] }],
    });
    const config = buildTradingSeriesConfig(makeRows(10), chart, DEFAULT_LIGHT_THEME);

    expect(config.priceLines).toHaveLength(7);
    expect(config.priceLines[0].price).toBe(100); // level 0
    expect(config.priceLines[3].price).toBe(150); // level 0.5
    expect(config.priceLines[6].price).toBe(200); // level 1
  });

  it('a fibRetracement annotation honors custom levels', () => {
    const chart = baseChart({
      annotations: [{ type: 'fibRetracement', points: [{ time: '2026-01-01', value: 0 }, { time: '2026-01-10', value: 100 }], levels: [0, 0.5, 1] }],
    });
    const config = buildTradingSeriesConfig(makeRows(10), chart, DEFAULT_LIGHT_THEME);
    expect(config.priceLines.map((p) => p.price)).toEqual([0, 50, 100]);
  });

  it('a label annotation becomes a price marker with the given text', () => {
    const chart = baseChart({ annotations: [{ type: 'label', points: [{ time: '2026-01-03', value: 120 }], label: 'Breakout' }] });
    const config = buildTradingSeriesConfig(makeRows(5), chart, DEFAULT_LIGHT_THEME);

    expect(config.markers).toHaveLength(1);
    expect(config.markers[0]).toMatchObject({ price: 120, text: 'Breakout', position: 'atPriceMiddle', shape: 'circle' });
  });
});
