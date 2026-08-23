import { useState, type CSSProperties, type ReactNode } from 'react';
import type { ActiveFilters, AgentDashboardWorkbook, ChartType, FilterType, FilterValue } from './types';
import { DashboardProvider } from './context/dashboard-context';
import type { ChartComponent } from './charts/chart-registry';
import { registerBuiltinCharts } from './charts/register-builtins';
import type { FilterComponent } from './filters/filter-registry';
import { registerBuiltinFilters } from './filters/register-builtins';
import { FilterBar } from './filters/filter-bar';
import { PageTabs } from './layout/page-tabs';
import { DashboardGrid } from './layout/dashboard-grid';
import type { DataLoader } from './data/lazy-data-source';
import { resolveThemeTokens, themeTokensToCssVars, type ThemeInput } from './theme';

registerBuiltinCharts();
registerBuiltinFilters();

export interface AgentDashboardProps {
  workbook: AgentDashboardWorkbook;
  /** Controlled active filter values — pass together with `onFilterChange`, else the dashboard manages its own filter state. */
  activeFilters?: ActiveFilters;
  onFilterChange?: (filterId: string, value: FilterValue | undefined, next: ActiveFilters) => void;
  /** Controlled current page — pass together with `onPageChange`, else the dashboard manages its own page state. */
  activePageId?: string;
  onPageChange?: (pageId: string) => void;
  /** Per-DataSource lazy loaders — see docs/agent-dashboard/data-loading.md. */
  dataLoaders?: Record<string, DataLoader>;
  chunkSize?: number;
  theme?: ThemeInput;
  /** Per-instance chart renderer overrides, layered on top of the global registry from registerChartRenderer(). */
  chartRenderers?: Partial<Record<ChartType, ChartComponent>>;
  filterRenderers?: Partial<Record<FilterType, FilterComponent>>;
  rowHeightPx?: number;
  className?: string;
  style?: CSSProperties;
  renderHeader?: (workbook: AgentDashboardWorkbook) => ReactNode;
  renderEmpty?: () => ReactNode;
}

/**
 * Top-level composition root: renders a full AgentDashboardWorkbook — filter
 * bar, page tabs, and the active page's chart grid. `className`/`style` land
 * on the root element so the host controls outer sizing/positioning from
 * JSX; everything inside (layout, chart placement) is schema-driven.
 */
export function AgentDashboard({
  workbook,
  activeFilters,
  onFilterChange,
  activePageId,
  onPageChange,
  dataLoaders,
  chunkSize,
  theme,
  chartRenderers,
  filterRenderers,
  rowHeightPx,
  className,
  style,
  renderHeader,
  renderEmpty,
}: AgentDashboardProps) {
  const [internalPageId, setInternalPageId] = useState<string | undefined>(workbook.pages[0]?.id);
  const isPageControlled = activePageId !== undefined && onPageChange !== undefined;
  const currentPageId = isPageControlled ? activePageId : internalPageId;
  const setCurrentPageId = (pageId: string) => {
    if (isPageControlled) onPageChange?.(pageId);
    else setInternalPageId(pageId);
  };

  const themeState = resolveThemeTokens(theme);
  const rootStyle = { ...themeTokensToCssVars(themeState.tokens), ...style } as CSSProperties;
  const rootClassName = ['kdash-root', className].filter(Boolean).join(' ');
  const dataThemeAttr = themeState.name === 'dark' ? 'dark' : undefined;

  if (workbook.pages.length === 0 || workbook.charts.length === 0) {
    return (
      <div className={rootClassName} data-kdash-theme={dataThemeAttr} style={rootStyle}>
        {renderEmpty ? renderEmpty() : <div className="kdash-empty-state kdash-muted">No pages or charts in this workbook.</div>}
      </div>
    );
  }

  const currentPage = workbook.pages.find((p) => p.id === currentPageId) ?? workbook.pages[0];

  return (
    <DashboardProvider
      workbook={workbook}
      activeFilters={activeFilters}
      onFilterChange={onFilterChange}
      dataLoaders={dataLoaders}
      chunkSize={chunkSize}
      theme={theme}
      chartRenderers={chartRenderers}
      filterRenderers={filterRenderers}
    >
      <div className={rootClassName} data-kdash-theme={dataThemeAttr} style={rootStyle}>
        {renderHeader?.(workbook)}
        <FilterBar />
        <PageTabs pages={workbook.pages} activePageId={currentPage.id} onSelect={setCurrentPageId} />
        <DashboardGrid page={currentPage} rowHeightPx={rowHeightPx} />
      </div>
    </DashboardProvider>
  );
}
