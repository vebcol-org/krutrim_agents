"""Tavily-backed web search — higher-quality, requires `TAVILY_API_KEY`.

Written as a plain `@tool` function against `tavily-python`'s
`AsyncTavilyClient` directly (not `langchain-tavily`'s `TavilySearch` class),
matching this module's existing convention (`duckduckgo.py`, `fetch.py`) of
hand-written async tools with a consistent numbered-result text shape, rather
than adopting a framework-provided tool wrapper with its own output format.
"""

from __future__ import annotations

import os

from langchain_core.tools import tool

MAX_SEARCH_RESULTS = 6
TAVILY_SEARCH_API_BASE = os.getenv("TAVILY_SEARCH_API_BASE") or "https://api.tavily.com"


@tool
async def tavily_search(query: str) -> str:
    """Search the web (via Tavily) and return titles, URLs, and snippets for the top results.

    Higher-quality, AI-oriented search results than `duckduckgo_search` —
    requires the `TAVILY_API_KEY` environment variable to be set. Use a
    focused query (specific terms, not a broad topic) rather than a vague
    one. For anything load-bearing, follow up with `fetch_url` on the
    specific source instead of relying on the snippet alone.
    """
    api_key = os.environ.get("TAVILY_API_KEY") or ""
    if not api_key:
        return "Error: Tavily search is not configured (TAVILY_API_KEY is not set)."

    try:
        from tavily import (
            AsyncTavilyClient,
        )  # deferred: only paid/opt-in when actually used

        client = AsyncTavilyClient(api_key=api_key, api_base_url=TAVILY_SEARCH_API_BASE)
        response = await client.search(query, max_results=MAX_SEARCH_RESULTS)
    except Exception as exc:  # noqa: BLE001 - surfaced as a tool-visible error, not a crash
        return f"Error: web search failed ({exc})."

    results = response.get("results") or []
    if not results:
        return "No results found."
    lines = []
    for i, r in enumerate(results, start=1):
        title = r.get("title", "(no title)")
        href = r.get("url", "")
        body = r.get("content", "")
        lines.append(f"{i}. {title}\n   {href}\n   {body}")
    return "\n".join(lines)
