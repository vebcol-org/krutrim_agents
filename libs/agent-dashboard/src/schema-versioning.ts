import type { AgentDashboardWorkbook } from './types';

/**
 * Bump this whenever AgentDashboardWorkbook's shape changes in a way that
 * isn't backward-compatible (a field renamed/removed/reshaped — a purely
 * additive optional field doesn't need a bump). Then register the adapter
 * that upgrades a `CURRENT_SCHEMA_VERSION - 1` payload to the new shape via
 * registerSchemaAdapter. See docs/agent-dashboard/schema-versioning.md.
 */
export const CURRENT_SCHEMA_VERSION = 1;

/**
 * A workbook payload of unknown/prior schema version — e.g. one loaded from
 * storage or received from a producer that hasn't upgraded yet. Not yet
 * known to match the current `AgentDashboardWorkbook` shape.
 */
export type VersionedWorkbookInput = { schemaVersion?: number } & Record<string, unknown>;

/** Upgrades a payload at `fromVersion` to the shape expected at `fromVersion + 1`. */
export type SchemaAdapter = (input: VersionedWorkbookInput) => VersionedWorkbookInput;

const adapters = new Map<number, SchemaAdapter>();

/**
 * Registers the adapter that upgrades a workbook payload from `fromVersion`
 * to `fromVersion + 1`. `migrateWorkbook` chains these to walk any older
 * payload up to `CURRENT_SCHEMA_VERSION`, one hop per registered adapter —
 * call this once per version gap you still need to support, typically at
 * app startup.
 */
export function registerSchemaAdapter(fromVersion: number, adapter: SchemaAdapter): void {
  adapters.set(fromVersion, adapter);
}

/** Removes every registered adapter. Exposed for test isolation, not meant for app code. */
export function clearSchemaAdapters(): void {
  adapters.clear();
}

/**
 * Upgrades `raw` to the current `AgentDashboardWorkbook` shape, running
 * whatever chain of registered adapters is needed. A payload with no
 * `schemaVersion` is treated as version 1 (every payload predating this
 * field is implicitly version 1 — today's only version). Throws rather than
 * guessing if a required hop's adapter hasn't been registered, or if `raw`
 * claims a version newer than this package build supports.
 */
export function migrateWorkbook(raw: VersionedWorkbookInput): AgentDashboardWorkbook {
  let version = raw.schemaVersion ?? 1;
  let data: VersionedWorkbookInput = raw;

  if (version > CURRENT_SCHEMA_VERSION) {
    throw new Error(
      `Workbook schemaVersion ${version} is newer than this build of @krutrim_agent/agent-dashboard supports (CURRENT_SCHEMA_VERSION=${CURRENT_SCHEMA_VERSION}). Upgrade the package.`,
    );
  }

  while (version < CURRENT_SCHEMA_VERSION) {
    const adapter = adapters.get(version);
    if (!adapter) {
      throw new Error(
        `No schema adapter registered to migrate a workbook from version ${version} to ${version + 1}. Call registerSchemaAdapter(${version}, ...) before migrateWorkbook().`,
      );
    }
    data = adapter(data);
    version += 1;
  }

  return { ...data, schemaVersion: CURRENT_SCHEMA_VERSION } as AgentDashboardWorkbook;
}
