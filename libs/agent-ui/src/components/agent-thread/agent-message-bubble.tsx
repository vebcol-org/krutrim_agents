import type { Message } from '@ag-ui/client';

import { messageText } from '../../hooks/use-agent-stream';

export interface AgentMessageBubbleProps {
  message: Message;
  /** Show a blinking caret after the text (last assistant message, mid-run). */
  streaming?: boolean;
}

/** One user/assistant turn. Reasoning and tool activity are no longer rendered
 * here — they live in the `AgentActivity` block above the assistant answer. */
export function AgentMessageBubble({ message, streaming }: AgentMessageBubbleProps) {
  const text = messageText(message);
  const isUser = message.role === 'user';

  // An assistant message whose content is still "" — the list's own running
  // indicator / the activity block cover the gap.
  if (!text) return null;

  if (isUser) {
    return (
      <div className="ml-auto max-w-[85%] whitespace-pre-wrap rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
        {text}
      </div>
    );
  }

  return (
    <div className="flex max-w-[85%] flex-col items-start">
      <div className="whitespace-pre-wrap rounded-lg bg-secondary px-3 py-2 text-sm text-foreground">
        {text}
        {streaming && <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-current align-text-bottom" />}
      </div>
    </div>
  );
}
