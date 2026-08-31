import { useState } from 'react';
import type { Message } from '@ag-ui/client';
import type { Chat, SessionInfo } from '@krutrim_agent/shared-types';
import { Badge, Button } from '@krutrim_agent/ui';
import { Settings } from 'lucide-react';

import type { ReasoningEntry } from '../../hooks/use-agent-stream';
import { useSessionFiles } from '../../hooks/use-session-files';
import { Composer } from './composer';
import { FilesButton, FilesDrawer } from './files-drawer';
import { MessageList } from './message-list';
import { SessionSwitcher } from './session-switcher';

export interface ChatThreadProps {
  backendUrl: string;
  activeChat: Chat | null;
  sessions: SessionInfo[];
  /** Where the switcher points (drives the `<Select>`). */
  activeSessionId: string | null;
  /** The session the thread + files actually belong to — lags `activeSessionId` mid-switch. */
  historySessionId: string | null;
  /** Full conversation (seeded history + live turn) — see `useChatStream`. */
  messages: Message[];
  reasoningByMessageId: Record<string, ReasoningEntry>;
  /** History (re)load in flight. */
  isLoading: boolean;
  /** A turn is streaming. */
  isSending: boolean;
  error: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewSession: () => void;
  onSend: (text: string) => void;
  onOpenSandboxSettings: () => void;
  /** Creates the chat's session on demand so a file can be attached before the first message. */
  onEnsureSession: () => Promise<string | null>;
}

export function ChatThread({
  backendUrl,
  activeChat,
  sessions,
  activeSessionId,
  historySessionId,
  messages,
  reasoningByMessageId,
  isLoading,
  isSending,
  error,
  onSelectSession,
  onNewSession,
  onSend,
  onOpenSandboxSettings,
  onEnsureSession,
}: ChatThreadProps) {
  // Keyed on `historySessionId` (not `activeSessionId`) so the file list can
  // never belong to a different session than the messages on screen.
  const files = useSessionFiles({ backendUrl, sessionId: historySessionId });
  const [filesOpen, setFilesOpen] = useState(false);
  const activeSession = sessions.find((s) => s.session_id === historySessionId) ?? null;

  return (
    <main className="flex min-w-0 flex-1 flex-col bg-background">
      <header className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <Badge variant="accent">Chat</Badge>
          <span className="truncate font-mono text-xs text-muted-foreground">
            {activeChat?.display_name ?? 'New chat'}
          </span>
        </div>
        {activeChat && (
          <div className="flex items-center gap-1.5">
            <SessionSwitcher
              sessions={sessions}
              activeSessionId={activeSessionId}
              onSelectSession={onSelectSession}
              onNewSession={onNewSession}
              disabled={isLoading || isSending}
            />
            <FilesButton
              count={files.count}
              disabled={!activeSessionId}
              onClick={() => setFilesOpen(true)}
            />
            <Button variant="ghost" size="icon" aria-label="Sandbox settings" onClick={onOpenSandboxSettings}>
              <Settings className="size-4" />
            </Button>
          </div>
        )}
      </header>

      <MessageList
        messages={messages}
        reasoningByMessageId={reasoningByMessageId}
        isLoading={isLoading}
        isSending={isSending}
        error={error}
      />

      <Composer
        disabled={isSending || isLoading || files.isProcessing}
        onSend={onSend}
        backendUrl={backendUrl}
        sessionId={activeSessionId}
        ensureSession={onEnsureSession}
        onAddFiles={files.addFiles}
        onFilesAdded={() => setFilesOpen(true)}
      />

      <FilesDrawer
        backendUrl={backendUrl}
        files={files}
        session={activeSession}
        open={filesOpen}
        onOpenChange={setFilesOpen}
      />
    </main>
  );
}
