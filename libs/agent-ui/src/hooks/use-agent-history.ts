import { useEffect, useState } from 'react';
import type { Message } from '@ag-ui/client';
import type { ChatApiMessage } from '@krutrim_agent/shared-types';

import { fetchSessionMessages } from '../api/sessions';
import type { TraceStep } from './use-agent-stream';

/**
 * Loads an **Agent** session's persisted history once, on mount / session
 * switch, so a page refresh doesn't wipe the conversation.
 *
 * The Agent flow (`use-agent-chat.ts`) is a pure live AG-UI stream — unlike the
 * Chat flow it has no store-backed history — so without this the message list
 * starts empty on every reload. `GET /api/sessions/{id}/messages` reads the
 * session's LangGraph checkpoint and returns the visible turns plus the tool
 * calls each made; this hook turns that into the two things the shell needs:
 *
 * - `messages` — user + non-empty assistant turns, to seed the `HttpAgent`;
 * - `trace` — the tool calls, rebuilt as `TraceStep[]` so the work-log panel
 *   (`AgentActivity`) is populated on reload, not just during a live run.
 *
 * `loadedSessionId` is the id the returned data actually belongs to — the
 * caller gates the `HttpAgent` (memoised on `sessionId`) on
 * `loadedSessionId === sessionId` so it is only built once its seed is ready,
 * and never re-seeded with a stale session's turns.
 */

function toAguiMessage(message: ChatApiMessage, index: number): Message {
  return { id: `history-${index}`, role: message.role, content: message.content };
}

/** Rebuild the activity trace from the tool calls the checkpoint recorded.
 * Steps / reasoning aren't persisted, so only `tool_call` rows come back. */
function reconstructTrace(raw: ChatApiMessage[]): TraceStep[] {
  const steps: TraceStep[] = [];
  let i = 0;
  for (const message of raw) {
    for (const call of message.tool_calls ?? []) {
      steps.push({
        id: call.id || `history-tc-${i}`,
        kind: 'tool_call',
        label: call.name,
        detail: call.result != null && call.result !== '' ? `${call.args}\n\n→ ${call.result}` : call.args,
        status: 'finished',
        timestamp: i,
      });
      i += 1;
    }
  }
  return steps;
}

export interface UseAgentHistoryResult {
  messages: Message[];
  /** The session id `messages` were loaded for, or `null` before the first load resolves. */
  loadedSessionId: string | null;
  /** Tool calls from the checkpoint, as trace steps — feeds `AgentActivity` on reload. */
  trace: TraceStep[];
  /** The last persisted turn is an assistant turn that was stopped mid-generation
   * (`ChatApiMessage.interrupted`). Its text is a partial work log, not a report —
   * `AgentLayout` uses this to keep it out of the output panel after a reload. */
  lastAssistantInterrupted: boolean;
  isLoading: boolean;
}

export function useAgentHistory({
  backendUrl,
  sessionId,
}: {
  backendUrl: string;
  sessionId: string | null;
}): UseAgentHistoryResult {
  const [state, setState] = useState<{
    sessionId: string | null;
    messages: Message[];
    trace: TraceStep[];
    lastAssistantInterrupted: boolean;
  }>({ sessionId: null, messages: [], trace: [], lastAssistantInterrupted: false });
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!sessionId) {
      setState({ sessionId: null, messages: [], trace: [], lastAssistantInterrupted: false });
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    fetchSessionMessages(backendUrl, sessionId)
      .then((raw) => {
        if (cancelled) return;
        const last = raw[raw.length - 1];
        setState({
          sessionId,
          // Skip empty (tool-call-only) assistant turns in the seed — the tool
          // calls live in `trace`; only turns with prose belong in the thread.
          messages: raw
            .filter((m) => m.role === 'user' || m.content.trim().length > 0)
            .map(toAguiMessage),
          trace: reconstructTrace(raw),
          lastAssistantInterrupted: last?.role === 'assistant' && last.interrupted === true,
        });
      })
      .catch(() => {
        // A failed load must not wedge the thread — adopt the id with an empty
        // history so the caller's `loadedSessionId === sessionId` gate opens and
        // the user can still start a turn.
        if (!cancelled) setState({ sessionId, messages: [], trace: [], lastAssistantInterrupted: false });
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [backendUrl, sessionId]);

  return {
    messages: state.messages,
    loadedSessionId: state.sessionId,
    trace: state.trace,
    lastAssistantInterrupted: state.lastAssistantInterrupted,
    isLoading,
  };
}
