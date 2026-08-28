import type { Message } from '@ag-ui/client';

import { messageText, type ReasoningEntry } from '../../hooks/use-agent-stream';
import { ThinkingDisclosure } from './thinking-disclosure';

export interface MessageBubbleProps {
  message: Message;
  reasoning?: ReasoningEntry;
  streaming?: boolean;
}

export function MessageBubble({ message, reasoning, streaming }: MessageBubbleProps) {
  const text = messageText(message);
  if (message.role === 'user') {
    return (
      <div className="ml-auto max-w-[85%] whitespace-pre-wrap rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
        {text}
      </div>
    );
  }

  if (!text && !reasoning) return null;

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
