import { afterEach, describe, expect, it } from 'vitest';
import {
  CURRENT_SCHEMA_VERSION,
  clearSchemaAdapters,
  migrateWorkbook,
  registerSchemaAdapter,
} from '../src/schema-versioning';

afterEach(clearSchemaAdapters);

function baseFields() {
  return { agentType: 'research', dataSources: [], charts: [], pages: [] };
}

describe('migrateWorkbook', () => {
  it('treats a payload with no schemaVersion as version 1 (today\'s shape) and stamps CURRENT_SCHEMA_VERSION', () => {
    const raw = { workbookId: 'wb', ...baseFields() };
    const result = migrateWorkbook(raw);
    expect(result.schemaVersion).toBe(CURRENT_SCHEMA_VERSION);
    expect(result.workbookId).toBe('wb');
  });

  it('is a no-op pass-through (beyond stamping schemaVersion) when the payload is already current', () => {
    const raw = { workbookId: 'wb', schemaVersion: CURRENT_SCHEMA_VERSION, ...baseFields() };
    expect(migrateWorkbook(raw)).toEqual(raw);
  });

  it('runs a registered adapter to walk an older payload up to the current version', () => {
    // A concrete demonstration of the chain mechanism using a hypothetical
    // "version 0" predecessor: version 0 called the id field "board"
    // instead of "workbookId". The same registerSchemaAdapter/migrateWorkbook
    // pair is what a real 1 -> 2 migration will use once the schema
    // actually changes — see docs/agent-dashboard/schema-versioning.md.
    registerSchemaAdapter(0, (legacy) => {
      const { board, ...rest } = legacy as { board: string };
      return { ...rest, workbookId: board };
    });

    const legacyPayload = { schemaVersion: 0, board: 'legacy-wb', ...baseFields() };
    const result = migrateWorkbook(legacyPayload);

    expect(result.workbookId).toBe('legacy-wb');
    expect(result.schemaVersion).toBe(CURRENT_SCHEMA_VERSION);
    expect((result as unknown as { board?: string }).board).toBeUndefined();
  });

  it('throws a clear error when no adapter is registered for a needed hop', () => {
    const legacyPayload = { schemaVersion: 0, workbookId: 'wb', ...baseFields() };
    expect(() => migrateWorkbook(legacyPayload)).toThrow(/No schema adapter registered/);
  });

  it('throws when the payload claims a version newer than this package supports', () => {
    const future = { schemaVersion: CURRENT_SCHEMA_VERSION + 1, workbookId: 'wb', ...baseFields() };
    expect(() => migrateWorkbook(future)).toThrow(/newer than this build/);
  });
});
