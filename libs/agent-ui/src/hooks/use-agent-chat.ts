import { useEffect, useMemo, useState } from 'react';
import { HttpAgent, randomUUID, type Message } from '@ag-ui/client';
import type { TraceStep } from '@krutrim_agent/agent-renderers';

/**
 * The live AG-UI streaming client for one Agent session — `POST
 * /agents/{agentId}` (see `backend/docs/services/krutrim_agent_backend.md`).
 * `@ag-ui/client`'s `HttpAgent` does the actual SSE parsing/message
 * accumulation; this hook just bridges it into React state.
 *
 * `threadId` is set to `sessionId` deliberately: each session already gets
 * its own dedicated LangGraph checkpoint file server-side
 * (`sessions/{id}/langgraph_checkpoint.sqlite`), and reusing the same
 * `threadId` on every run against that session is what makes the backend
 * resume the right conversation thread within that file — confirmed
 * empirically (a fresh `HttpAgent` instance, no local history, correctly
 * recalled context from a prior run against the same session).
 *
 * `onMessagesChanged` (not `onEvent`/`onTextMessageContentEvent` directly)
 * is the subscription hook used here — also confirmed empirically to fire
 * on every message-list mutation, including the incremental content growth
 * of a streaming assistant reply, which is exactly "live token-by-token
 * updates" from this hook's point of view.
 *
 * `trace` accumulates a second, independent view of the same run — step/
 * tool-call/reasoning events from the richer low-level `@ag-ui/core` event
 * stream, which `onMessagesChanged` alone never surfaces (tool/system
 * messages are intentionally absent from `messages`, see
 * `agent-message-list.tsx`). Built for the research renderer's "agent
 * thinking" trace panel, but generic enough for any profile.
 */

export interface UseAgentChatOptions {
  backendUrl: string;
  agentId: string;
  /** No session yet (still being created) → the hook stays inert; `sendMessage` no-ops. */
  sessionId: string | null;
}

export type { TraceStep };

export interface UseAgentChatResult {
  messages: Message[];
  trace: TraceStep[];
  isRunning: boolean;
  error: string | null;
  sendMessage: (text: string) => void;
}

/** Best-effort plain-text extraction — assistant replies from this platform's agents are
 * always plain text (no multimodal output), so this only needs to handle the shapes that
 * can actually occur: a string, absent (a tool-calls-only assistant message), or (in
 * principle, for a user message) a content-part array, which is never actually produced
 * here since `sendMessage` below only ever sends plain strings. */
export function messageText(message: Message): string {
  if (typeof message.content === 'string') return message.content;
  if (Array.isArray(message.content)) {
    return message.content
      .map((part) => ('type' in part && part.type === 'text' ? part.text : ''))
      .join('');
  }
  return '';
}

function upsertTrace(prev: TraceStep[], id: string, update: Partial<TraceStep> & Pick<TraceStep, 'kind' | 'label' | 'status'>): TraceStep[] {
  const existingIndex = prev.findIndex((step) => step.id === id);
  if (existingIndex === -1) {
    return [...prev, { id, timestamp: Date.now(), ...update }];
  }
  const next = [...prev];
  next[existingIndex] = { ...next[existingIndex], ...update };
  return next;
}

/** Finds the most recent *started* step of `kind`/`label` — used to pair a
 * finish/content event back to its start event when the underlying AG-UI
 * event carries no shared id of its own (step events only give `stepName`;
 * reasoning events give none at all, hence the reasoning-only id below). */
function findLastStarted(steps: TraceStep[], kind: TraceStep['kind'], label?: string): TraceStep | undefined {
  for (let i = steps.length - 1; i >= 0; i--) {
    const step = steps[i];
    if (step.kind === kind && step.status === 'started' && (label === undefined || step.label === label)) {
      return step;
    }
  }
  return undefined;
}

export function useAgentChat({ backendUrl, agentId, sessionId }: UseAgentChatOptions): UseAgentChatResult {
  const [messages, setMessages] = useState<Message[]>([]);
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const agent = useMemo(() => {
    if (!sessionId) return null;
    return new HttpAgent({
      url: `${backendUrl}/agents/${agentId}?session_id=${encodeURIComponent(sessionId)}`,
      threadId: sessionId,
    });
  }, [backendUrl, agentId, sessionId]);

  useEffect(() => {
    setMessages(agent?.messages ?? []);
    setTrace([]);
    setError(null);
    if (!agent) return;

    const { unsubscribe } = agent.subscribe({
      onMessagesChanged: ({ messages: updated }) => {
        setMessages([...updated]);
      },
      onRunErrorEvent: ({ event }) => {
        setError(event.message);
      },
      onStepStartedEvent: ({ event }) => {
        setTrace((prev) => [
          ...prev,
          { id: `step:${event.stepName}:${Date.now()}`, kind: 'step', label: event.stepName, status: 'started', timestamp: Date.now() },
        ]);
      },
      onStepFinishedEvent: ({ event }) => {
        setTrace((prev) => {
          const started = findLastStarted(prev, 'step', event.stepName);
          return started ? upsertTrace(prev, started.id, { kind: 'step', label: event.stepName, status: 'finished' }) : prev;
        });
      },
      onToolCallStartEvent: ({ event }) => {
        setTrace((prev) =>
          upsertTrace(prev, event.toolCallId, { kind: 'tool_call', label: event.toolCallName, status: 'started' })
        );
      },
      onToolCallArgsEvent: ({ event, toolCallBuffer, toolCallName }) => {
        setTrace((prev) =>
          upsertTrace(prev, event.toolCallId, { kind: 'tool_call', label: toolCallName, status: 'started', detail: toolCallBuffer })
        );
      },
      onToolCallEndEvent: ({ event, toolCallName, toolCallArgs }) => {
        setTrace((prev) =>
          upsertTrace(prev, event.toolCallId, {
            kind: 'tool_call',
            label: toolCallName,
            status: 'finished',
            detail: JSON.stringify(toolCallArgs),
          })
        );
      },
      onReasoningMessageStartEvent: () => {
        setTrace((prev) => [
          ...prev,
          { id: `reasoning:${Date.now()}`, kind: 'reasoning', label: 'Thinking', status: 'started', timestamp: Date.now() },
        ]);
      },
      onReasoningMessageContentEvent: ({ reasoningMessageBuffer }) => {
        setTrace((prev) => {
          const started = findLastStarted(prev, 'reasoning');
          return started
            ? upsertTrace(prev, started.id, { kind: 'reasoning', label: 'Thinking', status: 'started', detail: reasoningMessageBuffer })
            : prev;
        });
      },
      onReasoningMessageEndEvent: ({ reasoningMessageBuffer }) => {
        setTrace((prev) => {
          const started = findLastStarted(prev, 'reasoning');
          return started
            ? upsertTrace(prev, started.id, { kind: 'reasoning', label: 'Thinking', status: 'finished', detail: reasoningMessageBuffer })
            : prev;
        });
      },
    });
    return unsubscribe;
  }, [agent]);

  function sendMessage(text: string) {
    const trimmed = text.trim();
    if (!trimmed || !agent || isRunning) return;

    agent.addMessage({ id: randomUUID(), role: 'user', content: trimmed });
    setMessages([...agent.messages]);
    setTrace([]);
    setIsRunning(true);
    setError(null);

    agent
      .runAgent()
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Failed to run agent.');
      })
      .finally(() => {
        setIsRunning(false);
      });
  }

  return { messages, trace, isRunning, error, sendMessage };
}
