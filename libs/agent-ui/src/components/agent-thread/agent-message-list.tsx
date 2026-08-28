import { useEffect, useRef } from 'react';
import type { Message } from '@ag-ui/client';
import { ScrollArea } from '@krutrim_agent/ui';

import type { ReasoningEntry } from '../../hooks/use-agent-stream';
import { AgentMessageBubble } from './agent-message-bubble';

export interface AgentMessageListProps {
  messages: Message[];
  reasoningByMessageId?: Record<string, ReasoningEntry>;
  isRunning: boolean;
  error: string | null;
}

/** Auto-scrolls to the bottom whenever `messages` changes. Only ever shows
 * `user`/`assistant` turns — a run can also produce `system`/`tool`/`reasoning`
 * messages in the underlying list, not meant for display here. */
export function AgentMessageList({ messages, reasoningByMessageId = {}, isRunning, error }: AgentMessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, reasoningByMessageId]);

  const visible = messages.filter((m) => m.role === 'user' || m.role === 'assistant');
  const lastAssistantIdx = visible.map((m) => m.role).lastIndexOf('assistant');
  const newestReasoning = Object.values(reasoningByMessageId).at(-1);

  return (
    <ScrollArea ref={scrollRef} className="flex-1 px-5 py-4">
      <div className="mx-auto flex max-w-2xl flex-col gap-3">
        {visible.length === 0 && !isRunning && (
          <p className="text-sm text-muted-foreground">Ask this agent something to get started.</p>
        )}
        {visible.map((message, idx) => {
          const isLastAssistant = idx === lastAssistantIdx;
          const reasoning =
            reasoningByMessageId[message.id] ?? (isLastAssistant && isRunning ? newestReasoning : undefined);
          return (
            <AgentMessageBubble
              key={message.id}
              message={message}
              reasoning={reasoning}
              streaming={isLastAssistant && isRunning}
            />
          );
        })}
        {isRunning && lastAssistantIdx === -1 && (
          <p className="font-mono text-xs text-muted-foreground">thinking…</p>
        )}
        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
            {error}
          </p>
        )}
      </div>
    </ScrollArea>
  );
}
