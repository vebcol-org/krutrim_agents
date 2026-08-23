import type { ComponentType } from 'react';
import type { Filter, FilterType, FilterValue } from '../types';

export interface FilterComponentProps {
  filter: Filter;
  value: FilterValue | undefined;
  /** Distinct values seen for `filter.field` in its DataSource — only populated for `categorical`. */
  options?: string[];
  onChange: (value: FilterValue | undefined) => void;
}

export type FilterComponent = ComponentType<FilterComponentProps>;

const registry = new Map<FilterType, FilterComponent>();

/** Same override-or-default pattern as chart-registry.ts's `registerChartRenderer`. */
export function registerFilterRenderer(type: FilterType, component: FilterComponent): void {
  registry.set(type, component);
}

export function getFilterRenderer(type: FilterType): FilterComponent | undefined {
  return registry.get(type);
}
