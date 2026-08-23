import { buildPieOption } from './option-builders';
import { createEChartsChart } from './create-echarts-chart';

export const PieChart = createEChartsChart(buildPieOption);
