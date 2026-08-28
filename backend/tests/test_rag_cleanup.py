from __future__ import annotations

from krutrim_agent_management import LocalStorage
from krutrim_agent_management.config import settings
from krutrim_agent_management.hooks import _session_delete_hooks
from krutrim_agent_rag import cleanup


def test_importing_cleanup_registers_the_session_delete_hook():
    assert cleanup.drop_session_vectors in _session_delete_hooks


def test_drop_session_vectors_removes_faiss_index_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    monkeypatch.setattr(settings, "vector_store_backend", "faisslite")

    embeddings_dir = tmp_path / "sessions" / "sess-1" / "embeddings"
    embeddings_dir.mkdir(parents=True)
    (embeddings_dir / "index.faiss").write_bytes(b"stub")

    cleanup.drop_session_vectors("sess-1")

    assert not embeddings_dir.exists()


def test_drop_session_vectors_is_a_noop_when_nothing_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    monkeypatch.setattr(settings, "vector_store_backend", "faisslite")
    cleanup.drop_session_vectors("never-existed")  # must not raise


async def test_delete_session_runs_the_vector_cleanup_hook(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    monkeypatch.setattr(settings, "vector_store_backend", "faisslite")

    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    chat = await storage.create_chat("C", "openrouter", settings.default_model, project.project_id)
    session = await storage.create_session("chat", chat.chat_id)

    embeddings_dir = storage.session_dir(session.session_id) / "embeddings"
    embeddings_dir.mkdir(parents=True)
    (embeddings_dir / "index.faiss").write_bytes(b"stub")

    await storage.delete_chat(chat.chat_id)

    assert not embeddings_dir.exists()
    assert not storage.session_dir(session.session_id).exists()
