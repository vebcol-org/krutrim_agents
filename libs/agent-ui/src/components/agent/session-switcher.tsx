import type { SessionInfo } from '@krutrim_agent/shared-types';
import { Button, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@krutrim_agent/ui';
import { Plus } from 'lucide-react';

export interface SessionSwitcherProps {
  sessions: SessionInfo[];
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewSession: () => void;
  disabled: boolean;
}

export function SessionSwitcher({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  disabled,
}: SessionSwitcherProps) {
  return (
    <div className="flex items-center gap-1.5">
      {sessions.length > 0 && (
        <Select value={activeSessionId ?? undefined} disabled={disabled} onValueChange={onSelectSession}>
          <SelectTrigger aria-label="Switch session" className="h-8 w-auto gap-1.5">
            <SelectValue placeholder="New session…" />
          </SelectTrigger>
          <SelectContent>
            {sessions.map((session, idx) => (
              <SelectItem key={session.session_id} value={session.session_id}>
                Session {idx + 1}
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
