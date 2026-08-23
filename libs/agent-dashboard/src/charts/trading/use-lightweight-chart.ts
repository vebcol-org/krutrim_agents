import { useEffect, useRef, type RefObject } from 'react';
import {
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesType,
  type Time,
} from 'lightweight-charts';
import type { TradingSeriesConfig } from './build-trading-config';

export interface CandlestickColors {
  upColor: string;
  downColor: string;
  textColor: string;
  gridColor: string;
}

/**
 * Owns a lightweight-charts (TradingView's OSS charting library) instance's
 * full lifecycle via two effects:
 *
 * 1. Create/dispose the bare `IChartApi`, keyed on `colors` (layout options
 *    are set at chart-creation time). Zoom/pan (`handleScroll`/`handleScale`)
 *    and the crosshair are explicitly enabled here rather than left as
 *    incidental defaults.
 * 2. On every `config`/`colors` change: build the full series set from
 *    `config` — candlestick, an optional volume histogram (its own price
 *    scale, squeezed under the price pane via `scaleMargins`), overlay
 *    SMA/EMA lines, each `config.panes` entry (RSI/MACD/separate-pane
 *    indicators) in its own auto-created pane via `addSeries(..., paneIndex)`
 *    — panes in the same chart instance share time-scale/crosshair for
 *    free — annotation price lines, trendline segments, and markers. Returns
 *    a cleanup that removes exactly what this run created, which React
 *    calls before the next run (or on unmount) — this effect's own deps
 *    mirror effect 1's exactly so a chart recreation (effect 1) always
 *    triggers a full series rebuild (effect 2) in the same pass, rather than
 *    risking a stale reference to a disposed chart.
 */
export function useLightweightCandlestickChart(
  containerRef: RefObject<HTMLDivElement | null>,
  config: TradingSeriesConfig,
  colors: CandlestickColors,
) {
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight,
      layout: { background: { color: 'transparent' }, textColor: colors.textColor },
      grid: {
        vertLines: { color: colors.gridColor },
        horzLines: { color: colors.gridColor },
      },
      crosshair: { mode: CrosshairMode.Normal },
      handleScroll: true,
      handleScale: true,
    });
    chartRef.current = chart;

    const resizeObserver = new ResizeObserver(() => {
      chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [containerRef, colors.upColor, colors.downColor, colors.textColor, colors.gridColor]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const createdSeries: ISeriesApi<SeriesType, Time>[] = [];
    const createdMarkerPlugins: ISeriesMarkersPluginApi<Time>[] = [];
    const createdPriceLines: Array<{ series: ISeriesApi<SeriesType, Time>; line: IPriceLine }> = [];

    const addPriceLine = (series: ISeriesApi<SeriesType, Time>, spec: { price: number; color: string; title?: string }) => {
      const line = series.createPriceLine({
        price: spec.price,
        color: spec.color,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: spec.title ?? '',
      });
      createdPriceLines.push({ series, line });
    };

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: colors.upColor,
      downColor: colors.downColor,
      borderVisible: false,
      wickUpColor: colors.upColor,
      wickDownColor: colors.downColor,
    });
    candlestickSeries.setData(config.candlestick);
    createdSeries.push(candlestickSeries);

    if (config.volume) {
      const volumeSeries = chart.addSeries(HistogramSeries, {
        priceScaleId: 'kdash-volume',
        priceFormat: { type: 'volume' },
      });
      volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
      volumeSeries.setData(config.volume);
      createdSeries.push(volumeSeries);
    }

    for (const line of config.overlayLines) {
      const series = chart.addSeries(LineSeries, { color: line.color, lineWidth: 2 });
      series.setData(line.data);
      createdSeries.push(series);
    }

    for (const priceLineSpec of config.priceLines) {
      addPriceLine(candlestickSeries, priceLineSpec);
    }

    for (const trendline of config.trendlines) {
      const series = chart.addSeries(LineSeries, { color: trendline.color, lineWidth: 2 });
      series.setData(trendline.points);
      createdSeries.push(series);
    }

    if (config.markers.length > 0) {
      createdMarkerPlugins.push(createSeriesMarkers(candlestickSeries, config.markers));
    }

    let nextPaneIndex = 1;
    for (const pane of config.panes) {
      const paneIndex = nextPaneIndex++;
      let anchorSeries: ISeriesApi<SeriesType, Time> | undefined;

      for (const line of pane.lines) {
        const series = chart.addSeries(LineSeries, { color: line.color, lineWidth: 2 }, paneIndex);
        series.setData(line.data);
        createdSeries.push(series);
        anchorSeries ??= series;
      }
      if (pane.histogram) {
        const series = chart.addSeries(HistogramSeries, {}, paneIndex);
        series.setData(pane.histogram.data);
        createdSeries.push(series);
        anchorSeries ??= series;
      }

      chart.panes()[paneIndex]?.setStretchFactor(pane.stretchFactor);

      if (anchorSeries) {
        for (const priceLineSpec of pane.priceLines ?? []) {
          addPriceLine(anchorSeries, priceLineSpec);
        }
      }
    }

    return () => {
      for (const plugin of createdMarkerPlugins) plugin.detach();
      for (const { series, line } of createdPriceLines) series.removePriceLine(line);
      for (const series of createdSeries) chart.removeSeries(series);
    };
  }, [config, colors.upColor, colors.downColor, colors.textColor, colors.gridColor]);

  return chartRef;
}
