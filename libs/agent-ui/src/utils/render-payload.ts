import type { Message } from '@ag-ui/client';

import { messageText } from '../hooks/use-agent-stream';
import { getTurnSplitter } from '../screens/registry';
import type { AssistantTurnView } from '../screens/types';

/**
 * Bridges the shell's `Message[]` to a screen's turn splitter (`screens/`):
 * find the latest assistant turn, flatten it to text, and let that screen's
 * splitter divide it into `narration` (middle "work log" column) and `output`
 * (the output panel).
 *
 * All screen-specific knowledge — e.g. `research`'s `===FINAL_REPORT===` marker —
 * lives in `screens/<key>/`, not here; the shell just picks the turn and routes
 * the two halves.
 */
export function deriveAssistantTurn(
  messages: Message[],
  screenKey: string | null,
  agentDisplayName: string,
  opts: { finished: boolean },
): AssistantTurnView {
  const split = getTurnSplitter(screenKey);
  for (let i = messages.length - 1; i >= 0; i--) {
    // Skip tool-call-only assistant turns (no prose) — the real answer is an
    // earlier/later turn with text; the tool calls surface in the trace panel.
    if (messages[i].role !== 'assistant' || !messageText(messages[i]).trim()) continue;
    return split(messageText(messages[i]), { finished: opts.finished, title: agentDisplayName });
  }
  return { narration: '', output: null };
}
