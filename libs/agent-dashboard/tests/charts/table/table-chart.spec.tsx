import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { DashboardProvider } from '../../../src/context/dashboard-context';
import { TableChart } from '../../../src/charts/table/table-chart';
import { DEFAULT_LIGHT_THEME } from '../../../src/theme';
import type { AgentDashboardWorkbook, Chart } from '../../../src/types';

afterEach(cleanup);

const workbook: AgentDashboardWorkbook = {
  workbookId: 'wb',
  agentType: 'research',
  dataSources: [
    {
      id: 'ds',
      fields: [
        { name: 'name', role: 'dimension', dataType: 'string' },
        { name: 'amount', role: 'measure', dataType: 'number' },
      ],
      data: [],
    },
  ],
  charts: [],
  pages: [],
};

const chart: Chart = { id: 'c1', dataSourceId: 'ds', type: 'table', encoding: {} };

function renderTable(overrides: Partial<ComponentProps<typeof TableChart>> = {}) {
  const defaultProps: ComponentProps<typeof TableChart> = {
    chart,
    rows: [
      { name: 'B', amount: 2 },
      { name: 'A', amount: 5 },
    ],
    isLoading: false,
    loadedCount: 2,
    total: undefined,
    hasMore: false,
    onLoadMore: vi.fn(),
    themeTokens: DEFAULT_LIGHT_THEME,
    echartsThemeName: 'kdash-light',
  };
  return render(
    <DashboardProvider workbook={workbook}>
      <TableChart {...defaultProps} {...overrides} />
    </DashboardProvider>,
  );
}

describe('TableChart', () => {
  it('renders one row per data row with columns from the DataSource fields', () => {
    renderTable();
    expect(screen.getByText('name')).not.toBeNull();
    expect(screen.getByText('amount')).not.toBeNull();
    expect(screen.getAllByRole('row')).toHaveLength(3); // header + 2 data rows
  });

  it('sorts rows ascending when a column header is clicked', () => {
    renderTable();
    fireEvent.click(screen.getByText('name'));
    const cells = screen.getAllByRole('cell');
    expect(cells[0].textContent).toBe('A');
  });

  it('shows a Load more button that calls onLoadMore when hasMore is true', () => {
    const onLoadMore = vi.fn();
    renderTable({ hasMore: true, onLoadMore });
    fireEvent.click(screen.getByRole('button', { name: /load more/i }));
    expect(onLoadMore).toHaveBeenCalled();
  });

  it('renders an empty state when there are no rows and not loading', () => {
    renderTable({ rows: [] });
    expect(screen.getByText(/no data/i)).not.toBeNull();
  });
});
