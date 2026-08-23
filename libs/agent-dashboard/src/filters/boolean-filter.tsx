import type { FilterComponentProps } from './filter-registry';

export function BooleanFilter({ filter, value, onChange }: FilterComponentProps) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer' }}>
      <input
        type="checkbox"
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
        aria-label={filter.label ?? filter.field}
      />
    </label>
  );
}
