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
}

export interface UseAgentChatResult {
  messages: Message[];
  trace: TraceStep[];
  reasoningByMessageId: Record<string, ReasoningEntry>;
  runStats: RunStats | null;
  isRunning: boolean;
  error: string | null;
  sendMessage: (text: string) => void;
}

export function useAgentChat({ backendUrl, agentId, sessionId }: UseAgentChatOptions): UseAgentChatResult {
  const url = useMemo(
    () => (sessionId ? `${backendUrl}/agents/${agentId}?session_id=${encodeURIComponent(sessionId)}` : null),
    [backendUrl, agentId, sessionId],
  );
  return useAgentStream({ url, threadId: sessionId });
}
