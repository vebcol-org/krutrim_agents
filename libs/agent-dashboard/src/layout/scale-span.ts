/**
 * Proportionally rescales a layout item's [x, w] (defined against a
 * `fromCols`-wide grid) onto a `toCols`-wide grid, preserving relative
 * position and width as closely as integer columns allow. Used to derive
 * the medium-breakpoint (6-column) placement from the schema's native
 * 12-column layout — see dashboard-grid.tsx and
 * docs/agent-dashboard/architecture.md#responsive-layout.
 *
 * Width is rounded but always at least 1 and never wider than `toCols`; `x`
 * is then clamped so `x + w` never overflows the narrower grid, which
 * matters because rounding both independently can otherwise push a
 * right-aligned item just past the last column.
 */
export function scaleSpan(x: number, w: number, fromCols: number, toCols: number): { x: number; w: number } {
  if (fromCols === toCols) return { x, w };

  const scale = toCols / fromCols;
  const scaledW = Math.max(1, Math.min(toCols, Math.round(w * scale)));
  const scaledX = Math.max(0, Math.min(Math.round(x * scale), toCols - scaledW));

  return { x: scaledX, w: scaledW };
}
