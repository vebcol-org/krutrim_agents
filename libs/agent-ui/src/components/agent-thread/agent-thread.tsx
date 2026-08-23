import { useState } from 'react';
import type { Message } from '@ag-ui/client';
import type { Agent } from '@krutrim_agent/shared-types';
import { Badge, Button } from '@krutrim_agent/ui';
import { BookOpen, Settings } from 'lucide-react';

import { SandboxStatus } from '../sandbox-status';
import { Composer } from '../agent/composer';
import { RagUploadSheet } from '../agent/rag-upload-sheet';
import { AgentMessageList } from './agent-message-list';

/** Profiles with a `rag_tool` wired in — gates the "Add research information"
 * trigger. Update this if RAG ingestion becomes available to other profiles. */
const RAG_ENABLED_AGENT_KEYS = new Set(['research']);

export interface AgentThreadProps {
  backendUrl: string;
  agent: Agent;
  sessionId: string | null;
  onOpenSandboxSettings: () => void;
  /** Lifted to `AgentLayout` (via `useAgentChat`) so `OutputPanel`, a sibling,
   * can derive its canvas payload from the same live message list — see
   * `utils/render-payload.ts`. */
  messages: Message[];
  isRunning: boolean;
  error: string | null;
  sendMessage: (text: string) => void;
}

/** Live counterpart to `../agent/chat-thread.tsx`, for the `Agent` (AG-UI/streaming) flow
 * rather than the plain `chat` flow — same header/list/composer shape, driven by props
 * instead of its own `useAgentChat` call (see `AgentThreadProps`). */
export function AgentThread({
  backendUrl,
  agent,
  sessionId,
  onOpenSandboxSettings,
  messages,
  isRunning,
  error,
  sendMessage,
}: AgentThreadProps) {
  const [ragSheetOpen, setRagSheetOpen] = useState(false);
  const ragEnabled = RAG_ENABLED_AGENT_KEYS.has(agent.agent_key);

  return (
    <main className="flex min-w-0 flex-1 flex-col bg-background">
      <header className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <Badge variant="accent">Agent</Badge>
          <span className="truncate font-mono text-xs text-muted-foreground">{agent.display_name}</span>
          <SandboxStatus backendUrl={backendUrl} ownerId={sessionId} />
        </div>
        <div className="flex items-center gap-1">
          {ragEnabled && (
            <Button
              variant="ghost"
              size="icon"
              aria-label="Add research information"
              disabled={!sessionId}
              onClick={() => setRagSheetOpen(true)}
            >
              <BookOpen className="size-4" />
            </Button>
          )}
          <Button variant="ghost" size="icon" aria-label="Sandbox settings" onClick={onOpenSandboxSettings}>
            <Settings className="size-4" />
          </Button>
        </div>
      </header>

      <AgentMessageList messages={messages} isRunning={isRunning} error={error} />

      <Composer disabled={isRunning || !sessionId} onSend={sendMessage} />

      {ragSheetOpen && sessionId && (
        <RagUploadSheet backendUrl={backendUrl} sessionId={sessionId} onClose={() => setRagSheetOpen(false)} />
      )}
    </main>
  );
}
