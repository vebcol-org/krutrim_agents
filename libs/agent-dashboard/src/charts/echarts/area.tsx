import { buildCartesianOption } from './option-builders';
import { createEChartsChart } from './create-echarts-chart';

export const AreaChart = createEChartsChart((rows, encoding) => buildCartesianOption(rows, encoding, 'area'));
