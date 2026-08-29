import { useEffect, useState } from 'react';
import type { Message } from '@ag-ui/client';

import { fetchSessionMessages } from '../api/sessions';

/**
 * Loads an **Agent** session's persisted history once, on mount / session
 * switch, so a page refresh doesn't wipe the conversation.
 *
 * The Agent flow (`use-agent-chat.ts`) is a pure live AG-UI stream — unlike the
 * Chat flow it has no store-backed history — so without this the message list
 * starts empty on every reload. `GET /api/sessions/{id}/messages` reads the
 * session's LangGraph checkpoint (for `research` that's the in-sandbox run's
 * checkpoint, synced back on `SandboxRegistry.release`) and reduces it to the
 * visible turns.
 *
 * `loadedSessionId` is the id the returned `messages` actually belong to — the
 * caller gates the `HttpAgent` (memoised on `sessionId`) on
 * `loadedSessionId === sessionId` so it is only built once its seed is ready,
 * and never re-seeded with a stale session's turns.
 */

function toAguiMessage(message: { role: 'user' | 'assistant'; content: string }, index: number): Message {
  return { id: `history-${index}`, role: message.role, content: message.content };
}

export interface UseAgentHistoryResult {
  messages: Message[];
  /** The session id `messages` were loaded for, or `null` before the first load resolves. */
  loadedSessionId: string | null;
  isLoading: boolean;
}

export function useAgentHistory({
  backendUrl,
  sessionId,
}: {
  backendUrl: string;
  sessionId: string | null;
}): UseAgentHistoryResult {
  const [state, setState] = useState<{ sessionId: string | null; messages: Message[] }>({
    sessionId: null,
    messages: [],
  });
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!sessionId) {
      setState({ sessionId: null, messages: [] });
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    setIsLoading(true);
    fetchSessionMessages(backendUrl, sessionId)
      .then((raw) => {
        if (cancelled) return;
        setState({ sessionId, messages: raw.map(toAguiMessage) });
      })
      .catch(() => {
        // A failed load must not wedge the thread — adopt the id with an empty
        // history so the caller's `loadedSessionId === sessionId` gate opens and
        // the user can still start a turn.
        if (!cancelled) setState({ sessionId, messages: [] });
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [backendUrl, sessionId]);

  return { messages: state.messages, loadedSessionId: state.sessionId, isLoading };
}
