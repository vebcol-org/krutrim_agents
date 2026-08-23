import { useState } from 'react';
import { PROVIDER_KEYS, type ModelSettings, type ProviderKey } from '@krutrim_agent/shared-types';
import {
  Button,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
} from '@krutrim_agent/ui';

export interface RoleEditorProps {
  role: string;
  settings: ModelSettings;
  onSave: (next: ModelSettings) => void;
}

export function RoleEditor({ role, settings, onSave }: RoleEditorProps) {
  const [provider, setProvider] = useState<ProviderKey>(settings.provider);
  const [model, setModel] = useState(settings.model);
  const [temperature, setTemperature] = useState(settings.temperature);

  return (
    <div className="flex flex-col gap-3 rounded-md border border-border p-3">
      <span className="font-mono text-xs uppercase tracking-wide text-primary">{role}</span>
      <Separator />
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${role}-provider`}>Provider</Label>
        <Select value={provider} onValueChange={(v) => setProvider(v as ProviderKey)}>
          <SelectTrigger id={`${role}-provider`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PROVIDER_KEYS.map((p) => (
              <SelectItem key={p} value={p}>
                {p}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${role}-model`}>Model</Label>
        <Input id={`${role}-model`} value={model} onChange={(e) => setModel(e.target.value)} spellCheck={false} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${role}-temperature`}>Temperature</Label>
        <Input
          id={`${role}-temperature`}
          type="number"
          min={0}
          max={2}
          step={0.1}
          value={temperature}
          onChange={(e) => setTemperature(Number(e.target.value))}
        />
      </div>
      <Button size="sm" onClick={() => onSave({ ...settings, provider, model, temperature } as ModelSettings)}>
        Save
      </Button>
    </div>
  );
}
