from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from krutrim_agent_backend.api import sessions_routes
from krutrim_agent_backend.api.sessions_routes import router as sessions_router
from krutrim_agent_management import LocalStorage


class FakeAsyncResult:
    id = "fake-task-id"


class FakeCeleryClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list]] = []

    def send_task(self, name, args=None, **kwargs):
        self.calls.append((name, args))
        return FakeAsyncResult()


@pytest.fixture
def client(tmp_path, monkeypatch):
    fake_client = FakeCeleryClient()
    monkeypatch.setattr(sessions_routes, "celery_client", fake_client)

    app = FastAPI()
    app.state.storage = LocalStorage(tmp_path)
    app.include_router(sessions_router)
    test_client = TestClient(app)
    test_client.fake_celery = fake_client
    return test_client


def _create_session(client: TestClient) -> str:
    storage = client.app.state.storage

    async def _create():
        project = await storage.create_project("P")
        agent = await storage.create_agent(project.project_id, "research", "Test Agent")
        session = await storage.create_session("agent", agent.agent_id)
        return session.session_id

    return asyncio.run(_create())


def test_rag_file_dispatches_process_rag_document_task_and_preserves_extension(client):
    session_id = _create_session(client)

    response = client.post(
        f"/api/sessions/{session_id}/rag/file",
        files={"file": ("report.pdf", b"%PDF-1.4 fake bytes", "application/pdf")},
        data={"title": "Q3 Report"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    document_id = body["document_id"]
    assert body["job_id"] == f"{session_id}:rag:{document_id}"

    [(task_name, args)] = client.fake_celery.calls
    assert task_name == "krutrim_agent_celery.process_rag_document"
    assert args == [
        session_id,
        document_id,
        f"_rag_uploads/{document_id}.pdf",
        "Q3 Report",
    ]

    storage = client.app.state.storage
    written = asyncio.run(
        storage.read_workspace_file(session_id, f"_rag_uploads/{document_id}.pdf")
    )
    assert written == b"%PDF-1.4 fake bytes"


def test_rag_file_defaults_title_to_filename(client):
    session_id = _create_session(client)

    response = client.post(
        f"/api/sessions/{session_id}/rag/file",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )

    [(_, args)] = client.fake_celery.calls
    assert args[3] == "notes.txt"


def test_rag_file_rejects_empty_upload(client):
    session_id = _create_session(client)

    response = client.post(
        f"/api/sessions/{session_id}/rag/file",
        files={"file": ("empty.txt", b"", "text/plain")},
    )

    assert response.status_code == 400
    assert client.fake_celery.calls == []


def test_rag_file_rejects_oversized_upload(client, monkeypatch):
    monkeypatch.setattr(sessions_routes, "_MAX_RAG_UPLOAD_BYTES", 10)
    session_id = _create_session(client)

    response = client.post(
        f"/api/sessions/{session_id}/rag/file",
        files={"file": ("big.txt", b"x" * 100, "text/plain")},
    )

    assert response.status_code == 413
    assert client.fake_celery.calls == []


def test_rag_file_unknown_session_returns_404(client):
    response = client.post(
        "/api/sessions/nope/rag/file",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 404
    assert client.fake_celery.calls == []
