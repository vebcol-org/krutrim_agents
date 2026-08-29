import { useEffect, useMemo, useRef, useState } from 'react';
import { HttpAgent, randomUUID, type Message, type RunAgentParameters } from '@ag-ui/client';
import type { TraceStep } from '@krutrim_agent/agent-renderers';

/**
 * The shared AG-UI streaming client. Both the Agent flow
 * (`POST /agents/{agentId}`, see `use-agent-chat.ts`) and the plain Chat flow
 * (`POST /api/chat`, see `use-chat-stream.ts`) are the same protocol over the
 * same `@ag-ui/client` `HttpAgent` — this hook is that shared core, pointed at
 * whatever `url` the caller passes.
 *
 * On top of `@ag-ui/client`'s own message accumulation it tracks two extra
 * views of a run:
 *
 * - `trace` — the low-level step / tool-call / reasoning event stream, for the
 *   research renderer's "agent activity" panel (unchanged from the old
 *   `useAgentChat`).
 * - `reasoningByMessageId` — the streamed "thinking" text, keyed by the AG-UI
 *   message id it belongs to (the backend emits the reasoning message and the
 *   assistant text message under the *same* id), so a message bubble can render
 *   its own thinking disclosure. `running` flips false on
 *   `REASONING_MESSAGE_END`.
 */

export type { TraceStep };

export interface ReasoningEntry {
  text: string;
  running: boolean;
  startedAt: number;
  endedAt?: number;
}

/** Latest values from the translator's `run_stats` / `token_usage` CUSTOM events. */
export interface RunStats {
  elapsedMs?: number;
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
}

export interface UseAgentStreamOptions {
  /** Full run endpoint URL. `null` → the hook stays inert and `sendMessage` no-ops. */
  url: string | null;
  /** Optional POST endpoint that cancels an in-flight server-side run (in-sandbox
   * agents). `stop()` still aborts the local SSE stream when this is absent. */
  interruptUrl?: string | null;
  /** AG-UI `threadId`; reused across runs so the backend resumes the right checkpoint.
   * Also the identity the internal `HttpAgent` is memoised on — change it to start a
   * fresh conversation (a new `HttpAgent`, re-seeded from `initialMessages`). */
  threadId: string | null;
  /** History to seed a freshly-built `HttpAgent` with (read once, at build time — a
   * changing array does not rebuild the agent). Used by the chat flow so a mid-session
   * rebuild keeps prior turns. */
  initialMessages?: Message[];
  /** Extra fields merged into every run's `forwardedProps` (chat identity, etc.). */
  forwardedProps?: Record<string, unknown>;
  /** Fired for every `CUSTOM` AG-UI event (e.g. `chat_session`, `run_stats`). */
  onCustomEvent?: (name: string, value: unknown) => void;
  /** Fired once when a run's `RUN_FINISHED` arrives. */
  onRunFinished?: () => void;
}

export interface UseAgentStreamResult {
  messages: Message[];
  trace: TraceStep[];
  reasoningByMessageId: Record<string, ReasoningEntry>;
  runStats: RunStats | null;
  isRunning: boolean;
  error: string | null;
  sendMessage: (text: string) => void;
  /** Abort the current run: cancels the local SSE stream and, if `interruptUrl`
   * was provided, asks the server to cancel the in-sandbox turn too. */
  stop: () => void;
}

/** Best-effort plain-text extraction from an AG-UI `Message` (assistant replies here are
 * always plain text; user messages are plain strings from `sendMessage`). */
export function messageText(message: Message): string {
  if (typeof message.content === 'string') return message.content;
  if (Array.isArray(message.content)) {
    return message.content
      .map((part) => ('type' in part && part.type === 'text' ? part.text : ''))
      .join('');
  }
  return '';
}

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

/** Finds the most recent *started* step of `kind`/`label` — pairs a finish/content
 * event back to its start when the underlying AG-UI event carries no shared id. */
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

  // Kept in refs so a changing callback identity / forwardedProps object doesn't
  // tear down and rebuild the `HttpAgent` (which would drop an in-flight stream).
  const callbacksRef = useRef({ onCustomEvent, onRunFinished });
  callbacksRef.current = { onCustomEvent, onRunFinished };
  const forwardedPropsRef = useRef(forwardedProps);
  forwardedPropsRef.current = forwardedProps;
  const initialMessagesRef = useRef(initialMessages);
  initialMessagesRef.current = initialMessages;

  // The reasoning message currently streaming — lets an END/CONTENT event with a
  // mismatched id still resolve to the open entry.
  const activeReasoningIdRef = useRef<string | null>(null);

  const agent = useMemo(() => {
    if (!url) return null;
    // `initialMessages` is read from a ref, not a dep — only a `url`/`threadId`
    // change (i.e. a new conversation) rebuilds the agent and re-seeds it.
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
    activeReasoningIdRef.current = null;
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
      onRunErrorEvent: ({ event }) => setError(event.message),
      onRunFinishedEvent: () => callbacksRef.current.onRunFinished?.(),
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

    const params: RunAgentParameters = {};
    if (forwardedPropsRef.current) params.forwardedProps = forwardedPropsRef.current;

    agent
      .runAgent(params)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Failed to run agent.'))
      .finally(() => setIsRunning(false));
  }

  function stop() {
    if (!isRunning) return;
    agent?.abortRun();
    setIsRunning(false);
    if (interruptUrl) {
      // Fire-and-forget: the server cancels the in-sandbox turn; any late SSE
      // events are ignored since the local run is already aborted.
      void fetch(interruptUrl, { method: 'POST' }).catch(() => undefined);
    }
  }

  return { messages, trace, reasoningByMessageId, runStats, isRunning, error, sendMessage, stop };
}
