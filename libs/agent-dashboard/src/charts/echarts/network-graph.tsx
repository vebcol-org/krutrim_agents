import { buildNetworkGraphOption } from './option-builders';
import { createEChartsChart } from './create-echarts-chart';

export const NetworkGraphChart = createEChartsChart(buildNetworkGraphOption);
