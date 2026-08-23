# `@krutrim_agent/agent-dashboard`

Nx library `agent-dashboard` (`libs/agent-dashboard`), imported as `@krutrim_agent/agent-dashboard`. A **standalone rendering library** for the `AgentDashboardWorkbook` JSON contract: give it a workbook object (data sources + chart definitions + filters + page layout) and it renders the full dashboard — every chart type, theming, page layout, filters, and lazy/chunked data loading.

**Not wired into `apps/web` or `libs/agent-renderers` yet.** This package is deliberately built and documented in isolation — an agent backend (research/sales/trading) will eventually emit a workbook payload matching this contract, but plugging that output into the live app's canvas is a separate, later pass. Nothing here should be read as "live" the way `docs/frontend/*.md` describes the wired frontend.

## Install (in-repo)

Already a workspace member — just depend on it like any other `libs/*` package:

```ts
import { AgentDashboard } from '@krutrim_agent/agent-dashboard';
import '@krutrim_agent/agent-dashboard/theme.css';
```

## 30-second usage

```tsx
import { AgentDashboard, type AgentDashboardWorkbook } from '@krutrim_agent/agent-dashboard';
import '@krutrim_agent/agent-dashboard/theme.css';

const workbook: AgentDashboardWorkbook = {
  workbookId: 'sales_q3_2026',
  agentType: 'sales',
  title: 'Q3 Sales Overview',
  dataSources: [
    {
      id: 'deals',
      fields: [
        { name: 'region', role: 'dimension', dataType: 'string' },
        { name: 'amount', role: 'measure', dataType: 'number' },
      ],
      data: [
        { region: 'us', amount: 42000 },
        { region: 'eu', amount: 31000 },
      ],
    },
  ],
  charts: [
    { id: 'revenue-by-region', title: 'Revenue by region', dataSourceId: 'deals', type: 'bar', encoding: { x: 'region', y: 'amount', aggregate: 'sum' } },
  ],
  pages: [
    { id: 'overview', name: 'Overview', layout: [{ chartId: 'revenue-by-region', x: 0, y: 0, w: 12, h: 6 }] },
  ],
};

function Dashboard() {
  return <AgentDashboard workbook={workbook} style={{ width: '100%', height: 700 }} />;
}
```

## What's different from the schema you were given

One deliberate deviation: **`map_interactive` is dropped** (pin/route maps needing lat/lng + a live tile provider) — no map-tile adapter is bundled, so that chart `type` and the `lat`/`lng` encoding channels don't exist in this package's types/schema copy. Everything else — 15 remaining chart types plus `geo_choropleth` (which doesn't need live map tiles, just a registered GeoJSON) — is a 1:1 mirror. See [`types.md`](types.md) for the exact field list.

## Docs

- [`architecture.md`](architecture.md) — how the package fits together: the registry pattern, the ECharts/lightweight-charts engine split, the data pipeline, the layout model.
- [`types.md`](types.md) — every exported type, field by field.
- [`api.md`](api.md) — full prop/function/hook reference.
- [`chart-types.md`](chart-types.md) — all 16 chart types: engine, required encoding, minimal example.
- [`theming.md`](theming.md) — the `--kdash-*` token system, light/dark, custom themes.
- [`filters.md`](filters.md) — the 5 filter types, controlled vs. self-managed filter state.
- [`data-loading.md`](data-loading.md) — lazy/chunked data loading design and a worked example.
- [`customization.md`](customization.md) — overriding or adding chart/filter renderers, GeoJSON maps, header/empty slots.
- [`schema-versioning.md`](schema-versioning.md) — `schemaVersion`, `migrateWorkbook`, and the adapter-chain pattern for evolving the contract later without breaking older payloads.
- [`examples.md`](examples.md) — complete runnable workbook + component examples.

## Testing

Tests live under `libs/agent-dashboard/tests/`, mirroring `src/`'s directory structure one level up (`tests/data/aggregate.spec.ts` tests `src/data/aggregate.ts`, etc.) — kept separate from `src/` rather than colocated, unlike `libs/extensions`. `vite.config.mts`'s `test.include` points at `tests/**/*.{test,spec}.{ts,tsx}`; `tsconfig.spec.json` covers the folder for editor/type-checking support. Run with `pnpm exec nx run agent-dashboard:test`. ECharts/lightweight-charts tests assert against the constructed option objects and component behavior, not pixel output, since jsdom has no real canvas — and the responsive grid's breakpoint CSS (media queries, `calc()`) is asserted at the level of the custom properties `DashboardGrid` computes, not real browser layout, for the same reason.
