import { useEffect, useState } from 'react';
import type { ModelCard, RoleModelSettings } from '@krutrim_agent/shared-types';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@krutrim_agent/ui';

import {
  fetchModelCatalog,
  fetchSessionModelSettings,
  resetSessionModelSettings,
  updateSessionModelSettings,
} from '../../api';

const AGENT_DEFAULT = '__agent_default__';

/** Picks the role the composer switcher targets — the primary chat role. */
function primaryRole(roles: RoleModelSettings[]): RoleModelSettings | null {
  return roles.find((r) => r.role === 'main') ?? roles[0] ?? null;
}

export interface ComposerModelPickerProps {
  backendUrl: string;
  /** The active agent session — the switch is a per-session override. */
  sessionId: string;
}

/**
 * A compact model switcher in the composer. Writes a **session-scoped**
 * override of the agent's `main` role via `PUT /api/providers/sessions/{id}/{role}`;
 * "Agent default" clears it (`…/reset`). Takes effect on the next message.
 */
export function ComposerModelPicker({ backendUrl, sessionId }: ComposerModelPickerProps) {
  const [role, setRole] = useState<RoleModelSettings | null>(null);
  const [models, setModels] = useState<ModelCard[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setRole(null);
    Promise.all([fetchSessionModelSettings(backendUrl, sessionId), fetchModelCatalog(backendUrl, { kind: 'chat' })])
      .then(([settings, catalog]) => {
        if (cancelled) return;
        setRole(primaryRole(settings.roles));
        setModels(catalog);
      })
      .catch(() => {
        /* non-critical — the picker just stays hidden */
      });
    return () => {
      cancelled = true;
    };
  }, [backendUrl, sessionId]);

  if (!role) return null;

  const value = role.source === 'session' ? role.settings.model : AGENT_DEFAULT;
  const known = models.some((m) => m.id === role.settings.model);

  async function apply(next: string) {
    if (busy) return;
    setBusy(true);
    try {
      const data =
        next === AGENT_DEFAULT
          ? await resetSessionModelSettings(backendUrl, sessionId, role!.role)
          : await updateSessionModelSettings(backendUrl, sessionId, role!.role, {
              provider: models.find((m) => m.id === next)?.provider ?? role!.settings.provider,
              model: next,
            });
      setRole(primaryRole(data.roles));
    } catch {
      /* keep the previous selection on failure */
    } finally {
      setBusy(false);
    }
  }

  return (
    <Select value={value} onValueChange={apply} disabled={busy}>
      <SelectTrigger
        aria-label="Model for this session"
        className="h-7 gap-1 border-0 bg-transparent px-2 text-xs text-muted-foreground hover:text-foreground focus:ring-0"
      >
        <SelectValue placeholder="Model">
          {value === AGENT_DEFAULT
            ? 'Agent default'
            : (models.find((m) => m.id === value)?.label ?? value)}
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={AGENT_DEFAULT}>Agent default</SelectItem>
        {models.map((m) => (
          <SelectItem key={m.id} value={m.id}>
            {m.label}
          </SelectItem>
        ))}
        {!known && value !== AGENT_DEFAULT && (
          <SelectItem value={role.settings.model}>{role.settings.model} (custom)</SelectItem>
        )}
      </SelectContent>
    </Select>
  );
}
