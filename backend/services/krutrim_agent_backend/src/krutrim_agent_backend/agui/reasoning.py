"""Pulls the "reasoning" (chain-of-thought) delta out of one streamed model chunk.

Different providers surface reasoning tokens differently. This is a trimmed port
of `ag_ui_langgraph.utils.resolve_reasoning_content` covering the shapes this
platform actually produces (OpenRouter via `langchain-openai`), plus the
standard LangChain content-block shapes so a future provider swap keeps working:

- `additional_kwargs["reasoning_content"]` — a plain string (DeepSeek / Qwen /
  xAI style, which is what OpenRouter returns for `deepseek/*` today).
- `additional_kwargs["reasoning"]["summary"][0]["text"]` — OpenAI Responses style.
- `content=[{"type": "reasoning", "reasoning": "..."}]` — LangChain standardized.
- `content=[{"type": "thinking", "thinking": "..."}]` — older langchain-anthropic.
- `content=[{"type": "reasoning_content", "reasoning_content": {"text": "..."}}]` —
  AWS Bedrock Converse.
"""

from __future__ import annotations

from typing import Any


def _dual_get(obj: Any, key: str, default: Any = None) -> Any:
    """Read `key` from a mapping or an attribute-bearing object.

    Chunks are usually LangChain `BaseMessage` instances, but some upstream
    paths deliver raw dicts — handle both instead of `AttributeError`ing.
    """
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def resolve_reasoning_delta(chunk: Any) -> str | None:
    """Return this chunk's reasoning-text delta, or `None` if it carries none."""
    content = _dual_get(chunk, "content")

    if isinstance(content, list) and content and isinstance(content[0], dict):
        block = content[0]
        block_type = block.get("type")

        if block_type == "thinking" and block.get("thinking"):
            return block["thinking"]
        if block_type == "reasoning" and block.get("reasoning"):
            return block["reasoning"]
        if block_type == "reasoning_content" and isinstance(
            block.get("reasoning_content"), dict
        ):
            inner = block["reasoning_content"]
            if inner.get("text"):
                return inner["text"]
        if block_type == "reasoning" and isinstance(block.get("summary"), list):
            summary = block["summary"]
            if summary and isinstance(summary[0], dict) and summary[0].get("text"):
                return summary[0]["text"]

    additional_kwargs = _dual_get(chunk, "additional_kwargs")
    if isinstance(additional_kwargs, dict):
        reasoning = additional_kwargs.get("reasoning")
        if isinstance(reasoning, dict):
            summary = reasoning.get("summary") or []
            if summary and isinstance(summary[0], dict) and summary[0].get("text"):
                return summary[0]["text"]

        reasoning_content = additional_kwargs.get("reasoning_content")
        if isinstance(reasoning_content, str) and reasoning_content:
            return reasoning_content

    return None


def resolve_text_delta(chunk: Any) -> str | None:
    """Return this chunk's plain-text delta.

    `""` is a legitimate streaming delta some providers emit during
    tool-call / structured-output transitions, so the caller distinguishes
    `""` (a real, empty text chunk) from `None` (no text on this chunk).
    """
    content = _dual_get(chunk, "content")
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                parts.append(block["text"])
        return "".join(parts) if parts else None
    return None
