import type { SharingScope } from '@krutrim_agent/shared-types';
import { SHARING_SCOPES } from '@krutrim_agent/shared-types';
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

export interface ChatPolicySectionProps {
  sharing: SharingScope;
  onSharingChange: (sharing: SharingScope) => void;
  idleTimeout: string;
  onIdleTimeoutChange: (value: string) => void;
  onSave: () => void;
  /** Whether this chat currently has a project — the policy is stored regardless, but only
   * takes effect once one is set (see `Chat`'s docstring in `shared-types`). */
  hasProject: boolean;
}

export function ChatPolicySection({
  sharing,
  onSharingChange,
  idleTimeout,
  onIdleTimeoutChange,
  onSave,
  hasProject,
}: ChatPolicySectionProps) {
  return (
    <section className="flex flex-col gap-3 rounded-md border border-border p-3">
      <span className="font-mono text-xs uppercase tracking-wide text-primary">Chat</span>
      <Separator />
      {!hasProject && (
        <p className="rounded-md border border-border bg-secondary/50 p-2 text-xs text-muted-foreground">
          This chat isn&apos;t in a project yet — these settings are saved but have no effect until
          it&apos;s moved into one.
        </p>
      )}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="chat-sharing">Sharing policy</Label>
        <Select value={sharing} onValueChange={(v) => onSharingChange(v as SharingScope)}>
          <SelectTrigger id="chat-sharing">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SHARING_SCOPES.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          Chats can&apos;t message agents yet (see the hierarchy plan) — this only matters once that
          lands.
        </p>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="chat-idle-timeout">Idle timeout override (seconds)</Label>
        <Input
          id="chat-idle-timeout"
          type="number"
          min={0}
          placeholder="project default"
          value={idleTimeout}
          onChange={(e) => onIdleTimeoutChange(e.target.value)}
        />
      </div>
      <Button size="sm" onClick={onSave}>
        Save chat policy
      </Button>
    </section>
  );
}
