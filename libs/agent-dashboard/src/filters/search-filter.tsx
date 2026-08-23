import type { FilterComponentProps } from './filter-registry';

export function SearchFilter({ filter, value, onChange }: FilterComponentProps) {
  return (
    <input
      type="search"
      placeholder={filter.label ?? filter.field}
      aria-label={filter.label ?? filter.field}
      value={typeof value === 'string' ? value : ''}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}
