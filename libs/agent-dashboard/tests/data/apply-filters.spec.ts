import { describe, expect, it } from 'vitest';
import { applyFiltersToDataSource, rowMatchesFilter } from '../../src/data/apply-filters';
import type { Filter } from '../../src/types';

const categoricalFilter: Filter = {
  id: 'f-region',
  field: 'region',
  dataSourceId: 'ds1',
  type: 'categorical',
  appliesTo: ['*'],
};

const rangeFilter: Filter = {
  id: 'f-price',
  field: 'price',
  dataSourceId: 'ds1',
  type: 'range',
  appliesTo: ['*'],
};

const dateRangeFilter: Filter = {
  id: 'f-date',
  field: 'date',
  dataSourceId: 'ds1',
  type: 'dateRange',
  appliesTo: ['*'],
};

const booleanFilter: Filter = {
  id: 'f-active',
  field: 'active',
  dataSourceId: 'ds1',
  type: 'boolean',
  appliesTo: ['*'],
};

const searchFilter: Filter = {
  id: 'f-search',
  field: 'name',
  dataSourceId: 'ds1',
  type: 'search',
  appliesTo: ['chart-1'],
};

describe('rowMatchesFilter', () => {
  it('undefined/null active value always matches (no filtering applied)', () => {
    expect(rowMatchesFilter({ region: 'us' }, categoricalFilter, undefined)).toBe(true);
    expect(rowMatchesFilter({ region: 'us' }, categoricalFilter, null)).toBe(true);
  });

  it('categorical: empty selection matches everything, non-empty restricts', () => {
    expect(rowMatchesFilter({ region: 'us' }, categoricalFilter, [])).toBe(true);
    expect(rowMatchesFilter({ region: 'us' }, categoricalFilter, ['us', 'eu'])).toBe(true);
    expect(rowMatchesFilter({ region: 'apac' }, categoricalFilter, ['us', 'eu'])).toBe(false);
  });

  it('range: inclusive bounds', () => {
    expect(rowMatchesFilter({ price: 50 }, rangeFilter, [0, 100])).toBe(true);
    expect(rowMatchesFilter({ price: 0 }, rangeFilter, [0, 100])).toBe(true);
    expect(rowMatchesFilter({ price: 100 }, rangeFilter, [0, 100])).toBe(true);
    expect(rowMatchesFilter({ price: 101 }, rangeFilter, [0, 100])).toBe(false);
    expect(rowMatchesFilter({ price: 'nope' }, rangeFilter, [0, 100])).toBe(false);
  });

  it('dateRange: inclusive bounds on parsed dates', () => {
    expect(rowMatchesFilter({ date: '2026-06-15' }, dateRangeFilter, ['2026-06-01', '2026-06-30'])).toBe(true);
    expect(rowMatchesFilter({ date: '2026-07-01' }, dateRangeFilter, ['2026-06-01', '2026-06-30'])).toBe(false);
  });

  it('boolean: exact match', () => {
    expect(rowMatchesFilter({ active: true }, booleanFilter, true)).toBe(true);
    expect(rowMatchesFilter({ active: false }, booleanFilter, true)).toBe(false);
  });

  it('search: case-insensitive substring, empty query matches everything', () => {
    expect(rowMatchesFilter({ name: 'Acme Corp' }, searchFilter, 'acme')).toBe(true);
    expect(rowMatchesFilter({ name: 'Acme Corp' }, searchFilter, 'zzz')).toBe(false);
    expect(rowMatchesFilter({ name: 'Acme Corp' }, searchFilter, '')).toBe(true);
  });
});

describe('applyFiltersToDataSource', () => {
  const rows = [
    { region: 'us', name: 'Acme' },
    { region: 'eu', name: 'Globex' },
  ];

  it('only applies filters targeting this dataSourceId and chart', () => {
    const filters: Filter[] = [categoricalFilter, { ...searchFilter, dataSourceId: 'ds2' }];
    const result = applyFiltersToDataSource(rows, 'ds1', filters, { 'f-region': ['us'] }, 'chart-1');
    expect(result).toEqual([{ region: 'us', name: 'Acme' }]);
  });

  it('appliesTo restricts a filter to specific chart ids unless "*"', () => {
    const scoped: Filter = { ...searchFilter, appliesTo: ['other-chart'] };
    const result = applyFiltersToDataSource(rows, 'ds1', [scoped], { 'f-search': 'Acme' }, 'chart-1');
    expect(result).toHaveLength(2); // filter doesn't apply to chart-1, so no narrowing
  });

  it('returns rows unchanged when no filter targets this dataSource', () => {
    expect(applyFiltersToDataSource(rows, 'ds1', [], {}, 'chart-1')).toBe(rows);
  });
});
