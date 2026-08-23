from __future__ import annotations

import pytest
from krutrim_agent_management.config import settings
from krutrim_agent_rag.embeddings import FaissliteVectorStore
from krutrim_agent_rag.vector_store_factory import _registry as _vector_store_registry
from krutrim_agent_rag.vector_store_factory import (
    create_vector_store,
    register_vector_store_backend,
)


def test_create_vector_store_default_resolves_to_faisslite(tmp_path):
    store = create_vector_store(tmp_path / "embeddings", dim=4)
    assert isinstance(store, FaissliteVectorStore)


def test_create_vector_store_unknown_backend_raises_keyerror(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "vector_store_backend", "_nonexistent")
    with pytest.raises(KeyError):
        create_vector_store(tmp_path / "embeddings", dim=4)


def test_create_vector_store_resolves_a_newly_registered_backend(tmp_path, monkeypatch):
    register_vector_store_backend(
        "_test_fake_vector_store",
        lambda embeddings_dir, *, dim=None, algorithm="flat": "fake-store",
    )
    try:
        monkeypatch.setattr(settings, "vector_store_backend", "_test_fake_vector_store")
        assert create_vector_store(tmp_path / "embeddings", dim=4) == "fake-store"
    finally:
        _vector_store_registry.discard("_test_fake_vector_store")
