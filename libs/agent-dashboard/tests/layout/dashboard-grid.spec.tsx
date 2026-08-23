import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { DashboardProvider } from '../../src/context/dashboard-context';
import { DashboardGrid } from '../../src/layout/dashboard-grid';
import type { AgentDashboardWorkbook } from '../../src/types';

afterEach(cleanup);

const workbook: AgentDashboardWorkbook = {
  workbookId: 'wb',
  agentType: 'sales',
  dataSources: [{ id: 'ds', fields: [{ name: 'x', role: 'dimension', dataType: 'string' }], data: [] }],
  charts: [
    { id: 'c1', dataSourceId: 'ds', type: 'bar', encoding: {} },
    { id: 'c2', dataSourceId: 'ds', type: 'bar', encoding: {} },
  ],
  pages: [
    {
      id: 'p1',
      name: 'Page',
      layout: [
        { chartId: 'c2', x: 6, y: 0, w: 6, h: 3 }, // deliberately listed before c1
        { chartId: 'c1', x: 2, y: 1, w: 4, h: 3 },
      ],
    },
  ],
};

function Stub({ chart }: { chart: { id: string } }) {
  return <div data-testid={`stub-${chart.id}`} />;
}

// jsdom doesn't parse the external stylesheet (theme.css) or evaluate media
// queries/calc(), so these tests assert against the CSS custom properties
// DashboardGrid computes per item — the actual grid-column/grid-row math
// lives in theme.css's media-query rules, which is a browser-rendering
// concern outside jsdom's reach.
describe('DashboardGrid', () => {
  it('renders each item on .kdash-grid-item with lg (native 12-col) custom properties from its layout entry', () => {
    render(
      <DashboardProvider workbook={workbook} chartRenderers={{ bar: Stub }}>
        <DashboardGrid page={workbook.pages[0]} rowHeightPx={50} />
      </DashboardProvider>,
    );
    const wrapper = screen.getByTestId('stub-c1').closest('.kdash-grid-item') as HTMLElement;
    expect(wrapper.style.getPropertyValue('--kdash-item-x-lg')).toBe('2');
    expect(wrapper.style.getPropertyValue('--kdash-item-w-lg')).toBe('4');
    expect(wrapper.style.getPropertyValue('--kdash-item-y')).toBe('1');
    expect(wrapper.style.getPropertyValue('--kdash-item-h')).toBe('3');
  });

  it('also precomputes md (6-col) custom properties, proportionally rescaled from the 12-col layout', () => {
    render(
      <DashboardProvider workbook={workbook} chartRenderers={{ bar: Stub }}>
        <DashboardGrid page={workbook.pages[0]} />
      </DashboardProvider>,
    );
    const wrapper = screen.getByTestId('stub-c2').closest('.kdash-grid-item') as HTMLElement;
    // x=6,w=6 on a 12-col grid halves cleanly onto a 6-col grid
    expect(wrapper.style.getPropertyValue('--kdash-item-x-md')).toBe('3');
    expect(wrapper.style.getPropertyValue('--kdash-item-w-md')).toBe('3');
  });

  it('sets --kdash-row-height on the grid container from rowHeightPx', () => {
    const { container } = render(
      <DashboardProvider workbook={workbook} chartRenderers={{ bar: Stub }}>
        <DashboardGrid page={workbook.pages[0]} rowHeightPx={80} />
      </DashboardProvider>,
    );
    const grid = container.querySelector('.kdash-grid') as HTMLElement;
    expect(grid.style.getPropertyValue('--kdash-row-height')).toBe('80px');
  });

  it('renders items in reading order (sorted by y then x), independent of layout array order', () => {
    render(
      <DashboardProvider workbook={workbook} chartRenderers={{ bar: Stub }}>
        <DashboardGrid page={workbook.pages[0]} />
      </DashboardProvider>,
    );
    const items = screen.getAllByTestId(/^stub-/).map((el) => el.getAttribute('data-testid'));
    expect(items).toEqual(['stub-c2', 'stub-c1']); // c2 has y=0, c1 has y=1
  });

  it('silently skips a layout entry whose chartId does not resolve to a known chart', () => {
    const badPage = { id: 'p2', name: 'Bad', layout: [{ chartId: 'missing', x: 0, y: 0, w: 1, h: 1 }] };
    const { container } = render(
      <DashboardProvider workbook={workbook}>
        <DashboardGrid page={badPage} />
      </DashboardProvider>,
    );
    expect(container.querySelectorAll('.kdash-grid-item')).toHaveLength(0);
  });
});
