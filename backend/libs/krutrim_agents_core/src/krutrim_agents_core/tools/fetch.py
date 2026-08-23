"""Fetch a URL's content as plain text/markdown."""

from __future__ import annotations

import html2text
import httpx
from langchain_core.tools import tool

MAX_FETCH_CHARS = 8_000
FETCH_TIMEOUT_SECONDS = 15


@tool
async def fetch_url(url: str) -> str:
    """Fetch a web page and return its content as plain text/markdown.

    Use this to read a specific source in full after finding it via
    `web_search` (or when the user gives you a URL directly).
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                url,
                timeout=FETCH_TIMEOUT_SECONDS,
                headers={"User-Agent": "Mozilla/5.0 (krutrim-agent)"},
            )
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - surfaced as a tool-visible error, not a crash
        return f"Error: could not fetch '{url}' ({exc})."

    converter = html2text.HTML2Text()
    converter.ignore_images = True
    converter.ignore_links = False
    converter.body_width = 0
    text = converter.handle(response.text).strip()

    if len(text) > MAX_FETCH_CHARS:
        text = (
            text[:MAX_FETCH_CHARS]
            + "\n\n[Truncated - page content exceeded the fetch limit.]"
        )
    return text
