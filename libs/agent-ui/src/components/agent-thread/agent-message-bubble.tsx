import type { Message } from '@ag-ui/client';

import { messageText, type ReasoningEntry } from '../../hooks/use-agent-stream';
import { ThinkingDisclosure } from '../agent/thinking-disclosure';

export interface AgentMessageBubbleProps {
  message: Message;
  /** Streamed "thinking" for this message (keyed by id upstream), if any. */
  reasoning?: ReasoningEntry;
  /** Show a blinking caret after the text (last assistant message, mid-run). */
  streaming?: boolean;
}

export function AgentMessageBubble({ message, reasoning, streaming }: AgentMessageBubbleProps) {
  const text = messageText(message);
  const isUser = message.role === 'user';

  // Nothing to show yet: an assistant message whose content is still "" and that
  // has no reasoning either — the list's own running indicator covers the gap.
  if (!text && !reasoning) return null;

  if (isUser) {
    return (
      <div className="ml-auto max-w-[85%] whitespace-pre-wrap rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
        {text}
      </div>
    );
  }

  return (
    <div className="flex max-w-[85%] flex-col items-start">
      {reasoning && <ThinkingDisclosure reasoning={reasoning} />}
      {text && (
        <div className="whitespace-pre-wrap rounded-lg bg-secondary px-3 py-2 text-sm text-foreground">
          {text}
          {streaming && <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-current align-text-bottom" />}
        </div>
      )}
    </div>
  );
}
