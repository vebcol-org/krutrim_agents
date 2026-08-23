import { buildCartesianOption } from './option-builders';
import { createEChartsChart } from './create-echarts-chart';

export const ScatterChart = createEChartsChart((rows, encoding) => buildCartesianOption(rows, encoding, 'scatter'));
