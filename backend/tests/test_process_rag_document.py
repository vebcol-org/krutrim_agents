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
        title="Empty Doc",
        embed_fn=_fake_embed,
    )

    assert result == {
        "status": "ok",
        "document_id": "doc4",
        "title": "Empty Doc",
        "chunks_added": 0,
    }


async def test_process_rag_document_reingest_replaces_old_chunks():
    """Re-uploading the same document (same source_path) should replace its
    chunks, not duplicate them — delete-then-add keyed by source."""
    storage, session_id = await _make_session_with_file(
        "_rag_uploads/doc1.txt", b"version one " * 200
    )

    first = await process_rag_document_once(
        storage,
        session_id=session_id,
        document_id="doc1",
        source_path="_rag_uploads/doc1.txt",
        embed_fn=_fake_embed,
    )
    assert first["status"] == "ok"

    await storage.sync_workspace_from_container(
        session_id, [("_rag_uploads/doc1.txt", b"version two, shorter")]
    )
    second = await process_rag_document_once(
        storage,
        session_id=session_id,
        document_id="doc1",
        source_path="_rag_uploads/doc1.txt",
        embed_fn=_fake_embed,
    )
    assert second["status"] == "ok"

    embeddings_dir = storage.session_dir(session_id) / "embeddings"
    index = open_index(embeddings_dir)
    assert index.count() == second["chunks_added"]


async def test_process_rag_document_dispatches_extraction_through_parser_registry(
    monkeypatch,
):
    """`process_rag_document_once` delegates text extraction to
    `krutrim_agent_doc`'s parser registry rather than a bare UTF-8 decode —
    verified here against a fake registry so this test doesn't need a real
    PDF/docling model load."""
    import krutrim_agent_celery.tasks.process_rag_document as module
    from krutrim_agent_doc.base import ParsedDocument

    class FakeRegistry:
        def parse(self, data: bytes, *, file_name: str = "") -> ParsedDocument:
            return ParsedDocument(success=True, text="extracted via fake parser", parser_used="fake")

    monkeypatch.setattr(module, "default_registry", lambda: FakeRegistry())

    storage, session_id = await _make_session_with_file(
        "_rag_uploads/doc1.pdf", b"%PDF-1.4 fake bytes"
    )

    result = await process_rag_document_once(
        storage,
        session_id=session_id,
        document_id="doc1",
        source_path="_rag_uploads/doc1.pdf",
        embed_fn=_fake_embed,
    )

    assert result["status"] == "ok"
    assert result["chunks_added"] == 1

    embeddings_dir = storage.session_dir(session_id) / "embeddings"
    index = open_index(embeddings_dir)
    hits = index.search(_fake_embed(["extracted via fake parser"]), k=1)
    assert hits[0].text == "extracted via fake parser"


async def test_process_rag_document_parser_failure_returns_error(monkeypatch):
    import krutrim_agent_celery.tasks.process_rag_document as module
    from krutrim_agent_doc.base import ParsedDocument

    class FailingRegistry:
        def parse(self, data: bytes, *, file_name: str = "") -> ParsedDocument:
            return ParsedDocument(success=False, error="could not parse this format")

    monkeypatch.setattr(module, "default_registry", lambda: FailingRegistry())

    storage, session_id = await _make_session_with_file(
        "_rag_uploads/doc1.xyz", b"whatever"
    )

    result = await process_rag_document_once(
        storage,
        session_id=session_id,
        document_id="doc1",
        source_path="_rag_uploads/doc1.xyz",
        embed_fn=_fake_embed,
    )

    assert result == {"status": "error", "error": "could not parse this format"}
