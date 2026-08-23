# API reference

## `<AgentDashboard>`

The composition root — everything else in this doc is composable if you want to build your own layout instead.

```ts
interface AgentDashboardProps {
  workbook: AgentDashboardWorkbook;

  // Filters — omit both for self-managed filter state (see filters.md)
  activeFilters?: ActiveFilters;
  onFilterChange?: (filterId: string, value: FilterValue | undefined, next: ActiveFilters) => void;

  // Pages — omit both for self-managed page state
  activePageId?: string;
  onPageChange?: (pageId: string) => void;

  // Lazy loading — see data-loading.md
  dataLoaders?: Record<string, DataLoader>;
  chunkSize?: number; // default 200

  // Theming — see theming.md
  theme?: 'light' | 'dark' | ThemeTokens; // default 'light'

  // Customization — see customization.md
  chartRenderers?: Partial<Record<ChartType, ChartComponent>>;
  filterRenderers?: Partial<Record<FilterType, FilterComponent>>;

  rowHeightPx?: number; // default 60 — px per layout grid row unit

  // className/style land on the root element — host controls outer sizing here
  className?: string;
  style?: CSSProperties;

  renderHeader?: (workbook: AgentDashboardWorkbook) => ReactNode;
  renderEmpty?: () => ReactNode; // shown when workbook.pages or .charts is empty
}
```

## `<ChartRenderer chart={chart} />`

Must be rendered inside an `<AgentDashboard>` (or your own `DashboardProvider`, if composing manually). Resolves `chart`'s data (through lazy loading + filters + aggregation) and renders whatever's registered for `chart.type`, wrapped in a `.kdash-panel` with `chart.title` as the header.

## `<FilterBar />`

Renders one control per `workbook.filters[]` from context. Renders nothing if there are no filters. Uses `getFilterComponent` from context, so per-instance `filterRenderers` overrides apply automatically.

## `<DashboardGrid page={page} rowHeightPx={60} />`

Renders `page`'s chart grid from context's `workbook.charts`, responsively — see `architecture.md#responsive-layout` for the 12/6/1-column breakpoint behavior. Used internally by `<AgentDashboard>`; exported in case you want your own page-switching UI around it instead of `<PageTabs>`.

```ts
function scaleSpan(x: number, w: number, fromCols: number, toCols: number): { x: number; w: number };
```

The pure proportional-rescaling function `DashboardGrid` uses to derive the 6-column (tablet) placement from the schema's native 12-column layout. Exported in case you want to build your own responsive layout component against different breakpoints/column counts.

## `<PageTabs pages={pages} activePageId={id} onSelect={fn} />`

Pure/controlled — no internal state. Renders nothing when `pages.length <= 1`.

## `useDashboard()`

```ts
function useDashboard(): {
  workbook: AgentDashboardWorkbook;
  activeFilters: ActiveFilters;
  setFilterValue: (filterId: string, value: FilterValue | undefined) => void;
  dataLoaders: Record<string, DataLoader>;
  chunkSize: number;
  themeTokens: ThemeTokens;
  echartsThemeName: string;
  getChartComponent: (type: ChartType) => ChartComponent | undefined;
  getFilterComponent: (type: FilterType) => FilterComponent | undefined;
};
```

Throws if called outside an `<AgentDashboard>`. Use this from a custom chart/filter component (see `customization.md`) to reach the workbook, theme tokens, or other dashboard state.

## Data pipeline functions

```ts
function resolveChartRows(
  workbook: AgentDashboardWorkbook,
  chart: Chart,
  activeFilters?: ActiveFilters,
  overrideRows?: DataRow[], // pass lazily-loaded rows here instead of dataSource.data
): DataRow[];

function applyFiltersToDataSource(
  rows: DataRow[],
  dataSourceId: string,
  filters: Filter[],
  activeFilters: ActiveFilters,
  chartId: string,
): DataRow[];

function rowMatchesFilter(row: DataRow, filter: Filter, value: FilterValue | undefined): boolean;

function aggregateRows(rows: DataRow[], groupFields: string[], valueField: string | undefined, fn: AggregateFn | undefined): DataRow[];
```

## `useLazyDataSource(options)`

See `data-loading.md` for the full design.

```ts
function useLazyDataSource(options: {
  initialRows: DataRow[];
  loader?: DataLoader;
  chunkSize?: number;
  activeFilters: ActiveFilters;
  autoFetchAll?: boolean; // default true
}): {
  rows: DataRow[];
  isLoading: boolean;
  hasMore: boolean;
  error: Error | null;
  total?: number;
  loadedCount: number;
  loadMore: () => void;
};

type DataLoader = (params: { offset: number; limit: number; filters: ActiveFilters }) => Promise<{
  rows: DataRow[];
  hasMore: boolean;
  total?: number;
}>;
```

## Registries

```ts
function registerChartRenderer(type: ChartType, component: ChartComponent): void;
function getChartRenderer(type: ChartType): ChartComponent | undefined;
function getRegisteredChartTypes(): ChartType[];

function registerFilterRenderer(type: FilterType, component: FilterComponent): void;
function getFilterRenderer(type: FilterType): FilterComponent | undefined;
```

`ChartComponent` / `ChartComponentProps` and `FilterComponent` / `FilterComponentProps` are documented in `customization.md`.

## Geo maps

```ts
function registerGeoMap(name: string, geoJson: Record<string, unknown>): void;
function isGeoMapRegistered(name: string): boolean;

const DEFAULT_GEO_MAP_NAME = 'world'; // the map name geo_choropleth looks for unless you override its component
```

## Schema / validation

```ts
const AGENT_DASHBOARD_SCHEMA: object; // the JSON Schema, map_interactive removed

function validateWorkbook(workbook: AgentDashboardWorkbook): string[]; // structural cross-reference checks, dev aid only
```

## Schema versioning

See `schema-versioning.md` for the full design.

```ts
const CURRENT_SCHEMA_VERSION: number; // 1 today

type VersionedWorkbookInput = { schemaVersion?: number } & Record<string, unknown>;
type SchemaAdapter = (input: VersionedWorkbookInput) => VersionedWorkbookInput;

function registerSchemaAdapter(fromVersion: number, adapter: SchemaAdapter): void;
function migrateWorkbook(raw: VersionedWorkbookInput): AgentDashboardWorkbook;
function clearSchemaAdapters(): void; // test isolation only, not for app code
```

## Theming

```ts
const DEFAULT_LIGHT_THEME: ThemeTokens;
const DEFAULT_DARK_THEME: ThemeTokens;

function resolveThemeTokens(theme: 'light' | 'dark' | ThemeTokens | undefined): { name: 'light' | 'dark' | 'custom'; tokens: ThemeTokens };
function themeTokensToCssVars(tokens: ThemeTokens): Record<string, string>;
function buildEChartsTheme(tokens: ThemeTokens, name: string): string; // registers + returns the ECharts theme name
function echartsThemeName(themeState: { name: 'light' | 'dark' | 'custom'; tokens: ThemeTokens }): string;
```
