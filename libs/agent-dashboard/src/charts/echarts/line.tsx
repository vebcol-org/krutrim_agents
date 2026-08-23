import { buildCartesianOption } from './option-builders';
import { createEChartsChart } from './create-echarts-chart';

export const LineChart = createEChartsChart((rows, encoding) => buildCartesianOption(rows, encoding, 'line'));
