"""Web-search tool providers. `web_search` resolves to the configured default."""

from __future__ import annotations

from .duckduckgo import duckduckgo_search
from .registry import SEARCH_PROVIDERS, get_web_search_tool
from .tavily import tavily_search

web_search = get_web_search_tool()

__all__ = [
    "SEARCH_PROVIDERS",
    "duckduckgo_search",
    "get_web_search_tool",
    "tavily_search",
    "web_search",
]
