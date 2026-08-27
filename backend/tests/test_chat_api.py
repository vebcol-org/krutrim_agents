from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from krutrim_agent_backend.api import chat_routes
from krutrim_agent_backend.api.chat_routes import router as chat_router
from krutrim_agent_backend.api.chats_routes import router as chats_router
from krutrim_agent_backend.api.models_routes import router as models_router
from krutrim_agent_backend.api.projects_routes import router as projects_router
from krutrim_agent_backend.api.sessions_routes import router as sessions_router
from krutrim_agent_management import LocalStorage
from krutrim_agent_management.config import settings
from langchain_core.messages import AIMessage


class FakeChatModel:
    """Stands in for a real provider's chat model — no network calls."""

    def __init__(self, reply_text: str = "Hello there!"):
        self.reply_text = reply_text
        self.invocations: list[list] = []

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, messages):
        self.invocations.append(messages)
        return AIMessage(
            content=self.reply_text,
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        )


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(
        chat_routes, "build_chat_model", lambda settings: FakeChatModel()
    )

    app = FastAPI()
    app.state.storage = LocalStorage(tmp_path)
    app.include_router(projects_router)
    app.include_router(chats_router)
    app.include_router(sessions_router)
    app.include_router(chat_router)
    app.include_router(models_router)
    return TestClient(app)


def test_list_models_returns_catalog(client):
    response = client.get("/api/models")
    assert response.status_code == 200
    models = response.json()
    assert models == [
        {
            "provider": "openrouter",
            "model": settings.default_model,
            "display_name": "DeepSeek V4 Flash (OpenRouter)",
        }
    ]


def test_first_message_creates_chat_and_session(client):
    response = client.post(
        "/api/chat", json={"message": "What's the capital of France?"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == {"role": "assistant", "content": "Hello there!"}
    assert body["chat_id"]
    assert body["session_id"]

    chat = client.get(f"/api/chats/{body['chat_id']}").json()
    assert chat["project_id"] is None
    assert chat["provider"] == "openrouter"
    assert chat["model"] == settings.default_model
    assert chat["display_name"] == "What's the capital of France?"

    sessions = client.get(f"/api/chats/{body['chat_id']}/sessions").json()
    assert [s["session_id"] for s in sessions] == [body["session_id"]]


def test_second_message_reuses_chat_and_session_and_keeps_history(client):
    first = client.post("/api/chat", json={"message": "hi"}).json()
    second = client.post(
        "/api/chat",
        json={
            "message": "follow up",
            "chat_id": first["chat_id"],
            "session_id": first["session_id"],
        },
    ).json()

    assert second["chat_id"] == first["chat_id"]
    assert second["session_id"] == first["session_id"]

    # both lists should still only have one entry each
    assert (
        len(client.get("/api/chats").json()) == 1
    )  # standalone chats (no project_id -> None)
    assert len(client.get(f"/api/chats/{first['chat_id']}/sessions").json()) == 1


def test_unknown_chat_id_returns_404(client):
    response = client.post(
        "/api/chat", json={"message": "hi", "chat_id": "does-not-exist"}
    )
    assert response.status_code == 404


def test_unknown_session_id_returns_404(client):
    created = client.post("/api/chat", json={"message": "hi"}).json()
    response = client.post(
        "/api/chat",
        json={
            "message": "hi again",
            "chat_id": created["chat_id"],
            "session_id": "does-not-exist",
        },
    )
    assert response.status_code == 404


def test_session_from_different_chat_returns_400(client):
    first = client.post("/api/chat", json={"message": "hi"}).json()
    second = client.post("/api/chat", json={"message": "hi 2"}).json()

    response = client.post(
        "/api/chat",
        json={
            "message": "cross",
            "chat_id": first["chat_id"],
            "session_id": second["session_id"],
        },
    )
    assert response.status_code == 400


def test_unknown_model_returns_400(client):
    response = client.post(
        "/api/chat",
        json={"message": "hi", "provider": "openrouter", "model": "not-a-model"},
    )
    assert response.status_code == 400
    assert "Unknown chat model" in response.json()["detail"]


def test_chat_created_within_project_via_project_id(client):
    storage = client.app.state.storage

    async def _create_project():
        return (await storage.create_project("Proj")).project_id

    project_id = asyncio.run(_create_project())

    response = client.post(
        "/api/chat", json={"message": "hi", "project_id": project_id}
    )
    body = response.json()
    chat = client.get(f"/api/chats/{body['chat_id']}").json()
    assert chat["project_id"] == project_id


def test_create_project_via_api_creates_default_chat(client):
    response = client.post("/api/projects", json={"project_title": "Anthropic"})
    assert response.status_code == 200
    project_id = response.json()["project_id"]

    chats = client.get("/api/chats", params={"project_id": project_id}).json()
    assert len(chats) == 1
    assert chats[0]["display_name"] == "General"


def test_chat_crud_via_api(client):
    created = client.post("/api/chat", json={"message": "hi"}).json()
    chat_id = created["chat_id"]

    assert client.get(f"/api/chats/{chat_id}").json()["chat_id"] == chat_id

    delete_response = client.delete(f"/api/chats/{chat_id}")
    assert delete_response.status_code == 200
    assert client.get(f"/api/chats/{chat_id}").status_code == 404
    assert client.delete(f"/api/chats/{chat_id}").status_code == 404


def test_session_crud_via_api(client):
    created = client.post("/api/chat", json={"message": "hi"}).json()
    chat_id, session_id = created["chat_id"], created["session_id"]

    assert client.get(f"/api/sessions/{session_id}").status_code == 200

    delete_response = client.delete(f"/api/sessions/{session_id}")
    assert delete_response.status_code == 200
    assert client.get(f"/api/sessions/{session_id}").status_code == 404
    assert client.delete(f"/api/sessions/{session_id}").status_code == 404
    assert client.get("/api/chats/does-not-exist/sessions").status_code == 404


def test_session_messages_roundtrip(client):
    first = client.post("/api/chat", json={"message": "hi"}).json()
    chat_id, session_id = first["chat_id"], first["session_id"]
    client.post(
        "/api/chat",
        json={"message": "follow up", "chat_id": chat_id, "session_id": session_id},
    )

    response = client.get(f"/api/sessions/{session_id}/messages")
    assert response.status_code == 200
    assert response.json()["messages"] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "Hello there!"},
        {"role": "user", "content": "follow up"},
        {"role": "assistant", "content": "Hello there!"},
    ]


def test_session_messages_for_unknown_session_returns_404(client):
    assert client.get("/api/sessions/does-not-exist/messages").status_code == 404
