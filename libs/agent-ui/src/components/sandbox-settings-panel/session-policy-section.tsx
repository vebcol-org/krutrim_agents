import type { SessionInfo, SharingScope } from '@krutrim_agent/shared-types';
import { SHARING_SCOPES } from '@krutrim_agent/shared-types';
import { Button, Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue, Separator } from '@krutrim_agent/ui';

export interface SessionPolicySectionProps {
  sharing: SharingScope;
  onSharingChange: (sharing: SharingScope) => void;
  attachTo: string;
  onAttachToChange: (sessionId: string) => void;
  /** Every other session in this project — candidates for the attach/link pickers. */
  attachCandidates: SessionInfo[];
  linked: string[];
  onLinkedChange: (linked: string[]) => void;
  onSave: () => void;
}

export function SessionPolicySection({
  sharing,
  onSharingChange,
  attachTo,
  onAttachToChange,
  attachCandidates,
  linked,
  onLinkedChange,
  onSave,
}: SessionPolicySectionProps) {
  return (
    <section className="flex flex-col gap-3 rounded-md border border-border p-3">
      <span className="font-mono text-xs uppercase tracking-wide text-primary">This session</span>
      <Separator />
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="session-sharing">Sharing override</Label>
        <Select value={sharing} onValueChange={(v) => onSharingChange(v as SharingScope)}>
          <SelectTrigger id="session-sharing">
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
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="attach-to">Reuse another session&apos;s container</Label>
        <Select value={attachTo || undefined} onValueChange={onAttachToChange}>
          <SelectTrigger id="attach-to">
            <SelectValue placeholder="Not attached" />
          </SelectTrigger>
          <SelectContent>
            {attachCandidates.map((s, idx) => (
              <SelectItem key={s.session_id} value={s.session_id}>
                Session {idx + 1}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          Runs this session&apos;s agent inside the chosen session&apos;s exact container instead of its own.
          Cannot be undone from this panel once set.
        </p>
      </div>

      {sharing === 'session-shared' && (
        <div className="flex flex-col gap-1.5">
          <Label>Link sessions for agent messaging</Label>
          <div className="flex flex-col gap-1">
            {attachCandidates.length === 0 && (
              <p className="text-xs text-muted-foreground">No other sessions in this project yet.</p>
            )}
            {attachCandidates.map((s, idx) => (
              <label key={s.session_id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={linked.includes(s.session_id)}
                  onChange={(e) =>
                    onLinkedChange(
                      e.target.checked ? [...linked, s.session_id] : linked.filter((id) => id !== s.session_id),
                    )
                  }
                />
                Session {idx + 1}
              </label>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            Both sides must link each other before the message_agent tool becomes eligible between them.
          </p>
        </div>
      )}

      <Button size="sm" onClick={onSave}>
        Save session policy
      </Button>
    </section>
  );
}
