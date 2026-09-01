import { useState } from 'react';
import type { Agent, Chat, SessionInfo, SharingScope } from '@krutrim_agent/shared-types';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@krutrim_agent/ui';

import { updateAgentSandboxPolicy, updateChatSandboxPolicy, updateSessionSandboxPolicy } from '../../../api';
import { ApiError } from '../../../utils/http-client';
import { AgentPolicySection } from './agent-policy-section';
import { ChatPolicySection } from './chat-policy-section';
import { SessionPolicySection } from './session-policy-section';

/** What this panel is currently editing policy for — driven by whatever's selected in the
 * sidebar tree (see `agent-layout.tsx`). A bare `Project` isn't a selectable target here; only
 * its children are (see the hierarchy plan — the tree selects agents/chats, not projects). */
export type SandboxSettingsTarget =
  | { kind: 'chat'; chat: Chat }
  | { kind: 'agent'; agent: Agent; projectId: string };

export interface SandboxSettingsPanelProps {
  backendUrl: string;
  target: SandboxSettingsTarget;
  /** The currently active session, or `null` if none is selected yet. */
  session: SessionInfo | null;
  /** Every other session under the same owner — candidates for attach/link pickers. */
  siblingSessions: SessionInfo[];
  onClose: () => void;
}

/**
 * Sandbox policy editor: `Agent`- or `Chat`-level sharing/idle-timeout
 * (`AgentPolicySection`/`ChatPolicySection`, chosen by `target.kind`), and
 * — when a session is active — that session's sharing override, explicit
 * container reuse (`attached_to_session_id`), and cross-agent-messaging
 * peer links (`linked_session_ids`) (`SessionPolicySection`). Saves
 * directly via `PUT .../sandbox-policy` through
 * `../../api/{agents,chats,sessions}.ts` — it does not push the update back
 * into the parent's tree data, so the rest of the UI won't reflect a change
 * until the next reload. A real limitation for this first pass, not
 * silently worked around.
 */
export function SandboxSettingsPanel({ backendUrl, target, session, siblingSessions, onClose }: SandboxSettingsPanelProps) {
  const initialSharing = target.kind === 'agent' ? (target.agent.sandbox_sharing ?? 'isolated') : (target.chat.sandbox_sharing ?? 'isolated');
  const initialIdleTimeout =
    target.kind === 'agent'
      ? (target.agent.sandbox_idle_timeout_seconds?.toString() ?? '')
      : (target.chat.sandbox_idle_timeout_seconds?.toString() ?? '');

  const [sharing, setSharing] = useState<SharingScope>(initialSharing);
  const [idleTimeout, setIdleTimeout] = useState(initialIdleTimeout);
  const [sessionSharing, setSessionSharing] = useState<SharingScope>(session?.sandbox_sharing ?? 'isolated');
  const [attachTo, setAttachTo] = useState(session?.attached_to_session_id ?? '');
  const [linked, setLinked] = useState<string[]>(session?.linked_session_ids ?? []);
  const [status, setStatus] = useState<string | null>(null);

  const attachCandidates = siblingSessions.filter((s) => s.session_id !== session?.session_id);

  async function saveOwnerPolicy() {
    try {
      const idleTimeoutSeconds = idleTimeout.trim() === '' ? null : Number(idleTimeout);
      if (target.kind === 'agent') {
        await updateAgentSandboxPolicy(backendUrl, target.projectId, target.agent.agent_id, {
          sharing,
          idle_timeout_seconds: idleTimeoutSeconds,
        });
        setStatus('Agent sandbox policy saved.');
      } else {
        await updateChatSandboxPolicy(backendUrl, target.chat.chat_id, { sharing, idle_timeout_seconds: idleTimeoutSeconds });
        setStatus('Chat sandbox policy saved.');
      }
    } catch (err) {
      setStatus(err instanceof ApiError ? err.detail : 'Failed to save policy.');
    }
  }

  async function saveSessionPolicy() {
    if (!session) return;
    try {
      await updateSessionSandboxPolicy(backendUrl, session.session_id, {
        sharing: sessionSharing,
        attached_to_session_id: attachTo || null,
        linked_session_ids: sessionSharing === 'session-shared' ? linked : undefined,
      });
      setStatus('Session sandbox policy saved.');
    } catch (err) {
      setStatus(err instanceof ApiError ? err.detail : 'Failed to save session policy.');
    }
  }

  return (
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent aria-describedby={undefined}>
        <SheetHeader>
          <SheetTitle>Sandbox Settings</SheetTitle>
        </SheetHeader>

        {status && (
          <p className="rounded-md border border-primary/40 bg-primary/10 p-2 text-xs text-primary">{status}</p>
        )}

        <div className="flex flex-col gap-4 overflow-y-auto">
          {target.kind === 'agent' ? (
            <AgentPolicySection
              sharing={sharing}
              onSharingChange={setSharing}
              idleTimeout={idleTimeout}
              onIdleTimeoutChange={setIdleTimeout}
              onSave={saveOwnerPolicy}
            />
          ) : (
            <ChatPolicySection
              sharing={sharing}
              onSharingChange={setSharing}
              idleTimeout={idleTimeout}
              onIdleTimeoutChange={setIdleTimeout}
              onSave={saveOwnerPolicy}
              hasProject={target.chat.project_id != null}
            />
          )}

          {session && (
            <SessionPolicySection
              sharing={sessionSharing}
              onSharingChange={setSessionSharing}
              attachTo={attachTo}
              onAttachToChange={setAttachTo}
              attachCandidates={attachCandidates}
              linked={linked}
              onLinkedChange={setLinked}
              onSave={saveSessionPolicy}
            />
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
