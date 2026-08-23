import { useEffect, useRef } from 'react';
import type { ChatApiMessage } from '@krutrim_agent/shared-types';
import { ScrollArea } from '@krutrim_agent/ui';

import { MessageBubble } from './message-bubble';

export interface MessageListProps {
  messages: ChatApiMessage[];
  isLoading: boolean;
  isSending: boolean;
  error: string | null;
}

/** The scrollable message history. Auto-scrolls to the bottom whenever `messages` changes. */
export function MessageList({ messages, isLoading, isSending, error }: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  return (
    <ScrollArea ref={scrollRef} className="flex-1 px-5 py-4">
      <div className="mx-auto flex max-w-2xl flex-col gap-3">
        {messages.length === 0 && !isLoading && (
          <p className="text-sm text-muted-foreground">Ask a question to get started.</p>
        )}
        {isLoading && <p className="font-mono text-xs text-muted-foreground">loading…</p>}
        {messages.map((message, idx) => (
          <MessageBubble key={idx} message={message} />
        ))}
        {isSending && <p className="font-mono text-xs text-muted-foreground">thinking…</p>}
        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
            {error}
          </p>
        )}
      </div>
    </ScrollArea>
  );
}
