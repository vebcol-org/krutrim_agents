import { useMemo } from 'react';
import type { ChartComponentProps } from '../chart-registry';
import { EmptyState, LoadingBadge } from '../chart-states';
import { EChartsBase } from './echarts-base';
import { buildGeoChoroplethOption, DEFAULT_GEO_MAP_NAME } from './option-builders';
import { isGeoMapRegistered } from './geo-map-registry';

/**
 * Needs a GeoJSON map registered up front via `registerGeoMap(DEFAULT_GEO_MAP_NAME, geoJson)`
 * (world boundary data isn't bundled — see docs/agent-dashboard/customization.md). Shows a
 * placeholder with that instruction instead of a blank chart when nothing is registered yet.
 */
export function GeoChoroplethChart({ chart, rows, isLoading, loadedCount, total, echartsThemeName }: ChartComponentProps) {
  const option = useMemo(
    () => buildGeoChoroplethOption(rows, chart.encoding, DEFAULT_GEO_MAP_NAME),
    [rows, chart.encoding],
  );

  if (!isGeoMapRegistered(DEFAULT_GEO_MAP_NAME)) {
    return (
      <EmptyState
        message={`No GeoJSON registered for map "${DEFAULT_GEO_MAP_NAME}". Call registerGeoMap("${DEFAULT_GEO_MAP_NAME}", geoJson) once at startup.`}
      />
    );
  }
  if (rows.length === 0 && !isLoading) return <EmptyState />;

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <EChartsBase option={option} themeName={echartsThemeName} />
      {isLoading && <LoadingBadge loadedCount={loadedCount} total={total} />}
    </div>
  );
}
