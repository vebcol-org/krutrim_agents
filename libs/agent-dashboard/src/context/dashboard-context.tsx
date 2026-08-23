import { createContext, useCallback, useMemo, useState, type ReactNode } from 'react';
import type { ActiveFilters, AgentDashboardWorkbook, ChartType, FilterType, FilterValue } from '../types';
import type { ChartComponent } from '../charts/chart-registry';
import { getChartRenderer } from '../charts/chart-registry';
import type { FilterComponent } from '../filters/filter-registry';
import { getFilterRenderer } from '../filters/filter-registry';
import type { DataLoader } from '../data/lazy-data-source';
import { buildEChartsTheme, echartsThemeName, resolveThemeTokens, type ThemeInput, type ThemeTokens } from '../theme';

export interface DashboardContextValue {
  workbook: AgentDashboardWorkbook;
  activeFilters: ActiveFilters;
  setFilterValue: (filterId: string, value: FilterValue | undefined) => void;
  dataLoaders: Record<string, DataLoader>;
  chunkSize: number;
  themeTokens: ThemeTokens;
  echartsThemeName: string;
  getChartComponent: (type: ChartType) => ChartComponent | undefined;
  getFilterComponent: (type: FilterType) => FilterComponent | undefined;
}

export const DashboardContext = createContext<DashboardContextValue | null>(null);

export interface DashboardProviderProps {
  workbook: AgentDashboardWorkbook;
  activeFilters?: ActiveFilters;
  onFilterChange?: (filterId: string, value: FilterValue | undefined, next: ActiveFilters) => void;
  dataLoaders?: Record<string, DataLoader>;
  chunkSize?: number;
  theme?: ThemeInput;
  chartRenderers?: Partial<Record<ChartType, ChartComponent>>;
  filterRenderers?: Partial<Record<FilterType, FilterComponent>>;
  children: ReactNode;
}

function defaultFilterValues(workbook: AgentDashboardWorkbook): ActiveFilters {
  const defaults: ActiveFilters = {};
  for (const filter of workbook.filters ?? []) {
    if (filter.defaultValue !== undefined) defaults[filter.id] = filter.defaultValue;
  }
  return defaults;
}

/**
 * Wraps a workbook render in shared state: active filter values (controlled
 * if `activeFilters`/`onFilterChange` are both passed, else self-managed),
 * resolved theme tokens, and per-instance chart/filter renderer overrides
 * layered on top of the global registries (chart-registry.ts / filter-registry.ts).
 */
export function DashboardProvider({
  workbook,
  activeFilters: controlledFilters,
  onFilterChange,
  dataLoaders = {},
  chunkSize = 200,
  theme,
  chartRenderers = {},
  filterRenderers = {},
  children,
}: DashboardProviderProps) {
  const [internalFilters, setInternalFilters] = useState<ActiveFilters>(() => defaultFilterValues(workbook));
  const isControlled = controlledFilters !== undefined && onFilterChange !== undefined;
  const activeFilters = isControlled ? controlledFilters : internalFilters;

  const setFilterValue = useCallback(
    (filterId: string, value: FilterValue | undefined) => {
      if (isControlled) {
        onFilterChange(filterId, value, { ...controlledFilters, [filterId]: value });
      } else {
        setInternalFilters((prev) => ({ ...prev, [filterId]: value }));
      }
    },
    [isControlled, onFilterChange, controlledFilters],
  );

  const themeState = useMemo(() => resolveThemeTokens(theme), [theme]);
  const echartsName = useMemo(() => {
    const name = echartsThemeName(themeState);
    buildEChartsTheme(themeState.tokens, name);
    return name;
  }, [themeState]);

  const getChartComponent = useCallback(
    (type: ChartType) => chartRenderers[type] ?? getChartRenderer(type),
    [chartRenderers],
  );
  const getFilterComponent = useCallback(
    (type: FilterType) => filterRenderers[type] ?? getFilterRenderer(type),
    [filterRenderers],
  );

  const value = useMemo<DashboardContextValue>(
    () => ({
      workbook,
      activeFilters,
      setFilterValue,
      dataLoaders,
      chunkSize,
      themeTokens: themeState.tokens,
      echartsThemeName: echartsName,
      getChartComponent,
      getFilterComponent,
    }),
    [workbook, activeFilters, setFilterValue, dataLoaders, chunkSize, themeState, echartsName, getChartComponent, getFilterComponent],
  );

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}
