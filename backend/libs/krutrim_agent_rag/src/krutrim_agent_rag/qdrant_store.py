"""Qdrant `VectorStore` backend — the second implementation alongside
`embeddings.FaissliteVectorStore`, satisfying the same ABC. Opt-in via
`.env`: `KRUTRIM_AGENT_VECTOR_STORE_BACKEND=qdrant` (default stays
"faisslite" — see `AppSettings.vector_store_backend`).

One Qdrant collection per session. `embeddings_dir` is always
`.../sessions/{session_id}/embeddings` (see `Storage.session_dir`), so
`embeddings_dir.name` is always literally `"embeddings"` — the collection
name must come from `embeddings_dir.parent.name` (the session id) instead,
to keep sessions isolated the way faisslite's per-directory index already does.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

from krutrim_agent_rag.embeddings import VectorStore
from krutrim_agent_rag.models import StoredChunk
from krutrim_agent_rag.vector_store_factory import register_vector_store_backend

if TYPE_CHECKING:
    import numpy as np
    from qdrant_client import QdrantClient


def _point_id(source: str, chunk_index: int) -> str:
    """Deterministic per-(source, chunk_index) id — re-ingesting the same
    document with the same chunk count overwrites its own points on `add`,
    and combined with `delete(source=...)` (called before re-ingest by
    `process_rag_document_once`) makes re-upload idempotent."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}:{chunk_index}"))


class QdrantVectorStore(VectorStore):
    def __init__(
        self, client: QdrantClient, *, collection_name: str, dim: int | None
    ) -> None:
        self._client = client
        self._collection = collection_name
        self._dim = dim

    def _ensure_collection(self, dim: int) -> None:
        from qdrant_client.models import Distance, VectorParams

        if self._client.collection_exists(self._collection):
            return
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

    def add(self, vectors: np.ndarray, *, source: str, texts: list[str]) -> None:
        from qdrant_client.models import PointStruct

        dim = self._dim or vectors.shape[1]
        self._ensure_collection(dim)
        points = [
            PointStruct(
                id=_point_id(source, i),
                vector=vector.tolist(),
                payload={"source": source, "text": text},
            )
            for i, (vector, text) in enumerate(zip(vectors, texts))
        ]
        self._client.upsert(collection_name=self._collection, points=points)

    def save(self) -> None:
        pass  # Qdrant persists on write; no explicit flush step needed.

    def search(
        self, query: np.ndarray, k: int = 5, *, source: str | None = None
    ) -> list[StoredChunk]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        if not self._client.collection_exists(self._collection):
            return []
        query_filter = (
            Filter(must=[FieldCondition(key="source", match=MatchValue(value=source))])
            if source
            else None
        )
        result = self._client.query_points(
            collection_name=self._collection,
            query=query[0].tolist(),
            limit=k,
            query_filter=query_filter,
        )
        return [
            StoredChunk(
                id=point.id,
                text=(point.payload or {}).get("text", ""),
                source=(point.payload or {}).get("source"),
                score=point.score,
            )
            for point in result.points
        ]

    def get(self, id_: int | str) -> StoredChunk | None:
        if not self._client.collection_exists(self._collection):
            return None
        records = self._client.retrieve(collection_name=self._collection, ids=[id_])
        if not records:
            return None
        record = records[0]
        return StoredChunk(
            id=record.id,
            text=(record.payload or {}).get("text", ""),
            source=(record.payload or {}).get("source"),
        )

    def delete(self, *, source: str) -> None:
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            FilterSelector,
            MatchValue,
        )

        if not self._client.collection_exists(self._collection):
            return
        self._client.delete(
            collection_name=self._collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="source", match=MatchValue(value=source))]
                )
            ),
        )

    def scroll(self, *, batch_size: int = 256) -> Iterator[StoredChunk]:
        if not self._client.collection_exists(self._collection):
            return
        offset = None
        while True:
            records, offset = self._client.scroll(
                collection_name=self._collection,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                yield StoredChunk(
                    id=record.id,
                    text=(record.payload or {}).get("text", ""),
                    source=(record.payload or {}).get("source"),
                )
            if offset is None:
                break


def _open_qdrant_store(
    embeddings_dir: Path, *, dim: int | None = None, algorithm: str = "flat"
) -> VectorStore:
    from krutrim_agent_management.config import settings
    from qdrant_client import QdrantClient

    if settings.qdrant_location:
        client = QdrantClient(location=settings.qdrant_location)
    else:
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            prefer_grpc=settings.qdrant_prefer_grpc,
            https=settings.qdrant_https,
        )
    collection_name = f"session_{embeddings_dir.parent.name}"
    return QdrantVectorStore(client, collection_name=collection_name, dim=dim)


register_vector_store_backend("qdrant", _open_qdrant_store)
