import { useEffect, useRef, useState } from 'react';
import type { Message } from '@ag-ui/client';
import type { Agent, SessionInfo } from '@krutrim_agent/shared-types';
import { Badge, Button } from '@krutrim_agent/ui';
import { Settings } from 'lucide-react';

import { fetchSession } from '../../api';
import type { ReasoningEntry } from '../../hooks/use-agent-stream';
import { useBlurStatusTitle } from '../../hooks/use-blur-status-title';
import { useSessionFiles } from '../../hooks/use-session-files';
import { FilesButton, FilesDrawer } from '../agent/files-drawer';
import { Composer } from '../agent/composer';
import { SandboxStatus } from '../sandbox-status';
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
   * can derive its canvas payload from the same live message list. */
  messages: Message[];
  reasoningByMessageId: Record<string, ReasoningEntry>;
  isRunning: boolean;
  error: string | null;
  sendMessage: (text: string) => void;
  /** Cancels the in-flight turn (aborts the SSE stream and asks the server to
   * interrupt an in-sandbox run). */
  onStop: () => void;
}

/** Live counterpart to `../agent/chat-thread.tsx`, for the `Agent` (AG-UI/streaming) flow. */
export function AgentThread({
  backendUrl,
  agent,
  sessionId,
  onOpenSandboxSettings,
  messages,
  reasoningByMessageId,
  isRunning,
  error,
  sendMessage,
  onStop,
}: AgentThreadProps) {
  const files = useSessionFiles({ backendUrl, sessionId });
  const [filesOpen, setFilesOpen] = useState(false);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [justCompletedUpload, setJustCompletedUpload] = useState(false);
  const wasProcessingRef = useRef(false);

  useEffect(() => {
    if (!sessionId) {
      setSession(null);
      return;
    }
    let live = true;
    fetchSession(backendUrl, sessionId)
      .then((s) => {
        if (live) setSession(s);
      })
      .catch(() => {
        /* non-critical — the drawer just omits the start time */
      });
    return () => {
      live = false;
    };
  }, [backendUrl, sessionId]);

  useEffect(() => {
    const wasProcessing = wasProcessingRef.current;
    wasProcessingRef.current = files.isProcessing;
    if (wasProcessing && !files.isProcessing) {
      setJustCompletedUpload(true);
      const t = window.setTimeout(() => setJustCompletedUpload(false), UPLOAD_COMPLETE_TITLE_MS);
      return () => window.clearTimeout(t);
    }
    return undefined;
  }, [files.isProcessing]);

  useBlurStatusTitle(
    files.isProcessing || justCompletedUpload,
    files.isProcessing ? '● Embedding…' : justCompletedUpload ? '✓ Embedding complete' : null,
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
          <FilesButton count={files.count} disabled={!sessionId} onClick={() => setFilesOpen(true)} />
          <Button variant="ghost" size="icon" aria-label="Sandbox settings" onClick={onOpenSandboxSettings}>
            <Settings className="size-4" />
          </Button>
        </div>
      </header>

      <AgentMessageList
        messages={messages}
        reasoningByMessageId={reasoningByMessageId}
        isRunning={isRunning}
        error={error}
      />

      <Composer
        disabled={isRunning || !sessionId || files.isProcessing}
        isRunning={isRunning}
        onStop={onStop}
        onSend={sendMessage}
        backendUrl={backendUrl}
        sessionId={sessionId}
        onAddFiles={files.addFiles}
        onFilesAdded={() => setFilesOpen(true)}
      />

      <FilesDrawer
        backendUrl={backendUrl}
        files={files}
        session={session}
        open={filesOpen}
        onOpenChange={setFilesOpen}
      />
    </main>
  );
}
