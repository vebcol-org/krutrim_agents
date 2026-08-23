import { useEffect, useState } from 'react';
import type { ModelSettings, ProviderSettingsByRole } from '@krutrim_agent/shared-types';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@krutrim_agent/ui';

import { fetchProviderSettings, updateProviderSettings } from '../../api';
import { ApiError } from '../../utils/http-client';
import { RoleEditor } from './role-editor';

export interface SettingsPanelProps {
  agentKey: string;
  backendUrl: string;
  onClose: () => void;
}

export function SettingsPanel({ agentKey, backendUrl, onClose }: SettingsPanelProps) {
  const [settings, setSettings] = useState<ProviderSettingsByRole | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setSettings(null);
    setStatus(null);
    fetchProviderSettings(backendUrl, agentKey)
      .then((data) => {
        if (!cancelled) setSettings(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setStatus(err instanceof ApiError ? err.detail : `Could not reach the backend at ${backendUrl}.`);
      });
    return () => {
      cancelled = true;
    };
  }, [backendUrl, agentKey]);

  async function save(role: string, next: ModelSettings) {
    try {
      const data = await updateProviderSettings(backendUrl, agentKey, role, next);
      setSettings((prev) => (prev ? { ...prev, [role]: data.settings } : prev));
      setStatus(data.note);
    } catch (err) {
      setStatus(err instanceof ApiError ? err.detail : 'Failed to save — check the values and try again.');
    }
  }

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent aria-describedby={undefined}>
        <SheetHeader>
          <SheetTitle>{agentKey} — Provider Settings</SheetTitle>
        </SheetHeader>

        {status && (
          <p className="rounded-md border border-primary/40 bg-primary/10 p-2 text-xs text-primary">{status}</p>
        )}
        {!settings && !status && <p className="text-sm text-muted-foreground">Loading…</p>}

        <div className="flex flex-col gap-4 overflow-y-auto">
          {settings &&
            Object.keys(settings).map((role) => (
              <RoleEditor key={role} role={role} settings={settings[role]} onSave={(next) => save(role, next)} />
            ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}
