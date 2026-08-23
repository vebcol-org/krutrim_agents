import { useEffect, useRef } from 'react';
import type { Message } from '@ag-ui/client';
import { ScrollArea } from '@krutrim_agent/ui';

import { AgentMessageBubble } from './agent-message-bubble';

export interface AgentMessageListProps {
  messages: Message[];
  isRunning: boolean;
  error: string | null;
}

/** Auto-scrolls to the bottom whenever `messages` changes — same behavior as the plain-chat
 * `MessageList` (`../agent/message-list.tsx`), kept as a separate component rather than shared
 * since the two operate on genuinely different message shapes (`ChatApiMessage` vs. AG-UI's
 * `Message`). Only ever shows `user`/`assistant` turns — a real run can also produce
 * `system`/`tool`/`developer` messages in the underlying list, not meant for display here. */
export function AgentMessageList({ messages, isRunning, error }: AgentMessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const visible = messages.filter((m) => m.role === 'user' || m.role === 'assistant');

  return (
    <ScrollArea ref={scrollRef} className="flex-1 px-5 py-4">
      <div className="mx-auto flex max-w-2xl flex-col gap-3">
        {visible.length === 0 && !isRunning && (
          <p className="text-sm text-muted-foreground">Ask this agent something to get started.</p>
        )}
        {visible.map((message) => (
          <AgentMessageBubble key={message.id} message={message} />
        ))}
        {isRunning && <p className="font-mono text-xs text-muted-foreground">thinking…</p>}
        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
            {error}
          </p>
        )}
      </div>
    </ScrollArea>
  );
}
