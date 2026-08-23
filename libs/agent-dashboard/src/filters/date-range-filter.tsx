import type { FilterComponentProps } from './filter-registry';

export function DateRangeFilter({ filter, value, onChange }: FilterComponentProps) {
  const [start, end] = (Array.isArray(value) ? (value as [string, string]) : ['', '']) as [string, string];

  return (
    <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'center' }}>
      <input
        type="date"
        aria-label={`${filter.label ?? filter.field} start`}
        value={start ?? ''}
        onChange={(e) => onChange([e.target.value, end ?? e.target.value])}
      />
      <span className="kdash-muted">to</span>
      <input
        type="date"
        aria-label={`${filter.label ?? filter.field} end`}
        value={end ?? ''}
        onChange={(e) => onChange([start ?? e.target.value, e.target.value])}
      />
    </div>
  );
}
