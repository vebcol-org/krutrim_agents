"""Langfuse LLM tracing — dev-mode only.

`get_langfuse_handler()` is wired into `providers/registry.py::build_chat_model`,
not into individual routes: every chat model in the app (the plain `chat`
graph and every deepagents profile) is built through that one function, so
binding the callback there traces all of them for free.

Returns `None` (tracing off) unless `dev_mode` is on AND both Langfuse keys
are configured — this is a local dev aid, not something to run against
production traffic by default.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from krutrim_agent_management.config import settings
from loguru import logger

if TYPE_CHECKING:
    from langfuse.langchain import CallbackHandler


@lru_cache(maxsize=1)
def get_langfuse_handler() -> CallbackHandler | None:
    if not settings.dev_mode or not settings.langfuse_enabled:
        return None
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.warning(
            "dev_mode is on but LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY are not set - Langfuse tracing disabled."
        )
        return None

    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler

    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_host,
    )
    logger.info(
        "Langfuse tracing enabled (dev_mode, host={})",
        settings.langfuse_host or "default",
    )
    return CallbackHandler()
