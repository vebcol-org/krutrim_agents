# Filters

## The 5 filter types

| `type` | Value shape | Default control | Behavior |
|---|---|---|---|
| `categorical` | `string[]` | multi-select | Empty array = no filtering (matches everything), not "match nothing". |
| `range` | `[number, number]` | two number inputs | Inclusive bounds. |
| `dateRange` | `[string, string]` (ISO dates) | two date inputs | Inclusive bounds, compared as parsed `Date`s. |
| `boolean` | `boolean` | checkbox | Exact match against the row's (coerced) boolean value. |
| `search` | `string` | text input | Case-insensitive substring match; empty string = no filtering. |

Distinct option values for `categorical` filters are computed automatically from the target `DataSource`'s actual `data` (`FilterBar`'s `distinctValues`) — you don't declare the option list in the workbook.

## `appliesTo` semantics

A `Filter` only narrows a chart if `filter.appliesTo` includes that chart's `id`, or is exactly `['*']` (every chart reading the same `dataSourceId`). This lets a workbook have, say, a region filter that affects every chart on a data source, alongside a chart-specific search filter that only narrows one table.

## Controlled vs. self-managed filter state

```tsx
// Self-managed (simplest — the dashboard tracks its own state internally)
<AgentDashboard workbook={workbook} />

// Controlled (you own the state, e.g. to sync it to the URL or persist it)
const [activeFilters, setActiveFilters] = useState<ActiveFilters>({});
<AgentDashboard
  workbook={workbook}
  activeFilters={activeFilters}
  onFilterChange={(filterId, value, next) => setActiveFilters(next)}
/>
```

Pass **both** `activeFilters` and `onFilterChange` to go controlled, or **neither** to self-manage — passing only one is treated as self-managed (see `DashboardProvider`'s `isControlled` check in `dashboard-context.tsx`). `Filter.defaultValue` is applied once, on first render, only in self-managed mode.

## Custom filter controls

See `customization.md` for `registerFilterRenderer`/the `filterRenderers` prop — e.g. swapping the default two-input `range` control for a real dual-handle slider.
