import { useRef, useState } from 'react';
import type { Message } from '@ag-ui/client';
import type { Agent } from '@krutrim_agent/shared-types';
import { Badge, Button } from '@krutrim_agent/ui';
import { Settings } from 'lucide-react';

import { useBlurStatusTitle } from '../../hooks/use-blur-status-title';
import { SandboxStatus } from '../sandbox-status';
import { Composer } from '../agent/composer';
import { AgentMessageList } from './agent-message-list';

/** How long the "✓ Embedding complete" tab-title status stays up after the
 * last upload finishes, before reverting to the plain session title. */
const UPLOAD_COMPLETE_TITLE_MS = 10_000;

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
  const [uploading, setUploading] = useState(false);
  const [justCompletedUpload, setJustCompletedUpload] = useState(false);
  const wasUploadingRef = useRef(false);

  function handleUploadingChange(active: boolean) {
    if (wasUploadingRef.current && !active) {
      setJustCompletedUpload(true);
      window.setTimeout(() => setJustCompletedUpload(false), UPLOAD_COMPLETE_TITLE_MS);
    }
    wasUploadingRef.current = active;
    setUploading(active);
  }

  useBlurStatusTitle(
    uploading || justCompletedUpload,
    uploading ? '● Embedding…' : justCompletedUpload ? '✓ Embedding complete' : null,
  );

  return (
    <main className="flex min-w-0 flex-1 flex-col bg-background">
      <header className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <Badge variant="accent">Agent</Badge>
          <span className="truncate font-mono text-xs text-muted-foreground">{agent.display_name}</span>
          <SandboxStatus backendUrl={backendUrl} ownerId={sessionId} />
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" aria-label="Sandbox settings" onClick={onOpenSandboxSettings}>
            <Settings className="size-4" />
          </Button>
        </div>
      </header>

      <AgentMessageList messages={messages} isRunning={isRunning} error={error} />

      <Composer
        disabled={isRunning || !sessionId}
        onSend={sendMessage}
        backendUrl={backendUrl}
        sessionId={sessionId}
        onUploadingChange={handleUploadingChange}
      />
    </main>
  );
}
