import { buildSankeyOption } from './option-builders';
import { createEChartsChart } from './create-echarts-chart';

export const SankeyChart = createEChartsChart(buildSankeyOption);
