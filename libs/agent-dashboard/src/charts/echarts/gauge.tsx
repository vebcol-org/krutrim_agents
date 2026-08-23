import { buildGaugeOption } from './option-builders';
import { createEChartsChart } from './create-echarts-chart';

export const GaugeChart = createEChartsChart(buildGaugeOption);
