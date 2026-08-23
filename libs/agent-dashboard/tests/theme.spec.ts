import { describe, expect, it } from 'vitest';
import { DEFAULT_DARK_THEME, DEFAULT_LIGHT_THEME, resolveThemeTokens, themeTokensToCssVars } from '../src/theme';

describe('resolveThemeTokens', () => {
  it('defaults to light when no theme is given', () => {
    expect(resolveThemeTokens(undefined)).toEqual({ name: 'light', tokens: DEFAULT_LIGHT_THEME });
  });

  it('resolves the "dark" named theme', () => {
    expect(resolveThemeTokens('dark')).toEqual({ name: 'dark', tokens: DEFAULT_DARK_THEME });
  });

  it('treats a full ThemeTokens object as a custom theme, unchanged', () => {
    const custom = { ...DEFAULT_LIGHT_THEME, accent: '#ff0000' };
    expect(resolveThemeTokens(custom)).toEqual({ name: 'custom', tokens: custom });
  });
});

describe('themeTokensToCssVars', () => {
  it('maps every token to its --kdash-* CSS custom property', () => {
    const vars = themeTokensToCssVars(DEFAULT_LIGHT_THEME);
    expect(vars['--kdash-background']).toBe(DEFAULT_LIGHT_THEME.background);
    expect(vars['--kdash-series-1']).toBe(DEFAULT_LIGHT_THEME.series[0]);
    expect(vars['--kdash-up']).toBe(DEFAULT_LIGHT_THEME.up);
  });
});
