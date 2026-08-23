import { useMemo, useRef } from 'react';
import type { ChartComponentProps } from '../chart-registry';
import { EmptyState, LoadingBadge } from '../chart-states';
import { buildTradingSeriesConfig } from './build-trading-config';
import { useLightweightCandlestickChart } from './use-lightweight-chart';

/**
 * OHLC candlestick via lightweight-charts. Needs encoding.x (time) +
 * open/high/low/close. Optionally adds a volume histogram (encoding.volume),
 * SMA/EMA/RSI/MACD indicators (chart.indicators), and agent-authored
 * trendline/horizontalLine/fibRetracement/label annotations
 * (chart.annotations) — see docs/agent-dashboard/chart-types.md. All the
 * "what to draw" resolution happens in the pure buildTradingSeriesConfig;
 * this component only owns the container + hands the result to the
 * lightweight-charts lifecycle hook.
 */
export function CandlestickChart({ chart, rows, isLoading, loadedCount, total, themeTokens }: ChartComponentProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { x, open, high, low, close } = chart.encoding;
  const hasEncoding = Boolean(x && open && high && low && close);

  const config = useMemo(() => buildTradingSeriesConfig(rows, chart, themeTokens), [rows, chart, themeTokens]);

  useLightweightCandlestickChart(containerRef, config, {
    upColor: themeTokens.up,
    downColor: themeTokens.down,
    textColor: themeTokens.muted,
    gridColor: themeTokens.gridLine,
  });

  if (!hasEncoding) {
    return <EmptyState message="candlestick charts need encoding.x, open, high, low, and close." />;
  }
  if (rows.length === 0 && !isLoading) return <EmptyState />;

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
      {isLoading && <LoadingBadge loadedCount={loadedCount} total={total} />}
    </div>
  );
}
