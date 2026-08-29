import { useMemo } from 'react';
import type { Message } from '@ag-ui/client';

import {
  useAgentStream,
  type ReasoningEntry,
  type RunStats,
  type TraceStep,
} from './use-agent-stream';

/**
 * The live AG-UI streaming client for one **Agent** session — `POST
 * /agents/{agentId}` (see `backend/docs/services/krutrim_agent_backend.md`).
 * A thin adapter over the shared `useAgentStream` core (`./use-agent-stream.ts`)
 * that just builds the run URL from `agentId` + `sessionId`. `messageText` and
 * the `TraceStep`/`ReasoningEntry`/`RunStats` types live in `use-agent-stream`.
 *
 * `threadId` is set to `sessionId` deliberately: each session has its own
 * dedicated LangGraph checkpoint file server-side, and reusing the same
 * `threadId` on every run is what makes the backend resume the right thread.
 */

export interface UseAgentChatOptions {
  backendUrl: string;
  agentId: string;
  /** No session yet (still being created) → the hook stays inert; `sendMessage` no-ops. */
  sessionId: string | null;
  /** Prior turns to seed the conversation with on mount / session switch, so a
   * page refresh doesn't drop the history (see `useAgentHistory`). Read once at
   * `HttpAgent` build time — pass it already resolved for `sessionId`, and only
   * flip `sessionId` non-null once it is (the hook is memoised on `sessionId`). */
  initialMessages?: Message[];
}

export interface UseAgentChatResult {
  messages: Message[];
  trace: TraceStep[];
  reasoningByMessageId: Record<string, ReasoningEntry>;
  runStats: RunStats | null;
  isRunning: boolean;
  error: string | null;
  sendMessage: (text: string) => void;
  stop: () => void;
}

export function useAgentChat({
  backendUrl,
  agentId,
  sessionId,
  initialMessages,
}: UseAgentChatOptions): UseAgentChatResult {
  const url = useMemo(
    () => (sessionId ? `${backendUrl}/agents/${agentId}?session_id=${encodeURIComponent(sessionId)}` : null),
    [backendUrl, agentId, sessionId],
  );
  const interruptUrl = useMemo(
    () =>
      sessionId
        ? `${backendUrl}/agents/${agentId}/interrupt?session_id=${encodeURIComponent(sessionId)}`
        : null,
    [backendUrl, agentId, sessionId],
  );
  return useAgentStream({ url, interruptUrl, threadId: sessionId, initialMessages });
}
