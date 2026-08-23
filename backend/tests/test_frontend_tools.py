from __future__ import annotations

from unittest.mock import MagicMock

from krutrim_agents_core.frontend_tools import FrontendToolBridgeMiddleware
from langchain_core.messages import AIMessage


def test_merge_frontend_tools_adds_state_tools():
    mw = FrontendToolBridgeMiddleware()
    request = MagicMock()
    request.state = {
        "tools": [{"name": "render_content", "description": "x", "parameters": {}}]
    }
    request.tools = ["backend_tool_1"]
    request.override.return_value = "OVERRIDDEN"

    result = mw._merge_frontend_tools(request)

    request.override.assert_called_once_with(
        tools=[
            "backend_tool_1",
            {"name": "render_content", "description": "x", "parameters": {}},
        ]
    )
    assert result == "OVERRIDDEN"


def test_merge_frontend_tools_noop_when_none_declared():
    mw = FrontendToolBridgeMiddleware()
    request = MagicMock()
    request.state = {}

    result = mw._merge_frontend_tools(request)

    request.override.assert_not_called()
    assert result is request


def test_split_tool_calls_extracts_frontend_call():
    mw = FrontendToolBridgeMiddleware()
    ai_msg = AIMessage(
        content="",
        id="msg1",
        tool_calls=[
            {"name": "render_content", "args": {"kind": "markdown"}, "id": "call1"},
            {"name": "web_search", "args": {"query": "x"}, "id": "call2"},
        ],
    )
    state = {
        "tools": [{"name": "render_content", "description": "d", "parameters": {}}],
        "messages": [ai_msg],
    }

    update = mw._split_tool_calls(state)

    assert update is not None
    updated_msg = update["messages"][-1]
    assert [c["name"] for c in updated_msg.tool_calls] == ["web_search"]
    assert update["intercepted_tool_calls"][0]["name"] == "render_content"
    assert update["original_ai_message_id"] == "msg1"


def test_split_tool_calls_noop_when_no_frontend_tools_declared():
    mw = FrontendToolBridgeMiddleware()
    ai_msg = AIMessage(
        content="",
        id="msg1",
        tool_calls=[{"name": "web_search", "args": {}, "id": "call1"}],
    )
    state = {"tools": [], "messages": [ai_msg]}

    assert mw._split_tool_calls(state) is None


def test_split_tool_calls_noop_when_last_message_has_no_frontend_call():
    mw = FrontendToolBridgeMiddleware()
    ai_msg = AIMessage(
        content="",
        id="msg1",
        tool_calls=[{"name": "web_search", "args": {}, "id": "call1"}],
    )
    state = {
        "tools": [{"name": "render_content", "description": "d", "parameters": {}}],
        "messages": [ai_msg],
    }

    assert mw._split_tool_calls(state) is None


def test_restore_tool_calls_reattaches_to_original_message():
    mw = FrontendToolBridgeMiddleware()
    original = AIMessage(
        content="",
        id="msg1",
        tool_calls=[{"name": "web_search", "args": {}, "id": "call2"}],
    )
    other = AIMessage(content="hi", id="msg0")
    frontend_call = {
        "name": "render_content",
        "args": {"kind": "markdown"},
        "id": "call1",
    }
    state = {
        "messages": [other, original],
        "intercepted_tool_calls": [frontend_call],
        "original_ai_message_id": "msg1",
    }

    update = mw._restore_tool_calls(state)

    assert update is not None
    restored = update["messages"][-1]
    assert {c["id"] for c in restored.tool_calls} == {"call1", "call2"}
    assert update["intercepted_tool_calls"] is None
    assert update["original_ai_message_id"] is None


def test_restore_tool_calls_noop_when_nothing_intercepted():
    mw = FrontendToolBridgeMiddleware()
    state = {
        "messages": [],
        "intercepted_tool_calls": None,
        "original_ai_message_id": None,
    }

    assert mw._restore_tool_calls(state) is None
