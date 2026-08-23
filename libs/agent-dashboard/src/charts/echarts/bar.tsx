import { buildCartesianOption } from './option-builders';
import { createEChartsChart } from './create-echarts-chart';

export const BarChart = createEChartsChart((rows, encoding) => buildCartesianOption(rows, encoding, 'bar'));
