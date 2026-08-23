"""Selects which web-search tool a profile's default `web_search` export resolves to.

Default stays DuckDuckGo (zero-config); Tavily is opt-in globally via
`KRUTRIM_AGENT_WEB_SEARCH_PROVIDER=tavily` + `TAVILY_API_KEY`, not hardcoded
per-profile — keeps every profile's `_tools()` factory shape identical
regardless of which provider is actually configured.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from krutrim_agent_management.config import settings

from .duckduckgo import duckduckgo_search
from .tavily import tavily_search

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

SEARCH_PROVIDERS: dict[str, "BaseTool"] = {
    "duckduckgo": duckduckgo_search,
    "tavily": tavily_search,
}


def get_web_search_tool(provider: str | None = None) -> "BaseTool":
    """Resolve the configured (or explicitly requested) web-search tool.

    Falls back to `duckduckgo` for an unrecognized provider name rather than
    raising — a typo'd env var should degrade to the zero-config default,
    not break every profile's tool list at import time.
    """
    key = provider or settings.web_search_provider
    return SEARCH_PROVIDERS.get(key, duckduckgo_search)
