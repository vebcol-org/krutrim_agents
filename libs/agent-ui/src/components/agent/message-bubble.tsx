import type { ChatApiMessage } from '@krutrim_agent/shared-types';
import { cn } from '@krutrim_agent/ui';

export interface MessageBubbleProps {
  message: ChatApiMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  return (
    <div
      className={cn(
        'max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm',
        message.role === 'user' ? 'ml-auto bg-primary text-primary-foreground' : 'bg-secondary text-foreground',
      )}
    >
      {message.content}
    </div>
  );
}
