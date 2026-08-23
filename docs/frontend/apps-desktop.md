# `apps/desktop`

The Tauri desktop app — same React renderer as `apps/web`, wrapped in a native window by a minimal Rust shell. Nx project name `desktop`, `projectType: "application"`, with **explicit** `project.json` targets (`build`, `serve`, `package`) since Tauri isn't Vite-plugin-inferrable the way `apps/web` is.

```
apps/desktop/
├── index.html                own CSP <meta> tag
├── vite.renderer.config.mts   dev server + build (renderer only, no vitest config)
├── .env.example                VITE_BACKEND_URL=http://localhost:8000 (no .env.local present in-tree)
├── src/
│   └── renderer/
│       └── main.tsx            entry point — inlines what web splits into main.tsx + app.tsx
└── src-tauri/
    ├── src/main.rs               #[cfg_attr(...)] wrapper, calls lib::run()
    ├── src/lib.rs                  tauri::Builder::default().run(...) — zero customization
    ├── tauri.conf.json              window config, dev/build commands
    └── capabilities/default.json     permissions: ["core:default"] only
```

## `src/renderer/main.tsx`

```tsx
const backendUrl = import.meta.env['VITE_BACKEND_URL'] ?? DEFAULT_BACKEND_URL;
const root = ReactDOM.createRoot(document.getElementById('root') as HTMLElement);
root.render(
  <StrictMode>
    <BrowserRouter>
      <Routes><Route path="/" element={<Agent backendUrl={backendUrl} />} /></Routes>
    </BrowserRouter>
  </StrictMode>,
);
```
Structurally identical to `apps/web`'s `main.tsx` + `app.tsx` combined into one file — same `Agent` import from `@krutrim_agent/agent-ui`, same single `"/"` route, same `VITE_BACKEND_URL` fallback pattern. This confirms at the code level that the desktop shell really is "the same React renderer, minimal diff."

## `src-tauri/src/main.rs` + `src-tauri/src/lib.rs`

```rust
// main.rs
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
fn main() { krutrim_agent_desktop_lib::run(); }

// lib.rs
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running the Krutrim Agent desktop application");
}
```

**Confirmed: the Rust shell does not spawn or manage the backend process.** No `Command::new`, no `std::process` usage, no `#[tauri::command]` handlers at all — `tauri::Builder::default()` with zero customization. It's purely a native window wrapping the same webview content; the desktop app connects to whatever `VITE_BACKEND_URL` points at, same as the web app. `capabilities/default.json` grants only `["core:default"]` — no filesystem/shell/network capability beyond Tauri's baseline.

## `tauri.conf.json`

- `beforeDevCommand`: `pnpm exec vite --config vite.renderer.config.mts`
- `beforeBuildCommand`: `pnpm exec vite build --config vite.renderer.config.mts`
- `devUrl`: `http://localhost:4300`
- `frontendDist`: `../../../dist/apps/desktop/renderer`
- One window, `1280×820`. `security.csp: null` — CSP is instead set via a `<meta>` tag in `index.html` (below), not this config.

## `vite.renderer.config.mts`

Dev server port `4300`. `base: './'` — **relative** asset paths, needed because a production build gets loaded via `file://` inside the native webview, unlike `apps/web`'s absolute-path production deploy. Same `@ui-theme` alias and plugin set as `apps/web`'s `vite.config.mts`, minus `nxCopyAssetsPlugin`. Build output: `../../dist/apps/desktop/renderer`. **No embedded Vitest config** (unlike `apps/web`).

## `index.html`

Own `Content-Security-Policy` via `<meta http-equiv>`: `default-src 'self' 'unsafe-inline' http://localhost:* ws://localhost:*; img-src 'self' data:;` — a permissive localhost-only policy suited to dev. `<title>Research Agent</title>` (differs from `apps/web`'s `"Web"`).

## `.env.example`

```
VITE_BACKEND_URL=http://localhost:8000
```
Comment: "Copy to `apps/desktop/.env.local` and adjust if your backend runs elsewhere." No `.env.local` is actually present in the tree for desktop today — only the example.

## Diff from `apps/web`

| | `apps/web` | `apps/desktop` |
|---|---|---|
| Entry shape | `main.tsx` + `app/app.tsx` split | inlined into one `src/renderer/main.tsx` |
| Dev port | 4200 | 4300 |
| Vite `base` | default (absolute) | `'./'` (relative — needed for `file://` loading) |
| CSP | none set in `index.html` | explicit `<meta>` CSP tag |
| Title | "Web" | "Research Agent" |
| Vitest | embedded in `vite.config.mts` | none |

Same `Agent` component, same single `"/"` route, same `VITE_BACKEND_URL` env-var pattern, same Tailwind/theme wiring (`@ui-theme` alias) in both.

## Known limitations

- `src-tauri/icons/icon.png` is a solid-color placeholder — regenerate a real icon set (`pnpm exec tauri icon <path-to-1024px-png>`) before running `nx run desktop:package` (`tauri build`) to produce a real installable bundle.
- Requires the Rust toolchain (`rustup`/`cargo`) plus Tauri's platform-specific system deps (e.g. WebKitGTK on Linux) for `serve`/`package`; `build` is deliberately Rust-free (renderer only) so `nx run-many -t build` doesn't need Rust.
