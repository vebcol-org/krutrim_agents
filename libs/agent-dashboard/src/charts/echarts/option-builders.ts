import type { EChartsOption } from 'echarts';
import type { DataRow, Encoding } from '../../types';

/** Convention used by geo-choropleth when a chart doesn't need a different map — see registerGeoMap / customization.md. */
export const DEFAULT_GEO_MAP_NAME = 'world';

function num(value: unknown): number {
  const n = typeof value === 'number' ? value : Number(value);
  return Number.isNaN(n) ? 0 : n;
}

/** Shared by bar/line/area/scatter: category axis from `x`, one series per distinct `color` value (or a single series). */
export function buildCartesianOption(rows: DataRow[], encoding: Encoding, kind: 'bar' | 'line' | 'area' | 'scatter'): EChartsOption {
  const xField = encoding.x;
  const yField = encoding.y ?? encoding.value;
  const colorField = encoding.color;
  if (!xField || !yField) return { series: [] };

  if (kind === 'scatter') {
    const seriesMap = new Map<string, Array<[number | string, number]>>();
    for (const row of rows) {
      const key = colorField ? String(row[colorField] ?? '') : yField;
      const xv = row[xField];
      const bucket = seriesMap.get(key) ?? [];
      bucket.push([typeof xv === 'number' ? xv : String(xv ?? ''), num(row[yField])]);
      seriesMap.set(key, bucket);
    }
    const names = Array.from(seriesMap.keys());
    return {
      xAxis: { type: 'value' },
      yAxis: { type: 'value' },
      tooltip: { trigger: 'item' },
      legend: names.length > 1 ? { data: names } : undefined,
      series: names.map((name) => ({ type: 'scatter', name, data: seriesMap.get(name) })),
    };
  }

  const categories = Array.from(new Set(rows.map((r) => String(r[xField] ?? ''))));
  const seriesNames = colorField ? Array.from(new Set(rows.map((r) => String(r[colorField] ?? '')))) : [yField];

  const series = seriesNames.map((name) => {
    const byCategory = new Map<string, number>();
    for (const row of rows) {
      if (colorField && String(row[colorField] ?? '') !== name) continue;
      byCategory.set(String(row[xField] ?? ''), num(row[yField]));
    }
    return {
      name,
      type: kind === 'area' ? 'line' : kind,
      areaStyle: kind === 'area' ? {} : undefined,
      data: categories.map((c) => byCategory.get(c) ?? null),
    };
  });

  return {
    xAxis: { type: 'category', data: categories },
    yAxis: { type: 'value' },
    tooltip: { trigger: 'axis' },
    legend: series.length > 1 ? { data: seriesNames } : undefined,
    series,
  };
}

export function buildPieOption(rows: DataRow[], encoding: Encoding): EChartsOption {
  const nameField = encoding.x ?? encoding.color;
  const valueField = encoding.y ?? encoding.value;
  if (!nameField || !valueField) return { series: [] };
  return {
    tooltip: { trigger: 'item' },
    legend: {},
    series: [
      {
        type: 'pie',
        radius: '65%',
        data: rows.map((r) => ({ name: String(r[nameField] ?? ''), value: num(r[valueField]) })),
      },
    ],
  };
}

/** `x`/`y` are both treated as categorical axes here (e.g. day-of-week x hour-of-day); `value` (or `color`) is the intensity measure. */
export function buildHeatmapOption(rows: DataRow[], encoding: Encoding): EChartsOption {
  const xField = encoding.x;
  const yField = encoding.y;
  const valueField = encoding.value ?? encoding.color;
  if (!xField || !yField || !valueField) return { series: [] };

  const xCategories = Array.from(new Set(rows.map((r) => String(r[xField] ?? ''))));
  const yCategories = Array.from(new Set(rows.map((r) => String(r[yField] ?? ''))));
  const data = rows.map((r) => [
    xCategories.indexOf(String(r[xField] ?? '')),
    yCategories.indexOf(String(r[yField] ?? '')),
    num(r[valueField]),
  ]);
  const values = data.map((d) => d[2] as number);

  return {
    tooltip: { position: 'top' },
    xAxis: { type: 'category', data: xCategories },
    yAxis: { type: 'category', data: yCategories },
    visualMap: {
      min: Math.min(0, ...values),
      max: Math.max(1, ...values),
      calculable: true,
      orient: 'horizontal',
      bottom: 0,
    },
    series: [{ type: 'heatmap', data }],
  };
}

function quantileSorted(sorted: number[], q: number): number {
  if (sorted.length === 0) return 0;
  const pos = (sorted.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  return sorted[base + 1] !== undefined ? sorted[base] + rest * (sorted[base + 1] - sorted[base]) : sorted[base];
}

/** Groups raw (non-aggregated) rows by `x` and computes a [min, Q1, median, Q3, max] five-number summary of `y` per group. */
export function buildBoxplotOption(rows: DataRow[], encoding: Encoding): EChartsOption {
  const xField = encoding.x;
  const yField = encoding.y ?? encoding.value;
  if (!xField || !yField) return { series: [] };

  const categories = Array.from(new Set(rows.map((r) => String(r[xField] ?? ''))));
  const data = categories.map((cat) => {
    const values = rows
      .filter((r) => String(r[xField] ?? '') === cat)
      .map((r) => num(r[yField]))
      .sort((a, b) => a - b);
    if (values.length === 0) return [0, 0, 0, 0, 0];
    return [values[0], quantileSorted(values, 0.25), quantileSorted(values, 0.5), quantileSorted(values, 0.75), values[values.length - 1]];
  });

  return {
    xAxis: { type: 'category', data: categories },
    yAxis: { type: 'value' },
    tooltip: { trigger: 'item' },
    series: [{ type: 'boxplot', data }],
  };
}

/** `x` = indicator/axis name, `y`/`value` = magnitude, `color` (optional) = one series per compared entity. */
export function buildRadarOption(rows: DataRow[], encoding: Encoding): EChartsOption {
  const indicatorField = encoding.x;
  const valueField = encoding.y ?? encoding.value;
  const seriesField = encoding.color;
  if (!indicatorField || !valueField) return { series: [] };

  const indicators = Array.from(new Set(rows.map((r) => String(r[indicatorField] ?? ''))));
  const maxVal = Math.max(1, ...rows.map((r) => num(r[valueField])));
  const seriesNames = seriesField ? Array.from(new Set(rows.map((r) => String(r[seriesField] ?? '')))) : ['value'];

  const seriesData = seriesNames.map((name) => ({
    name,
    value: indicators.map((ind) => {
      const row = rows.find(
        (r) => String(r[indicatorField] ?? '') === ind && (!seriesField || String(r[seriesField] ?? '') === name),
      );
      return row ? num(row[valueField]) : 0;
    }),
  }));

  return {
    tooltip: {},
    legend: seriesNames.length > 1 ? { data: seriesNames } : undefined,
    radar: { indicator: indicators.map((name) => ({ name, max: maxVal })) },
    series: [{ type: 'radar', data: seriesData }],
  };
}

export function buildFunnelOption(rows: DataRow[], encoding: Encoding): EChartsOption {
  const nameField = encoding.x;
  const valueField = encoding.y ?? encoding.value;
  if (!nameField || !valueField) return { series: [] };
  return {
    tooltip: { trigger: 'item' },
    series: [
      {
        type: 'funnel',
        data: rows
          .map((r) => ({ name: String(r[nameField] ?? ''), value: num(r[valueField]) }))
          .sort((a, b) => b.value - a.value),
      },
    ],
  };
}

export function buildSankeyOption(rows: DataRow[], encoding: Encoding): EChartsOption {
  const sourceField = encoding.source;
  const targetField = encoding.target_node;
  const valueField = encoding.value ?? encoding.y;
  if (!sourceField || !targetField) return { series: [] };

  const nodeNames = new Set<string>();
  const links = rows.map((r) => {
    const source = String(r[sourceField] ?? '');
    const target = String(r[targetField] ?? '');
    nodeNames.add(source);
    nodeNames.add(target);
    return { source, target, value: valueField ? num(r[valueField]) : 1 };
  });

  return {
    tooltip: { trigger: 'item' },
    series: [{ type: 'sankey', data: Array.from(nodeNames, (name) => ({ name })), links }],
  };
}

export function buildNetworkGraphOption(rows: DataRow[], encoding: Encoding): EChartsOption {
  const sourceField = encoding.source;
  const targetField = encoding.target_node;
  const weightField = encoding.size ?? encoding.value;
  if (!sourceField || !targetField) return { series: [] };

  const nodeNames = new Set<string>();
  const links = rows.map((r) => {
    const source = String(r[sourceField] ?? '');
    const target = String(r[targetField] ?? '');
    nodeNames.add(source);
    nodeNames.add(target);
    return { source, target, value: weightField ? num(r[weightField]) : 1 };
  });

  return {
    tooltip: {},
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        label: { show: true },
        force: { repulsion: 100 },
        data: Array.from(nodeNames, (name) => ({ name, symbolSize: 20 })),
        links,
      },
    ],
  };
}

/** Needs a GeoJSON map registered via registerGeoMap(mapName, geoJson) — see docs/agent-dashboard/customization.md. Returns an empty option (caller shows a placeholder) if unregistered. */
export function buildGeoChoroplethOption(rows: DataRow[], encoding: Encoding, mapName: string): EChartsOption {
  const regionField = encoding.region;
  const valueField = encoding.value ?? encoding.y;
  if (!regionField || !valueField) return { series: [] };

  const data = rows.map((r) => ({ name: String(r[regionField] ?? ''), value: num(r[valueField]) }));
  const values = data.map((d) => d.value);

  return {
    tooltip: { trigger: 'item' },
    visualMap: { min: Math.min(0, ...values), max: Math.max(1, ...values), calculable: true },
    series: [{ type: 'map', map: mapName, data }],
  };
}

export function buildGaugeOption(rows: DataRow[], encoding: Encoding): EChartsOption {
  const valueField = encoding.value ?? encoding.y;
  const targetField = encoding.target;
  if (!valueField) return { series: [] };

  const value = rows.length > 0 ? num(rows[0][valueField]) : 0;
  const target = targetField && rows.length > 0 ? num(rows[0][targetField]) : undefined;
  const max = target ? Math.max(target * 1.2, value * 1.2, 100) : Math.max(value * 1.5, 100);

  return {
    series: [{ type: 'gauge', max, data: [{ value, name: valueField }] }],
  };
}
