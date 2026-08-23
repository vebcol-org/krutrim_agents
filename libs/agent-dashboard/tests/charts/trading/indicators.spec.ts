import { describe, expect, it } from 'vitest';
import { computeEMA, computeMACD, computeRSI, computeSMA } from '../../../src/charts/trading/indicators';

describe('computeSMA', () => {
  it('averages a trailing window, skipping the warm-up period', () => {
    const result = computeSMA([1, 2, 3, 4, 5], 3);
    expect(result).toEqual([
      { index: 2, value: 2 },
      { index: 3, value: 3 },
      { index: 4, value: 4 },
    ]);
  });

  it('returns nothing when there are fewer values than the period', () => {
    expect(computeSMA([1, 2], 3)).toEqual([]);
  });
});

describe('computeEMA', () => {
  it('seeds with the SMA of the first window, then smooths forward', () => {
    const result = computeEMA([1, 2, 3, 4, 5], 3);
    // seed = SMA(1,2,3) = 2 at index 2; k = 2/4 = 0.5
    expect(result[0]).toEqual({ index: 2, value: 2 });
    expect(result[1].value).toBeCloseTo(4 * 0.5 + 2 * 0.5); // 3
    expect(result).toHaveLength(3);
  });
});

describe('computeRSI', () => {
  it('is 100 for a strictly increasing (all-gains) series', () => {
    const values = Array.from({ length: 20 }, (_, i) => i + 1);
    const result = computeRSI(values, 14);
    expect(result.length).toBeGreaterThan(0);
    for (const point of result) expect(point.value).toBe(100);
  });

  it('is 0 for a strictly decreasing (all-losses) series', () => {
    const values = Array.from({ length: 20 }, (_, i) => 20 - i);
    const result = computeRSI(values, 14);
    for (const point of result) expect(point.value).toBe(0);
  });

  it('sits at 50 for a perfectly flat series (no gains or losses)', () => {
    const values = Array(20).fill(10);
    const result = computeRSI(values, 14);
    for (const point of result) expect(point.value).toBe(50);
  });

  it('returns nothing when there are fewer values than the period', () => {
    expect(computeRSI([1, 2, 3], 14)).toEqual([]);
  });
});

describe('computeMACD', () => {
  it('produces macd/signal/histogram arrays aligned to the same indices, with histogram = macd - signal', () => {
    const values = Array.from({ length: 60 }, (_, i) => 100 + Math.sin(i / 5) * 10);
    const { macd, signal, histogram } = computeMACD(values, 12, 26, 9);

    expect(macd.length).toBeGreaterThan(0);
    expect(signal.length).toBeGreaterThan(0);
    expect(histogram.length).toBe(signal.length);

    const macdByIndex = new Map(macd.map((m) => [m.index, m.value]));
    for (const h of histogram) {
      const signalPoint = signal.find((s) => s.index === h.index)!;
      expect(h.value).toBeCloseTo(macdByIndex.get(h.index)! - signalPoint.value);
    }
  });

  it('returns empty arrays when there is not enough data for the slow EMA', () => {
    expect(computeMACD([1, 2, 3], 12, 26, 9)).toEqual({ macd: [], signal: [], histogram: [] });
  });
});
