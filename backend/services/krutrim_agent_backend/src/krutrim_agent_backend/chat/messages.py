"""Converts between LangChain `BaseMessage`s and the plain-dict shape persisted in `checkpointer.json`."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


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


def to_display_messages(messages: list[BaseMessage]) -> list[dict[str, str]]:
    """The user-visible transcript for reloading a past conversation: human
    turns plus assistant turns that actually carried text.

    Drops `ToolMessage`s, tool-call-only (empty-text) assistant turns, and
    system messages — the same subset the live AG-UI stream renders as chat
    bubbles (tool calls go to the trace panel, not the message list). Matters
    for in-sandbox agent sessions (`research`), whose LangGraph checkpoint
    stores the full ReAct scratchpad, not just the visible turns.
    """
    out: list[dict[str, str]] = []
    for m in messages:
        text = _text(getattr(m, "content", ""))
        if isinstance(m, HumanMessage):
            out.append({"role": "user", "content": text})
        elif isinstance(m, AIMessage) and text.strip():
            out.append({"role": "assistant", "content": text})
    return out


def derive_title(message: str, max_len: int = 60) -> str:
    """First line of a chat message, condensed into a project title."""
    stripped = " ".join(message.split())
    if not stripped:
        return "Untitled chat"
    return (
        stripped if len(stripped) <= max_len else stripped[: max_len - 1].rstrip() + "…"
    )
