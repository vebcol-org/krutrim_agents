"""Session-scoped embedding-index I/O behind a swappable `VectorStore` interface.

`FaissliteVectorStore` is the only implementation today. Chunking/embedding
happens in `chunking.py`/`embeddings_provider.py` and the celery ingestion
tasks that call them, never here — this module is deliberately I/O-only:
open/save/add/search.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from faisslite import Store
from faisslite.store import SearchResult

from krutrim_agent_rag.vector_store_factory import (
    create_vector_store,
    register_vector_store_backend,
)

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "FaissliteVectorStore",
    "SearchResult",
    "VectorStore",
    "index_exists",
    "open_index",
]


class VectorStore(ABC):
    """`add`/`save`/`search` are the ops callers use directly; `FaissliteVectorStore`
    exposes faisslite's full API (count/get/...) via attribute delegation beyond that."""

    @abstractmethod
    def add(self, vectors: "np.ndarray", *, source: str, texts: list[str]) -> None: ...

    @abstractmethod
    def save(self) -> None: ...

    @abstractmethod
    def search(
        self, query: "np.ndarray", k: int = 5, *, source: str | None = None
    ) -> list[SearchResult]: ...


class FaissliteVectorStore(VectorStore):
    def __init__(self, store: Store) -> None:
        self._store = store

    def add(self, vectors: "np.ndarray", *, source: str, texts: list[str]) -> None:
        self._store.add(vectors, source=source, texts=texts)

    def save(self) -> None:
        self._store.save()

    def search(
        self, query: "np.ndarray", k: int = 5, *, source: str | None = None
    ) -> list[SearchResult]:
        return self._store.search(query, k=k, source=source)

    def __getattr__(self, name: str):
        return getattr(self._store, name)


def _open_faisslite_store(
    embeddings_dir: Path, *, dim: int | None = None, algorithm: str = "flat"
) -> VectorStore:
    return FaissliteVectorStore(
        Store(
            namespace=embeddings_dir.name,
            path=embeddings_dir,
            dim=dim,
            algorithm=algorithm,
        )
    )


register_vector_store_backend("faisslite", _open_faisslite_store)


def open_index(
    embeddings_dir: Path, *, dim: int | None = None, algorithm: str = "flat"
) -> VectorStore:
    """Opens (or creates) the vector store at `embeddings_dir`. `dim` is required the
    first time; inferred from disk afterwards."""
    return create_vector_store(embeddings_dir, dim=dim, algorithm=algorithm)


def index_exists(embeddings_dir: Path) -> bool:
    return (embeddings_dir / "index.faiss").exists()
