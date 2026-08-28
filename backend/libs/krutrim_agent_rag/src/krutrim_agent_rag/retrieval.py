"""Top-k retrieval over a session's vector index — the shared core behind both
`tool.rag_tool` (agent-initiated) and `middleware.RagInjectionMiddleware`
(opt-in silent injection). The actual "how do we rank" logic lives in
`retrieval_strategy.py` (vector-only vs. hybrid) — this module only resolves
the session's index and dispatches to whichever strategy is configured."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import numpy as np
from krutrim_agent_management.config import settings
from loguru import logger

from krutrim_agent_rag.embeddings import index_exists, open_index
from krutrim_agent_rag.embeddings_provider import default_embed
from krutrim_agent_rag.models import RetrievedChunk
from krutrim_agent_rag.retrieval_strategy_factory import create_retrieval_strategy

if TYPE_CHECKING:
    from krutrim_agent_management.base import Storage

__all__ = ["RetrievedChunk", "retrieve"]


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
    backend = settings.vector_store_backend
    logger.debug(
        "rag.retrieve: session={} backend={} strategy={} k={} query={!r}",
        session_id,
        backend,
        settings.retrieval_strategy,
        k,
        query[:120],
    )
    if backend == "faisslite" and not index_exists(embeddings_dir):
        logger.debug("rag.retrieve: no FAISS index at {} yet — returning []", embeddings_dir)
        return []

    index = open_index(embeddings_dir)
    strategy = create_retrieval_strategy()
    chunks = strategy.retrieve(index, query, k=k, embed_fn=embed_fn)
    logger.info(
        "rag.retrieve: session={} returned {} chunk(s) (backend={}, strategy={})",
        session_id,
        len(chunks),
        backend,
        settings.retrieval_strategy,
    )
    return chunks
