import { useEffect, useState } from 'react';
import type {
  ModelCard,
  ModelSelection,
  ProviderCard,
  RoleModelSettings,
} from '@krutrim_agent/shared-types';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@krutrim_agent/ui';

import {
  fetchAgentModelSettings,
  fetchModelCatalog,
  fetchProviders,
  resetAgentModelSettings,
  updateAgentModelSettings,
} from '../../api';
import { ApiError } from '../../utils/http-client';
import { RoleEditor } from './role-editor';

/** The one user-facing model. Subagent roles (researcher/critic/…) are a
 * multi-agent-system internal and always use the profile default. */
const PRIMARY_ROLE = 'main';

export interface SettingsPanelProps {
  /** An `Agent` *instance* id (not a profile key) — model picks are per instance. */
  agentId: string;
  agentLabel?: string;
  backendUrl: string;
  onClose: () => void;
}

export function SettingsPanel({ agentId, agentLabel, backendUrl, onClose }: SettingsPanelProps) {
  const [roles, setRoles] = useState<RoleModelSettings[] | null>(null);
  const [models, setModels] = useState<ModelCard[]>([]);
  const [providers, setProviders] = useState<ProviderCard[]>([]);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRoles(null);
    setStatus(null);
    Promise.all([
      fetchAgentModelSettings(backendUrl, agentId),
      fetchModelCatalog(backendUrl, { kind: 'chat' }),
      fetchProviders(backendUrl),
    ])
      .then(([settings, catalog, provs]) => {
        if (cancelled) return;
        setRoles(settings.roles);
        setModels(catalog);
        setProviders(provs);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setStatus(err instanceof ApiError ? err.detail : `Could not reach the backend at ${backendUrl}.`);
      });
    return () => {
      cancelled = true;
    };
  }, [backendUrl, agentId]);

  async function save(role: string, selection: ModelSelection) {
    try {
      const data = await updateAgentModelSettings(backendUrl, agentId, role, selection);
      setRoles(data.roles);
      setStatus('Saved — applies on the next message.');
    } catch (err) {
      setStatus(err instanceof ApiError ? err.detail : 'Failed to save — check the values and try again.');
    }
  }

  async function reset(role: string) {
    try {
      const data = await resetAgentModelSettings(backendUrl, agentId, role);
      setRoles(data.roles);
      setStatus('Reset to the profile default.');
    } catch (err) {
      setStatus(err instanceof ApiError ? err.detail : 'Failed to reset.');
    }
  }

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent aria-describedby={undefined}>
        <SheetHeader>
          <SheetTitle>{agentLabel ?? agentId} — Model Settings</SheetTitle>
        </SheetHeader>

        {status && (
          <p className="rounded-md border border-primary/40 bg-primary/10 p-2 text-xs text-primary">{status}</p>
        )}
        {!roles && !status && <p className="text-sm text-muted-foreground">Loading…</p>}

        <div className="flex flex-col gap-4 overflow-y-auto">
          {(() => {
            const primary = roles?.find((r) => r.role === PRIMARY_ROLE) ?? roles?.[0];
            return primary ? (
              <RoleEditor
                label="Model"
                settings={primary.settings}
                source={primary.source}
                models={models}
                providers={providers}
                onSave={(next) => save(primary.role, next)}
                onReset={() => reset(primary.role)}
              />
            ) : null;
          })()}
        </div>
      </SheetContent>
    </Sheet>
  );
}
