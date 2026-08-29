import type { AgentDashboardWorkbook } from './types';

/**
 * The AgentDashboardWorkbook JSON Schema, reproduced from the schema this
 * package's input contract is built from — with `map_interactive` (and the
 * `lat`/`lng` encoding channels it alone used) removed. See types.ts for the
 * TypeScript mirror and docs/agent-dashboard/types.md for the field guide.
 */
export const AGENT_DASHBOARD_SCHEMA = {
  $schema: 'https://json-schema.org/draft/2020-12/schema',
  title: 'AgentDashboardWorkbook',
  type: 'object',
  description:
    'A complete dashboard produced by an agent (research). Contains the raw data, chart definitions, filters, and page layout. Render by resolving each chart\'s dataSourceId against dataSources, applying active filters, then laying out charts per page.layout.',
  required: ['workbookId', 'agentType', 'dataSources', 'charts', 'pages'],
  properties: {
    workbookId: { type: 'string' },
    agentType: { type: 'string', enum: ['research'] },
    schemaVersion: { type: 'integer', minimum: 1 },
    title: { type: 'string' },
    generatedAt: { type: 'string', format: 'date-time' },
    dataSources: { type: 'array', items: { $ref: '#/$defs/DataSource' }, minItems: 1 },
    filters: { type: 'array', items: { $ref: '#/$defs/Filter' } },
    charts: { type: 'array', items: { $ref: '#/$defs/Chart' }, minItems: 1 },
    pages: { type: 'array', items: { $ref: '#/$defs/Page' }, minItems: 1 },
  },
  $defs: {
    DataSource: {
      type: 'object',
      required: ['id', 'fields', 'data'],
      properties: {
        id: { type: 'string' },
        label: { type: 'string' },
        fields: { type: 'array', items: { $ref: '#/$defs/Field' }, minItems: 1 },
        data: { type: 'array', items: { type: 'object' } },
      },
    },
    Field: {
      type: 'object',
      required: ['name', 'role', 'dataType'],
      properties: {
        name: { type: 'string' },
        role: { type: 'string', enum: ['dimension', 'measure'] },
        dataType: { type: 'string', enum: ['string', 'number', 'boolean', 'date', 'datetime'] },
        description: { type: 'string' },
      },
    },
    Filter: {
      type: 'object',
      required: ['id', 'field', 'dataSourceId', 'type', 'appliesTo'],
      properties: {
        id: { type: 'string' },
        label: { type: 'string' },
        field: { type: 'string' },
        dataSourceId: { type: 'string' },
        type: { type: 'string', enum: ['categorical', 'range', 'dateRange', 'boolean', 'search'] },
        defaultValue: { type: ['array', 'string', 'boolean', 'null'] },
        appliesTo: { type: 'array', items: { type: 'string' } },
      },
    },
    Chart: {
      type: 'object',
      required: ['id', 'dataSourceId', 'type', 'encoding'],
      properties: {
        id: { type: 'string' },
        title: { type: 'string' },
        dataSourceId: { type: 'string' },
        type: {
          type: 'string',
          enum: [
            'bar', 'line', 'area', 'scatter', 'pie',
            'candlestick', 'heatmap', 'boxplot', 'radar',
            'funnel', 'sankey', 'network_graph', 'geo_choropleth',
            'table', 'kpi', 'gauge',
          ],
        },
        encoding: {
          type: 'object',
          properties: {
            x: { type: 'string' },
            y: { type: 'string' },
            color: { type: 'string' },
            size: { type: 'string' },
            value: { type: 'string' },
            target: { type: 'string' },
            aggregate: { type: 'string', enum: ['sum', 'avg', 'count', 'min', 'max', 'none'] },
            open: { type: 'string' },
            high: { type: 'string' },
            low: { type: 'string' },
            close: { type: 'string' },
            source: { type: 'string' },
            target_node: { type: 'string' },
            region: { type: 'string' },
            volume: { type: 'string' },
          },
        },
        indicators: { type: 'array', items: { $ref: '#/$defs/IndicatorSpec' } },
        annotations: { type: 'array', items: { $ref: '#/$defs/Annotation' } },
      },
    },
    IndicatorSpec: {
      type: 'object',
      required: ['type'],
      properties: {
        type: { type: 'string', enum: ['sma', 'ema', 'rsi', 'macd'] },
        field: { type: 'string' },
        period: { type: 'number' },
        fastPeriod: { type: 'number' },
        slowPeriod: { type: 'number' },
        signalPeriod: { type: 'number' },
        color: { type: 'string' },
        pane: { type: 'string', enum: ['overlay', 'separate'] },
        label: { type: 'string' },
      },
    },
    Annotation: {
      type: 'object',
      required: ['type', 'points'],
      properties: {
        type: { type: 'string', enum: ['trendline', 'horizontalLine', 'fibRetracement', 'label'] },
        points: {
          type: 'array',
          items: {
            type: 'object',
            required: ['time', 'value'],
            properties: {
              time: { type: ['string', 'number'] },
              value: { type: 'number' },
            },
          },
        },
        color: { type: 'string' },
        label: { type: 'string' },
        levels: { type: 'array', items: { type: 'number' } },
      },
    },
    Page: {
      type: 'object',
      required: ['id', 'name', 'layout'],
      properties: {
        id: { type: 'string' },
        name: { type: 'string' },
        layout: {
          type: 'array',
          items: {
            type: 'object',
            required: ['chartId', 'x', 'y', 'w', 'h'],
            properties: {
              chartId: { type: 'string' },
              x: { type: 'integer' },
              y: { type: 'integer' },
              w: { type: 'integer' },
              h: { type: 'integer' },
            },
          },
        },
      },
    },
  },
} as const;

/**
 * Dependency-free structural sanity check (no ajv/zod) — not full JSON
 * Schema validation, just the cross-reference checks a schema validator
 * can't express on its own (dataSourceId/chartId are free-text strings, so
 * "does this id actually resolve" needs the whole workbook in view). Meant
 * as a dev-time aid: log the results, don't throw.
 */
export function validateWorkbook(workbook: AgentDashboardWorkbook): string[] {
  const problems: string[] = [];
  const dataSourceIds = new Set(workbook.dataSources.map((ds) => ds.id));
  const chartIds = new Set(workbook.charts.map((c) => c.id));

  for (const chart of workbook.charts) {
    if (!dataSourceIds.has(chart.dataSourceId)) {
      problems.push(`Chart "${chart.id}" references unknown dataSourceId "${chart.dataSourceId}"`);
    }
  }

  for (const filter of workbook.filters ?? []) {
    if (!dataSourceIds.has(filter.dataSourceId)) {
      problems.push(`Filter "${filter.id}" references unknown dataSourceId "${filter.dataSourceId}"`);
    }
    for (const chartId of filter.appliesTo) {
      if (chartId !== '*' && !chartIds.has(chartId)) {
        problems.push(`Filter "${filter.id}" appliesTo references unknown chart id "${chartId}"`);
      }
    }
  }

  for (const page of workbook.pages) {
    for (const item of page.layout) {
      if (!chartIds.has(item.chartId)) {
        problems.push(`Page "${page.id}" layout references unknown chart id "${item.chartId}"`);
      }
    }
  }

  return problems;
}
