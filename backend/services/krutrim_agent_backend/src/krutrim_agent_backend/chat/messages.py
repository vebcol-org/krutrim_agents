"""Converts between LangChain `BaseMessage`s and the plain-dict shape persisted in `checkpointer.json`."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


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


def derive_title(message: str, max_len: int = 60) -> str:
    """First line of a chat message, condensed into a project title."""
    stripped = " ".join(message.split())
    if not stripped:
        return "Untitled chat"
    return (
        stripped if len(stripped) <= max_len else stripped[: max_len - 1].rstrip() + "…"
    )
