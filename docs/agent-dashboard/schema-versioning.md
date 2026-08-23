# Schema versioning

## Why

Nothing about the current `AgentDashboardWorkbook` contract is expected to change soon, but an agent backend's stored/cached workbook payloads will outlive any given version of this package. Without a versioning story, changing a field's shape later would either break every payload produced before the change, or force this package to permanently support every historical shape inline in its main types. Neither is good — so the contract carries an explicit `schemaVersion`, and upgrading an old payload is a separate, pluggable step (`migrateWorkbook`) rather than something `<AgentDashboard>` has to guess at render time.

## The pieces (`src/schema-versioning.ts`)

```ts
const CURRENT_SCHEMA_VERSION = 1; // bump this when the shape changes incompatibly

type VersionedWorkbookInput = { schemaVersion?: number } & Record<string, unknown>;
type SchemaAdapter = (input: VersionedWorkbookInput) => VersionedWorkbookInput;

function registerSchemaAdapter(fromVersion: number, adapter: SchemaAdapter): void;
function migrateWorkbook(raw: VersionedWorkbookInput): AgentDashboardWorkbook;
```

- **`AgentDashboardWorkbook.schemaVersion`** (in `types.ts`) is optional. A payload with no `schemaVersion` is treated as version 1 — today's only version, and the implicit version of every payload that predates this field.
- **`registerSchemaAdapter(fromVersion, adapter)`** registers the one-hop upgrade from `fromVersion` to `fromVersion + 1`. Call it once per version gap you still need to support, typically at app startup, before any `migrateWorkbook` call.
- **`migrateWorkbook(raw)`** reads `raw.schemaVersion` (defaulting to 1), then walks the registered adapter chain one hop at a time until it reaches `CURRENT_SCHEMA_VERSION`, stamping the result with that version. It throws — rather than silently returning a wrong-shaped object — if:
  - a hop in the chain has no registered adapter, or
  - `raw.schemaVersion` is already newer than `CURRENT_SCHEMA_VERSION` (the payload needs a newer package version, not a migration).

## Using it today

There's only one version right now, so `migrateWorkbook` on a current payload is a no-op beyond stamping `schemaVersion`. Call it anyway wherever you load a workbook from an external source (an API response, local storage, a message queue) so the call site doesn't need to change later:

```ts
import { migrateWorkbook, type AgentDashboardWorkbook } from '@krutrim_agent/agent-dashboard';

const raw = await fetchWorkbookFromBackend();
const workbook: AgentDashboardWorkbook = migrateWorkbook(raw);
```

## Adding a v2 later

When the schema needs an incompatible change:

1. Update `AgentDashboardWorkbook` (and `AGENT_DASHBOARD_SCHEMA`) in this package to the new shape.
2. Bump `CURRENT_SCHEMA_VERSION` to `2`.
3. In your app (or this package, if the change is common enough to ship a default adapter), register the upgrade:

   ```ts
   registerSchemaAdapter(1, (v1) => ({
     ...v1,
     // e.g. a field was renamed:
     charts: (v1.charts as any[]).map((c) => ({ ...c, dataSourceId: c.dataset_id })),
   }));
   ```

4. Every existing v1 payload now upgrades automatically through `migrateWorkbook` — callers don't need to know how many versions back a payload is, only that `migrateWorkbook` handles it (or throws a clear, actionable error if a hop is missing).

This is exactly the mechanism `tests/schema-versioning.spec.ts` exercises today, using a hypothetical "version 0" predecessor as a concrete stand-in for the real 1 → 2 migration that will exist once the schema actually changes.
