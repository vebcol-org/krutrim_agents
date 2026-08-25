"""Shared result types for `krutrim_agent_rag`.

`StoredChunk` replaces faisslite's own `SearchResult` as the `VectorStore`
ABC's return type, so a non-faisslite backend (e.g. Qdrant) never has to
import or construct a faisslite-specific class to satisfy the interface.

`RetrievedChunk` is the retrieval-layer output (`retrieval.py`,
`retrieval_strategy.py`) — score is required (not optional, unlike
`StoredChunk.score`, which is `None` for a bare `get()`/`scroll()` row with
no similarity score attached).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoredChunk:
    id: int | str
    text: str
    source: str | None
    score: float | None = None


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    source: str
    score: float
