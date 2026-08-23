import type { FilterComponentProps } from './filter-registry';

/** Min/max numeric range, as two number inputs (a real dual-handle slider is a reasonable custom override — see docs/agent-dashboard/customization.md). */
export function RangeFilter({ filter, value, onChange }: FilterComponentProps) {
  const [min, max] = (Array.isArray(value) ? (value as [number, number]) : [undefined, undefined]) as [
    number | undefined,
    number | undefined,
  ];

  return (
    <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'center' }}>
      <input
        type="number"
        aria-label={`${filter.label ?? filter.field} minimum`}
        value={min ?? ''}
        onChange={(e) => onChange([Number(e.target.value), max ?? Number(e.target.value)])}
      />
      <span className="kdash-muted">to</span>
      <input
        type="number"
        aria-label={`${filter.label ?? filter.field} maximum`}
        value={max ?? ''}
        onChange={(e) => onChange([min ?? Number(e.target.value), Number(e.target.value)])}
      />
    </div>
  );
}
