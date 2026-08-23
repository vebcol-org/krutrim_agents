import { useMemo } from 'react';
import type { EChartsOption } from 'echarts';
import type { DataRow, Encoding } from '../../types';
import type { ChartComponent, ChartComponentProps } from '../chart-registry';
import { EmptyState, LoadingBadge } from '../chart-states';
import { EChartsBase } from './echarts-base';

/** Wraps an (rows, encoding) -> EChartsOption pure function as a ChartComponent — shared by every ECharts-backed type. */
export function createEChartsChart(build: (rows: DataRow[], encoding: Encoding) => EChartsOption): ChartComponent {
  return function EChartsChart({ chart, rows, isLoading, loadedCount, total, echartsThemeName }: ChartComponentProps) {
    const option = useMemo(() => build(rows, chart.encoding), [rows, chart.encoding]);

    if (rows.length === 0 && !isLoading) return <EmptyState />;

    return (
      <div style={{ position: 'relative', width: '100%', height: '100%' }}>
        <EChartsBase option={option} themeName={echartsThemeName} />
        {isLoading && <LoadingBadge loadedCount={loadedCount} total={total} />}
      </div>
    );
  };
}
