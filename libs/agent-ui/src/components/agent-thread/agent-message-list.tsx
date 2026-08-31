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
  /** The latest assistant turn's working narration, as decided by the agent's
   * turn splitter (`deriveAssistantTurn`). `''` for agents with no work-log
   * concept. The finished output goes to the output panel instead. */
  narration?: string;
  isRunning: boolean;
  error: string | null;
  /** Run stopped by the user / dropped connection — shown as a neutral notice. */
  interrupted?: boolean;
}

/**
 * The middle column is the **work log**, not the answer: user turns, the
 * `AgentActivity` block (thinking / tool calls / steps), and the assistant's
 * running `narration`. The finished output is never rendered here — it goes to
 * the output panel (`OutputPanel`, via the agent's turn splitter — see
 * `deriveAssistantTurn`). Auto-scrolls on new messages/trace.
 */
export function AgentMessageList({
  messages,
  trace = [],
  narration,
  isRunning,
  error,
  interrupted,
}: AgentMessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, trace, narration]);

  const userTurns = messages.filter((m) => m.role === 'user');
  const hasAnyTurn = messages.some((m) => m.role === 'user' || m.role === 'assistant');

  return (
    <ScrollArea ref={scrollRef} className="flex-1 px-5 py-4">
      <div className="mx-auto flex max-w-2xl flex-col gap-3">
        {!hasAnyTurn && !isRunning && (
          <p className="text-sm text-muted-foreground">Ask this agent something to get started.</p>
        )}
        {userTurns.map((message, idx) => (
          <Fragment key={message.id}>
            <AgentMessageBubble message={message} />
            {idx === userTurns.length - 1 && (
              <>
                {(trace.length > 0 || isRunning) && (
                  <AgentActivity trace={trace} isRunning={isRunning} />
                )}
                {narration && (
                  <div className="w-full max-w-[85%] whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
                    {narration}
                  </div>
                )}
              </>
            )}
          </Fragment>
        ))}
        {isRunning && trace.length === 0 && !narration && (
          <p className="font-mono text-xs text-muted-foreground">thinking…</p>
        )}
        {interrupted && !error && (
          <p className="rounded-md border border-border bg-muted/40 p-2 text-xs text-muted-foreground">
            You stopped the response. Ask a follow-up or send a new message to continue.
          </p>
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
