"""Tests for `precompute_embeddings_once` — the testable core of the FAISS
embedding precompute task. Uses a real `LocalStorage(tmp_path)` and a real
faisslite index on disk (both fast, local, no network) but a fake
deterministic `embed_fn` so no real embedding model/API is needed.
"""

from __future__ import annotations

import numpy as np
from krutrim_agent_celery.tasks.precompute_embeddings import (
    chunk_text,
    precompute_embeddings_once,
)
from krutrim_agent_management import LocalStorage
from krutrim_agent_rag.embeddings import open_index


def _fake_embed(texts: list[str], dim: int = 4) -> np.ndarray:
    """Deterministic, hash-based — no real model, but varies per input like
    a real embedder would (so different chunks land at different points)."""
    out = np.zeros((len(texts), dim), dtype="float32")
    for i, text in enumerate(texts):
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        out[i] = rng.standard_normal(dim).astype("float32")
    return out


# -- chunk_text ---------------------------------------------------------------


def test_chunk_text_empty_string():
    assert chunk_text("") == []


def test_chunk_text_shorter_than_chunk_size_returns_single_chunk():
    assert chunk_text("hello world", chunk_size=1000) == ["hello world"]


def test_chunk_text_splits_with_overlap():
    text = "a" * 250
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)
    # consecutive chunks overlap by the requested amount
    assert chunks[0][-20:] == chunks[1][:20]


# -- precompute_embeddings_once ------------------------------------------------


async def _make_session_with_files(files: dict[str, bytes]):
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    storage = LocalStorage(tmp)
    project = await storage.create_project("P")
    agent = await storage.create_agent(project.project_id, "research", "Test Agent")
    session = await storage.create_session("agent", agent.agent_id)
    if files:
        await storage.sync_workspace_from_container(
            session.session_id, list(files.items())
        )
    return storage, session.session_id


async def test_precompute_embeddings_creates_index_and_reports_counts():
    storage, session_id = await _make_session_with_files(
        {"notes.txt": b"hello world", "report.md": b"a" * 2500}
    )

    result = await precompute_embeddings_once(
        storage,
        session_id=session_id,
        source_paths=["notes.txt", "report.md"],
        embed_fn=_fake_embed,
    )

    assert result["files_processed"] == 2
    assert result["chunks_added"] > 0

    embeddings_dir = storage.session_dir(session_id) / "embeddings"
    index = open_index(embeddings_dir)
    assert index.count() == result["chunks_added"]


async def test_precompute_embeddings_skips_missing_file_without_error():
    storage, session_id = await _make_session_with_files({"notes.txt": b"hello"})

    result = await precompute_embeddings_once(
        storage,
        session_id=session_id,
        source_paths=["notes.txt", "does-not-exist.txt"],
        embed_fn=_fake_embed,
    )

    assert result["files_processed"] == 2
    assert result["chunks_added"] == 1  # only notes.txt contributed


async def test_precompute_embeddings_empty_source_paths_creates_no_index():
    storage, session_id = await _make_session_with_files({})

    result = await precompute_embeddings_once(
        storage, session_id=session_id, source_paths=[], embed_fn=_fake_embed
    )

    assert result == {"files_processed": 0, "chunks_added": 0}
    embeddings_dir = storage.session_dir(session_id) / "embeddings"
    assert not (embeddings_dir / "index.faiss").exists()


async def test_precompute_embeddings_calls_on_progress_per_file():
    storage, session_id = await _make_session_with_files(
        {"a.txt": b"aaa", "b.txt": b"bbb"}
    )
    progress_calls: list[tuple[int, int]] = []

    await precompute_embeddings_once(
        storage,
        session_id=session_id,
        source_paths=["a.txt", "b.txt"],
        embed_fn=_fake_embed,
        on_progress=lambda processed, total: progress_calls.append((processed, total)),
    )

    assert progress_calls == [(1, 2), (2, 2)]
