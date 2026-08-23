// Types — see docs/agent-dashboard/types.md
export * from './types';

// Schema + dev-time structural validation
export { AGENT_DASHBOARD_SCHEMA, validateWorkbook } from './schema';

// Schema versioning — see docs/agent-dashboard/schema-versioning.md
export {
  CURRENT_SCHEMA_VERSION,
  migrateWorkbook,
  registerSchemaAdapter,
  clearSchemaAdapters,
  type SchemaAdapter,
  type VersionedWorkbookInput,
} from './schema-versioning';

// Theming — see docs/agent-dashboard/theming.md
export {
  DEFAULT_LIGHT_THEME,
  DEFAULT_DARK_THEME,
  resolveThemeTokens,
  themeTokensToCssVars,
  buildEChartsTheme,
  echartsThemeName,
  type ThemeTokens,
  type ThemeInput,
} from './theme';

// Top-level component — see docs/agent-dashboard/api.md
export { AgentDashboard, type AgentDashboardProps } from './agent-dashboard';

// Composable pieces, for apps that want to build their own layout around them
export { ChartRenderer, type ChartRendererProps } from './charts/chart-renderer';
export { FilterBar } from './filters/filter-bar';
export { DashboardGrid, type DashboardGridProps } from './layout/dashboard-grid';
export { PageTabs, type PageTabsProps } from './layout/page-tabs';
export { scaleSpan } from './layout/scale-span';

// Context, for custom chart/filter components that need workbook/theme access
export { useDashboard } from './context/use-dashboard';
export type { DashboardContextValue } from './context/dashboard-context';

// Customization — see docs/agent-dashboard/customization.md
export { registerChartRenderer, getChartRenderer, getRegisteredChartTypes, type ChartComponent, type ChartComponentProps } from './charts/chart-registry';
export { registerFilterRenderer, getFilterRenderer, type FilterComponent, type FilterComponentProps } from './filters/filter-registry';
export { registerGeoMap, isGeoMapRegistered } from './charts/echarts/geo-map-registry';
export { DEFAULT_GEO_MAP_NAME, buildGeoChoroplethOption } from './charts/echarts/option-builders';
export { EChartsBase, type EChartsBaseProps } from './charts/echarts/echarts-base';
export { buildTradingSeriesConfig, type TradingSeriesConfig } from './charts/trading/build-trading-config';
export { computeSMA, computeEMA, computeRSI, computeMACD } from './charts/trading/indicators';

// Data pipeline, exposed for testing/advanced use — see docs/agent-dashboard/data-loading.md
export { resolveChartRows } from './data/resolve-data';
export { applyFiltersToDataSource, rowMatchesFilter } from './data/apply-filters';
export { aggregateRows } from './data/aggregate';
export {
  useLazyDataSource,
  type DataLoader,
  type DataLoaderParams,
  type DataLoaderResult,
  type LazyDataSourceState,
} from './data/lazy-data-source';
