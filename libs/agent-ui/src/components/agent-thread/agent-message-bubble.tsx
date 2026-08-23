import type { Message } from '@ag-ui/client';
import { cn } from '@krutrim_agent/ui';

import { messageText } from '../../hooks/use-agent-chat';

export interface AgentMessageBubbleProps {
  message: Message;
}

export function AgentMessageBubble({ message }: AgentMessageBubbleProps) {
  const text = messageText(message);
  // Skips rendering entirely while a streaming assistant message is still
  // empty (its `content` grows from "" as tokens arrive) — the list's own
  // `isRunning` indicator covers that gap, see `AgentMessageList`.
  if (!text) return null;

  return (
    <div
      className={cn(
        'max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm',
        message.role === 'user' ? 'ml-auto bg-primary text-primary-foreground' : 'bg-secondary text-foreground',
      )}
    >
      {text}
    </div>
  );
}
