# agent-ui

Published as `@krutrim_agent/agent-ui` — the whole `<Agent>` product frontend.
See the root [`README.md`](../../README.md#reusable-packages--consuming-this-repo-from-another-codebase)
for how an external repo consumes this package, and its `extensions` prop for
wiring in real auth/visibility hooks.

## Layout

- `components/{shell,thread,panels,sheets}/` — the agent-agnostic frame (history
  rail, composer + message list, settings / sandbox panels, creation sheets).
- `screens/` — the per-agent plugin surface. `screens/<key>/` exports an
  `AgentScreenModule` (`Center` pane + optional `OutputRenderer` + `turnSplitter`);
  `home`, `chat`, `default` and each agent type are all modules registered in
  `screens/registry.ts`. `AgentLayout` just resolves `getScreen(key)`.
  (This folder absorbed the former `@krutrim_agent/agent-renderers` package.)
- `api/`, `hooks/`, `store/`, `utils/` — the shared data layer.

## Adding an agent screen

Create `screens/<key>/index.ts` exporting an `AgentScreenModule`, then add it to
the array in `screens/registry.ts`. Nothing in `components/` changes.

## Running unit tests

Run `nx test agent-ui` to execute the unit tests via [Jest](https://jestjs.io).
