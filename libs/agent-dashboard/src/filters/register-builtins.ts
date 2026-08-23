import { registerFilterRenderer } from './filter-registry';
import { CategoricalFilter } from './categorical-filter';
import { RangeFilter } from './range-filter';
import { DateRangeFilter } from './date-range-filter';
import { BooleanFilter } from './boolean-filter';
import { SearchFilter } from './search-filter';

let registered = false;

/** Idempotent — index.ts calls this once so consumers get working defaults without any setup. */
export function registerBuiltinFilters(): void {
  if (registered) return;
  registered = true;
  registerFilterRenderer('categorical', CategoricalFilter);
  registerFilterRenderer('range', RangeFilter);
  registerFilterRenderer('dateRange', DateRangeFilter);
  registerFilterRenderer('boolean', BooleanFilter);
  registerFilterRenderer('search', SearchFilter);
}
