from __future__ import annotations

from krutrim_agent_backend.chat.catalog import DEFAULT_CHAT_MODEL, is_known_chat_model
from krutrim_agent_backend.chat.graph import build_chat_graph
from krutrim_agent_backend.chat.messages import (
    derive_title,
    from_lc_messages,
    to_lc_messages,
)
from krutrim_agent_backend.chat.usage import accumulate_usage
from krutrim_agent_management.config import settings
from langchain_core.messages import AIMessage, HumanMessage


def test_default_chat_model_is_openrouter_deepseek():
    assert DEFAULT_CHAT_MODEL.provider == "openrouter"
    assert DEFAULT_CHAT_MODEL.model == settings.default_model


def test_is_known_chat_model():
    assert is_known_chat_model("openrouter", settings.default_model)
    assert not is_known_chat_model("openrouter", "made-up-model")


def test_derive_title_truncates_long_messages():
    assert derive_title("hello") == "hello"
    long_message = "x" * 100
    title = derive_title(long_message, max_len=10)
    assert len(title) == 10
    assert title.endswith("…")


def test_derive_title_handles_empty_message():
    assert derive_title("   ") == "Untitled chat"


def test_message_roundtrip_to_and_from_lc():
    raw = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    lc_messages = to_lc_messages(raw)
    assert isinstance(lc_messages[0], HumanMessage)
    assert isinstance(lc_messages[1], AIMessage)
    assert from_lc_messages(lc_messages) == raw


def test_accumulate_usage_sums_across_turns():
    reply = AIMessage(
        content="hi",
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    )
    first = accumulate_usage(None, reply)
    assert first["totals"] == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
    }
    assert len(first["turns"]) == 1

    second = accumulate_usage(first, reply)
    assert second["totals"] == {
        "input_tokens": 20,
        "output_tokens": 10,
        "total_tokens": 30,
    }
    assert len(second["turns"]) == 2


def test_accumulate_usage_handles_missing_usage_metadata():
    reply = AIMessage(content="hi")
    result = accumulate_usage(None, reply)
    assert result["totals"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }


class _FakeModel:
    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        assert messages[0].content == "system prompt"
        return AIMessage(content="reply")


async def test_build_chat_graph_prepends_system_prompt_and_returns_reply():
    graph = build_chat_graph(_FakeModel(), system_prompt="system prompt")
    result = await graph.ainvoke({"messages": [HumanMessage(content="hi")]})
    assert result["messages"][-1].content == "reply"
