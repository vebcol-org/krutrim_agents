import { Fragment, useEffect, useRef } from 'react';
import type { Message } from '@ag-ui/client';
import { ScrollArea } from '@krutrim_agent/ui';

import type { TraceStep } from '../../hooks/use-agent-stream';
import { AgentActivity } from './agent-activity';
import { AgentMessageBubble } from './agent-message-bubble';

export interface AgentMessageListProps {
  messages: Message[];
  /** Live step / tool-call / reasoning trace for the current turn. */
  trace?: TraceStep[];
  isRunning: boolean;
  error: string | null;
}

/** Auto-scrolls to the bottom whenever `messages` or `trace` changes. Only ever
 * shows `user`/`assistant` turns — a run can also produce `system`/`tool`/
 * `reasoning` messages in the underlying list, not meant for display here; the
 * agent's thinking and tool use surface in the `AgentActivity` block instead. */
export function AgentMessageList({ messages, trace = [], isRunning, error }: AgentMessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, trace]);

  const visible = messages.filter((m) => m.role === 'user' || m.role === 'assistant');
  const lastAssistantIdx = visible.map((m) => m.role).lastIndexOf('assistant');

  return (
    <ScrollArea ref={scrollRef} className="flex-1 px-5 py-4">
      <div className="mx-auto flex max-w-2xl flex-col gap-3">
        {visible.length === 0 && !isRunning && (
          <p className="text-sm text-muted-foreground">Ask this agent something to get started.</p>
        )}
        {visible.map((message, idx) => {
          const isLastAssistant = idx === lastAssistantIdx;
          return (
            <Fragment key={message.id}>
              {isLastAssistant && <AgentActivity trace={trace} isRunning={isRunning} />}
              <AgentMessageBubble message={message} streaming={isLastAssistant && isRunning} />
            </Fragment>
          );
        })}
        {/* No assistant turn yet — show the activity block (or a bare hint) at the end. */}
        {lastAssistantIdx === -1 && trace.length > 0 && <AgentActivity trace={trace} isRunning={isRunning} />}
        {isRunning && lastAssistantIdx === -1 && trace.length === 0 && (
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
