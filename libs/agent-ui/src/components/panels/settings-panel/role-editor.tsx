import { useMemo, useState } from 'react';
import type {
  ModelCard,
  ModelSelection,
  ModelSettings,
  ModelSettingsSource,
  ProviderCard,
} from '@krutrim_agent/shared-types';
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

const CUSTOM = '__custom__';

const SOURCE_LABEL: Record<ModelSettingsSource, string> = {
  session: 'session override',
  agent: 'set on this agent',
  profile: 'profile default',
};

export interface RoleEditorProps {
  /** Heading shown above the editor (e.g. "Model"). */
  label: string;
  settings: ModelSettings;
  source: ModelSettingsSource;
  models: ModelCard[];
  providers: ProviderCard[];
  onSave: (next: ModelSelection) => void;
  onReset: () => void;
}

export function RoleEditor({ label, settings, source, models, providers, onSave, onReset }: RoleEditorProps) {
  const slug = label.toLowerCase().replace(/\s+/g, '-');
  const [provider, setProvider] = useState<string>(settings.provider);
  const modelInCatalog = models.some((m) => m.id === settings.model && m.provider === settings.provider);
  const [modelChoice, setModelChoice] = useState<string>(modelInCatalog ? settings.model : CUSTOM);
  const [customModel, setCustomModel] = useState<string>(modelInCatalog ? '' : settings.model);
  const [temperature, setTemperature] = useState<number>(settings.temperature);

  const providerModels = useMemo(
    () => models.filter((m) => m.provider === provider),
    [models, provider],
  );

  const isCustom = modelChoice === CUSTOM;
  const model = isCustom ? customModel.trim() : modelChoice;
  const providerKeys = providers.length > 0 ? providers.map((p) => p.key) : [settings.provider];

  return (
    <div className="flex flex-col gap-3 rounded-md border border-border p-3">
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs uppercase tracking-wide text-primary">{label}</span>
        <span className="text-[10px] text-muted-foreground">{SOURCE_LABEL[source]}</span>
      </div>
      <Separator />

      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${slug}-provider`}>Provider</Label>
        <Select
          value={provider}
          onValueChange={(v) => {
            setProvider(v);
            setModelChoice(CUSTOM);
          }}
        >
          <SelectTrigger id={`${slug}-provider`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {providerKeys.map((p) => {
              const card = providers.find((x) => x.key === p);
              const note = card?.available === false ? ' (not installed)' : card?.configured === false ? ' (no API key)' : '';
              return (
                <SelectItem key={p} value={p}>
                  {(card?.label ?? p) + note}
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${slug}-model`}>Model</Label>
        <Select value={modelChoice} onValueChange={setModelChoice}>
          <SelectTrigger id={`${slug}-model`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {providerModels.map((m) => (
              <SelectItem key={m.id} value={m.id}>
                {m.label}
              </SelectItem>
            ))}
            <SelectItem value={CUSTOM}>Custom…</SelectItem>
          </SelectContent>
        </Select>
        {isCustom && (
          <Input
            aria-label={`${slug} custom model id`}
            placeholder="vendor/model-id"
            value={customModel}
            onChange={(e) => setCustomModel(e.target.value)}
            spellCheck={false}
          />
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${slug}-temperature`}>Temperature</Label>
        <Input
          id={`${slug}-temperature`}
          type="number"
          min={0}
          max={2}
          step={0.1}
          value={temperature}
          onChange={(e) => setTemperature(Number(e.target.value))}
        />
      </div>

      <div className="flex gap-2">
        <Button
          size="sm"
          disabled={!model}
          onClick={() => onSave({ provider, model, temperature, custom: isCustom })}
        >
          Save
        </Button>
        <Button size="sm" variant="ghost" disabled={source === 'profile'} onClick={onReset}>
          Reset
        </Button>
      </div>
    </div>
  );
}
