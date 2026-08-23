# Examples

## 1. Trading desk: candlestick + kpi + table

```tsx
import { AgentDashboard, type AgentDashboardWorkbook } from '@krutrim_agent/agent-dashboard';
import '@krutrim_agent/agent-dashboard/theme.css';

const workbook: AgentDashboardWorkbook = {
  workbookId: 'trading_2026_08_23',
  agentType: 'trading',
  title: 'Trading Desk Overview',
  dataSources: [
    {
      id: 'ticks',
      fields: [
        { name: 'ts', role: 'dimension', dataType: 'datetime' },
        { name: 'open', role: 'measure', dataType: 'number' },
        { name: 'high', role: 'measure', dataType: 'number' },
        { name: 'low', role: 'measure', dataType: 'number' },
        { name: 'close', role: 'measure', dataType: 'number' },
        { name: 'volume', role: 'measure', dataType: 'number' },
      ],
      data: [
        { ts: '2026-08-20', open: 100, high: 108, low: 98, close: 105, volume: 12000 },
        { ts: '2026-08-21', open: 105, high: 110, low: 103, close: 107, volume: 15500 },
        { ts: '2026-08-22', open: 107, high: 109, low: 101, close: 102, volume: 9800 },
      ],
    },
    {
      id: 'summary',
      fields: [
        { name: 'pnl', role: 'measure', dataType: 'number' },
        { name: 'target', role: 'measure', dataType: 'number' },
      ],
      data: [{ pnl: 42500, target: 40000 }],
    },
    {
      id: 'positions',
      fields: [
        { name: 'symbol', role: 'dimension', dataType: 'string' },
        { name: 'qty', role: 'measure', dataType: 'number' },
        { name: 'avgPrice', role: 'measure', dataType: 'number' },
      ],
      data: [
        { symbol: 'AAPL', qty: 100, avgPrice: 189.2 },
        { symbol: 'MSFT', qty: 50, avgPrice: 402.1 },
      ],
    },
  ],
  charts: [
    {
      id: 'price',
      title: 'AAPL',
      dataSourceId: 'ticks',
      type: 'candlestick',
      encoding: { x: 'ts', open: 'open', high: 'high', low: 'low', close: 'close', volume: 'volume' },
      // sma overlays the price pane; rsi gets its own synced sub-pane, sharing time-scale/crosshair with the price pane above
      indicators: [{ type: 'sma', period: 20 }, { type: 'rsi', period: 14 }],
      // agent-authored, declarative — see docs/agent-dashboard/chart-types.md#candlestick-volume-indicators-and-annotations
      annotations: [{ type: 'trendline', points: [{ time: '2026-08-20', value: 100 }, { time: '2026-08-22', value: 110 }], label: 'Uptrend' }],
    },
    { id: 'pnl', title: 'Realized P&L', dataSourceId: 'summary', type: 'kpi', encoding: { value: 'pnl', target: 'target' } },
    { id: 'positions', title: 'Open Positions', dataSourceId: 'positions', type: 'table', encoding: {} },
  ],
  pages: [
    {
      id: 'overview',
      name: 'Overview',
      layout: [
        { chartId: 'price', x: 0, y: 0, w: 8, h: 8 }, // taller than a plain OHLC chart to leave room for the volume overlay + RSI sub-pane
        { chartId: 'pnl', x: 8, y: 0, w: 4, h: 3 },
        { chartId: 'positions', x: 8, y: 3, w: 4, h: 5 },
      ],
    },
  ],
};

export function TradingDashboard() {
  return <AgentDashboard workbook={workbook} theme="dark" style={{ width: '100%', height: 700 }} />;
}
```

## 2. Sales overview: bar + pie + a filter

```tsx
const workbook: AgentDashboardWorkbook = {
  workbookId: 'sales_q3_2026',
  agentType: 'sales',
  title: 'Q3 Sales Overview',
  dataSources: [
    {
      id: 'deals',
      fields: [
        { name: 'region', role: 'dimension', dataType: 'string' },
        { name: 'stage', role: 'dimension', dataType: 'string' },
        { name: 'amount', role: 'measure', dataType: 'number' },
      ],
      data: [
        { region: 'us', stage: 'closed', amount: 42000 },
        { region: 'eu', stage: 'closed', amount: 31000 },
        { region: 'us', stage: 'pipeline', amount: 90000 },
        { region: 'apac', stage: 'pipeline', amount: 25000 },
      ],
    },
  ],
  filters: [{ id: 'region-filter', label: 'Region', field: 'region', dataSourceId: 'deals', type: 'categorical', appliesTo: ['*'] }],
  charts: [
    { id: 'by-region', title: 'Revenue by region', dataSourceId: 'deals', type: 'bar', encoding: { x: 'region', y: 'amount', aggregate: 'sum' } },
    { id: 'by-stage', title: 'Pipeline mix', dataSourceId: 'deals', type: 'pie', encoding: { x: 'stage', y: 'amount', aggregate: 'sum' } },
  ],
  pages: [
    {
      id: 'overview',
      name: 'Overview',
      layout: [
        { chartId: 'by-region', x: 0, y: 0, w: 8, h: 6 },
        { chartId: 'by-stage', x: 8, y: 0, w: 4, h: 6 },
      ],
    },
  ],
};

export function SalesDashboard() {
  return <AgentDashboard workbook={workbook} style={{ width: '100%', height: 500 }} />;
}
```

## 3. Lazy-loaded table against a paginated API

```tsx
<AgentDashboard
  workbook={workbookWithEmptyDataSource}
  dataLoaders={{
    trade_log: async ({ offset, limit }) => {
      const res = await fetch(`/api/trade-log?offset=${offset}&limit=${limit}`);
      const page = await res.json();
      return { rows: page.items, hasMore: page.hasMore, total: page.total };
    },
  }}
/>
```

See `data-loading.md` for the full design this builds on.
