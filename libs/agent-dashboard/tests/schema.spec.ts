import { describe, expect, it } from 'vitest';
import { validateWorkbook } from '../src/schema';
import type { AgentDashboardWorkbook } from '../src/types';

function baseWorkbook(): AgentDashboardWorkbook {
  return {
    workbookId: 'wb',
    agentType: 'research',
    dataSources: [{ id: 'ds1', fields: [{ name: 'a', role: 'dimension', dataType: 'string' }], data: [] }],
    filters: [{ id: 'f1', field: 'a', dataSourceId: 'ds1', type: 'categorical', appliesTo: ['*'] }],
    charts: [{ id: 'c1', dataSourceId: 'ds1', type: 'bar', encoding: {} }],
    pages: [{ id: 'p1', name: 'Page', layout: [{ chartId: 'c1', x: 0, y: 0, w: 1, h: 1 }] }],
  };
}

describe('validateWorkbook', () => {
  it('returns no problems for an internally-consistent workbook', () => {
    expect(validateWorkbook(baseWorkbook())).toEqual([]);
  });

  it('flags a chart referencing an unknown dataSourceId', () => {
    const wb = baseWorkbook();
    wb.charts[0].dataSourceId = 'missing';
    expect(validateWorkbook(wb)).toEqual(['Chart "c1" references unknown dataSourceId "missing"']);
  });

  it('flags a filter referencing an unknown dataSourceId or chart id', () => {
    const wb = baseWorkbook();
    wb.filters![0].dataSourceId = 'missing-ds';
    wb.filters![0].appliesTo = ['missing-chart'];
    expect(validateWorkbook(wb)).toEqual([
      'Filter "f1" references unknown dataSourceId "missing-ds"',
      'Filter "f1" appliesTo references unknown chart id "missing-chart"',
    ]);
  });

  it('flags a page layout entry referencing an unknown chart id', () => {
    const wb = baseWorkbook();
    wb.pages[0].layout[0].chartId = 'missing-chart';
    expect(validateWorkbook(wb)).toEqual(['Page "p1" layout references unknown chart id "missing-chart"']);
  });
});
