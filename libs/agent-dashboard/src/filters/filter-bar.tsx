import type { AgentDashboardWorkbook, Filter } from '../types';
import { useDashboard } from '../context/use-dashboard';

function distinctValues(workbook: AgentDashboardWorkbook, filter: Filter): string[] {
  const dataSource = workbook.dataSources.find((ds) => ds.id === filter.dataSourceId);
  if (!dataSource) return [];
  const values = new Set<string>();
  for (const row of dataSource.data) {
    const cell = row[filter.field];
    if (cell !== undefined && cell !== null) values.add(String(cell));
  }
  return Array.from(values).sort();
}

/** Renders one control per `workbook.filters` entry. Renders nothing when there are no filters. */
export function FilterBar() {
  const { workbook, activeFilters, setFilterValue, getFilterComponent } = useDashboard();
  const filters = workbook.filters ?? [];
  if (filters.length === 0) return null;

  return (
    <div className="kdash-filter-bar">
      {filters.map((filter) => {
        const Component = getFilterComponent(filter.type);
        if (!Component) return null;
        return (
          <div className="kdash-filter" key={filter.id}>
            <span className="kdash-filter-label">{filter.label ?? filter.field}</span>
            <Component
              filter={filter}
              value={activeFilters[filter.id]}
              options={filter.type === 'categorical' ? distinctValues(workbook, filter) : undefined}
              onChange={(value) => setFilterValue(filter.id, value)}
            />
          </div>
        );
      })}
    </div>
  );
}
