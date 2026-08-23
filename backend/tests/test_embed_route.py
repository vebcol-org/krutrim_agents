"""Tests for `POST /api/sessions/{id}/embed` — the dispatch route.
`celery_client.send_task` is monkeypatched so this never needs a real Redis
broker or worker; the point of this route is correct argument marshalling,
not Celery's own delivery guarantees.
"""

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


def test_embed_with_explicit_source_paths_dispatches_task(client):
    session_id = _create_session(client)

    response = client.post(
        f"/api/sessions/{session_id}/embed",
        json={"source_paths": ["notes.txt", "report.md"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "queued",
        "task_id": "fake-task-id",
        "job_id": f"{session_id}:embed",
        "file_count": 2,
    }
    assert client.fake_celery.calls == [
        (
            "krutrim_agent_celery.precompute_embeddings",
            [session_id, ["notes.txt", "report.md"]],
        )
    ]


def test_embed_without_source_paths_defaults_to_workspace_mirror(client):
    session_id = _create_session(client)
    storage = client.app.state.storage
    asyncio.run(
        storage.sync_workspace_from_container(
            session_id, [("a.txt", b"x"), ("b.txt", b"y")]
        )
    )

    response = client.post(f"/api/sessions/{session_id}/embed", json={})

    assert response.status_code == 200
    assert response.json()["file_count"] == 2
    dispatched_paths = client.fake_celery.calls[0][1][1]
    assert sorted(dispatched_paths) == ["a.txt", "b.txt"]


def test_embed_unknown_session_returns_404(client):
    response = client.post("/api/sessions/nope/embed", json={})
    assert response.status_code == 404
    assert client.fake_celery.calls == []


def test_rag_text_dispatches_process_rag_document_task(client):
    session_id = _create_session(client)

    response = client.post(
        f"/api/sessions/{session_id}/rag/text",
        json={"text": "some pasted research notes", "title": "My Notes"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["task_id"] == "fake-task-id"
    document_id = body["document_id"]
    assert body["job_id"] == f"{session_id}:rag:{document_id}"

    [(task_name, args)] = client.fake_celery.calls
    assert task_name == "krutrim_agent_celery.process_rag_document"
    assert args == [
        session_id,
        document_id,
        f"_rag_uploads/{document_id}.txt",
        "My Notes",
    ]

    storage = client.app.state.storage
    written = asyncio.run(
        storage.read_workspace_file(session_id, f"_rag_uploads/{document_id}.txt")
    )
    assert written == b"some pasted research notes"


def test_rag_text_defaults_title_to_document_id(client):
    session_id = _create_session(client)

    response = client.post(
        f"/api/sessions/{session_id}/rag/text", json={"text": "notes"}
    )

    document_id = response.json()["document_id"]
    [(_, args)] = client.fake_celery.calls
    assert args[3] == document_id


def test_rag_text_rejects_empty_text(client):
    session_id = _create_session(client)

    response = client.post(f"/api/sessions/{session_id}/rag/text", json={"text": "   "})

    assert response.status_code == 400
    assert client.fake_celery.calls == []


def test_rag_text_unknown_session_returns_404(client):
    response = client.post("/api/sessions/nope/rag/text", json={"text": "notes"})
    assert response.status_code == 404
    assert client.fake_celery.calls == []
