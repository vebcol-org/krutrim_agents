"""Embedding precompute: chunks a session's source files, embeds them, and
adds the vectors to that session's faisslite index — giving an agent
RAG-style recall over documents too large to paste into a prompt directly.

`precompute_embeddings_once` is the testable core (plain async function,
injectable `embed_fn`/`on_progress`); `precompute_embeddings` is the thin
Celery-task wrapper using real dependencies, publishing each `on_progress`
call to Redis (`krutrim_agent_sandbox.status_channel`) under a `job_id` of
`"{session_id}:embed"` (session ids are globally unique — see
`krutrim_agent_management.base.Storage` — so no project qualifier is needed) — one
embed job per session at a time is enough for this first pass, so a
deterministic id (not a UUID) is fine and lets `krutrim_agent_backend`'s dispatch
route hand the same id back to the caller without round-tripping through
Celery's own result backend.

Chunking (`chunk_text`) and the default embedder now live in `krutrim_agent_rag`
— shared with `process_rag_document` (the raw-text ingestion task) so both
paths use identical chunking and, critically, the SAME embedding model. A
session's FAISS index holds vectors from whichever path(s) wrote to it; two
different embedding models in one index would silently corrupt retrieval
(cosine/L2 distances stop meaning anything across models), so this task's
default embedder is OpenRouter (`krutrim_agent_rag.embeddings_provider`)
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

import numpy as np
from krutrim_agent_management.config import settings
from krutrim_agent_management.storage_factory import create_storage
from krutrim_agent_rag.chunking import chunk_text
from krutrim_agent_rag.embeddings import open_index
from krutrim_agent_rag.embeddings_provider import default_embed as _default_embed
from krutrim_agent_sandbox.status_channel import (
    RedisPubSubBackend,
    publish_job_progress,
)
from loguru import logger

from krutrim_agent_celery.app import celery_app

if TYPE_CHECKING:
    from krutrim_agent_management.base import Storage

__all__ = ["chunk_text", "precompute_embeddings", "precompute_embeddings_once"]


async def precompute_embeddings_once(
    store: Storage,
    *,
    session_id: str,
    source_paths: Sequence[str],
    embed_fn: Callable[[list[str]], np.ndarray] = _default_embed,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Reads each of `source_paths` from the session's persisted workspace
    mirror, chunks it, embeds the chunks, and adds them to that session's
    faisslite index (created on first use, dim inferred from the first
    embedding batch). A `source_paths` entry with no matching workspace file
    is skipped, not an error — best-effort, matching the reaper's own
    "missing content just means nothing happens" convention.
    """
    total = len(source_paths)
    embeddings_dir = store.session_dir(session_id) / "embeddings"
    index = None
    chunks_added = 0
    logger.info(
        "precompute_embeddings: session={} processing {} source file(s)",
        session_id,
        total,
    )
    for processed, path in enumerate(source_paths, start=1):
        content = await store.read_workspace_file(session_id, path)
        if content is not None:
            text = content.decode("utf-8", errors="replace")
            chunks = chunk_text(text)
            if chunks:
                vectors = embed_fn(chunks)
                if index is None:
                    index = open_index(embeddings_dir, dim=vectors.shape[1])
                index.add(vectors, source=path, texts=chunks)
                chunks_added += len(chunks)
                logger.debug(
                    "precompute_embeddings: {} -> {} chunk(s) ({}/{})",
                    path,
                    len(chunks),
                    processed,
                    total,
                )
            else:
                logger.debug("precompute_embeddings: {} produced no chunks", path)
        else:
            logger.debug("precompute_embeddings: no workspace file at {} — skipped", path)
        if on_progress is not None:
            on_progress(processed, total)
    if index is not None:
        index.save()
    logger.info(
        "precompute_embeddings: session={} done — {} file(s), {} chunk(s) added",
        session_id,
        total,
        chunks_added,
    )
    return {"files_processed": total, "chunks_added": chunks_added}


@celery_app.task(name="krutrim_agent_celery.precompute_embeddings")
def precompute_embeddings(session_id: str, source_paths: list[str]) -> dict:
    pubsub = RedisPubSubBackend(settings.redis_url)
    job_id = f"{session_id}:embed"

    def on_progress(processed: int, total: int) -> None:
        # Live status is best-effort — a Redis hiccup must never fail the
        # actual embedding job.
        try:
            publish_job_progress(pubsub, job_id, processed, total)
        except Exception:  # noqa: BLE001
            pass

    return asyncio.run(
        precompute_embeddings_once(
            create_storage(settings),
            session_id=session_id,
            source_paths=source_paths,
            on_progress=on_progress,
        )
    )
