import { registerChartRenderer } from './chart-registry';
import { BarChart } from './echarts/bar';
import { LineChart } from './echarts/line';
import { AreaChart } from './echarts/area';
import { ScatterChart } from './echarts/scatter';
import { PieChart } from './echarts/pie';
import { HeatmapChart } from './echarts/heatmap';
import { BoxplotChart } from './echarts/boxplot';
import { RadarChart } from './echarts/radar';
import { FunnelChart } from './echarts/funnel';
import { SankeyChart } from './echarts/sankey';
import { NetworkGraphChart } from './echarts/network-graph';
import { GeoChoroplethChart } from './echarts/geo-choropleth';
import { GaugeChart } from './echarts/gauge';
import { CandlestickChart } from './trading/candlestick';
import { TableChart } from './table/table-chart';
import { KpiChart } from './kpi/kpi-chart';

let registered = false;

/** Idempotent — index.ts calls this once so all 16 chart types work out of the box. */
export function registerBuiltinCharts(): void {
  if (registered) return;
  registered = true;
  registerChartRenderer('bar', BarChart);
  registerChartRenderer('line', LineChart);
  registerChartRenderer('area', AreaChart);
  registerChartRenderer('scatter', ScatterChart);
  registerChartRenderer('pie', PieChart);
  registerChartRenderer('heatmap', HeatmapChart);
  registerChartRenderer('boxplot', BoxplotChart);
  registerChartRenderer('radar', RadarChart);
  registerChartRenderer('funnel', FunnelChart);
  registerChartRenderer('sankey', SankeyChart);
  registerChartRenderer('network_graph', NetworkGraphChart);
  registerChartRenderer('geo_choropleth', GeoChoroplethChart);
  registerChartRenderer('gauge', GaugeChart);
  registerChartRenderer('candlestick', CandlestickChart);
  registerChartRenderer('table', TableChart);
  registerChartRenderer('kpi', KpiChart);
}
