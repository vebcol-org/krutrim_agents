import { describe, expect, it } from 'vitest';
import { resolveChartRows } from '../../src/data/resolve-data';
import type { AgentDashboardWorkbook } from '../../src/types';

const workbook: AgentDashboardWorkbook = {
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
        { region: 'us', amount: 100 },
        { region: 'us', amount: 50 },
        { region: 'eu', amount: 30 },
      ],
    },
  ],
  filters: [{ id: 'region-filter', field: 'region', dataSourceId: 'deals', type: 'categorical', appliesTo: ['*'] }],
  charts: [
    {
      id: 'chart-1',
      dataSourceId: 'deals',
      type: 'bar',
      encoding: { x: 'region', y: 'amount', aggregate: 'sum' },
    },
  ],
  pages: [{ id: 'page-1', name: 'Overview', layout: [{ chartId: 'chart-1', x: 0, y: 0, w: 12, h: 4 }] }],
};

describe('resolveChartRows', () => {
  it('filters then aggregates by encoding.x with encoding.aggregate', () => {
    const rows = resolveChartRows(workbook, workbook.charts[0], {});
    expect(rows).toEqual([
      { region: 'us', amount: 150 },
      { region: 'eu', amount: 30 },
    ]);
  });

  it('applies active filters before aggregating', () => {
    const rows = resolveChartRows(workbook, workbook.charts[0], { 'region-filter': ['us'] });
    expect(rows).toEqual([{ region: 'us', amount: 150 }]);
  });

  it('uses overrideRows (from lazy loading) instead of the static dataSource.data when provided', () => {
    const rows = resolveChartRows(workbook, workbook.charts[0], {}, [{ region: 'apac', amount: 999 }]);
    expect(rows).toEqual([{ region: 'apac', amount: 999 }]);
  });

  it('returns an empty array for an unknown dataSourceId', () => {
    const badChart = { ...workbook.charts[0], dataSourceId: 'missing' };
    expect(resolveChartRows(workbook, badChart, {})).toEqual([]);
  });
});
