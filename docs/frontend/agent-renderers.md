# `libs/agent-renderers`

Nx library `agent-renderers` (import as `@krutrim_agent/agent-renderers`). The canvas renderer registry for the AG-UI flow's `render_content` tool.

**Wired in.** `libs/agent-ui`'s `OutputPanel` calls `getAgentRenderer(agentKey)` and renders the result — see [`agent-ui.md`](agent-ui.md#componentsagentoutput-paneltsx--no-longer-a-placeholder). This library is no longer orphaned; it's reachable from every real agent run through `AgentLayout` → `OutputPanel` → `getAgentRenderer`.

```
libs/agent-renderers/src/
├── index.ts                 re-exports types, registry, default-renderer
├── registry.ts                getAgentRenderer(agentKey) — dict lookup + fallback
├── types.ts                    AgentRendererProps (payload, trace?) / AgentRendererComponent / TraceStep
├── prose.tsx                    ProseMarkdown — shared markdown-prose wrapper, extracted from the two duplicates below
├── default-renderer.tsx         DefaultRenderer — kind-based switch (markdown/chart/news)
├── chart-view.tsx                 ChartView — dependency-free bar chart
├── news-view.tsx                    NewsView — card list
├── research/
│   ├── renderer.tsx                  ResearchRenderer — full markdown-spec implementation (TOC, math, trace panel)
│   ├── section-markers.ts             TS port of the backend's sec:id marker parser
│   ├── toc.tsx                         SectionToc — nested section nav
│   └── trace-panel.tsx                  TracePanel — renders TraceStep[] via libs/ui's Timeline
├── sales/renderer.tsx              SalesRenderer — pass-through to DefaultRenderer
└── trading/renderer.tsx             TradingRenderer — adds a persistent disclaimer footer
```

## `registry.ts` — `getAgentRenderer(agentKey)`

```ts
const RENDERERS: Record<string, AgentRendererComponent> = {
  research: ResearchRenderer,
  trading: TradingRenderer,
  sales: SalesRenderer,
};
export const getAgentRenderer = (agentKey: string) => RENDERERS[agentKey] ?? DefaultRenderer;
```
Simple dict lookup with a fallback — no error thrown for an unknown key, it just falls back to `DefaultRenderer`. No change to the lookup logic itself in this pass — what changed is that it's no longer hypothetical/unreachable: `libs/agent-ui`'s `OutputPanel` is now a real caller (see above).

## `types.ts`

```ts
interface AgentRendererProps {
  payload: RenderContentPayload;
  trace?: TraceStep[]; // undefined outside a live agent run context
}
type AgentRendererComponent = (props: AgentRendererProps) => JSX.Element;
```
`RenderContentPayload` (`{ kind, title, content }`) comes from `@krutrim_agent/shared-types` — see [`shared-types.md`](shared-types.md). `AgentRendererProps` is widened with an optional `trace` — non-breaking, since `sales`/`trading`/`DefaultRenderer` just ignore the prop.

**`TraceStep` is defined here**, not in `agent-ui` (despite `agent-ui`'s `useAgentChat` being what actually produces it): `agent-ui` already depends on `agent-renderers`, not the reverse, so the shared type has to live on the consumer side. `use-agent-chat.ts` imports it back via `import type { TraceStep } from '@krutrim_agent/agent-renderers'`.

```ts
interface TraceStep {
  id: string;
  kind: 'tool_call' | 'step' | 'reasoning';
  label: string;
  detail?: string;
  status: 'started' | 'finished';
  timestamp: number;
}
```

## `prose.tsx` — `ProseMarkdown`

Shared markdown-prose wrapper (the `<div className="prose-invert ...">` + `<ReactMarkdown>` pair), extracted from markup previously duplicated verbatim in `default-renderer.tsx` and `trading/renderer.tsx` — both refactored to use it, with `ChartView`/`NewsView` moved outside the prose wrapper `<div>` in the process (confirmed self-contained, no visual regression). Accepts `remarkPlugins`/`rehypePlugins`/`components` pass-through, always includes `remark-gfm` regardless of what's passed, so `research/renderer.tsx` (below) can extend it with spec-specific plugins (math, raw-HTML image-width hints) without touching the shared styling.

## `default-renderer.tsx` — `DefaultRenderer`

Header: `payload.kind` (uppercase, amber) + `payload.title`. Body switches on `payload.kind`:
- `'chart'` → `<ChartView>`
- `'news'` → `<NewsView>`
- anything else → `<ProseMarkdown content={payload.content} />` (i.e. markdown is the default/fallback kind)

## `chart-view.tsx` — `ChartView`

`ChartView({ content })` parses `content` as JSON into `ChartContent` (`{labels, series}` — see [`shared-types.md`](shared-types.md)); on parse failure or empty data, shows a "Couldn't parse chart data." / "No chart data." message. Renders a **dependency-free bar chart** — plain `<div>`s sized by percentage height, no SVG or charting library — using a 4-color palette drawn from CSS custom properties (`--color-primary/success/destructive/muted-foreground`, defined in `libs/ui`'s `theme.css`), grouped bars per label when there are multiple series, with a legend shown when `series.length > 1`.

## `news-view.tsx` — `NewsView`

`NewsView({ content })` parses as `NewsContent` (`{items: [{headline, source, summary, url?}]}`); renders one `Card` per item — a source `Badge`, the headline (linked if `item.url` is present), and a summary paragraph.

## `research/` — `ResearchRenderer`

**No longer a pass-through to `DefaultRenderer`.** A real implementation of `backend/harness/prompts/format/markdown/markdown-spec.md`, split across four files:

- **`section-markers.ts`** — a TypeScript port of `backend/libs/krutrim_agents_core/src/krutrim_agents_core/format/markdown_parser.py` (that module's own docstring explicitly invites this: "trivially portable to any backend language/runtime"). Exports `parseDocumentTree`/`flattenTree`/`stripSectionMarkers` mirroring the Python functions 1:1, plus a frontend-only `prepareResearchMarkdown` (not in the Python source) that additionally strips `<!-- repeat-header -->` (a print-only hint with no browser equivalent — silently dropped) and rewrites `<!-- width:NN% -->` image hints into inline `<img width="NN%">` tags. Parses/strips client-side since the content already sits in the browser as the final assistant message text, rather than round-tripping to the backend.
- **`toc.tsx`** — `SectionToc`, a nested nav built directly from the parsed `sec:id` tree; click-to-scroll. Heading `id`s are assigned in `renderer.tsx` itself, by matching document-order headings 1:1 against the flattened tree — no separate slugger needed, since a spec-compliant document has exactly one heading per section marker in the same order.
- **`trace-panel.tsx`** — `TracePanel`, renders the `TraceStep[]` produced by `useAgentChat` (see [`agent-ui.md`](agent-ui.md)) via `libs/ui`'s new `Timeline` primitive (see [`ui.md`](ui.md)); distinguishes `rag_tool` calls (prefixed "RAG") from other tools like `web_search`/`fetch_url`. Renders nothing once `trace` is empty, so an idle canvas isn't cluttered.
- **`renderer.tsx`** — `ResearchRenderer`, wiring the above together: `SectionToc` in a left rail, `TracePanel` above the content when `trace` is present, and the document body via `ProseMarkdown` extended with `remark-math`/`rehype-katex` (math) and `rehype-raw` (for the width-hint inline `<img>` tags).

**Math dependencies**: `remark-math`, `rehype-katex`, `katex` (for `katex/dist/katex.min.css`), `rehype-raw` — all new in `package.json`. **CSS-import subtlety**: the KaTeX CSS is imported as a plain external ESM import (`import 'katex/dist/katex.min.css'`) directly in `renderer.tsx`. For that import to survive this library's own Vite lib build without being tree-shaken away, `package.json`'s `sideEffects` had to change from `false` to `["*.css"]`. Confirmed working end-to-end via a full `web:build`/`desktop:build` — KaTeX fonts and CSS show up in `dist/apps/*/assets/`, i.e. the consuming app's bundler is what actually resolves and ships the CSS, not this library in isolation.

## Other per-agent renderers

| Renderer | Behavior |
|---|---|
| `sales/renderer.tsx` — `SalesRenderer` | Literal pass-through: `return <DefaultRenderer {...props} />`. Comment: sales reports are plain documents, no reason to duplicate the default. |
| `trading/renderer.tsx` — `TradingRenderer` | The one genuinely **custom** non-research renderer. Same header/kind-switch structure as `DefaultRenderer` (now also via `ProseMarkdown`), but adds a fixed `<footer>` on **every** render regardless of `kind`: *"Not financial advice — informational only."* (destructive-colored, uppercase, dashed top border), plus a `Badge` naming the content kind next to the title. Still delegates chart/news rendering to the shared `ChartView`/`NewsView` rather than reimplementing them. |

## `index.ts`

Re-exports `types`, `registry`, `default-renderer` — **not** the per-agent renderer files directly (those are only reachable through `getAgentRenderer`). `types.ts` is already in the `export *` barrel, so `TraceStep` is reachable from the package root today — no change needed here for the new type to be importable as `@krutrim_agent/agent-renderers`'s `TraceStep`.

## Adding a renderer for a new agent profile

Per the root [`README.md`](../../README.md#adding-a-new-agent-type): add `libs/agent-renderers/src/<key>/renderer.tsx` plus one line in `registry.ts`'s `RENDERERS` map — optional; omitting it falls back to `DefaultRenderer` automatically. No other file in this package needs to change.
