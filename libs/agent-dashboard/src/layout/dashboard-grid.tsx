import type { CSSProperties } from 'react';
import type { Page } from '../types';
import { ChartRenderer } from '../charts/chart-renderer';
import { useDashboard } from '../context/use-dashboard';
import { scaleSpan } from './scale-span';

export interface DashboardGridProps {
  page: Page;
  /** Pixels per layout row unit — h=2 renders as 2 * rowHeightPx tall (at every breakpoint). Static grid, no drag/resize. */
  rowHeightPx?: number;
}

const LARGE_COLUMNS = 12;
const MEDIUM_COLUMNS = 6;

/**
 * Responsive CSS Grid built from `page.layout`. The three breakpoints live
 * in theme.css (`.kdash-grid`/`.kdash-grid-item`) as plain media queries —
 * this component's only job is precomputing, per item, the CSS custom
 * properties those media queries switch between:
 *
 * - **>1024px** (desktop): the schema's native 12-column layout, unchanged.
 * - **641–1024px** (tablet): `x`/`w` proportionally rescaled onto a
 *   6-column grid via `scaleSpan` — `y`/`h` (row units) don't need
 *   rescaling, only the column axis does.
 * - **<=640px** (phone/narrow portrait): collapses to a single full-width
 *   column; items stack in reading order (sorted by `y` then `x` below,
 *   since a 1-column grid has no `x` to place against) while still
 *   respecting `h` so a chart that needed more vertical room keeps it.
 *
 * See docs/agent-dashboard/architecture.md#responsive-layout.
 */
export function DashboardGrid({ page, rowHeightPx = 60 }: DashboardGridProps) {
  const { workbook } = useDashboard();
  const chartsById = new Map(workbook.charts.map((c) => [c.id, c]));

  const orderedLayout = [...page.layout].sort((a, b) => a.y - b.y || a.x - b.x);

  const gridStyle = { '--kdash-row-height': `${rowHeightPx}px` } as CSSProperties;

  return (
    <div className="kdash-grid" style={gridStyle}>
      {orderedLayout.map((item) => {
        const chart = chartsById.get(item.chartId);
        if (!chart) return null;

        const medium = scaleSpan(item.x, item.w, LARGE_COLUMNS, MEDIUM_COLUMNS);
        const itemStyle = {
          '--kdash-item-x-lg': item.x,
          '--kdash-item-w-lg': item.w,
          '--kdash-item-x-md': medium.x,
          '--kdash-item-w-md': medium.w,
          '--kdash-item-y': item.y,
          '--kdash-item-h': item.h,
        } as CSSProperties;

        return (
          <div key={item.chartId} className="kdash-grid-item" style={itemStyle}>
            <ChartRenderer chart={chart} />
          </div>
        );
      })}
    </div>
  );
}
