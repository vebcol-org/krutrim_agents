import { buildRadarOption } from './option-builders';
import { createEChartsChart } from './create-echarts-chart';

export const RadarChart = createEChartsChart(buildRadarOption);
