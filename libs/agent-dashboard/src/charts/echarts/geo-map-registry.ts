import * as echarts from 'echarts';

const registeredMaps = new Set<string>();

/**
 * Registers a GeoJSON region map (e.g. world countries, US states) under
 * `name` for `geo_choropleth` charts to render against. Not bundled with
 * this package — GeoJSON boundary data is large and app-specific; call this
 * once at app startup. See docs/agent-dashboard/customization.md.
 */
export function registerGeoMap(name: string, geoJson: Record<string, unknown>): void {
  echarts.registerMap(name, geoJson as never);
  registeredMaps.add(name);
}

export function isGeoMapRegistered(name: string): boolean {
  return registeredMaps.has(name);
}
