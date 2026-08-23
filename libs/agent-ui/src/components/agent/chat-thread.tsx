import type { Chat, ChatApiMessage, SessionInfo } from '@krutrim_agent/shared-types';
import { Badge, Button } from '@krutrim_agent/ui';
import { Settings } from 'lucide-react';

import { SandboxStatus } from '../sandbox-status';
import { Composer } from './composer';
import { MessageList } from './message-list';
import { SessionSwitcher } from './session-switcher';

export interface ChatThreadProps {
  backendUrl: string;
  activeChat: Chat | null;
  sessions: SessionInfo[];
  activeSessionId: string | null;
  messages: ChatApiMessage[];
  isLoading: boolean;
  isSending: boolean;
  error: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewSession: () => void;
  onSend: (text: string) => void;
  onOpenSandboxSettings: () => void;
}

export function ChatThread({
  backendUrl,
  activeChat,
  sessions,
  activeSessionId,
  messages,
  isLoading,
  isSending,
  error,
  onSelectSession,
  onNewSession,
  onSend,
  onOpenSandboxSettings,
}: ChatThreadProps) {
  return (
    <main className="flex min-w-0 flex-1 flex-col bg-background">
      <header className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex min-w-0 items-center gap-2">
          <Badge variant="accent">Chat</Badge>
          <span className="truncate font-mono text-xs text-muted-foreground">
            {activeChat?.display_name ?? 'New chat'}
          </span>
          <SandboxStatus backendUrl={backendUrl} ownerId={activeSessionId} />
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
            <Button variant="ghost" size="icon" aria-label="Sandbox settings" onClick={onOpenSandboxSettings}>
              <Settings className="size-4" />
            </Button>
          </div>
        )}
      </header>

      <MessageList messages={messages} isLoading={isLoading} isSending={isSending} error={error} />

      <Composer disabled={isSending} onSend={onSend} />
    </main>
  );
}
