"""DuckDuckGo-backed web search — zero-config, no API key required."""

from __future__ import annotations

import asyncio

from ddgs import DDGS
from langchain_core.tools import tool

MAX_SEARCH_RESULTS = 6


@tool
async def duckduckgo_search(query: str) -> str:
    """Search the web (via DuckDuckGo) and return titles, URLs, and snippets for the top results.

    Use a focused query (specific terms, not a broad topic) rather than a
    vague one. For anything load-bearing, follow up with `fetch_url` on the
    specific source instead of relying on the snippet alone.
    """
    try:
        results = await asyncio.to_thread(
            DDGS().text, query, max_results=MAX_SEARCH_RESULTS
        )
    except Exception as exc:  # noqa: BLE001 - surfaced as a tool-visible error, not a crash
        return f"Error: web search failed ({exc})."
    if not results:
        return "No results found."
    lines = []
    for i, r in enumerate(results, start=1):
        title = r.get("title", "(no title)")
        href = r.get("href", "")
        body = r.get("body", "")
        lines.append(f"{i}. {title}\n   {href}\n   {body}")
    return "\n".join(lines)
