import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { KpiChart } from '../../../src/charts/kpi/kpi-chart';
import { DEFAULT_LIGHT_THEME } from '../../../src/theme';
import type { Chart } from '../../../src/types';
import type { ChartComponentProps } from '../../../src/charts/chart-registry';

afterEach(cleanup);

const baseProps: Omit<ChartComponentProps, 'chart' | 'rows'> = {
  isLoading: false,
  loadedCount: 1,
  total: undefined,
  hasMore: false,
  onLoadMore: () => {},
  themeTokens: DEFAULT_LIGHT_THEME,
  echartsThemeName: 'kdash-light',
};

const chart: Chart = { id: 'kpi-1', title: 'Active Users', dataSourceId: 'ds', type: 'kpi', encoding: { value: 'count', target: 'goal' } };

describe('KpiChart', () => {
  it('renders the value from the first row', () => {
    render(<KpiChart {...baseProps} chart={chart} rows={[{ count: 1234, goal: 1000 }]} />);
    expect(screen.getByText('1,234')).not.toBeNull();
  });

  it('shows an "up" delta line when value exceeds target', () => {
    render(<KpiChart {...baseProps} chart={chart} rows={[{ count: 1234, goal: 1000 }]} />);
    expect(screen.getByText(/vs target/i).className).toContain('kdash-kpi-delta-up');
  });

  it('shows a "down" delta line when value is below target', () => {
    render(<KpiChart {...baseProps} chart={chart} rows={[{ count: 500, goal: 1000 }]} />);
    expect(screen.getByText(/vs target/i).className).toContain('kdash-kpi-delta-down');
  });

  it('omits the delta line when there is no target field', () => {
    const noTarget: Chart = { ...chart, encoding: { value: 'count' } };
    render(<KpiChart {...baseProps} chart={noTarget} rows={[{ count: 42 }]} />);
    expect(screen.queryByText(/vs target/i)).toBeNull();
  });

  it('renders an empty state when there are no rows', () => {
    render(<KpiChart {...baseProps} chart={chart} rows={[]} />);
    expect(screen.getByText(/no data/i)).not.toBeNull();
  });
});
