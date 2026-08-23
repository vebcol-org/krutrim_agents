import { buildHeatmapOption } from './option-builders';
import { createEChartsChart } from './create-echarts-chart';

export const HeatmapChart = createEChartsChart(buildHeatmapOption);
