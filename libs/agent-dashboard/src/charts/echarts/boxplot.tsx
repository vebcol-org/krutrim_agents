import { buildBoxplotOption } from './option-builders';
import { createEChartsChart } from './create-echarts-chart';

export const BoxplotChart = createEChartsChart(buildBoxplotOption);
