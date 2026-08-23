# `libs/tauri-utils`

Nx library `tauri-utils` (import as `@krutrim_agent/tauri-utils`). The smallest package in the frontend — one function.

```
libs/tauri-utils/src/
├── index.ts             export * from './lib/is-tauri'
└── lib/
    └── is-tauri.ts         isTauriRuntime()
```

## `is-tauri.ts` — `isTauriRuntime()`

```ts
export function isTauriRuntime(): boolean {
  return isTauri(); // from @tauri-apps/api/core
}
```

Doc comment: "Lets shared code (e.g. `agent-ui`) branch on desktop vs. web without every consumer importing `@tauri-apps/api` directly." — i.e. this exists as a single seam so that shared UI code never needs to import `@tauri-apps/api` itself; it can import this tiny wrapper instead, which is a no-op (`isTauri()` always returns `false`) when running in a plain browser.

## Currently unused

Grep for `isTauriRuntime`/`tauri-utils` outside this package's own source turns up nothing — no import anywhere in `apps/web`, `apps/desktop`, `libs/agent-ui`, `libs/agent-renderers`, or `libs/ui`. This isn't a bug; it's intentional scaffolding for the first time desktop-only frontend behavior is actually needed (e.g. a native file picker, a different keyboard-shortcut set, a Tauri-only settings section) — at that point there's already one place to check rather than a new ad-hoc `@tauri-apps/api` import scattered wherever the need comes up. Nothing stops `apps/web` from importing it too (it would just always get `false`), but there's no reason to.
