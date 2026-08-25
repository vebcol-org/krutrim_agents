from __future__ import annotations

import numpy as np
import pytest
from krutrim_agent_management.config import settings
from krutrim_agent_rag.retrieval_strategy import HybridStrategy, VectorOnlyStrategy
from krutrim_agent_rag.retrieval_strategy_factory import (
    _registry as _strategy_registry,
)
from krutrim_agent_rag.retrieval_strategy_factory import (
    create_retrieval_strategy,
    register_retrieval_strategy,
)
from krutrim_agent_rag.vector_store_factory import create_vector_store


def test_create_retrieval_strategy_default_resolves_to_vector_only():
    assert isinstance(create_retrieval_strategy(), VectorOnlyStrategy)


def test_create_retrieval_strategy_unknown_raises_keyerror(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_strategy", "_nonexistent")
    with pytest.raises(KeyError):
        create_retrieval_strategy()


def test_create_retrieval_strategy_resolves_hybrid(monkeypatch):
    monkeypatch.setattr(settings, "retrieval_strategy", "hybrid")
    assert isinstance(create_retrieval_strategy(), HybridStrategy)


def test_create_retrieval_strategy_resolves_a_newly_registered_strategy(monkeypatch):
    register_retrieval_strategy("_test_fake_strategy", lambda: "fake-strategy")
    try:
        monkeypatch.setattr(settings, "retrieval_strategy", "_test_fake_strategy")
        assert create_retrieval_strategy() == "fake-strategy"
    finally:
        _strategy_registry.discard("_test_fake_strategy")


def _fake_embed(dim: int):
    def embed(texts: list[str]) -> np.ndarray:
        # Every text embeds identically far from every stored vector, so
        # pure vector search never ranks the keyword-only match highly —
        # isolates the assertion to BM25's contribution.
        return np.tile(np.array([[0.0] * dim], dtype="float32"), (len(texts), 1))

    return embed


def test_hybrid_strategy_surfaces_keyword_match_vector_search_misses(tmp_path):
    embed_fn = _fake_embed(dim=4)
    store = create_vector_store(tmp_path / "embeddings", dim=4)

    # All vectors point away from the query embedding (all-zero) equally, so
    # ranking is driven entirely by BM25 term overlap in this test.
    vectors = np.array(
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]], dtype="float32"
    )
    store.add(
        vectors,
        source="doc.txt",
        texts=[
            "the quick brown fox",
            "quarterly revenue projections for the finance team",
            "unrelated filler text about gardening",
        ],
    )
    store.save()

    strategy = HybridStrategy(candidate_k=10)
    results = strategy.retrieve(store, "quarterly revenue", k=1, embed_fn=embed_fn)

    assert len(results) == 1
    assert "revenue" in results[0].text
