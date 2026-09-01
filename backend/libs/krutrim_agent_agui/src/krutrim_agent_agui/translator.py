"""Our own LangGraph -> AG-UI event translator.

Replaces `ag_ui_langgraph.LangGraphAgent`: consume a compiled LangGraph's
`astream(...)` and yield `ag_ui.core` events over the same SSE contract the
frontend's `@ag-ui/client` `HttpAgent` already speaks. Owned in-tree so we can
hook per-run instrumentation into it (see `plugins.py` / `stats.py`).

Scope vs. the package it replaces:

- **Input**: only the last `user` message from `RunAgentInput.messages` is fed
  to the graph as a `HumanMessage`; prior turns are replayed from the
  per-session checkpointer (`thread_id`). This is the same simplification
  `api/chat_routes.py` has always used — the frontend history array is
  advisory, the checkpoint is the source of truth. `RunAgentInput.tools` is
  forwarded into `state["tools"]` for `FrontendToolBridgeMiddleware`.
- **Streaming**: `stream_mode=["messages", "updates"]` with `subgraphs=True`.
  Text / reasoning / tool-call events are emitted for the **root** graph only,
  so a subagent's own model tokens don't get spliced into the main answer;
  subgraph activity still surfaces as `STEP_*` events.
- **Not ported**: interrupts / resume, regenerate, `predict_state`, encrypted
  (Anthropic redacted) reasoning, `MESSAGES_SNAPSHOT` (the frontend never
  requested agent history over this route anyway).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any

from ag_ui.core import (
    BaseEvent,
    EventType,
    ReasoningEndEvent,
    ReasoningMessageContentEvent,
    ReasoningMessageEndEvent,
    ReasoningMessageStartEvent,
    ReasoningStartEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StepFinishedEvent,
    StepStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from loguru import logger

from krutrim_agent_agui.plugins import AguiPlugin, AguiRunContext
from krutrim_agent_agui.reasoning import (
    resolve_reasoning_delta,
    resolve_text_delta,
)

if TYPE_CHECKING:
    from ag_ui.core.types import RunAgentInput
    from langgraph.graph.state import CompiledStateGraph

def _recursion_limit() -> int:
    """LangGraph super-step cap for one turn. `KRUTRIM_AGENT_GRAPH_RECURSION_LIMIT`
    (default 100); the in-sandbox runtime exports it from `RunConfig`."""
    try:
        return int(os.getenv("KRUTRIM_AGENT_GRAPH_RECURSION_LIMIT") or 100)
    except ValueError:
        return 100


def _last_user_text(input_data: RunAgentInput) -> str:
    for message in reversed(input_data.messages or []):
        if getattr(message, "role", None) == "user":
            content = message.content
            return content if isinstance(content, str) else str(content)
    raise ValueError("RunAgentInput carried no user message to run.")


def _frontend_tools(input_data: RunAgentInput) -> list[dict[str, Any]]:
    return [t.model_dump() for t in (input_data.tools or [])]


_CONTINUATION_HINT = (
    "Your previous response was cut off mid-generation (the user interrupted it). "
    "If this message asks you to continue or resume, pick up exactly where that "
    "response stopped instead of restarting; otherwise just answer normally."
)


async def _persist_partial_turn(
    graph: CompiledStateGraph, config: dict[str, Any], partial_text: str
) -> None:
    """Append the partially-streamed assistant text to the session checkpoint
    when a run is cancelled mid-node. Marked `interrupted` in `additional_kwargs`
    so the *next* run can add a continuation hint (see `_continuation_hint`).
    Best-effort: shielded from the in-flight cancellation, failures are logged."""
    if not partial_text.strip():
        return
    message = AIMessage(content=partial_text, additional_kwargs={"interrupted": True})
    task = asyncio.ensure_future(graph.aupdate_state(config, {"messages": [message]}))
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        with contextlib.suppress(Exception):
            await task  # the shielded task keeps running — let it finish
    except Exception:  # noqa: BLE001 - never mask the original cancellation
        logger.exception("agui: failed to persist partial turn")


async def _continuation_hint(
    graph: CompiledStateGraph, config: dict[str, Any]
) -> list[SystemMessage]:
    """A one-off `SystemMessage` for this turn only when the last stored turn
    was an interrupted assistant message. It IS checkpointed (system messages
    are hidden from the chat UI by `to_display_messages`), but only lands once
    per interrupt since a completed reply clears the `interrupted` marker."""
    try:
        snapshot = await graph.aget_state(config)
    except Exception:  # noqa: BLE001 - no checkpoint yet / read failure -> no hint
        return []
    messages = (getattr(snapshot, "values", None) or {}).get("messages") or []
    last = messages[-1] if messages else None
    if isinstance(last, AIMessage) and (last.additional_kwargs or {}).get("interrupted"):
        return [SystemMessage(content=_CONTINUATION_HINT)]
    return []


async def _run_hook(plugin: AguiPlugin, hook: str, ctx: AguiRunContext) -> list[BaseEvent]:
    """Iterate one plugin lifecycle hook to completion, swallowing any failure."""
    try:
        return [event async for event in getattr(plugin, hook)(ctx)]
    except Exception:  # noqa: BLE001 - a bad plugin must not break the stream
        logger.exception("agui: plugin {} {} failed", type(plugin).__name__, hook)
        return []


class _RunEmitter:
    """Per-run streaming state machine. One instance per `run_graph_as_agui` call."""

    def __init__(self, ctx: AguiRunContext, plugins: Sequence[AguiPlugin]) -> None:
        self.ctx = ctx
        self.plugins = plugins
        self.text_id: str | None = None
        self.reasoning_id: str | None = None
        self.tool_started: set[str] = set()
        self.tool_ended: set[str] = set()
        self.last_tool_id: str | None = None
        # Raw assistant text as produced — persisted verbatim if the run is
        # cancelled before the node commits its own message.
        self.assistant_full = ""

    async def emit(self, event: BaseEvent) -> AsyncIterator[BaseEvent]:
        """Yield one core event, then whatever each plugin's `on_event` adds."""
        yield event
        for plugin in self.plugins:
            try:
                async for extra in plugin.on_event(event, self.ctx):
                    if extra is not event:
                        yield extra
            except Exception:  # noqa: BLE001 - a bad plugin must not break the stream
                logger.exception("agui: plugin {} on_event failed", type(plugin).__name__)

    async def open_reasoning(self, chunk_id: str | None) -> AsyncIterator[BaseEvent]:
        if self.reasoning_id is not None:
            return
        self.reasoning_id = chunk_id or uuid.uuid4().hex
        async for event in self.emit(ReasoningStartEvent(type=EventType.REASONING_START, message_id=self.reasoning_id)):
            yield event
        async for event in self.emit(
            ReasoningMessageStartEvent(
                type=EventType.REASONING_MESSAGE_START, message_id=self.reasoning_id, role="reasoning"
            )
        ):
            yield event

    async def close_reasoning(self) -> AsyncIterator[BaseEvent]:
        if self.reasoning_id is None:
            return
        rid, self.reasoning_id = self.reasoning_id, None
        async for event in self.emit(ReasoningMessageEndEvent(type=EventType.REASONING_MESSAGE_END, message_id=rid)):
            yield event
        async for event in self.emit(ReasoningEndEvent(type=EventType.REASONING_END, message_id=rid)):
            yield event

    async def open_text(self, chunk_id: str | None) -> AsyncIterator[BaseEvent]:
        if self.text_id is not None:
            return
        self.text_id = chunk_id or uuid.uuid4().hex
        async for event in self.emit(
            TextMessageStartEvent(type=EventType.TEXT_MESSAGE_START, message_id=self.text_id, role="assistant")
        ):
            yield event

    async def close_text(self) -> AsyncIterator[BaseEvent]:
        if self.text_id is None:
            return
        tid, self.text_id = self.text_id, None
        async for event in self.emit(TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=tid)):
            yield event

    async def close_tool_calls(self) -> AsyncIterator[BaseEvent]:
        for tool_id in list(self.tool_started - self.tool_ended):
            self.tool_ended.add(tool_id)
            async for event in self.emit(ToolCallEndEvent(type=EventType.TOOL_CALL_END, tool_call_id=tool_id)):
                yield event
        self.last_tool_id = None

    async def emit_text(self, chunk_id: str | None, delta: str) -> AsyncIterator[BaseEvent]:
        async for event in self.open_text(chunk_id):
            yield event
        async for event in self.emit(
            TextMessageContentEvent(type=EventType.TEXT_MESSAGE_CONTENT, message_id=self.text_id, delta=delta)
        ):
            yield event

    async def handle_ai_chunk(self, chunk: AIMessage) -> AsyncIterator[BaseEvent]:
        reasoning_delta = resolve_reasoning_delta(chunk)
        text_delta = resolve_text_delta(chunk)
        tool_call_chunks = getattr(chunk, "tool_call_chunks", None) or []
        finish_reason = (getattr(chunk, "response_metadata", None) or {}).get("finish_reason")
        chunk_id = getattr(chunk, "id", None)

        if reasoning_delta:
            async for event in self.open_reasoning(chunk_id):
                yield event
            async for event in self.emit(
                ReasoningMessageContentEvent(
                    type=EventType.REASONING_MESSAGE_CONTENT, message_id=self.reasoning_id, delta=reasoning_delta
                )
            ):
                yield event
        elif self.reasoning_id is not None and (text_delta or tool_call_chunks or finish_reason):
            async for event in self.close_reasoning():
                yield event

        if text_delta:
            self.assistant_full += text_delta
            async for event in self.emit_text(chunk_id, text_delta):
                yield event

        for tool_call in tool_call_chunks:
            tool_id = tool_call.get("id") or self.last_tool_id
            name = tool_call.get("name")
            args = tool_call.get("args")
            if tool_id and name and tool_id not in self.tool_started:
                self.tool_started.add(tool_id)
                self.last_tool_id = tool_id
                async for event in self.emit(
                    ToolCallStartEvent(
                        type=EventType.TOOL_CALL_START,
                        tool_call_id=tool_id,
                        tool_call_name=name,
                        parent_message_id=self.text_id,
                    )
                ):
                    yield event
            if tool_id and args:
                self.last_tool_id = tool_id
                async for event in self.emit(
                    ToolCallArgsEvent(type=EventType.TOOL_CALL_ARGS, tool_call_id=tool_id, delta=args)
                ):
                    yield event

        if finish_reason:
            async for event in self.close_text():
                yield event
            async for event in self.close_reasoning():
                yield event
            async for event in self.close_tool_calls():
                yield event

    async def handle_tool_message(self, message: ToolMessage) -> AsyncIterator[BaseEvent]:
        content = message.content if isinstance(message.content, str) else str(message.content)
        async for event in self.emit(
            ToolCallResultEvent(
                type=EventType.TOOL_CALL_RESULT,
                message_id=getattr(message, "id", None) or uuid.uuid4().hex,
                tool_call_id=message.tool_call_id,
                content=content,
                role="tool",
            )
        ):
            yield event

    async def close_open(self) -> AsyncIterator[BaseEvent]:
        async for event in self.close_text():
            yield event
        async for event in self.close_reasoning():
            yield event
        async for event in self.close_tool_calls():
            yield event


async def run_graph_as_agui(
    graph: CompiledStateGraph,
    input_data: RunAgentInput,
    *,
    thread_id: str,
    plugins: Sequence[AguiPlugin] = (),
    on_finish: Callable[[AguiRunContext], Awaitable[None]] | None = None,
) -> AsyncIterator[BaseEvent]:
    """Run `graph` for one turn and yield the AG-UI event stream for it.

    On a mid-stream failure this yields a single `RUN_ERROR` and returns (no
    `RUN_FINISHED`); it never raises, so callers can treat "the generator is
    done" as "the run is over, one way or another".

    `on_finish`, if given, is awaited once with the fully-populated
    `AguiRunContext` (`final_state` / `final_message` set) after a *successful*
    run, before `RUN_FINISHED` — the chat route uses it to fold token usage
    into `usage.json`. A failure in `on_finish` is logged, not raised.
    """
    run_id = input_data.run_id or uuid.uuid4().hex
    ctx = AguiRunContext(thread_id=thread_id, run_id=run_id, input=input_data)
    emitter = _RunEmitter(ctx, plugins)

    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": _recursion_limit(),
    }
    hint = await _continuation_hint(graph, config)
    graph_input = {
        "messages": [*hint, HumanMessage(content=_last_user_text(input_data))],
        "tools": _frontend_tools(input_data),
    }

    for plugin in plugins:
        for event in await _run_hook(plugin, "before_run", ctx):
            yield event

    async for event in emitter.emit(
        RunStartedEvent(type=EventType.RUN_STARTED, thread_id=thread_id, run_id=run_id)
    ):
        yield event

    try:
        async for namespace, mode, payload in graph.astream(
            graph_input, config, stream_mode=["messages", "updates"], subgraphs=True
        ):
            if mode == "messages":
                message, _metadata = payload
                if namespace:
                    continue  # subagent tokens — surfaced via STEP_* only
                if isinstance(message, ToolMessage):
                    async for event in emitter.handle_tool_message(message):
                        yield event
                elif isinstance(message, AIMessage):
                    async for event in emitter.handle_ai_chunk(message):
                        yield event
            elif mode == "updates" and isinstance(payload, dict):
                prefix = ":".join(str(part) for part in namespace) + ":" if namespace else ""
                for node_name in payload:
                    if node_name.startswith("__"):
                        continue
                    step_name = f"{prefix}{node_name}"
                    async for event in emitter.emit(
                        StepStartedEvent(type=EventType.STEP_STARTED, step_name=step_name)
                    ):
                        yield event
                    async for event in emitter.emit(
                        StepFinishedEvent(type=EventType.STEP_FINISHED, step_name=step_name)
                    ):
                        yield event
    except asyncio.CancelledError:
        # Client hit Stop / the SSE connection dropped. The interrupted node
        # never committed its assistant message, so fold whatever streamed so
        # far into the checkpoint — reload then shows the partial turn. No
        # events are yielded here (the consumer is already gone).
        logger.info("agui: run {} cancelled — persisting partial turn", run_id)
        await _persist_partial_turn(graph, config, emitter.assistant_full)
        raise
    except Exception as exc:  # noqa: BLE001 - convert any run failure into a protocol event
        logger.exception("agui: run {} failed mid-stream", run_id)
        async for event in emitter.close_open():
            yield event
        yield RunErrorEvent(type=EventType.RUN_ERROR, message=f"{type(exc).__name__}: {exc}")
        return

    async for event in emitter.close_open():
        yield event

    try:
        snapshot = await graph.aget_state(config)
        values = snapshot.values if snapshot else None
        ctx.final_state = values if isinstance(values, dict) else None
        messages = (ctx.final_state or {}).get("messages") or []
        if messages and isinstance(messages[-1], AIMessage):
            ctx.final_message = messages[-1]
    except Exception:  # noqa: BLE001 - post-run bookkeeping only; never fail the run for it
        logger.exception("agui: run {} could not read final state", run_id)

    if on_finish is not None:
        try:
            await on_finish(ctx)
        except Exception:  # noqa: BLE001 - caller bookkeeping must not break the stream
            logger.exception("agui: run {} on_finish callback failed", run_id)

    for plugin in plugins:
        for event in await _run_hook(plugin, "after_run", ctx):
            yield event

    async for event in emitter.emit(
        RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id=thread_id, run_id=run_id)
    ):
        yield event
