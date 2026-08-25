"""Session-scoped embedding-index I/O behind a swappable `VectorStore` interface.

`FaissliteVectorStore` and `QdrantVectorStore` (`qdrant_store.py`) are the two
implementations. Chunking/embedding happens in `chunking.py`/`embeddings_provider.py`
and the celery ingestion tasks that call them, never here — this module is
deliberately I/O-only: open/save/add/get/search/delete/scroll.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from faisslite import Store

from krutrim_agent_rag.models import StoredChunk
from krutrim_agent_rag.vector_store_factory import (
    create_vector_store,
    register_vector_store_backend,
)

if TYPE_CHECKING:
    import numpy as np

__all__ = [
    "FaissliteVectorStore",
    "StoredChunk",
    "VectorStore",
    "index_exists",
    "open_index",
]


class VectorStore(ABC):
    """The base vectordb interface every backend (faisslite, Qdrant, ...)
    implements. Returns `StoredChunk` — never a backend-specific type — so
    callers (`retrieval.py`, `retrieval_strategy.py`) work unchanged
    regardless of which backend is active."""

    @abstractmethod
    def add(self, vectors: np.ndarray, *, source: str, texts: list[str]) -> None: ...

    @abstractmethod
    def save(self) -> None: ...

    @abstractmethod
    def search(
        self, query: np.ndarray, k: int = 5, *, source: str | None = None
    ) -> list[StoredChunk]: ...

    @abstractmethod
    def get(self, id_: int | str) -> StoredChunk | None: ...

    @abstractmethod
    def delete(self, *, source: str) -> None:
        """Removes every chunk previously added with this `source`. Used for
        idempotent re-ingest (delete-then-add) when a document is re-uploaded."""

    @abstractmethod
    def scroll(self, *, batch_size: int = 256) -> Iterator[StoredChunk]:
        """Yields every live chunk in the store, for building a full-corpus
        index (e.g. BM25 in `retrieval_strategy.HybridStrategy`)."""


class FaissliteVectorStore(VectorStore):
    def __init__(self, store: Store) -> None:
        self._store = store

    def add(self, vectors: np.ndarray, *, source: str, texts: list[str]) -> None:
        self._store.add(vectors, source=source, texts=texts)

    def save(self) -> None:
        self._store.save()

    def search(
        self, query: np.ndarray, k: int = 5, *, source: str | None = None
    ) -> list[StoredChunk]:
        hits = self._store.search(query, k=k, source=source)
        chunks: list[StoredChunk] = []
        for hit in hits:
            row = self._store.get(hit.id)
            if row is None or row.get("text") is None:
                continue
            chunks.append(
                StoredChunk(
                    id=hit.id,
                    text=row["text"],
                    source=row.get("source"),
                    score=hit.score,
                )
            )
        return chunks

    def get(self, id_: int | str) -> StoredChunk | None:
        row = self._store.get(id_)
        if row is None or row.get("text") is None:
            return None
        return StoredChunk(id=id_, text=row["text"], source=row.get("source"))

    def delete(self, *, source: str) -> None:
        ids = self._store.meta.live_ids(source=source)
        if ids:
            self._store.delete(list(ids))

    def scroll(self, *, batch_size: int = 256) -> Iterator[StoredChunk]:
        ids = sorted(self._store.meta.live_ids())
        for start in range(0, len(ids), batch_size):
            batch = ids[start : start + batch_size]
            rows = self._store.meta.get_many(batch)
            for id_ in batch:
                row = rows.get(id_)
                if row is None or row.get("text") is None:
                    continue
                yield StoredChunk(id=id_, text=row["text"], source=row.get("source"))

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
