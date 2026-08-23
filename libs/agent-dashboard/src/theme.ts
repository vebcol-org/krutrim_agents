import * as echarts from 'echarts';

export interface ThemeTokens {
  background: string;
  surface: string;
  border: string;
  text: string;
  muted: string;
  accent: string;
  series: [string, string, string, string, string, string, string, string];
  gridLine: string;
  up: string;
  down: string;
}

export const DEFAULT_LIGHT_THEME: ThemeTokens = {
  background: '#ffffff',
  surface: '#f7f8fa',
  border: '#e2e5ea',
  text: '#1a1d21',
  muted: '#6b7280',
  accent: '#2563eb',
  series: ['#2563eb', '#16a34a', '#d97706', '#dc2626', '#7c3aed', '#0891b2', '#db2777', '#65a30d'],
  gridLine: '#eceff2',
  up: '#16a34a',
  down: '#dc2626',
};

export const DEFAULT_DARK_THEME: ThemeTokens = {
  background: '#0b0e11',
  surface: '#12161b',
  border: '#232a31',
  text: '#d7dbde',
  muted: '#7c8790',
  accent: '#3b82f6',
  series: ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#a855f7', '#06b6d4', '#ec4899', '#84cc16'],
  gridLine: '#1c2126',
  up: '#22c55e',
  down: '#ef4444',
};

/** Named theme or a fully custom token set — the shape `<AgentDashboard theme>` accepts. */
export type ThemeInput = 'light' | 'dark' | ThemeTokens;

export function resolveThemeTokens(theme: ThemeInput | undefined): { name: 'light' | 'dark' | 'custom'; tokens: ThemeTokens } {
  if (theme === undefined || theme === 'light') return { name: 'light', tokens: DEFAULT_LIGHT_THEME };
  if (theme === 'dark') return { name: 'dark', tokens: DEFAULT_DARK_THEME };
  return { name: 'custom', tokens: theme };
}

/** CSS custom properties to spread into the root element's inline `style`. */
export function themeTokensToCssVars(tokens: ThemeTokens): Record<string, string> {
  return {
    '--kdash-background': tokens.background,
    '--kdash-surface': tokens.surface,
    '--kdash-border': tokens.border,
    '--kdash-text': tokens.text,
    '--kdash-muted': tokens.muted,
    '--kdash-accent': tokens.accent,
    '--kdash-series-1': tokens.series[0],
    '--kdash-series-2': tokens.series[1],
    '--kdash-series-3': tokens.series[2],
    '--kdash-series-4': tokens.series[3],
    '--kdash-series-5': tokens.series[4],
    '--kdash-series-6': tokens.series[5],
    '--kdash-series-7': tokens.series[6],
    '--kdash-series-8': tokens.series[7],
    '--kdash-grid-line': tokens.gridLine,
    '--kdash-up': tokens.up,
    '--kdash-down': tokens.down,
  };
}

const REGISTERED_ECHARTS_THEMES = new Set<string>();

/**
 * Registers (once per token set) an ECharts theme mirroring `tokens`, so
 * every ECharts-backed chart type picks up matching colors without each
 * chart's own option-builder duplicating the palette. Returns the theme
 * name to pass to `echarts.init(el, themeName)`.
 */
export function buildEChartsTheme(tokens: ThemeTokens, name: string): string {
  if (REGISTERED_ECHARTS_THEMES.has(name)) return name;
  echarts.registerTheme(name, {
    color: tokens.series,
    backgroundColor: 'transparent',
    textStyle: { color: tokens.text },
    title: { textStyle: { color: tokens.text }, subtextStyle: { color: tokens.muted } },
    legend: { textStyle: { color: tokens.muted } },
    tooltip: {
      backgroundColor: tokens.surface,
      borderColor: tokens.border,
      textStyle: { color: tokens.text },
    },
    categoryAxis: {
      axisLine: { lineStyle: { color: tokens.border } },
      axisLabel: { color: tokens.muted },
      splitLine: { lineStyle: { color: tokens.gridLine } },
    },
    valueAxis: {
      axisLine: { lineStyle: { color: tokens.border } },
      axisLabel: { color: tokens.muted },
      splitLine: { lineStyle: { color: tokens.gridLine } },
    },
  });
  REGISTERED_ECHARTS_THEMES.add(name);
  return name;
}

export function echartsThemeName(themeState: { name: 'light' | 'dark' | 'custom'; tokens: ThemeTokens }): string {
  return themeState.name === 'custom' ? `kdash-custom-${hashTokens(themeState.tokens)}` : `kdash-${themeState.name}`;
}

function hashTokens(tokens: ThemeTokens): string {
  let hash = 0;
  const str = JSON.stringify(tokens);
  for (let i = 0; i < str.length; i++) {
    hash = (hash * 31 + str.charCodeAt(i)) | 0;
  }
  return Math.abs(hash).toString(36);
}
