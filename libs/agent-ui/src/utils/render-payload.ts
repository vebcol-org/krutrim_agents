import type { Message } from '@ag-ui/client';
import { getAgentTurnSplitter, type AssistantTurnView } from '@krutrim_agent/agent-renderers';

import { messageText } from '../hooks/use-agent-stream';

/**
 * Bridges the shell's `Message[]` to the per-agent turn splitter in
 * `@krutrim_agent/agent-renderers`: find the latest assistant turn, flatten it
 * to text, and let that agent's splitter divide it into `narration` (middle
 * "work log" column) and `output` (the output panel).
 *
 * All agent-specific knowledge — e.g. `research`'s `===FINAL_REPORT===` marker —
 * lives in the renderer package, not here; the shell just picks the turn and
 * routes the two halves.
 */
export function deriveAssistantTurn(
  messages: Message[],
  agentKey: string | null,
  agentDisplayName: string,
  opts: { finished: boolean },
): AssistantTurnView {
  const split = getAgentTurnSplitter(agentKey);
  for (let i = messages.length - 1; i >= 0; i--) {
    // Skip tool-call-only assistant turns (no prose) — the real answer is an
    // earlier/later turn with text; the tool calls surface in the trace panel.
    if (messages[i].role !== 'assistant' || !messageText(messages[i]).trim()) continue;
    return split(messageText(messages[i]), { finished: opts.finished, title: agentDisplayName });
  }
  return { narration: '', output: null };
}
