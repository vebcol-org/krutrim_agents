import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { AgentDashboard } from '../src/agent-dashboard';
import type { AgentDashboardWorkbook } from '../src/types';
import type { ChartComponentProps } from '../src/charts/chart-registry';

afterEach(cleanup);

// A stub renderer keeps this suite about AgentDashboard's own composition
// (filters, page tabs, layout, registry overrides), independent of the real
// ECharts/lightweight-charts engines — those are covered by
// charts/echarts/option-builders.spec.ts against jsdom-safe pure functions.
function StubChart({ chart, rows }: ChartComponentProps) {
  return (
    <div data-testid={`stub-${chart.id}`}>
      {chart.id}: {rows.length} rows
    </div>
  );
}

function makeWorkbook(): AgentDashboardWorkbook {
  return {
    workbookId: 'wb1',
    agentType: 'research',
    dataSources: [
      {
        id: 'deals',
        fields: [
          { name: 'region', role: 'dimension', dataType: 'string' },
          { name: 'amount', role: 'measure', dataType: 'number' },
        ],
        data: [
          { region: 'us', amount: 10 },
          { region: 'eu', amount: 20 },
        ],
      },
    ],
    filters: [{ id: 'region-filter', label: 'Region', field: 'region', dataSourceId: 'deals', type: 'categorical', appliesTo: ['*'] }],
    charts: [{ id: 'bar-chart', title: 'Revenue by region', dataSourceId: 'deals', type: 'bar', encoding: { x: 'region', y: 'amount' } }],
    pages: [
      { id: 'page-1', name: 'Overview', layout: [{ chartId: 'bar-chart', x: 0, y: 0, w: 12, h: 4 }] },
      { id: 'page-2', name: 'Details', layout: [] },
    ],
  };
}

describe('AgentDashboard (end-to-end)', () => {
  it("renders the active page's charts through the registered renderer, with its title", () => {
    render(<AgentDashboard workbook={makeWorkbook()} chartRenderers={{ bar: StubChart }} />);
    expect(screen.getByText('bar-chart: 2 rows')).not.toBeNull();
    expect(screen.getByText('Revenue by region')).not.toBeNull();
  });

  it('a per-instance chartRenderers override wins over the built-in registry', () => {
    render(<AgentDashboard workbook={makeWorkbook()} chartRenderers={{ bar: StubChart }} />);
    expect(screen.getByTestId('stub-bar-chart')).not.toBeNull();
  });

  it('narrows chart rows when a filter is applied (self-managed filter state)', () => {
    render(<AgentDashboard workbook={makeWorkbook()} chartRenderers={{ bar: StubChart }} />);
    const select = screen.getByRole('listbox');
    const usOption = screen.getByRole('option', { name: 'us' }) as HTMLOptionElement;
    usOption.selected = true;
    fireEvent.change(select);
    expect(screen.getByText('bar-chart: 1 rows')).not.toBeNull();
  });

  it('switches pages via PageTabs, re-rendering the grid for the newly active page', () => {
    render(<AgentDashboard workbook={makeWorkbook()} chartRenderers={{ bar: StubChart }} />);
    expect(screen.getByTestId('stub-bar-chart')).not.toBeNull();
    fireEvent.click(screen.getByRole('tab', { name: 'Details' }));
    expect(screen.queryByTestId('stub-bar-chart')).toBeNull();
  });

  it('renders an empty state for a workbook with no pages or charts', () => {
    render(<AgentDashboard workbook={{ ...makeWorkbook(), charts: [], pages: [] }} />);
    expect(screen.getByText(/no pages or charts/i)).not.toBeNull();
  });
});
