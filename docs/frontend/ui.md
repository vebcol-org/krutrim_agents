# `libs/ui`

Nx library `ui` (import as `@krutrim_agent/ui`). Generic, shadcn/radix-style UI primitives and the shared theme — consumed by `libs/agent-ui` and `libs/agent-renderers`. No app-specific logic lives here; this is the "never touched when adding an agent" layer referenced in [`AGENTS.md`](../../AGENTS.md#project-directory-architecture).

## Components (`libs/ui/src/lib/`, exported from `index.ts`)

| File | Export(s) | Notes |
|---|---|---|
| `utils.ts` | `cn()` | `twMerge(clsx(inputs))` — standard shadcn helper for merging conditional Tailwind classes |
| `button.tsx` | `Button`, `buttonVariants` | `cva`-based: variants `default/outline/ghost/destructive`, sizes `default/sm/icon` |
| `input.tsx` | `Input` | Forward-ref styled `<input>` |
| `textarea.tsx` | `Textarea` | Forward-ref styled `<textarea>`, min-height 4rem, no resize |
| `label.tsx` | `Label` | Wraps `@radix-ui/react-label` |
| `separator.tsx` | `Separator` | Wraps `@radix-ui/react-separator`, horizontal/vertical |
| `badge.tsx` | `Badge`, `badgeVariants` | `cva` variants: `default/accent/success/destructive` |
| `card.tsx` | `Card`, `CardHeader`, `CardTitle`, `CardContent` | Plain styled `<div>`/`<h3>` wrappers, no Radix dependency |
| `scroll-area.tsx` | `ScrollArea` | Wraps `@radix-ui/react-scroll-area`; **ref forwards to the Radix `Viewport`**, not `Root` — deliberate, so consumers (e.g. `ChatThread` in `agent-ui`) can call `scrollRef.current.scrollTo(...)` directly |
| `select.tsx` | `Select`, `SelectTrigger`, `SelectContent`, `SelectItem`, `SelectValue`, `SelectGroup` (+ internal scroll buttons) | Wraps `@radix-ui/react-select` |
| `sheet.tsx` | `Sheet`, `SheetTrigger`, `SheetClose`, `SheetContent`, `SheetHeader`, `SheetTitle` | Wraps `@radix-ui/react-dialog` as a right-side slide-over panel — used by `SettingsPanel` and `SandboxSettingsPanel` in `agent-ui` |
| `timeline.tsx` | `Timeline`, `TimelineItemData` | Generic ordered-step primitive — a status dot (`pending`/`active`/`done`) per item, optional expandable detail (click to toggle). Used by the agent trace panel (`agent-renderers`' `research/trace-panel.tsx`), domain-agnostic so it's reusable elsewhere |
| `progress.tsx` | `Progress` | Simple determinate progress bar (`value`/`max`/`label`) — used by `RagUploadSheet` (`agent-ui`) for RAG-ingestion stage progress |

## Theme (`libs/ui/src/`, not exported via `index.ts`)

| File | Export(s) | Notes |
|---|---|---|
| `components/theme-provider.tsx` | `ThemeProvider`, `useTheme` | React context; persists `'dark' \| 'light'` to `localStorage['krutrim-agent-theme']`; initial theme from stored value or `prefers-color-scheme`; sets `data-theme` attribute on `<html>` |
| `components/theme-toggle.tsx` | `ThemeToggle` | Icon button (Sun/Moon from `lucide-react`) calling `toggleTheme()` |
| `components/avatar.tsx` | `Avatar` | Wraps `@radix-ui/react-avatar`; shows `src` image if given, else initials computed from `label` (first letters of the first two words) |
| `theme.css` | — | The design-token source, imported directly via Vite's `@ui-theme` alias (set in both `apps/web/vite.config.mts` and `apps/desktop/vite.renderer.config.mts`), **not** through `index.ts` |

`theme.css` defines a "terminal-amber" dark-first palette as CSS custom properties inside `@theme` (Tailwind v4 syntax), with a `[data-theme='light']` override block for a warm-paper light palette. Includes `@source` globs so Tailwind's content scanner reaches into `libs/agent-ui` and `libs/agent-renderers` (Tailwind's auto-detection is scoped per-app and doesn't walk sideways into sibling libs by default — these globs are what make Tailwind classes used in those libs actually get generated). Sets `--radius`, `--font-sans`, `--font-mono`, and a `prefers-reduced-motion` override that collapses all animation/transition durations.

`ChartView` (in `libs/agent-renderers`) reads several of these theme colors directly by CSS variable name (`--color-primary`, `--color-success`, `--color-destructive`, `--color-muted-foreground`) for its bar-chart palette — if you rename or remove one of those variables in `theme.css`, check `chart-view.tsx` too.
