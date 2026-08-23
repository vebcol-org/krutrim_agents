# `apps/web`

The browser frontend — Vite + React + TypeScript. Nx project name `web`, `projectType: "application"`, empty `targets: {}` in `project.json` (build/serve/lint/test are all Nx-plugin-inferred from `vite.config.mts` — see [`README.md#building-running-testing`](README.md#building-running-testing)).

```
apps/web/
├── index.html
├── vite.config.mts        dev server + build + embedded Vitest config
├── .env.local              committed symlink → root .env
└── src/
    ├── main.tsx             ReactDOM.createRoot → <App />
    ├── styles.css
    └── app/
        └── app.tsx           BrowserRouter, single "/" route → <Agent>
```

## `src/main.tsx`

```tsx
ReactDOM.createRoot(document.getElementById('root')!).render(
  <StrictMode><App /></StrictMode>,
);
```
Vanilla React 19 root render. Imports `./styles.css`. Does not itself read `VITE_BACKEND_URL` — that happens in `app.tsx`.

## `src/app/app.tsx`

```tsx
const backendUrl = import.meta.env['VITE_BACKEND_URL'] ?? DEFAULT_BACKEND_URL;

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Agent backendUrl={backendUrl} />} />
      </Routes>
    </BrowserRouter>
  );
}
```
- Imports `Agent` from `@krutrim_agent/agent-ui` (**not** `AgentApp` — see the [reality-check in the frontend README](README.md#️-read-this-first--the-docs-vs-the-code)) and `DEFAULT_BACKEND_URL` from `@krutrim_agent/shared-types`.
- **Routing**: exactly one route, `"/"` → `<Agent>`. No `?agent=` query-param parsing, no nested routes. `react-router-dom` is present but essentially unused beyond this single route — it exists as a seam for future routes, not because routing is load-bearing today.

## `vite.config.mts`

- Dev server: `localhost:4200`; preview: same port.
- Alias `@ui-theme` → `libs/ui/src/theme.css` (absolute file URL) — how `Agent`'s styling reaches the shared design tokens.
- Plugins: `@vitejs/plugin-react`, `@tailwindcss/vite`, `nxViteTsPaths()` (resolves `@krutrim_agent/*` workspace imports), `nxCopyAssetsPlugin(['*.md'])`.
- Build output: `../../dist/apps/web`, `emptyOutDir: true`.
- **Embedded Vitest config** (same file, not a separate `vitest.config.*`): `environment: 'jsdom'`, test globs `src|tests/**/*.{test,spec}.*`, coverage → `../../coverage/apps/web`, provider `v8` — this is the one project with `--coverage` actually wired.

## `index.html`

`<base href="/" />`; links `/favicon.ico` and `/src/styles.css` directly (plain `<link>`, not bundler-injected); loads `/src/main.tsx` as a module script. `<title>Web</title>`.

## Env vars

Only `VITE_BACKEND_URL` is consumed by frontend code (default `http://localhost:8000`, matching the backend's default port). `.env.local` is a **committed symlink** to the repo-root `.env` (per the root [`README.md`](../../README.md#setup) convention — one shared env file, several symlinks pointing at it: `backend/.env`, `apps/web/.env.local`, `docker/.env`). Per the root `.env.example`'s own comment, `VITE_BACKEND_URL` is "baked in at BUILD time for the Docker/production build" but read live by `vite dev` for local dev. Don't put real secret *values* in this doc — only var names; the actual `.env`/`.env.local` files hold real-looking keys and are gitignored except for their symlink nature.

## Diff from `apps/desktop`

See [`apps-desktop.md#diff-from-appsweb`](apps-desktop.md#diff-from-appsweb) — the two apps share the same `Agent` component and single-route pattern; only the entry-file shape, dev port, and a couple of Vite/CSP details differ.
