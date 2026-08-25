"""Tests for `krutrim_agent_rag/qdrant_store.py` — run against Qdrant's
in-process `:memory:` mode, so no real Qdrant server is needed."""

from __future__ import annotations

import numpy as np
import pytest
from krutrim_agent_management.config import settings
from krutrim_agent_rag.vector_store_factory import (
    _registry as _vector_store_registry,
)
from krutrim_agent_rag.vector_store_factory import create_vector_store


@pytest.fixture(autouse=True)
def _use_in_memory_qdrant(monkeypatch):
    monkeypatch.setattr(settings, "qdrant_location", ":memory:")
    monkeypatch.setattr(settings, "vector_store_backend", "qdrant")


def _store(tmp_path, session_id="s1"):
    embeddings_dir = tmp_path / "sessions" / session_id / "embeddings"
    return create_vector_store(embeddings_dir, dim=4, algorithm="flat")


def test_create_vector_store_resolves_to_qdrant(tmp_path):
    from krutrim_agent_rag.qdrant_store import QdrantVectorStore

    store = _store(tmp_path)
    assert isinstance(store, QdrantVectorStore)


def test_add_search_get_roundtrip(tmp_path):
    store = _store(tmp_path)
    vectors = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype="float32")
    store.add(vectors, source="notes.txt", texts=["chunk one", "chunk two"])
    store.save()

    results = store.search(vectors[:1], k=1)
    assert len(results) == 1
    assert results[0].text == "chunk one"
    assert results[0].source == "notes.txt"

    fetched = store.get(results[0].id)
    assert fetched is not None
    assert fetched.text == "chunk one"


def test_search_filters_by_source(tmp_path):
    store = _store(tmp_path)
    vectors = np.array(
        [[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]],
        dtype="float32",
    )
    store.add(vectors[:2], source="a.txt", texts=["a1", "a2"])
    store.add(vectors[2:], source="b.txt", texts=["b1"])

    results = store.search(vectors[:1], k=10, source="b.txt")
    assert {r.source for r in results} == {"b.txt"}


def test_delete_by_source_removes_only_matching_chunks(tmp_path):
    store = _store(tmp_path)
    vectors = np.array(
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]],
        dtype="float32",
    )
    store.add(vectors[:2], source="a.txt", texts=["a1", "a2"])
    store.add(vectors[2:], source="b.txt", texts=["b1"])

    store.delete(source="a.txt")

    remaining = {chunk.source for chunk in store.scroll()}
    assert remaining == {"b.txt"}


def test_scroll_yields_every_chunk(tmp_path):
    store = _store(tmp_path)
    vectors = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype="float32")
    store.add(vectors, source="notes.txt", texts=["chunk one", "chunk two"])

    texts = {chunk.text for chunk in store.scroll(batch_size=1)}
    assert texts == {"chunk one", "chunk two"}


def test_search_on_missing_collection_returns_empty(tmp_path):
    store = _store(tmp_path, session_id="never-ingested")
    query = np.array([[1.0, 0.0, 0.0, 0.0]], dtype="float32")
    assert store.search(query, k=5) == []
    assert store.get(1) is None
    assert list(store.scroll()) == []


def test_reingest_is_idempotent_via_delete_then_add(tmp_path):
    store = _store(tmp_path)
    vectors = np.array([[1.0, 0.0, 0.0, 0.0]], dtype="float32")
    store.add(vectors, source="doc.txt", texts=["v1"])
    store.delete(source="doc.txt")
    store.add(vectors, source="doc.txt", texts=["v2"])

    chunks = list(store.scroll())
    assert [c.text for c in chunks] == ["v2"]


def test_qdrant_backend_is_registered():
    from krutrim_agent_rag import (
        qdrant_store,  # noqa: F401 - import triggers self-registration
    )

    assert "qdrant" in _vector_store_registry.all()
