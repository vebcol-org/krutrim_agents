"""Automatic context-window management, as a pluggable `AgentMiddleware`.

`build_context_management_middleware(model)` returns one of LangChain's built-in
middlewares (or `None`) based on `AppSettings.context_management_strategy`:

    off        -> None
    trim       -> ContextEditingMiddleware   (drop oldest tool results)
    summarize  -> SummarizationMiddleware     (LLM-compress old messages)
    rag        -> not implemented yet; falls back to `summarize`

Both built-ins hook `before_model` / `wrap_model_call` (plus their async twins),
so they work with the deepagents graphs *and* the research profile's hand-rolled
one (see `profiles/research/agent.py`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from krutrim_agent_management.config import settings
from loguru import logger

if TYPE_CHECKING:
    from langchain.agents.middleware.types import AgentMiddleware
    from langchain_core.language_models import BaseChatModel


def build_context_management_middleware(
    model: BaseChatModel | str,
) -> AgentMiddleware | None:
    """The context-management middleware for the configured strategy, or `None`
    when it is `"off"` / unrecognised. `model` is used only by `summarize` (for
    the compression call) — pass the agent's own main-role model."""
    strategy = (settings.context_management_strategy or "off").lower()
    if strategy in ("", "off", "none"):
        return None

    from langchain.agents.middleware import (
        ContextEditingMiddleware,
        SummarizationMiddleware,
    )

    if strategy == "trim":
        return ContextEditingMiddleware()

    if strategy == "rag":
        logger.warning(
            "context_management_strategy='rag' is not implemented yet — "
            "using 'summarize'."
        )
        strategy = "summarize"

    if strategy == "summarize":
        return SummarizationMiddleware(
            model=model,
            trigger=("tokens", settings.context_trigger_tokens),
            keep=("messages", settings.context_keep_messages),
        )

    logger.warning(
        "unknown context_management_strategy={!r} — context management disabled.",
        settings.context_management_strategy,
    )
    return None
