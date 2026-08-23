# Theming

This package is **self-contained** — it does not depend on `@krutrim_agent/ui` or its Tailwind theme, since it has to work as a standalone library before any integration into the app. Import its own stylesheet once:

```ts
import '@krutrim_agent/agent-dashboard/theme.css';
```

## Token model

`theme.css` defines a namespaced token set (`--kdash-*`, never colliding with a host app's own tokens) scoped to `.kdash-root` — the class `<AgentDashboard>` puts on its own root `<div>`, not on `<html>` or `<body>`. That scoping is what lets this package sit inside any host page without touching the host's theme.

| Token | Meaning |
|---|---|
| `--kdash-background` / `--kdash-surface` | Page background / panel background. |
| `--kdash-border` | Panel borders, table row dividers. |
| `--kdash-text` / `--kdash-muted` | Primary / secondary text. |
| `--kdash-accent` | Active tab underline, links, "load more". |
| `--kdash-series-1` … `--kdash-series-8` | ECharts series palette, in order. |
| `--kdash-grid-line` | ECharts axis split lines. |
| `--kdash-up` / `--kdash-down` | Candlestick colors, KPI delta colors. |

Light is the default (bare `.kdash-root` selector); dark is `.kdash-root[data-kdash-theme='dark']`.

## The `theme` prop

```tsx
<AgentDashboard workbook={workbook} theme="light" />   // default
<AgentDashboard workbook={workbook} theme="dark" />
<AgentDashboard workbook={workbook} theme={{           // fully custom — see ThemeTokens in api.md
  background: '#000814', surface: '#001d3d', border: '#003566',
  text: '#ffd60a', muted: '#8899aa', accent: '#ffc300',
  series: ['#ffc300', '#ffd60a', '#00b4d8', '#90e0ef', '#ff006e', '#8338ec', '#3a86ff', '#fb5607'],
  gridLine: '#003566', up: '#38b000', down: '#d90429',
}} />
```

`'light'`/`'dark'` set `data-kdash-theme` on the root element so the CSS rules above apply. A full `ThemeTokens` object instead applies every token as an inline CSS variable on the root element (no `data-kdash-theme` attribute, since there's nothing for the CSS file to match against) — see `resolveThemeTokens`/`themeTokensToCssVars` in `api.md`.

## `className`/`style` — sizing from JSX

`<AgentDashboard>` forwards `className` and `style` straight onto its root element, alongside the theme CSS variables (your `style` values win if a key overlaps, since they're spread last). This is how the host controls outer sizing/positioning — everything inside (chart layout, grid placement) is schema-driven, not something you size individually:

```tsx
<AgentDashboard workbook={workbook} style={{ width: '100%', height: '80vh' }} className="rounded-lg shadow-xl" />
```

## ECharts theme sync

`buildEChartsTheme(tokens, name)` derives an ECharts theme (series colors, axis/grid-line colors, tooltip styling) from the same `ThemeTokens` object and registers it once via `echarts.registerTheme`. `DashboardProvider` calls this automatically whenever `theme` changes, so every ECharts-backed chart type picks up the right palette without each chart's own option-builder duplicating color logic. `lightweight-charts`' candlestick chart reads `up`/`down`/`muted`/`gridLine` directly from `themeTokens` instead, since it isn't an ECharts theme.
