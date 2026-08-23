import { describe, expect, it } from 'vitest';
import { scaleSpan } from '../../src/layout/scale-span';

describe('scaleSpan', () => {
  it('returns the input unchanged when fromCols === toCols', () => {
    expect(scaleSpan(3, 4, 12, 12)).toEqual({ x: 3, w: 4 });
  });

  it('halves x/w when scaling 12 columns down to 6', () => {
    expect(scaleSpan(0, 6, 12, 6)).toEqual({ x: 0, w: 3 });
    expect(scaleSpan(6, 6, 12, 6)).toEqual({ x: 3, w: 3 });
  });

  it('two side-by-side 12-col items (0,6)+(6,6) stay side by side and non-overlapping at 6 columns', () => {
    const a = scaleSpan(0, 6, 12, 6);
    const b = scaleSpan(6, 6, 12, 6);
    expect(a.x + a.w).toBe(b.x);
    expect(b.x + b.w).toBe(6);
  });

  it('never produces a width of 0, even for a narrow original item', () => {
    expect(scaleSpan(11, 1, 12, 6).w).toBeGreaterThanOrEqual(1);
  });

  it('never overflows the target column count', () => {
    // an item flush against the right edge of a 12-col grid
    const result = scaleSpan(8, 4, 12, 6);
    expect(result.x + result.w).toBeLessThanOrEqual(6);
  });

  it('never produces a width wider than the target column count', () => {
    expect(scaleSpan(0, 12, 12, 6).w).toBeLessThanOrEqual(6);
  });
});
