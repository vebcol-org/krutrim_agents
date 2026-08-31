import { useEffect, useMemo, useRef, useState } from 'react';
import { HttpAgent, randomUUID, type Message, type RunAgentParameters } from '@ag-ui/client';

import type { TraceStep } from '../screens/types';

/**
 * The shared AG-UI streaming client. Both the Agent flow
 * (`POST /agents/{agentId}`, see `use-agent-chat.ts`) and the plain Chat flow
 * (`POST /api/chat`, see `use-chat-stream.ts`) are the same protocol over the
 * same `@ag-ui/client` `HttpAgent` — this hook is that shared core.
 *
 * Extra views on top of `@ag-ui/client`'s message accumulation:
 *
 * - `trace` — low-level step / tool-call / reasoning event stream.
 * - `reasoningByMessageId` — streamed "thinking" text keyed by AG-UI message id.
 * - `interrupted` — the run was stopped by the user / the connection dropped.
 *   That is NOT an error. Aborting the SSE cancels the server run, which folds
 *   the partial assistant turn into the session checkpoint backend-side (see
 *   `krutrim_agent_agui.translator._persist_partial_turn`), so it comes back on
 *   the next history load — there is no client-side persistence here.
 */

export type { TraceStep };

export interface ReasoningEntry {
  text: string;
  running: boolean;
  startedAt: number;
  endedAt?: number;
}

export interface RunStats {
  elapsedMs?: number;
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
}

export interface UseAgentStreamOptions {
  url: string | null;
  interruptUrl?: string | null;
  threadId: string | null;
  initialMessages?: Message[];
  forwardedProps?: Record<string, unknown>;
  onCustomEvent?: (name: string, value: unknown) => void;
  onRunFinished?: () => void;
}

export interface UseAgentStreamResult {
  messages: Message[];
  trace: TraceStep[];
  reasoningByMessageId: Record<string, ReasoningEntry>;
  runStats: RunStats | null;
  isRunning: boolean;
  error: string | null;
  /** Stopped by the user / dropped connection — show a neutral notice, not an error. */
  interrupted: boolean;
  sendMessage: (text: string) => void;
  stop: () => void;
}

export function messageText(message: Message): string {
  if (typeof message.content === 'string') return message.content;
  if (Array.isArray(message.content)) {
    return message.content
      .map((part) => ('type' in part && part.type === 'text' ? part.text : ''))
      .join('');
  }
  return '';
}

const isAbortError = (msg: string) => /abort|BodyStreamBuffer|cancell?ed|network error/i.test(msg);

function upsertTrace(
  prev: TraceStep[],
  id: string,
  update: Partial<TraceStep> & Pick<TraceStep, 'kind' | 'label' | 'status'>,
): TraceStep[] {
  const existingIndex = prev.findIndex((step) => step.id === id);
  if (existingIndex === -1) {
    return [...prev, { id, timestamp: Date.now(), ...update }];
  }
  const next = [...prev];
  next[existingIndex] = { ...next[existingIndex], ...update };
  return next;
}

function findLastStarted(steps: TraceStep[], kind: TraceStep['kind'], label?: string): TraceStep | undefined {
  for (let i = steps.length - 1; i >= 0; i--) {
    const step = steps[i];
    if (step.kind === kind && step.status === 'started' && (label === undefined || step.label === label)) {
      return step;
    }
  }
  return undefined;
}

export function useAgentStream({
  url,
  interruptUrl,
  threadId,
  initialMessages,
  forwardedProps,
  onCustomEvent,
  onRunFinished,
}: UseAgentStreamOptions): UseAgentStreamResult {
  const [messages, setMessages] = useState<Message[]>([]);
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [reasoningByMessageId, setReasoningByMessageId] = useState<Record<string, ReasoningEntry>>({});
  const [runStats, setRunStats] = useState<RunStats | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [interrupted, setInterrupted] = useState(false);

  const callbacksRef = useRef({ onCustomEvent, onRunFinished });
  callbacksRef.current = { onCustomEvent, onRunFinished };
  const forwardedPropsRef = useRef(forwardedProps);
  forwardedPropsRef.current = forwardedProps;
  const initialMessagesRef = useRef(initialMessages);
  initialMessagesRef.current = initialMessages;

  const activeReasoningIdRef = useRef<string | null>(null);
  const abortedByUserRef = useRef(false);

  const agent = useMemo(() => {
    if (!url) return null;
    return new HttpAgent({
      url,
      threadId: threadId ?? undefined,
      initialMessages: initialMessagesRef.current?.length ? [...initialMessagesRef.current] : undefined,
    });
  }, [url, threadId]);

  useEffect(() => {
    setMessages(agent?.messages ?? []);
    setTrace([]);
    setReasoningByMessageId({});
    setRunStats(null);
    setError(null);
    setInterrupted(false);
    activeReasoningIdRef.current = null;
    abortedByUserRef.current = false;
    if (!agent) return;

    const bumpReasoning = (id: string | null, patch: (entry: ReasoningEntry) => ReasoningEntry) => {
      const key = id ?? activeReasoningIdRef.current;
      if (!key) return;
      setReasoningByMessageId((prev) => {
        const current = prev[key] ?? { text: '', running: true, startedAt: Date.now() };
        return { ...prev, [key]: patch(current) };
      });
    };

    const { unsubscribe } = agent.subscribe({
      onMessagesChanged: ({ messages: updated }) => setMessages([...updated]),
      onRunErrorEvent: ({ event }) => {
        if (abortedByUserRef.current || isAbortError(event.message)) setInterrupted(true);
        else setError(event.message);
      },
      onRunFinishedEvent: () => {
        setInterrupted(false);
        callbacksRef.current.onRunFinished?.();
      },
      onCustomEvent: ({ event }) => {
        callbacksRef.current.onCustomEvent?.(event.name, event.value);
        if (event.name === 'run_stats' && event.value && typeof event.value === 'object') {
          const v = event.value as { elapsed_ms?: number };
          setRunStats((prev) => ({ ...prev, elapsedMs: v.elapsed_ms }));
        }
        if (event.name === 'token_usage' && event.value && typeof event.value === 'object') {
          const v = event.value as { input_tokens?: number; output_tokens?: number; total_tokens?: number };
          setRunStats((prev) => ({
            ...prev,
            inputTokens: v.input_tokens,
            outputTokens: v.output_tokens,
            totalTokens: v.total_tokens,
          }));
        }
      },

      onReasoningMessageStartEvent: ({ event }) => {
        activeReasoningIdRef.current = event.messageId;
        bumpReasoning(event.messageId, () => ({ text: '', running: true, startedAt: Date.now() }));
        setTrace((prev) => [
          ...prev,
          { id: `reasoning:${event.messageId}`, kind: 'reasoning', label: 'Thinking', status: 'started', timestamp: Date.now() },
        ]);
      },
      onReasoningMessageContentEvent: ({ event, reasoningMessageBuffer }) => {
        bumpReasoning(event.messageId, (entry) => ({ ...entry, text: reasoningMessageBuffer, running: true }));
        setTrace((prev) => {
          const started = findLastStarted(prev, 'reasoning');
          return started
            ? upsertTrace(prev, started.id, { kind: 'reasoning', label: 'Thinking', status: 'started', detail: reasoningMessageBuffer })
            : prev;
        });
      },
      onReasoningMessageEndEvent: ({ event, reasoningMessageBuffer }) => {
        bumpReasoning(event.messageId, (entry) => ({
          ...entry,
          text: reasoningMessageBuffer || entry.text,
          running: false,
          endedAt: Date.now(),
        }));
        activeReasoningIdRef.current = null;
        setTrace((prev) => {
          const started = findLastStarted(prev, 'reasoning');
          return started
            ? upsertTrace(prev, started.id, { kind: 'reasoning', label: 'Thinking', status: 'finished', detail: reasoningMessageBuffer })
            : prev;
        });
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
        setTrace((prev) => upsertTrace(prev, event.toolCallId, { kind: 'tool_call', label: event.toolCallName, status: 'started' }));
      },
      onToolCallArgsEvent: ({ event, toolCallBuffer, toolCallName }) => {
        setTrace((prev) =>
          upsertTrace(prev, event.toolCallId, { kind: 'tool_call', label: toolCallName, status: 'started', detail: toolCallBuffer }),
        );
      },
      onToolCallEndEvent: ({ event, toolCallName, toolCallArgs }) => {
        setTrace((prev) =>
          upsertTrace(prev, event.toolCallId, {
            kind: 'tool_call',
            label: toolCallName,
            status: 'finished',
            detail: JSON.stringify(toolCallArgs),
          }),
        );
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
    setReasoningByMessageId({});
    setRunStats(null);
    setIsRunning(true);
    setError(null);
    setInterrupted(false);
    abortedByUserRef.current = false;

    const params: RunAgentParameters = {};
    if (forwardedPropsRef.current) params.forwardedProps = forwardedPropsRef.current;

    agent
      .runAgent(params)
      .catch((err: unknown) => {
        const msg = err instanceof Error ? err.message : 'Failed to run agent.';
        if (abortedByUserRef.current || isAbortError(msg)) setInterrupted(true);
        else setError(msg);
      })
      .finally(() => setIsRunning(false));
  }

  function stop() {
    if (!isRunning) return;
    abortedByUserRef.current = true;
    // Aborting the SSE disconnects the server run — the backend folds the
    // partial assistant turn into the checkpoint on cancel.
    agent?.abortRun();
    setIsRunning(false);
    setInterrupted(true);
    if (interruptUrl) {
      void fetch(interruptUrl, { method: 'POST' }).catch(() => undefined);
    }
  }

  return {
    messages,
    trace,
    reasoningByMessageId,
    runStats,
    isRunning,
    error,
    interrupted,
    sendMessage,
    stop,
  };
}
