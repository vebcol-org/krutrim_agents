import type { Message } from '@ag-ui/client';
import type { RenderContentPayload } from '@krutrim_agent/shared-types';

import { messageText } from '../hooks/use-agent-chat';

/**
 * Derives the canvas payload from a live AG-UI message list — the last
 * assistant message's text, wrapped as `kind: 'markdown'`. Research (and
 * every other agent profile today) always produces markdown per
 * `backend/harness/prompts/format/markdown/markdown-spec.md` — tables,
 * math, and images are all embedded *within* the markdown, not a separate
 * `chart`/`news` kind — so this adapter hardcodes `'markdown'` rather than
 * inspecting content to guess a kind.
 *
 * Returns `null` while there's no assistant output yet, so `OutputPanel`
 * can keep showing its existing placeholder state unchanged.
 */
export function deriveRenderPayload(messages: Message[], agentDisplayName: string): RenderContentPayload | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message.role !== 'assistant') continue;
    const text = messageText(message);
    if (!text) continue;
    return { kind: 'markdown', title: agentDisplayName, content: text };
  }
  return null;
}
