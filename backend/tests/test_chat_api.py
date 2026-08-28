from __future__ import annotations

import asyncio
import itertools
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from krutrim_agent_backend.api import chat_routes
from krutrim_agent_backend.api.chat_routes import CHAT_SESSION_EVENT
from krutrim_agent_backend.api.chat_routes import router as chat_router
from krutrim_agent_backend.api.chats_routes import router as chats_router
from krutrim_agent_backend.api.models_routes import router as models_router
from krutrim_agent_backend.api.projects_routes import router as projects_router
from krutrim_agent_backend.api.sessions_routes import router as sessions_router
from krutrim_agent_management import LocalStorage
from krutrim_agent_management.config import settings
from langchain_core.language_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

REPLY_TEXT = "Hello there friend"


def _fake_model_factory(_settings):
    # A real BaseChatModel so LangGraph's `stream_mode="messages"` actually
    # captures token deltas — a plain stub would only surface the whole reply.
    return GenericFakeChatModel(messages=itertools.repeat(AIMessage(content=REPLY_TEXT)))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(chat_routes, "build_chat_model", _fake_model_factory)

    app = FastAPI()
    app.state.storage = LocalStorage(tmp_path)
    app.include_router(projects_router)
    app.include_router(chats_router)
    app.include_router(sessions_router)
    app.include_router(chat_router)
    app.include_router(models_router)
    return TestClient(app)


def _parse_sse(text: str) -> list[dict]:
    events: list[dict] = []
    for block in text.strip().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[len("data:") :].strip()))
    return events


def send_chat(client: TestClient, *, message: str, **forwarded) -> dict:
    """POST /api/chat (RunAgentInput body, identity in forwardedProps) and fold
    the AG-UI SSE stream into an assertable summary."""
    run_input = {
        "threadId": forwarded.get("session_id") or "pending",
        "runId": "run-test",
        "state": {},
        "messages": [{"id": "u1", "role": "user", "content": message}],
        "tools": [],
        "context": [],
        "forwardedProps": {k: v for k, v in forwarded.items() if v is not None},
    }
    response = client.post("/api/chat", json=run_input)
    if response.status_code != 200:
        return {"status": response.status_code, "detail": response.json().get("detail")}

    events = _parse_sse(response.text)
    session_event = next(e for e in events if e.get("name") == CHAT_SESSION_EVENT)
    text = "".join(e["delta"] for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")
    return {
        "status": 200,
        "events": events,
        "types": [e["type"] for e in events],
        "chat_id": session_event["value"]["chat_id"],
        "session_id": session_event["value"]["session_id"],
        "text": text,
    }


def test_list_models_returns_catalog(client):
    response = client.get("/api/models")
    assert response.status_code == 200
    assert response.json() == [
        {
            "provider": "openrouter",
            "model": settings.default_model,
            "display_name": "DeepSeek V4 Flash (OpenRouter)",
        }
    ]


def test_first_message_creates_chat_and_session(client):
    result = send_chat(client, message="What's the capital of France?")

    assert result["status"] == 200
    assert result["types"][:2] == ["CUSTOM", "RUN_STARTED"]
    assert result["types"][-1] == "RUN_FINISHED"
    assert result["text"] == REPLY_TEXT
    # streamed, not delivered whole
    assert len([t for t in result["types"] if t == "TEXT_MESSAGE_CONTENT"]) > 1
    assert result["chat_id"] and result["session_id"]

    chat = client.get(f"/api/chats/{result['chat_id']}").json()
    assert chat["project_id"] is None
    assert chat["provider"] == "openrouter"
    assert chat["model"] == settings.default_model
    assert chat["display_name"] == "What's the capital of France?"

    sessions = client.get(f"/api/chats/{result['chat_id']}/sessions").json()
    assert [s["session_id"] for s in sessions] == [result["session_id"]]


def test_run_stats_and_token_usage_events_are_emitted(client):
    result = send_chat(client, message="hi")
    names = {e.get("name") for e in result["events"] if e["type"] == "CUSTOM"}
    assert CHAT_SESSION_EVENT in names
    assert "run_stats" in names  # TimingPlugin


def test_usage_json_accumulates_per_turn(client):
    first = send_chat(client, message="hi")
    send_chat(
        client,
        message="again",
        chat_id=first["chat_id"],
        session_id=first["session_id"],
    )
    storage = client.app.state.storage
    usage = asyncio.run(storage.read_usage(first["session_id"]))
    assert len(usage["turns"]) == 2


def test_second_message_reuses_chat_and_session_and_keeps_history(client):
    first = send_chat(client, message="hi")
    second = send_chat(
        client,
        message="follow up",
        chat_id=first["chat_id"],
        session_id=first["session_id"],
    )

    assert second["chat_id"] == first["chat_id"]
    assert second["session_id"] == first["session_id"]
    assert len(client.get("/api/chats").json()) == 1
    assert len(client.get(f"/api/chats/{first['chat_id']}/sessions").json()) == 1


def test_unknown_chat_id_returns_404(client):
    assert send_chat(client, message="hi", chat_id="does-not-exist")["status"] == 404


def test_unknown_session_id_returns_404(client):
    created = send_chat(client, message="hi")
    result = send_chat(
        client, message="hi again", chat_id=created["chat_id"], session_id="does-not-exist"
    )
    assert result["status"] == 404


def test_session_from_different_chat_returns_400(client):
    first = send_chat(client, message="hi")
    second = send_chat(client, message="hi 2")
    result = send_chat(
        client, message="cross", chat_id=first["chat_id"], session_id=second["session_id"]
    )
    assert result["status"] == 400


def test_unknown_model_returns_400(client):
    result = send_chat(client, message="hi", provider="openrouter", model="not-a-model")
    assert result["status"] == 400
    assert "Unknown chat model" in result["detail"]


def test_chat_created_within_project_via_project_id(client):
    storage = client.app.state.storage
    project_id = asyncio.run(storage.create_project("Proj")).project_id

    result = send_chat(client, message="hi", project_id=project_id)
    chat = client.get(f"/api/chats/{result['chat_id']}").json()
    assert chat["project_id"] == project_id


def test_create_project_via_api_creates_default_chat(client):
    response = client.post("/api/projects", json={"project_title": "Anthropic"})
    assert response.status_code == 200
    project_id = response.json()["project_id"]

    chats = client.get("/api/chats", params={"project_id": project_id}).json()
    assert len(chats) == 1
    assert chats[0]["display_name"] == "General"


def test_chat_crud_via_api(client):
    chat_id = send_chat(client, message="hi")["chat_id"]

    assert client.get(f"/api/chats/{chat_id}").json()["chat_id"] == chat_id

    assert client.delete(f"/api/chats/{chat_id}").status_code == 200
    assert client.get(f"/api/chats/{chat_id}").status_code == 404
    assert client.delete(f"/api/chats/{chat_id}").status_code == 404


def test_session_crud_via_api(client):
    created = send_chat(client, message="hi")
    session_id = created["session_id"]

    assert client.get(f"/api/sessions/{session_id}").status_code == 200

    assert client.delete(f"/api/sessions/{session_id}").status_code == 200
    assert client.get(f"/api/sessions/{session_id}").status_code == 404
    assert client.delete(f"/api/sessions/{session_id}").status_code == 404
    assert client.get("/api/chats/does-not-exist/sessions").status_code == 404


def test_session_messages_roundtrip(client):
    first = send_chat(client, message="hi")
    chat_id, session_id = first["chat_id"], first["session_id"]
    send_chat(client, message="follow up", chat_id=chat_id, session_id=session_id)

    response = client.get(f"/api/sessions/{session_id}/messages")
    assert response.status_code == 200
    assert response.json()["messages"] == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": REPLY_TEXT},
        {"role": "user", "content": "follow up"},
        {"role": "assistant", "content": REPLY_TEXT},
    ]


def test_session_messages_for_unknown_session_returns_404(client):
    assert client.get("/api/sessions/does-not-exist/messages").status_code == 404
