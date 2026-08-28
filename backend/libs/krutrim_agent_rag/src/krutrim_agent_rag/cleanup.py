"""Drop a session's vector index when its chat/session is deleted.

Importing this module registers `drop_session_vectors` as a
`krutrim_agent_management` session-delete hook, so it runs automatically
from `Storage.delete_session` — and therefore from the `delete_chat` /
`delete_project` cascades too. The FastAPI app imports it once at startup
(`krutrim_agent_backend.main`); nothing else needs to call it.

Which store to clean is read from config (`settings.vector_store_backend`):

  * "qdrant"    -> delete the per-session Qdrant collection
                   (`session_{session_id}`, matching `qdrant_store._open_qdrant_store`)
  * "faisslite" -> remove the on-disk `sessions/{session_id}/embeddings/` dir
                   (also covered by `Storage.delete_session`'s `rmtree`, done
                   here too so it works even if called on its own)

Everything is best-effort: a missing collection / directory / unreachable
Qdrant is logged, never raised — deletion must not be blocked by cleanup.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from krutrim_agent_management.config import settings
from krutrim_agent_management.hooks import register_session_delete_hook
from loguru import logger


def _session_embeddings_dir(session_id: str) -> Path:
    # Mirrors krutrim_agent_management.local._LocalStorageImpl.session_dir.
    return settings.storage_root / "sessions" / session_id / "embeddings"


def _qdrant_collection_name(session_id: str) -> str:
    # Mirrors krutrim_agent_rag.qdrant_store._open_qdrant_store, whose
    # embeddings_dir.parent.name is always the session id.
    return f"session_{session_id}"


def _drop_faiss_index(session_id: str) -> None:
    embeddings_dir = _session_embeddings_dir(session_id)
    if embeddings_dir.exists():
        shutil.rmtree(embeddings_dir, ignore_errors=True)
        logger.info("RAG cleanup: removed FAISS index dir {}", embeddings_dir)
    else:
        logger.debug("RAG cleanup: no FAISS index dir at {}", embeddings_dir)


def _drop_qdrant_collection(session_id: str) -> None:
    from qdrant_client import QdrantClient

    collection = _qdrant_collection_name(session_id)
    if settings.qdrant_location:
        client = QdrantClient(location=settings.qdrant_location)
    else:
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            prefer_grpc=settings.qdrant_prefer_grpc,
            https=settings.qdrant_https,
        )
    try:
        if client.collection_exists(collection):
            client.delete_collection(collection)
            logger.info("RAG cleanup: deleted Qdrant collection {}", collection)
        else:
            logger.debug("RAG cleanup: Qdrant collection {} not present", collection)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def drop_session_vectors(session_id: str) -> None:
    backend = settings.vector_store_backend
    logger.info(
        "RAG cleanup: dropping vector store for session {} (backend={})",
        session_id,
        backend,
    )
    try:
        if backend == "qdrant":
            _drop_qdrant_collection(session_id)
        else:
            _drop_faiss_index(session_id)
    except Exception as exc:  # noqa: BLE001 - best-effort, see module docstring
        logger.warning(
            "RAG cleanup: failed to drop vector store for session {}: {}",
            session_id,
            exc,
        )


register_session_delete_hook(drop_session_vectors)
