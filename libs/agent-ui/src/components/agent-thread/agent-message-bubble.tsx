import type { Message } from '@ag-ui/client';

import { messageText } from '../../hooks/use-agent-stream';

export interface AgentMessageBubbleProps {
  message: Message;
}

/** One **user** turn. Assistant text is not rendered in the middle column at
 * all — it goes to the output panel. */
export function AgentMessageBubble({ message }: AgentMessageBubbleProps) {
  if (message.role !== 'user') return null;
  const text = messageText(message);
  if (!text) return null;
  return (
    <div className="ml-auto max-w-[85%] whitespace-pre-wrap rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
      {text}
    </div>
  );
}
