import type { FilterComponentProps } from './filter-registry';

/** Multi-select dropdown over distinct values. Empty selection == "no filtering" (matches rowMatchesFilter's semantics). */
export function CategoricalFilter({ filter, value, options, onChange }: FilterComponentProps) {
  const selected = Array.isArray(value) && typeof value[0] !== 'number' ? (value as string[]) : [];

  return (
    <select
      multiple
      aria-label={filter.label ?? filter.field}
      value={selected}
      onChange={(e) => {
        const next = Array.from(e.target.selectedOptions, (o) => o.value);
        onChange(next.length > 0 ? next : []);
      }}
    >
      {(options ?? []).map((opt) => (
        <option key={opt} value={opt}>
          {opt}
        </option>
      ))}
    </select>
  );
}
