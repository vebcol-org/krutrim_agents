import { useEffect, useRef } from 'react';
import type { Message } from '@ag-ui/client';
import { ScrollArea } from '@krutrim_agent/ui';

import type { ReasoningEntry } from '../../hooks/use-agent-stream';
import { MessageBubble } from './message-bubble';

export interface MessageListProps {
  /** Full conversation (seeded history + live turn) as AG-UI messages — see `useChatStream`. */
  messages: Message[];
  reasoningByMessageId?: Record<string, ReasoningEntry>;
  isLoading: boolean;
  isSending: boolean;
  error: string | null;
}

/** The scrollable chat history. Auto-scrolls to the bottom whenever `messages` changes. */
export function MessageList({ messages, reasoningByMessageId = {}, isLoading, isSending, error }: MessageListProps) {
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
        {visible.length === 0 && !isLoading && (
          <p className="text-sm text-muted-foreground">Ask a question to get started.</p>
        )}
        {isLoading && <p className="font-mono text-xs text-muted-foreground">loading…</p>}
        {visible.map((message, idx) => {
          const isLastAssistant = idx === lastAssistantIdx;
          const reasoning =
            reasoningByMessageId[message.id] ?? (isLastAssistant && isSending ? newestReasoning : undefined);
          return (
            <MessageBubble
              key={message.id}
              message={message}
              reasoning={reasoning}
              streaming={isLastAssistant && isSending}
            />
          );
        })}
        {isSending && lastAssistantIdx === -1 && (
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
