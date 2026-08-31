"""Unit tests for `krutrim_agent_backend.agui.translator.run_graph_as_agui`.

Drives the translator with a fake graph whose `astream` yields scripted
`(namespace, mode, payload)` triples — the same shape LangGraph produces with
`stream_mode=["messages", "updates"], subgraphs=True` — and asserts the emitted
AG-UI event sequence plus the plugin hook ordering.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest
from ag_ui.core import CustomEvent, EventType
from ag_ui.core.types import RunAgentInput
from krutrim_agent_agui import PluginBase, run_graph_as_agui
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage


class FakeGraph:
    def __init__(self, script: list[tuple], final_messages: list) -> None:
        self._script = script
        self._final_messages = final_messages

    async def astream(self, _input, _config, *, stream_mode, subgraphs):
        for item in self._script:
            yield item

    async def aget_state(self, _config):
        return SimpleNamespace(values={"messages": self._final_messages})


def _run_input() -> RunAgentInput:
    return RunAgentInput(
        thread_id="t1",
        run_id="r1",
        state={},
        messages=[{"id": "u1", "role": "user", "content": "hello"}],
        tools=[],
        context=[],
        forwarded_props={},
    )


async def _collect(agen: AsyncIterator) -> list:
    return [event async for event in agen]


async def test_emits_text_stream_with_run_and_step_events() -> None:
    chunk_a = AIMessageChunk(content="Hel", id="m1")
    chunk_b = AIMessageChunk(content="lo", id="m1")
    chunk_end = AIMessageChunk(content="", id="m1", response_metadata={"finish_reason": "stop"})
    graph = FakeGraph(
        script=[
            ((), "updates", {"model": {}}),
            ((), "messages", (chunk_a, {})),
            ((), "messages", (chunk_b, {})),
            ((), "messages", (chunk_end, {})),
        ],
        final_messages=[AIMessage(content="Hello", id="m1")],
    )

    events = await _collect(run_graph_as_agui(graph, _run_input(), thread_id="t1"))
    types = [e.type for e in events]

    assert types[0] == EventType.RUN_STARTED
    assert types[-1] == EventType.RUN_FINISHED
    assert EventType.STEP_STARTED in types and EventType.STEP_FINISHED in types
    assert types.count(EventType.TEXT_MESSAGE_START) == 1
    assert [e.delta for e in events if e.type == EventType.TEXT_MESSAGE_CONTENT] == ["Hel", "lo"]
    assert types.count(EventType.TEXT_MESSAGE_END) == 1


async def test_emits_reasoning_before_text() -> None:
    reasoning = AIMessageChunk(content="", id="m1", additional_kwargs={"reasoning_content": "thinking..."})
    text = AIMessageChunk(content="answer", id="m1")
    done = AIMessageChunk(content="", id="m1", response_metadata={"finish_reason": "stop"})
    graph = FakeGraph(
        script=[((), "messages", (reasoning, {})), ((), "messages", (text, {})), ((), "messages", (done, {}))],
        final_messages=[AIMessage(content="answer", id="m1")],
    )

    events = await _collect(run_graph_as_agui(graph, _run_input(), thread_id="t1"))
    types = [e.type for e in events]

    assert types.index(EventType.REASONING_MESSAGE_START) < types.index(EventType.TEXT_MESSAGE_START)
    assert types.index(EventType.REASONING_MESSAGE_END) < types.index(EventType.TEXT_MESSAGE_START)
    assert [e.delta for e in events if e.type == EventType.REASONING_MESSAGE_CONTENT] == ["thinking..."]


async def test_all_assistant_text_streams_as_text_message_content() -> None:
    chunks = [
        AIMessageChunk(content="# Report\n", id="m1"),
        AIMessageChunk(content="Body of the answer.", id="m1"),
        AIMessageChunk(content="", id="m1", response_metadata={"finish_reason": "stop"}),
    ]
    graph = FakeGraph(
        script=[((), "messages", (c, {})) for c in chunks],
        final_messages=[AIMessage(content="x", id="m1")],
    )
    events = await _collect(run_graph_as_agui(graph, _run_input(), thread_id="t1"))
    text = "".join(e.delta for e in events if e.type == EventType.TEXT_MESSAGE_CONTENT)
    assert text == "# Report\nBody of the answer."
    assert not any(e.type == EventType.CUSTOM for e in events)


async def test_subagent_tokens_are_not_streamed_as_text() -> None:
    sub = AIMessageChunk(content="secret subagent thought", id="s1")
    graph = FakeGraph(
        script=[(("researcher:1",), "messages", (sub, {}))],
        final_messages=[],
    )

    events = await _collect(run_graph_as_agui(graph, _run_input(), thread_id="t1"))

    assert not any(e.type == EventType.TEXT_MESSAGE_CONTENT for e in events)


async def test_tool_call_start_args_end_and_result() -> None:
    start = AIMessageChunk(
        content="",
        id="m1",
        tool_call_chunks=[{"name": "web_search", "args": '{"q":', "id": "tc1", "index": 0}],
    )
    more = AIMessageChunk(
        content="",
        id="m1",
        tool_call_chunks=[{"name": None, "args": '"cats"}', "id": None, "index": 0}],
    )
    done = AIMessageChunk(content="", id="m1", response_metadata={"finish_reason": "tool_calls"})
    result = ToolMessage(content="results here", tool_call_id="tc1", id="tm1")
    graph = FakeGraph(
        script=[
            ((), "messages", (start, {})),
            ((), "messages", (more, {})),
            ((), "messages", (done, {})),
            ((), "messages", (result, {})),
        ],
        final_messages=[],
    )

    events = await _collect(run_graph_as_agui(graph, _run_input(), thread_id="t1"))
    types = [e.type for e in events]

    assert types.count(EventType.TOOL_CALL_START) == 1
    assert [e.delta for e in events if e.type == EventType.TOOL_CALL_ARGS] == ['{"q":', '"cats"}']
    assert types.count(EventType.TOOL_CALL_END) == 1
    assert types.index(EventType.TOOL_CALL_END) < types.index(EventType.TOOL_CALL_RESULT)


async def test_plugin_hooks_inject_events_in_order() -> None:
    class StubPlugin(PluginBase):
        async def before_run(self, ctx):
            yield CustomEvent(type=EventType.CUSTOM, name="before", value={})

        async def on_event(self, event, ctx):
            yield event
            if event.type == EventType.RUN_STARTED:
                yield CustomEvent(type=EventType.CUSTOM, name="saw_start", value={})

        async def after_run(self, ctx):
            yield CustomEvent(type=EventType.CUSTOM, name="after", value={"had_final": ctx.final_message is not None})

    graph = FakeGraph(script=[], final_messages=[AIMessage(content="x", id="m1")])
    events = await _collect(
        run_graph_as_agui(graph, _run_input(), thread_id="t1", plugins=[StubPlugin()])
    )
    custom = [e.name for e in events if e.type == EventType.CUSTOM]

    assert custom[0] == "before"
    assert "saw_start" in custom
    assert custom[-1] == "after"
    assert events[-1].type == EventType.RUN_FINISHED


async def test_cancelled_run_persists_partial_turn_to_checkpoint() -> None:
    class CancelGraph(FakeGraph):
        def __init__(self) -> None:
            super().__init__(script=[], final_messages=[])
            self.updated: list = []

        async def astream(self, _input, _config, *, stream_mode, subgraphs):
            yield ((), "messages", (AIMessageChunk(content="partial ans", id="m1"), {}))
            raise asyncio.CancelledError

        async def aupdate_state(self, _config, values):
            self.updated.append(values)

    graph = CancelGraph()
    with pytest.raises(asyncio.CancelledError):
        await _collect(run_graph_as_agui(graph, _run_input(), thread_id="t1"))

    assert len(graph.updated) == 1
    msg = graph.updated[0]["messages"][0]
    assert msg.content == "partial ans"
    assert msg.additional_kwargs.get("interrupted") is True


async def test_continuation_hint_injected_after_an_interrupted_turn() -> None:
    from langchain_core.messages import SystemMessage

    class HintGraph(FakeGraph):
        def __init__(self, prior: list) -> None:
            super().__init__(script=[], final_messages=prior)
            self.seen_input: dict | None = None

        async def astream(self, graph_input, _config, *, stream_mode, subgraphs):
            self.seen_input = graph_input
            yield ((), "messages", (AIMessageChunk(content="ok", id="m2"), {}))
            yield (
                (),
                "messages",
                (AIMessageChunk(content="", id="m2", response_metadata={"finish_reason": "stop"}), {}),
            )

    # last stored turn is an interrupted assistant message -> hint expected
    interrupted_prior = [AIMessage(content="half a", additional_kwargs={"interrupted": True})]
    g1 = HintGraph(interrupted_prior)
    await _collect(run_graph_as_agui(g1, _run_input(), thread_id="t1"))
    kinds = [type(m).__name__ for m in g1.seen_input["messages"]]
    assert kinds == ["SystemMessage", "HumanMessage"]
    assert isinstance(g1.seen_input["messages"][0], SystemMessage)

    # a normal completed prior turn -> no hint
    g2 = HintGraph([AIMessage(content="a full answer", id="m1")])
    await _collect(run_graph_as_agui(g2, _run_input(), thread_id="t1"))
    assert [type(m).__name__ for m in g2.seen_input["messages"]] == ["HumanMessage"]


async def test_graph_failure_becomes_run_error_not_raise() -> None:
    class BoomGraph(FakeGraph):
        async def astream(self, _input, _config, *, stream_mode, subgraphs):
            yield ((), "messages", (AIMessageChunk(content="partial", id="m1"), {}))
            raise RuntimeError("model exploded")

    graph = BoomGraph(script=[], final_messages=[])
    events = await _collect(run_graph_as_agui(graph, _run_input(), thread_id="t1"))
    types = [e.type for e in events]

    assert EventType.RUN_ERROR in types
    assert EventType.RUN_FINISHED not in types
    assert types[-1] == EventType.RUN_ERROR
    err = next(e for e in events if e.type == EventType.RUN_ERROR)
    assert "model exploded" in err.message
