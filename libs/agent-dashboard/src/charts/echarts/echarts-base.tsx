import { useRef } from 'react';
import type { EChartsOption } from 'echarts';
import { useEChartsInstance } from './use-echarts-instance';

export interface EChartsBaseProps {
  option: EChartsOption;
  themeName: string;
}

/** Thin container shared by every ECharts-backed chart type — just owns the instance lifecycle. */
export function EChartsBase({ option, themeName }: EChartsBaseProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  useEChartsInstance(containerRef, option, themeName);
  return <div ref={containerRef} style={{ width: '100%', height: '100%' }} />;
}
