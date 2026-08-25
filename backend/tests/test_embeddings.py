"""Tests for `krutrim_agent_rag/embeddings.py` — pure I/O around a real
faisslite `Store` (no mocking needed; it's fast, local, no network)."""

from __future__ import annotations

import numpy as np
from krutrim_agent_rag.embeddings import index_exists, open_index


def test_index_does_not_exist_before_creation(tmp_path):
    embeddings_dir = tmp_path / "embeddings"
    assert index_exists(embeddings_dir) is False


def test_open_index_creates_and_persists(tmp_path):
    embeddings_dir = tmp_path / "embeddings"
    store = open_index(embeddings_dir, dim=4)
    vectors = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype="float32")
    store.add(vectors, source="notes.txt", texts=["chunk one", "chunk two"])
    store.save()

    assert index_exists(embeddings_dir) is True

    reopened = open_index(embeddings_dir)  # dim inferred from disk
    assert reopened.count() == 2
    results = reopened.search(vectors[0], k=1)
    assert reopened.get(results[0].id).text == "chunk one"


def test_delete_by_source_removes_only_matching_chunks(tmp_path):
    embeddings_dir = tmp_path / "embeddings"
    store = open_index(embeddings_dir, dim=4)
    vectors = np.array(
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]], dtype="float32"
    )
    store.add(vectors[:2], source="a.txt", texts=["a1", "a2"])
    store.add(vectors[2:], source="b.txt", texts=["b1"])

    store.delete(source="a.txt")

    remaining = {chunk.source for chunk in store.scroll()}
    assert remaining == {"b.txt"}


def test_scroll_yields_every_live_chunk(tmp_path):
    embeddings_dir = tmp_path / "embeddings"
    store = open_index(embeddings_dir, dim=4)
    vectors = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype="float32")
    store.add(vectors, source="notes.txt", texts=["chunk one", "chunk two"])

    texts = {chunk.text for chunk in store.scroll(batch_size=1)}
    assert texts == {"chunk one", "chunk two"}


def test_open_index_dim_required_for_new_store(tmp_path):
    embeddings_dir = tmp_path / "embeddings"
    try:
        open_index(embeddings_dir)
        raised = False
    except ValueError:
        raised = True
    assert raised
