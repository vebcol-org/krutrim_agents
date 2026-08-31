import { z } from 'zod';
import { SHARING_SCOPES } from '@krutrim_agent/shared-types';
import type {
  Agent,
  AgentMeta,
  Chat,
  ChatApiMessage,
  EmbedResponse,
  ModelSettings,
  Project,
  ProviderSettingsByRole,
  RagDocument,
  RagDocumentsResponse,
  RagTextResponse,
  SessionInfo,
  UpdateSettingsResponse,
} from '@krutrim_agent/shared-types';

/**
 * Runtime (zod) schemas for every backend JSON shape this package consumes.
 *
 * Each schema is assigned to a `z.ZodType<T>`-typed const, where `T` is the
 * hand-written interface from `@krutrim_agent/shared-types`. That
 * assignment is a compile-time check that the schema's inferred shape
 * actually matches the type we claim it validates — if you add a field to
 * a `shared-types` interface without adding it here, TypeScript will not
 * let you assign this schema to that type until you do.
 *
 * Every object schema below is `.strict()`: an unexpected extra field in a
 * backend response fails validation at runtime instead of being silently
 * dropped (zod's default `.object()` behavior). That's deliberate — see
 * `ApiSchemaError` in `../utils/http-client.ts` for why a new/renamed field
 * on the backend should be a loud, specific error during development
 * instead of a value nobody notices is missing.
 */

const sharingScopeSchema = z.enum(SHARING_SCOPES);
const resourceOverridesSchema = z.record(z.string(), z.number()).nullable();

export const agentMetaSchema: z.ZodType<AgentMeta> = z
  .object({
    key: z.string(),
    display_name: z.string(),
    description: z.string(),
    roles: z.array(z.string()),
  })
  .strict();

export const projectSchema: z.ZodType<Project> = z
  .object({
    project_id: z.string(),
    project_title: z.string(),
    project_information: z.string(),
    created_at: z.string(),
    updated_at: z.string(),
    sandbox_sharing: sharingScopeSchema,
    sandbox_idle_timeout_seconds: z.number().nullable(),
    sandbox_resource_overrides: resourceOverridesSchema,
  })
  .strict();

export const agentSchema: z.ZodType<Agent> = z
  .object({
    agent_id: z.string(),
    project_id: z.string(),
    agent_key: z.string(),
    display_name: z.string(),
    created_at: z.string(),
    updated_at: z.string(),
    // `null` means "inherit the project's default" — a real, distinct value
    // from every SharingScope literal, not an absent/optional field.
    sandbox_sharing: sharingScopeSchema.nullable(),
    sandbox_idle_timeout_seconds: z.number().nullable(),
    sandbox_resource_overrides: resourceOverridesSchema,
  })
  .strict();

export const chatSchema: z.ZodType<Chat> = z
  .object({
    chat_id: z.string(),
    project_id: z.string().nullable(),
    display_name: z.string(),
    provider: z.string(),
    model: z.string(),
    created_at: z.string(),
    updated_at: z.string(),
    sandbox_sharing: sharingScopeSchema.nullable(),
    sandbox_idle_timeout_seconds: z.number().nullable(),
    sandbox_resource_overrides: resourceOverridesSchema,
  })
  .strict();

export const sessionInfoSchema: z.ZodType<SessionInfo> = z
  .object({
    session_id: z.string(),
    owner_type: z.enum(['agent', 'chat']),
    owner_id: z.string(),
    project_id: z.string().nullable(),
    display_name: z.string().nullable(),
    created_at: z.string(),
    updated_at: z.string(),
    sandbox_sharing: sharingScopeSchema,
    attached_to_session_id: z.string().nullable(),
    linked_session_ids: z.array(z.string()),
  })
  .strict();

export const chatApiMessageSchema: z.ZodType<ChatApiMessage> = z
  .object({
    role: z.enum(['user', 'assistant']),
    content: z.string(),
  })
  .strict();

export const sessionMessagesResponseSchema: z.ZodType<{ messages: ChatApiMessage[] }> = z
  .object({ messages: z.array(chatApiMessageSchema) })
  .strict();

export const embedResponseSchema: z.ZodType<EmbedResponse> = z
  .object({
    status: z.literal('queued'),
    task_id: z.string(),
    job_id: z.string(),
    file_count: z.number(),
  })
  .strict();

export const ragTextResponseSchema: z.ZodType<RagTextResponse> = z
  .object({
    status: z.literal('queued'),
    task_id: z.string(),
    job_id: z.string(),
    document_id: z.string(),
  })
  .strict();

export const ragDocumentSchema: z.ZodType<RagDocument> = z
  .object({
    document_id: z.string(),
    title: z.string(),
    filename: z.string().nullable(),
    source_path: z.string(),
    kind: z.enum(['file', 'text']),
    created_at: z.string(),
  })
  .strict();

export const ragDocumentsResponseSchema: z.ZodType<RagDocumentsResponse> = z
  .object({ documents: z.array(ragDocumentSchema) })
  .strict();

const baseModelSettingsShape = {
  model: z.string(),
  temperature: z.number(),
  max_tokens: z.number().nullable(),
  top_p: z.number().nullable(),
  timeout: z.number().nullable(),
};

// Not annotated as `z.ZodType<OpenRouterModelSettings>` (unlike every other
// schema in this file) — `z.discriminatedUnion` needs its members typed as
// concrete `ZodObject`s to pick the right variant by `provider`, and
// widening to the `ZodType` interface here would break that. The
// compile-time shape check still happens below, at the union level: if
// either variant's shape drifts from its `shared-types` interface, the
// `modelSettingsSchema` assignment two lines down fails to compile instead.
const openRouterModelSettingsSchema = z
  .object({
    ...baseModelSettingsShape,
    provider: z.literal('openrouter'),
    api_key_env: z.string(),
    base_url: z.string(),
    site_url: z.string().nullable(),
    app_name: z.string(),
  })
  .strict();


export const modelSettingsSchema: z.ZodType<ModelSettings> = z.discriminatedUnion('provider', [
  openRouterModelSettingsSchema,
]);

export const providerSettingsByRoleSchema: z.ZodType<ProviderSettingsByRole> = z.record(
  z.string(),
  modelSettingsSchema,
);

export const updateSettingsResponseSchema: z.ZodType<UpdateSettingsResponse> = z
  .object({
    settings: modelSettingsSchema,
    note: z.string(),
  })
  .strict();

/**
 * SSE status events (`GET /api/status/containers/{ownerId}`) are validated
 * leniently on purpose — not `.strict()`, and a mismatch is handled by the
 * caller (see `useSseStatus` in `../hooks/use-sse-status.ts`) by warning and
 * keeping the last-known-good value, not throwing. A live status stream
 * should degrade gracefully on one malformed frame; that's different from a
 * one-shot REST response, where a schema mismatch should fail loudly and
 * immediately. `status` mirrors `ContainerStatusEvent['status']`, which is
 * itself an open string union in `shared-types` for the same reason.
 */
export const containerStatusEventSchema = z.object({
  status: z.string(),
  ref_count: z.number().optional(),
});
