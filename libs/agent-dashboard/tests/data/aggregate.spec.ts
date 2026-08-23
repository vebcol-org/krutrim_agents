import { describe, expect, it } from 'vitest';
import { aggregateRows } from '../../src/data/aggregate';

const rows = [
  { symbol: 'AAPL', region: 'us', pnl: 10 },
  { symbol: 'AAPL', region: 'us', pnl: 20 },
  { symbol: 'MSFT', region: 'us', pnl: 5 },
];

describe('aggregateRows', () => {
  it('passes rows through unchanged when fn is "none" or missing', () => {
    expect(aggregateRows(rows, ['symbol'], 'pnl', 'none')).toBe(rows);
    expect(aggregateRows(rows, ['symbol'], 'pnl', undefined)).toBe(rows);
  });

  it('passes rows through unchanged when groupFields or valueField are missing', () => {
    expect(aggregateRows(rows, [], 'pnl', 'sum')).toBe(rows);
    expect(aggregateRows(rows, ['symbol'], undefined, 'sum')).toBe(rows);
  });

  it('sums grouped values, preserving first-seen group order', () => {
    const result = aggregateRows(rows, ['symbol'], 'pnl', 'sum');
    expect(result).toEqual([
      { symbol: 'AAPL', pnl: 30 },
      { symbol: 'MSFT', pnl: 5 },
    ]);
  });

  it('averages, counts, mins, and maxes within a group', () => {
    expect(aggregateRows(rows, ['symbol'], 'pnl', 'avg')[0]).toEqual({ symbol: 'AAPL', pnl: 15 });
    expect(aggregateRows(rows, ['symbol'], 'pnl', 'count')[0]).toEqual({ symbol: 'AAPL', pnl: 2 });
    expect(aggregateRows(rows, ['symbol'], 'pnl', 'min')[0]).toEqual({ symbol: 'AAPL', pnl: 10 });
    expect(aggregateRows(rows, ['symbol'], 'pnl', 'max')[0]).toEqual({ symbol: 'AAPL', pnl: 20 });
  });

  it('supports a compound group key (e.g. x + color)', () => {
    const compound = [
      { symbol: 'AAPL', region: 'us', pnl: 10 },
      { symbol: 'AAPL', region: 'eu', pnl: 7 },
      { symbol: 'AAPL', region: 'us', pnl: 3 },
    ];
    const result = aggregateRows(compound, ['symbol', 'region'], 'pnl', 'sum');
    expect(result).toEqual([
      { symbol: 'AAPL', region: 'us', pnl: 13 },
      { symbol: 'AAPL', region: 'eu', pnl: 7 },
    ]);
  });

  it('ignores non-numeric values in the aggregate rather than throwing', () => {
    const dirty = [
      { symbol: 'AAPL', pnl: 10 },
      { symbol: 'AAPL', pnl: 'n/a' },
    ];
    expect(aggregateRows(dirty, ['symbol'], 'pnl', 'sum')).toEqual([{ symbol: 'AAPL', pnl: 10 }]);
  });
});
