import { buildFunnelOption } from './option-builders';
import { createEChartsChart } from './create-echarts-chart';

export const FunnelChart = createEChartsChart(buildFunnelOption);
