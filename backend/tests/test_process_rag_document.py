"""Tests for `process_rag_document_once` — the testable core of the raw-text
RAG ingestion task. Uses a real `LocalStorage(tmp_path)` and a real faisslite
index on disk (both fast, local, no network) but a fake deterministic
`embed_fn` so no real embedding model/API is needed.
"""

from __future__ import annotations

import numpy as np
from krutrim_agent_celery.tasks.process_rag_document import process_rag_document_once
from krutrim_agent_management import LocalStorage
from krutrim_agent_rag.embeddings import open_index


def _fake_embed(texts: list[str], dim: int = 4) -> np.ndarray:
    out = np.zeros((len(texts), dim), dtype="float32")
    for i, text in enumerate(texts):
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        out[i] = rng.standard_normal(dim).astype("float32")
    return out


async def _make_session_with_file(path: str, content: bytes):
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    storage = LocalStorage(tmp)
    project = await storage.create_project("P")
    agent = await storage.create_agent(project.project_id, "research", "Test Agent")
    session = await storage.create_session("agent", agent.agent_id)
    await storage.sync_workspace_from_container(session.session_id, [(path, content)])
    return storage, session.session_id


async def test_process_rag_document_indexes_chunks_and_reports_progress():
    storage, session_id = await _make_session_with_file(
        "_rag_uploads/doc1.txt", b"hello world " * 200
    )
    stages: list[tuple[str, int, int]] = []

    result = await process_rag_document_once(
        storage,
        session_id=session_id,
        document_id="doc1",
        source_path="_rag_uploads/doc1.txt",
        title="My Notes",
        embed_fn=_fake_embed,
        on_progress=lambda stage, processed, total: stages.append(
            (stage, processed, total)
        ),
    )

    assert result["status"] == "ok"
    assert result["chunks_added"] > 0
    assert result["title"] == "My Notes"
    assert [s[0] for s in stages] == [
        "extracting",
        "extracting",
        "chunking",
        "chunking",
        "embedding",
        "embedding",
        "indexing",
        "indexing",
    ]

    embeddings_dir = storage.session_dir(session_id) / "embeddings"
    index = open_index(embeddings_dir)
    assert index.count() == result["chunks_added"]


async def test_process_rag_document_missing_source_returns_error():
    storage, session_id = await _make_session_with_file(
        "_rag_uploads/doc1.txt", b"hello"
    )

    result = await process_rag_document_once(
        storage,
        session_id=session_id,
        document_id="doc2",
        source_path="_rag_uploads/does-not-exist.txt",
        embed_fn=_fake_embed,
    )

    assert result["status"] == "error"


async def test_process_rag_document_rejects_non_utf8_content():
    storage, session_id = await _make_session_with_file(
        "_rag_uploads/doc1.txt", b"\xff\xfe\x00\x01"
    )

    result = await process_rag_document_once(
        storage,
        session_id=session_id,
        document_id="doc3",
        source_path="_rag_uploads/doc1.txt",
        embed_fn=_fake_embed,
    )

    assert result["status"] == "error"
    assert "UTF-8" in result["error"]


async def test_process_rag_document_empty_text_adds_no_chunks():
    storage, session_id = await _make_session_with_file("_rag_uploads/doc1.txt", b"")

    result = await process_rag_document_once(
        storage,
        session_id=session_id,
        document_id="doc4",
        source_path="_rag_uploads/doc1.txt",
        embed_fn=_fake_embed,
    )

    assert result == {"status": "ok", "chunks_added": 0}
