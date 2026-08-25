"""Pluggable retrieval strategy: vector-only (today's behavior) vs. hybrid
(vector + BM25, fused via reciprocal rank fusion).

Independent of `vector_store_factory`'s backend selection: that decides
*which database* stores vectors; this decides *how retrieval works* against
whichever store is active. Selected via `settings.retrieval_strategy`
through `retrieval_strategy_factory.create_retrieval_strategy()`.
`retrieval.py::retrieve()` is the only caller — `tool.py`/`middleware.py`
need no changes when the strategy changes.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np
from faisslite.exceptions import FaissliteError

from krutrim_agent_rag.embeddings_provider import default_embed
from krutrim_agent_rag.models import RetrievedChunk, StoredChunk
from krutrim_agent_rag.retrieval_strategy_factory import register_retrieval_strategy

if TYPE_CHECKING:
    from krutrim_agent_rag.embeddings import VectorStore

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _vector_search(
    store: VectorStore,
    query: str,
    *,
    k: int,
    embed_fn: Callable[[list[str]], np.ndarray],
) -> list[StoredChunk]:
    try:
        return store.search(embed_fn([query]), k=k)
    except FaissliteError:
        return []


class RetrievalStrategy(ABC):
    @abstractmethod
    def retrieve(
        self,
        store: VectorStore,
        query: str,
        *,
        k: int = 5,
        embed_fn: Callable[[list[str]], np.ndarray] = default_embed,
    ) -> list[RetrievedChunk]: ...


class VectorOnlyStrategy(RetrievalStrategy):
    def retrieve(
        self,
        store: VectorStore,
        query: str,
        *,
        k: int = 5,
        embed_fn: Callable[[list[str]], np.ndarray] = default_embed,
    ) -> list[RetrievedChunk]:
        hits = _vector_search(store, query, k=k, embed_fn=embed_fn)
        return [
            RetrievedChunk(
                text=hit.text, source=hit.source or "", score=hit.score or 0.0
            )
            for hit in hits
        ]


class HybridStrategy(RetrievalStrategy):
    """Vector search + BM25 over the store's full corpus,
    fused by reciprocal rank fusion (RRF) — no score-normalization tuning
    needed, unlike a weighted-alpha blend of two differently-scaled scores.
    """

    def __init__(self, *, candidate_k: int = 25, rrf_k: int = 60) -> None:
        self._candidate_k = candidate_k
        self._rrf_k = rrf_k

    def retrieve(
        self,
        store: VectorStore,
        query: str,
        *,
        k: int = 5,
        embed_fn: Callable[[list[str]], np.ndarray] = default_embed,
    ) -> list[RetrievedChunk]:
        vector_ranked = _vector_search(
            store, query, k=self._candidate_k, embed_fn=embed_fn
        )
        bm25_ranked = self._bm25_search(store, query, k=self._candidate_k)

        fused_scores: dict[Any, float] = {}
        chunks_by_id: dict[Any, StoredChunk] = {}
        for ranked in (vector_ranked, bm25_ranked):
            for rank, chunk in enumerate(ranked, start=1):
                fused_scores[chunk.id] = fused_scores.get(chunk.id, 0.0) + 1.0 / (
                    self._rrf_k + rank
                )
                chunks_by_id.setdefault(chunk.id, chunk)

        top_ids = sorted(fused_scores, key=lambda cid: fused_scores[cid], reverse=True)[
            :k
        ]
        return [
            RetrievedChunk(
                text=chunks_by_id[cid].text,
                source=chunks_by_id[cid].source or "",
                score=fused_scores[cid],
            )
            for cid in top_ids
        ]

    def _bm25_search(
        self, store: VectorStore, query: str, *, k: int
    ) -> list[StoredChunk]:
        from rank_bm25 import BM25Okapi

        corpus = list(store.scroll())
        if not corpus:
            return []

        bm25 = BM25Okapi([_tokenize(chunk.text) for chunk in corpus])
        scores = bm25.get_scores(_tokenize(query))
        ranked_indices = np.argsort(scores)[::-1][:k]
        return [corpus[i] for i in ranked_indices if scores[i] > 0]


register_retrieval_strategy("vector_only", VectorOnlyStrategy)
register_retrieval_strategy("hybrid", HybridStrategy)
