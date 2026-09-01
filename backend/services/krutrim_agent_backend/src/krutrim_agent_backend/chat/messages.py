"""Converts between LangChain `BaseMessage`s and the plain-dict shape persisted in `checkpointer.json`."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage


def _text(content: Any) -> str:
    """Flatten a message's `content` to plain text — handles both the plain
    string chat messages use and the structured `[{type: "text", ...}]` list an
    in-sandbox agent's checkpoint can carry."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return "" if content is None else str(content)


def to_lc_messages(raw: list[dict[str, Any]]) -> list[BaseMessage]:
    return [
        AIMessage(content=item["content"])
        if item["role"] == "assistant"
        else HumanMessage(content=item["content"])
        for item in raw
    ]


def from_lc_messages(messages: list[BaseMessage]) -> list[dict[str, str]]:
    return [
        {
            "role": "assistant" if isinstance(m, AIMessage) else "user",
            "content": m.content,
        }
        for m in messages
    ]


def to_display_messages(
    messages: list[BaseMessage], *, include_tool_calls: bool = False
) -> list[dict[str, Any]]:
    """The transcript for reloading a past conversation.

    Always: human turns and assistant turns that carried text. System messages
    and standalone `ToolMessage`s are dropped.

    With `include_tool_calls` (agent sessions — `research` etc., whose LangGraph
    checkpoint holds the full ReAct scratchpad): assistant turns also report the
    tools they called, each with its result folded in from the matching
    `ToolMessage`, and a tool-call-only turn (no text) is kept so the reloaded
    work-log panel matches what the live stream showed. Plain `chat` sessions
    pass this `False` and get just `{role, content}` per turn, as before.

    An assistant turn cut off by a client Stop / dropped connection carries
    `additional_kwargs["interrupted"]` (set by
    `krutrim_agent_agui.translator._persist_partial_turn`); it's surfaced so the
    frontend routes that partial text to its work-log column, not the
    finished-report view (see `render-payload.ts` / the agent turn splitter).
    """
    results: dict[str, str] = {
        m.tool_call_id: _text(m.content)
        for m in messages
        if isinstance(m, ToolMessage) and getattr(m, "tool_call_id", None)
    }

    out: list[dict[str, Any]] = []
    for m in messages:
        text = _text(getattr(m, "content", ""))
        if isinstance(m, HumanMessage):
            out.append({"role": "user", "content": text})
        elif isinstance(m, AIMessage):
            tool_calls = (
                [
                    {
                        "id": tc.get("id") or "",
                        "name": tc.get("name") or "",
                        "args": json.dumps(tc.get("args") or {}, ensure_ascii=False, sort_keys=True),
                        "result": results.get(tc.get("id") or ""),
                    }
                    for tc in (getattr(m, "tool_calls", None) or [])
                ]
                if include_tool_calls
                else []
            )
            if not text.strip() and not tool_calls:
                continue  # nothing the reader would see
            entry: dict[str, Any] = {"role": "assistant", "content": text}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            if (getattr(m, "additional_kwargs", None) or {}).get("interrupted"):
                entry["interrupted"] = True
            out.append(entry)
    return out


def derive_title(message: str, max_len: int = 60) -> str:
    """First line of a chat message, condensed into a project title."""
    stripped = " ".join(message.split())
    if not stripped:
        return "Untitled chat"
    return (
        stripped if len(stripped) <= max_len else stripped[: max_len - 1].rstrip() + "…"
    )
