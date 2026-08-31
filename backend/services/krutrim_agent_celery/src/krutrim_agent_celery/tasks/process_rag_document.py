

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

import numpy as np
import redis
from krutrim_agent_doc.registry import default_registry
from krutrim_agent_management.config import settings
from krutrim_agent_management.storage_factory import create_storage
from krutrim_agent_rag.chunking import chunk_text
from krutrim_agent_rag.embeddings import open_index
from krutrim_agent_rag.embeddings_provider import default_embed as _default_embed
from krutrim_agent_sandbox.status_channel import (
    RedisPubSubBackend,
    publish_job_error,
    publish_job_stage_progress,
)
from loguru import logger

from krutrim_agent_celery.app import celery_app

if TYPE_CHECKING:
    from krutrim_agent_management.base import Storage

STAGE_EXTRACTING = "extracting"
STAGE_CHUNKING = "chunking"
STAGE_EMBEDDING = "embedding"
STAGE_INDEXING = "indexing"

# Cluster-wide mutex serializing the heavy extract/chunk/embed/index body
# across every `process_rag_document` run, regardless of worker concurrency
# — see the module docstring for why. `timeout` is a safety net (auto-expires
# if a worker dies mid-task, e.g. OOM-killed on a large PDF) rather than the
# expected path; the lock is always released in a `finally` block.
_RAG_INGESTION_LOCK_KEY = "krutrim_agent_celery:rag_ingestion_lock"
_RAG_INGESTION_LOCK_TIMEOUT_SECONDS = 600
_RAG_INGESTION_RETRY_COUNTDOWN_SECONDS = 3


async def process_rag_document_once(
    store: Storage,
    *,
    session_id: str,
    document_id: str,
    source_path: str,
    title: str | None = None,
    embed_fn: Callable[[list[str]], np.ndarray] = _default_embed,
    on_progress: Callable[[str, int, int], None] | None = None,
) -> dict:
    """Ingests one document already written into the session's workspace
    mirror (by the `/rag/text` or `/rag/file` route, before this task is
    dispatched). Text extraction is delegated to
    `krutrim_agent_doc.registry.default_registry()`, dispatched by
    `source_path`'s extension — `.txt`/`.md` decode directly, PDF/DOCX go
    through docling. A parser failure (including plain-text's non-UTF-8 case)
    is reported as an error result, not silently mangled.

    Delete-then-add on `source_path` makes re-ingesting the same document
    (e.g. a re-upload) idempotent — old chunks for this source are replaced,
    not duplicated.
    """

    def _report(stage: str, processed: int, total: int) -> None:
        logger.debug(
            "process_rag_document[{}]: stage={} {}/{}", document_id, stage, processed, total
        )
        if on_progress is not None:
            on_progress(stage, processed, total)

    logger.info(
        "process_rag_document[{}]: start session={} source={} title={!r}",
        document_id,
        session_id,
        source_path,
        title,
    )

    _report(STAGE_EXTRACTING, 0, 1)
    content = await store.read_workspace_file(session_id, source_path)
    if content is None:
        logger.warning(
            "process_rag_document[{}]: no content at {!r} — aborting", document_id, source_path
        )
        return {"status": "error", "error": f"No content found at '{source_path}'."}
    parsed = default_registry().parse(content, file_name=source_path)
    if not parsed.success:
        logger.warning(
            "process_rag_document[{}]: parse failed: {}", document_id, parsed.error
        )
        return {"status": "error", "error": parsed.error or "Failed to parse document."}
    text = parsed.text
    logger.debug(
        "process_rag_document[{}]: extracted {} chars from {} bytes",
        document_id,
        len(text),
        len(content),
    )
    _report(STAGE_EXTRACTING, 1, 1)

    _report(STAGE_CHUNKING, 0, 1)
    chunks = chunk_text(text)
    _report(STAGE_CHUNKING, 1, 1)
    logger.info("process_rag_document[{}]: chunked into {} chunk(s)", document_id, len(chunks))

    if not chunks:
        logger.info("process_rag_document[{}]: nothing to index (0 chunks)", document_id)
        return {
            "status": "ok",
            "document_id": document_id,
            "title": title,
            "chunks_added": 0,
        }

    _report(STAGE_EMBEDDING, 0, 1)
    vectors = embed_fn(chunks)
    _report(STAGE_EMBEDDING, 1, 1)

    _report(STAGE_INDEXING, 0, 1)
    embeddings_dir = store.session_dir(session_id) / "embeddings"
    index = open_index(embeddings_dir, dim=vectors.shape[1])
    index.delete(source=source_path)
    index.add(
        vectors,
        source=source_path,
        texts=chunks,
    )
    index.save()
    _report(STAGE_INDEXING, 1, 1)
    logger.info(
        "process_rag_document[{}]: indexed {} chunk(s) (dim={}) for session {}",
        document_id,
        len(chunks),
        vectors.shape[1],
        session_id,
    )

    return {
        "status": "ok",
        "document_id": document_id,
        "title": title,
        "chunks_added": len(chunks),
    }


@celery_app.task(
    bind=True, name="krutrim_agent_celery.process_rag_document", max_retries=None
)
def process_rag_document(
    self, session_id: str, document_id: str, source_path: str, title: str | None = None
) -> dict:
    """`bind=True`/`max_retries=None`: on a lock miss, this retries itself
    indefinitely (with a short countdown) rather than blocking — that
    releases the worker slot immediately instead of tying it up waiting, so
    other task types (`precompute_embeddings`) on the same worker aren't
    starved by a deep RAG-ingestion queue."""
    redis_client = redis.Redis.from_url(settings.redis_url)
    lock = redis_client.lock(
        _RAG_INGESTION_LOCK_KEY, timeout=_RAG_INGESTION_LOCK_TIMEOUT_SECONDS
    )
    if not lock.acquire(blocking=False):
        logger.debug(
            "process_rag_document[{}]: ingestion lock held, retrying in {}s",
            document_id,
            _RAG_INGESTION_RETRY_COUNTDOWN_SECONDS,
        )
        raise self.retry(countdown=_RAG_INGESTION_RETRY_COUNTDOWN_SECONDS)

    try:
        pubsub = RedisPubSubBackend(settings.redis_url)
        job_id = f"{session_id}:rag:{document_id}"

        def on_progress(stage: str, processed: int, total: int) -> None:
            # Live status is best-effort — a Redis hiccup must never fail the
            # actual ingestion job.
            try:
                publish_job_stage_progress(pubsub, job_id, stage, processed, total)
            except Exception:  # noqa: BLE001
                pass

        result = asyncio.run(
            process_rag_document_once(
                create_storage(settings),
                session_id=session_id,
                document_id=document_id,
                source_path=source_path,
                title=title,
                on_progress=on_progress,
            )
        )
        if result.get("status") == "error":
            logger.warning(
                "process_rag_document[{}]: finished with error: {}",
                document_id,
                result.get("error"),
            )
            try:
                publish_job_error(
                    pubsub, job_id, result.get("error", "Ingestion failed.")
                )
            except Exception:  # noqa: BLE001 - best-effort, same as on_progress above
                pass
        else:
            logger.info(
                "process_rag_document[{}]: done ({} chunk(s) added)",
                document_id,
                result.get("chunks_added"),
            )
        return result
    finally:
        try:
            lock.release()
        except redis.exceptions.LockError:
            pass  # already expired (timeout) or released elsewhere — not fatal
