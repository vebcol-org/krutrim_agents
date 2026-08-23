"""RAG document ingestion: extracts, chunks, embeds, and indexes a single
document a user submitted (pasted text, or a `.txt` file's contents read
client-side — see `krutrim_agent_backend/api/sessions_routes.py`'s
`POST /{session_id}/rag/text`) into that session's faisslite index.

Same testable-core-plus-thin-wrapper shape as `precompute_embeddings.py`, but
reports STAGE-level progress (`extracting`/`chunking`/`embedding`/`indexing`)
via `publish_job_stage_progress` rather than a bare processed/total count,
since a single document's ingestion doesn't have a natural "N of M" unit the
way precompute's multi-file loop does.

`job_id` is `"{session_id}:rag:{document_id}"` — per-document, unlike
`/embed`'s single `"{session_id}:embed"` — since a session can ingest
multiple RAG documents over time and each needs its own progress stream.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

import numpy as np
from krutrim_agent_management.config import settings
from krutrim_agent_management.storage_factory import create_storage
from krutrim_agent_rag.chunking import chunk_text
from krutrim_agent_rag.embeddings import open_index
from krutrim_agent_rag.embeddings_provider import default_embed as _default_embed
from krutrim_agent_sandbox.status_channel import (
    RedisPubSubBackend,
    publish_job_stage_progress,
)

from krutrim_agent_celery.app import celery_app

if TYPE_CHECKING:
    from krutrim_agent_management.base import Storage

STAGE_EXTRACTING = "extracting"
STAGE_CHUNKING = "chunking"
STAGE_EMBEDDING = "embedding"
STAGE_INDEXING = "indexing"


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
    mirror (by the `/rag/text` route, before this task is dispatched).

    v1 scope is text-only, per product decision — a non-UTF-8 blob is
    reported as an error result rather than silently mangled via
    `errors="replace"` (unlike `precompute_embeddings_once`, which tolerates
    replacement chars for arbitrary file-path ingestion; a document a user
    explicitly submitted through the text-ingestion flow should always
    decode cleanly, so a decode failure signals something genuinely wrong).
    """

    def _report(stage: str, processed: int, total: int) -> None:
        if on_progress is not None:
            on_progress(stage, processed, total)

    _report(STAGE_EXTRACTING, 0, 1)
    content = await store.read_workspace_file(session_id, source_path)
    if content is None:
        return {"status": "error", "error": f"No content found at '{source_path}'."}
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        return {
            "status": "error",
            "error": "Document is not valid UTF-8 text (v1 supports text only).",
        }
    _report(STAGE_EXTRACTING, 1, 1)

    _report(STAGE_CHUNKING, 0, 1)
    chunks = chunk_text(text)
    _report(STAGE_CHUNKING, 1, 1)

    if not chunks:
        return {"status": "ok", "chunks_added": 0}

    _report(STAGE_EMBEDDING, 0, 1)
    vectors = embed_fn(chunks)
    _report(STAGE_EMBEDDING, 1, 1)

    _report(STAGE_INDEXING, 0, 1)
    embeddings_dir = store.session_dir(session_id) / "embeddings"
    index = open_index(embeddings_dir, dim=vectors.shape[1])
    index.add(
        vectors,
        source=source_path,
        texts=chunks,
    )
    index.save()
    _report(STAGE_INDEXING, 1, 1)

    return {
        "status": "ok",
        "document_id": document_id,
        "title": title,
        "chunks_added": len(chunks),
    }


@celery_app.task(name="krutrim_agent_celery.process_rag_document")
def process_rag_document(
    session_id: str, document_id: str, source_path: str, title: str | None = None
) -> dict:
    pubsub = RedisPubSubBackend(settings.redis_url)
    job_id = f"{session_id}:rag:{document_id}"

    def on_progress(stage: str, processed: int, total: int) -> None:
        # Live status is best-effort — a Redis hiccup must never fail the
        # actual ingestion job.
        try:
            publish_job_stage_progress(pubsub, job_id, stage, processed, total)
        except Exception:  # noqa: BLE001
            pass

    return asyncio.run(
        process_rag_document_once(
            create_storage(settings),
            session_id=session_id,
            document_id=document_id,
            source_path=source_path,
            title=title,
            on_progress=on_progress,
        )
    )
