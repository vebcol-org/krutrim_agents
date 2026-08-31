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

export interface AgentPolicySectionProps {
  sharing: SharingScope;
  onSharingChange: (sharing: SharingScope) => void;
  idleTimeout: string;
  onIdleTimeoutChange: (value: string) => void;
  onSave: () => void;
}

export function AgentPolicySection({
  sharing,
  onSharingChange,
  idleTimeout,
  onIdleTimeoutChange,
  onSave,
}: AgentPolicySectionProps) {
  return (
    <section className="flex flex-col gap-3 rounded-md border border-border p-3">
      <span className="font-mono text-xs uppercase tracking-wide text-primary">Agent</span>
      <Separator />
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="agent-sharing">Sharing policy</Label>
        <Select value={sharing} onValueChange={(v) => onSharingChange(v as SharingScope)}>
          <SelectTrigger id="agent-sharing">
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
          Governs whether this agent&apos;s sessions can reach — or be reached by — sibling agents in
          the same project via the <code>message_agent</code> tool. &quot;project-shared&quot; grants
          it to every project-shared agent in this project; &quot;isolated&quot; (default) grants it
          to none.
        </p>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="agent-idle-timeout">Idle timeout override (seconds)</Label>
        <Input
          id="agent-idle-timeout"
          type="number"
          min={0}
          placeholder="project default"
          value={idleTimeout}
          onChange={(e) => onIdleTimeoutChange(e.target.value)}
        />
      </div>
      <Button size="sm" onClick={onSave}>
        Save agent policy
      </Button>
    </section>
  );
}
