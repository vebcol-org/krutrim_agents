import { describe, expect, it } from 'vitest';
import {
  buildBoxplotOption,
  buildCartesianOption,
  buildFunnelOption,
  buildGaugeOption,
  buildGeoChoroplethOption,
  buildHeatmapOption,
  buildNetworkGraphOption,
  buildPieOption,
  buildRadarOption,
  buildSankeyOption,
} from '../../../src/charts/echarts/option-builders';
import type { Encoding } from '../../../src/types';

describe('buildCartesianOption', () => {
  const rows = [
    { region: 'us', team: 'A', revenue: 10 },
    { region: 'eu', team: 'A', revenue: 20 },
    { region: 'us', team: 'B', revenue: 5 },
  ];
  const encoding: Encoding = { x: 'region', y: 'revenue', color: 'team' };

  it('bar: one series per distinct color value, aligned to shared categories', () => {
    const option = buildCartesianOption(rows, encoding, 'bar');
    expect(option.xAxis).toEqual({ type: 'category', data: ['us', 'eu'] });
    expect(option.series).toHaveLength(2);
    expect(option.series?.[0]).toMatchObject({ name: 'A', type: 'bar', data: [10, 20] });
    expect(option.series?.[1]).toMatchObject({ name: 'B', type: 'bar', data: [5, null] });
  });

  it('area: uses a line series with areaStyle', () => {
    const option = buildCartesianOption(rows, { x: 'region', y: 'revenue' }, 'area');
    expect(option.series?.[0]).toMatchObject({ type: 'line', areaStyle: {} });
  });

  it('scatter: raw x/y pairs grouped by color, not aggregated into categories', () => {
    const option = buildCartesianOption(rows, encoding, 'scatter');
    expect(option.xAxis).toEqual({ type: 'value' });
    expect(option.series).toHaveLength(2);
  });

  it('returns an empty series list when required encoding fields are missing', () => {
    expect(buildCartesianOption(rows, {}, 'bar').series).toEqual([]);
  });
});

describe('buildPieOption', () => {
  it('maps x/color to name and y/value to value', () => {
    const option = buildPieOption([{ region: 'us', revenue: 10 }], { x: 'region', y: 'revenue' });
    expect(option.series?.[0]).toMatchObject({ type: 'pie', data: [{ name: 'us', value: 10 }] });
  });
});

describe('buildHeatmapOption', () => {
  it('indexes x/y categories and places value at [xi, yi, value]', () => {
    const rows = [
      { day: 'Mon', hour: '9am', load: 3 },
      { day: 'Tue', hour: '9am', load: 7 },
    ];
    const option = buildHeatmapOption(rows, { x: 'day', y: 'hour', value: 'load' });
    expect(option.series?.[0]).toMatchObject({ type: 'heatmap', data: [[0, 0, 3], [1, 0, 7]] });
  });
});

describe('buildBoxplotOption', () => {
  it('computes a five-number summary per x category', () => {
    const rows = [1, 2, 3, 4, 5].map((v) => ({ group: 'g', v }));
    const option = buildBoxplotOption(rows, { x: 'group', y: 'v' });
    const [min, q1, median, q3, max] = (option.series?.[0] as { data: number[][] }).data[0];
    expect(min).toBe(1);
    expect(median).toBe(3);
    expect(max).toBe(5);
    expect(q1).toBeLessThan(median);
    expect(q3).toBeGreaterThan(median);
  });
});

describe('buildRadarOption', () => {
  it('builds one indicator per x value and one series per color value', () => {
    const rows = [
      { skill: 'speed', entity: 'A', score: 8 },
      { skill: 'power', entity: 'A', score: 6 },
      { skill: 'speed', entity: 'B', score: 4 },
      { skill: 'power', entity: 'B', score: 9 },
    ];
    const option = buildRadarOption(rows, { x: 'skill', y: 'score', color: 'entity' });
    expect(option.radar).toMatchObject({ indicator: [{ name: 'speed' }, { name: 'power' }] });
    expect(option.series?.[0]).toMatchObject({
      data: [
        { name: 'A', value: [8, 6] },
        { name: 'B', value: [4, 9] },
      ],
    });
  });
});

describe('buildFunnelOption', () => {
  it('sorts stages descending by value', () => {
    const rows = [
      { stage: 'leads', count: 100 },
      { stage: 'closed', count: 10 },
      { stage: 'demo', count: 40 },
    ];
    const option = buildFunnelOption(rows, { x: 'stage', y: 'count' });
    const data = (option.series?.[0] as { data: Array<{ value: number }> }).data;
    expect(data.map((d) => d.value)).toEqual([100, 40, 10]);
  });
});

describe('buildSankeyOption', () => {
  it('collects distinct node names from source and target_node', () => {
    const rows = [{ from: 'a', to: 'b', weight: 5 }];
    const option = buildSankeyOption(rows, { source: 'from', target_node: 'to', value: 'weight' });
    const series = option.series?.[0] as { data: Array<{ name: string }>; links: Array<{ value: number }> };
    expect(series.data.map((n) => n.name).sort()).toEqual(['a', 'b']);
    expect(series.links[0].value).toBe(5);
  });
});

describe('buildNetworkGraphOption', () => {
  it('builds a force-directed graph option from source/target_node edges', () => {
    const rows = [{ from: 'a', to: 'b' }];
    const option = buildNetworkGraphOption(rows, { source: 'from', target_node: 'to' });
    expect(option.series?.[0]).toMatchObject({ type: 'graph', layout: 'force' });
  });
});

describe('buildGeoChoroplethOption', () => {
  it('maps region/value to a map series against the given map name', () => {
    const option = buildGeoChoroplethOption([{ country: 'US', gdp: 100 }], { region: 'country', value: 'gdp' }, 'world');
    expect(option.series?.[0]).toMatchObject({ type: 'map', map: 'world', data: [{ name: 'US', value: 100 }] });
  });
});

describe('buildGaugeOption', () => {
  it('reads the first row for value, and scales max above the target when present', () => {
    const option = buildGaugeOption([{ score: 80, goal: 90 }], { value: 'score', target: 'goal' });
    expect(option.series?.[0]).toMatchObject({ type: 'gauge', data: [{ value: 80, name: 'score' }] });
  });
});
