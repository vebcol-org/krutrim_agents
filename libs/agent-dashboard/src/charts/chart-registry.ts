import type { ComponentType } from 'react';
import type { Chart, ChartType, DataRow } from '../types';
import type { ThemeTokens } from '../theme';

export interface ChartComponentProps {
  chart: Chart;
  rows: DataRow[];
  isLoading: boolean;
  loadedCount: number;
  total?: number;
  hasMore: boolean;
  /** Fetch the next chunk from this chart's registered DataLoader, if any. No-op otherwise. Used by the table chart's "Load more". */
  onLoadMore: () => void;
  themeTokens: ThemeTokens;
  echartsThemeName: string;
}

export type ChartComponent = ComponentType<ChartComponentProps>;

const registry = new Map<ChartType, ChartComponent>();

/**
 * Registers (or replaces) the component used for a chart `type` across every
 * `<AgentDashboard>` in the app — the global extension point. For a
 * single-instance override use `<AgentDashboard chartRenderers={{...}}>`
 * instead (see agent-dashboard.tsx), which layers on top of this registry
 * without mutating it.
 */
export function registerChartRenderer(type: ChartType, component: ChartComponent): void {
  registry.set(type, component);
}

export function getChartRenderer(type: ChartType): ChartComponent | undefined {
  return registry.get(type);
}

export function getRegisteredChartTypes(): ChartType[] {
  return Array.from(registry.keys());
}
