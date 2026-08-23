"""Top-k retrieval over a session's FAISS index — the shared core behind both
`tool.rag_tool` (agent-initiated) and `middleware.RagInjectionMiddleware`
(opt-in silent injection)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from faisslite.exceptions import FaissliteError

from krutrim_agent_rag.embeddings import index_exists, open_index
from krutrim_agent_rag.embeddings_provider import default_embed

if TYPE_CHECKING:
    from krutrim_agent_management.base import Storage


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    source: str
    score: float


def retrieve(
    store: Storage,
    session_id: str,
    query: str,
    *,
    k: int = 5,
    embed_fn: Callable[[list[str]], np.ndarray] = default_embed,
) -> list[RetrievedChunk]:
    """Returns `[]` (not an error) if the session has no index yet, or the
    index has no live vectors — a research run early in its lifecycle,
    before anything's been ingested, is a normal state, not a failure."""
    embeddings_dir = store.session_dir(session_id) / "embeddings"
    if not index_exists(embeddings_dir):
        return []

    index = open_index(embeddings_dir)
    query_vector = embed_fn([query])

    try:
        hits = index.search(query_vector, k=k)
    except FaissliteError:
        return []

    chunks: list[RetrievedChunk] = []
    for hit in hits:
        row = index.get(hit.id)
        if row is None or row.get("text") is None:
            continue
        chunks.append(
            RetrievedChunk(
                text=row["text"], source=row.get("source") or "", score=hit.score
            )
        )
    return chunks
