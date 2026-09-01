"""`api/settings_routes.py` — the provider/model catalog + per-role selection.

No real LLM is touched: these routes only read the static catalog and
read/write the per-agent / per-session override JSON.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from krutrim_agent_backend.api.settings_routes import router as settings_router
from krutrim_agent_management import LocalStorage
from krutrim_agent_management.config import settings


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    app.state.storage = LocalStorage(tmp_path)
    app.include_router(settings_router)
    return TestClient(app)


async def _make_agent(storage: LocalStorage, agent_key: str = "research"):
    project = await storage.create_project("P")
    return await storage.create_agent(project.project_id, agent_key, "A")


def test_list_providers_and_models(client):
    providers = client.get("/api/providers").json()["providers"]
    assert any(p["key"] == "openrouter" for p in providers)

    models = client.get("/api/providers/models").json()["models"]
    assert models and all(m["kind"] == "chat" for m in models)

    embeddings = client.get("/api/providers/models", params={"kind": "embedding"}).json()
    assert all(m["kind"] == "embedding" for m in embeddings["models"])


def test_agent_role_defaults_then_override_then_reset(client):
    import asyncio

    agent = asyncio.run(_make_agent(client.app.state.storage))
    base = f"/api/providers/agents/{agent.agent_id}"

    roles = client.get(base).json()["roles"]
    by_role = {r["role"]: r for r in roles}
    assert by_role["main"]["source"] == "profile"
    assert by_role["main"]["settings"]["model"] == settings.default_model

    put = client.put(
        f"{base}/main",
        json={"provider": "openrouter", "model": "anthropic/claude-sonnet-4.5"},
    )
    assert put.status_code == 200
    main = next(r for r in put.json()["roles"] if r["role"] == "main")
    assert main["source"] == "agent"
    assert main["settings"]["model"] == "anthropic/claude-sonnet-4.5"

    reset = client.post(f"{base}/main/reset")
    assert reset.status_code == 200
    main = next(r for r in reset.json()["roles"] if r["role"] == "main")
    assert main["source"] == "profile"


def test_non_catalog_model_rejected_unless_custom(client):
    import asyncio

    agent = asyncio.run(_make_agent(client.app.state.storage))
    url = f"/api/providers/agents/{agent.agent_id}/main"

    rejected = client.put(url, json={"provider": "openrouter", "model": "made-up/model"})
    assert rejected.status_code == 422

    ok = client.put(
        url, json={"provider": "openrouter", "model": "made-up/model", "custom": True}
    )
    assert ok.status_code == 200
    main = next(r for r in ok.json()["roles"] if r["role"] == "main")
    assert main["settings"]["model"] == "made-up/model"


def test_unknown_role_is_404(client):
    import asyncio

    agent = asyncio.run(_make_agent(client.app.state.storage))
    r = client.put(
        f"/api/providers/agents/{agent.agent_id}/not-a-role",
        json={"provider": "openrouter", "model": settings.default_model},
    )
    assert r.status_code == 404


def test_session_override_layers_on_top_of_agent(client):
    import asyncio

    storage = client.app.state.storage
    agent = asyncio.run(_make_agent(storage))
    session = asyncio.run(storage.create_session("agent", agent.agent_id))

    # agent-level pick
    client.put(
        f"/api/providers/agents/{agent.agent_id}/main",
        json={"provider": "openrouter", "model": "anthropic/claude-opus-4.1"},
    )
    # session-level partial override (temperature only)
    put = client.put(
        f"/api/providers/sessions/{session.session_id}/main",
        json={"provider": "openrouter", "model": "google/gemini-2.5-pro", "temperature": 0.1},
    )
    assert put.status_code == 200
    main = next(r for r in put.json()["roles"] if r["role"] == "main")
    assert main["source"] == "session"
    assert main["settings"]["model"] == "google/gemini-2.5-pro"
    assert main["settings"]["temperature"] == pytest.approx(0.1)

    # reset session -> falls back to the agent-level pick, not the profile default
    client.post(f"/api/providers/sessions/{session.session_id}/main/reset")
    got = client.get(f"/api/providers/sessions/{session.session_id}").json()
    main = next(r for r in got["roles"] if r["role"] == "main")
    assert main["source"] == "agent"
    assert main["settings"]["model"] == "anthropic/claude-opus-4.1"


def test_unavailable_provider_rejected_with_422(client, monkeypatch):
    import asyncio

    from krutrim_agent_backend.api import settings_routes

    agent = asyncio.run(_make_agent(client.app.state.storage))
    monkeypatch.setattr(settings_routes, "provider_available", lambda _key: False)
    r = client.put(
        f"/api/providers/agents/{agent.agent_id}/main",
        json={"provider": "openrouter", "model": settings.default_model},
    )
    assert r.status_code == 422
    assert "not installed" in r.json()["detail"]


def test_session_settings_requires_agent_session(client):
    import asyncio

    storage = client.app.state.storage
    chat = asyncio.run(
        storage.create_chat("C", "openrouter", settings.default_model)
    )
    chat_session = asyncio.run(storage.create_session("chat", chat.chat_id))
    r = client.get(f"/api/providers/sessions/{chat_session.session_id}")
    assert r.status_code == 400
