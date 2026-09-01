import type { SessionInfo } from '@krutrim_agent/shared-types';
import { Button, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@krutrim_agent/ui';
import { Plus } from 'lucide-react';

export interface SessionSwitcherProps {
  /** Oldest → newest (as `chat-slice` keeps them). */
  sessions: SessionInfo[];
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewSession: () => void;
  disabled: boolean;
}

function shortStamp(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function SessionSwitcher({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  disabled,
}: SessionSwitcherProps) {
  // "Session N" is numbered by creation order (N stays put as later sessions are
  // added), but the list is shown newest-first.
  const numbered = sessions.map((session, idx) => ({ session, label: `Session ${idx + 1}`, stamp: shortStamp(session.created_at) }));
  const newestFirst = [...numbered].reverse();

  return (
    <div className="flex items-center gap-1.5">
      {newestFirst.length > 0 && (
        <Select value={activeSessionId ?? undefined} disabled={disabled} onValueChange={onSelectSession}>
          <SelectTrigger aria-label="Switch session" className="h-8 w-auto gap-1.5">
            <SelectValue placeholder="New session…" />
          </SelectTrigger>
          <SelectContent>
            {newestFirst.map(({ session, label, stamp }) => (
              <SelectItem key={session.session_id} value={session.session_id}>
                <span className="flex items-baseline gap-2">
                  <span>{label}</span>
                  {stamp && <span className="text-xs text-muted-foreground">{stamp}</span>}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      <Button variant="ghost" size="icon" onClick={onNewSession} aria-label="New session" disabled={disabled}>
        <Plus className="size-4" />
      </Button>
    </div>
  );
}
