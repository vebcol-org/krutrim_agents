"""Tests for `api/agent_run.py`'s agent-instance-based routing: agent
lookup, session resolution (create-if-missing, ownership validation), the
health route, and the sandbox-registry lifecycle guarantee
(get_or_create/release always pair up, even when the run errors mid-stream).

The actual AG-UI streaming/deepagents graph machinery is `ag_ui_langgraph`'s
and `deepagents`' own concern, not ours — so the full-request tests below
monkeypatch `build_agent`/`LangGraphAgent` with fakes and use a fake sandbox
registry, keeping focus on the wiring this module owns.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from krutrim_agent_backend.api import agent_run
from krutrim_agent_backend.api.agent_run import (
    _get_agent,
    _get_or_create_run_session,
    mount_agent_run_endpoint,
)
from krutrim_agent_management import LocalStorage
from krutrim_agent_sandbox.registry import AttachHandle

RUN_INPUT_BODY = {
    "threadId": "thread-1",
    "runId": "run-1",
    "state": {},
    "messages": [],
    "tools": [],
    "context": [],
    "forwardedProps": {},
}


class FakeProviderStore:
    def get(self, agent_key: str, role: str):
        return SimpleNamespace(provider="openrouter", model="test-model")


async def _make_agent(storage: LocalStorage, agent_key: str = "research"):
    project = await storage.create_project("P")
    return await storage.create_agent(project.project_id, agent_key, "Test Agent")


# -- _get_agent --------------------------------------------------------------


async def test_get_agent_returns_existing(tmp_path):
    storage = LocalStorage(tmp_path)
    agent = await _make_agent(storage)

    fetched = await _get_agent(storage, agent.agent_id)

    assert fetched.agent_id == agent.agent_id
    assert fetched.agent_key == "research"


async def test_get_agent_unknown_id_raises_404(tmp_path):
    storage = LocalStorage(tmp_path)

    with pytest.raises(HTTPException) as exc_info:
        await _get_agent(storage, "nope")
    assert exc_info.value.status_code == 404


# -- _get_or_create_run_session -----------------------------------------------


async def test_get_or_create_run_session_creates_new(tmp_path):
    storage = LocalStorage(tmp_path)
    agent = await _make_agent(storage)

    session = await _get_or_create_run_session(storage, agent, None)

    assert session.owner_type == "agent"
    assert session.owner_id == agent.agent_id


async def test_get_or_create_run_session_reuses_matching(tmp_path):
    storage = LocalStorage(tmp_path)
    agent = await _make_agent(storage)
    created = await storage.create_session("agent", agent.agent_id)

    fetched = await _get_or_create_run_session(storage, agent, created.session_id)

    assert fetched.session_id == created.session_id


async def test_get_or_create_run_session_rejects_session_from_other_agent(tmp_path):
    storage = LocalStorage(tmp_path)
    agent_a = await _make_agent(storage)
    agent_b = await _make_agent(storage)
    foreign_session = await storage.create_session("agent", agent_b.agent_id)

    with pytest.raises(HTTPException) as exc_info:
        await _get_or_create_run_session(storage, agent_a, foreign_session.session_id)
    assert exc_info.value.status_code == 400


async def test_get_or_create_run_session_unknown_id_raises_404(tmp_path):
    storage = LocalStorage(tmp_path)
    agent = await _make_agent(storage)

    with pytest.raises(HTTPException) as exc_info:
        await _get_or_create_run_session(storage, agent, "nope")
    assert exc_info.value.status_code == 404


# -- health route --------------------------------------------------------------


@pytest.fixture
def bare_app(tmp_path) -> FastAPI:
    app = FastAPI()
    app.state.storage = LocalStorage(tmp_path)
    mount_agent_run_endpoint(app)
    return app


def test_health_route_known_agent(bare_app):
    client = TestClient(bare_app)
    agent = asyncio.run(_make_agent(bare_app.state.storage))

    response = client.get(f"/agents/{agent.agent_id}/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "agent": {"id": agent.agent_id, "agent_key": "research"},
    }


def test_health_route_unknown_agent(bare_app):
    client = TestClient(bare_app)
    response = client.get("/agents/does-not-exist/health")
    assert response.status_code == 404


def test_run_route_unknown_agent_returns_404_before_streaming(bare_app):
    client = TestClient(bare_app)
    response = client.post("/agents/does-not-exist", json=RUN_INPUT_BODY)
    assert response.status_code == 404


# -- full request: sandbox registry lifecycle ---------------------------------


class FakeBackend:
    pass


class FakeSandboxRegistry:
    def __init__(self) -> None:
        self.get_or_create_calls: list[str] = []
        self.release_calls: list[str] = []

    async def get_or_create(self, session_id: str) -> AttachHandle:
        self.get_or_create_calls.append(session_id)
        return AttachHandle(backend=FakeBackend(), owner_id=session_id)

    async def release(self, owner_id: str) -> None:
        self.release_calls.append(owner_id)


class FakeLangGraphAgent:
    """Replaces the real ag_ui_langgraph.LangGraphAgent so tests never touch
    a real LLM/deepagents graph — only agent_run.py's own wiring."""

    instances: list[FakeLangGraphAgent] = []

    def __init__(self, name, graph, description=None):
        self.name = name
        FakeLangGraphAgent.instances.append(self)

    async def run(self, input_data):
        if False:
            yield  # pragma: no cover - makes this an async generator with zero events


class RaisingFakeLangGraphAgent(FakeLangGraphAgent):
    async def run(self, input_data):
        raise RuntimeError("boom")
        yield  # pragma: no cover - unreachable, keeps this an async generator


@pytest.fixture
def wired_app(tmp_path, monkeypatch):
    monkeypatch.setattr(
        agent_run,
        "build_agent",
        lambda profile, store, sandbox, checkpointer=None, extra_tools=None: object(),
    )
    FakeLangGraphAgent.instances.clear()

    app = FastAPI()
    app.state.storage = LocalStorage(tmp_path)
    app.state.provider_store = FakeProviderStore()
    app.state.sandbox_registry = FakeSandboxRegistry()
    mount_agent_run_endpoint(app)
    return app


def test_successful_run_creates_session_and_releases_sandbox(wired_app, monkeypatch):
    monkeypatch.setattr(agent_run, "LangGraphAgent", FakeLangGraphAgent)
    agent = asyncio.run(_make_agent(wired_app.state.storage))
    client = TestClient(wired_app)

    response = client.post(f"/agents/{agent.agent_id}", json=RUN_INPUT_BODY)

    assert response.status_code == 200
    registry: FakeSandboxRegistry = wired_app.state.sandbox_registry
    assert len(registry.get_or_create_calls) == 1
    session_id = registry.get_or_create_calls[0]
    assert registry.release_calls == [
        session_id
    ]  # released with the same owner_id it was created with

    async def _check():
        session = await wired_app.state.storage.get_session(session_id)
        assert session.owner_type == "agent"
        assert session.owner_id == agent.agent_id

    asyncio.run(_check())


def test_mid_stream_error_still_releases_sandbox(wired_app, monkeypatch):
    monkeypatch.setattr(agent_run, "LangGraphAgent", RaisingFakeLangGraphAgent)
    agent = asyncio.run(_make_agent(wired_app.state.storage))
    client = TestClient(wired_app)

    response = client.post(f"/agents/{agent.agent_id}", json=RUN_INPUT_BODY)

    assert (
        response.status_code == 200
    )  # headers already sent before the error occurs mid-stream
    registry: FakeSandboxRegistry = wired_app.state.sandbox_registry
    assert len(registry.get_or_create_calls) == 1
    assert (
        len(registry.release_calls) == 1
    )  # finally-block guarantee holds even when run() raises


def test_explicit_session_id_is_reused(wired_app, monkeypatch):
    monkeypatch.setattr(agent_run, "LangGraphAgent", FakeLangGraphAgent)
    client = TestClient(wired_app)
    storage = wired_app.state.storage

    async def _setup():
        agent = await _make_agent(storage)
        session = await storage.create_session("agent", agent.agent_id)
        return agent.agent_id, session.session_id

    agent_id, session_id = asyncio.run(_setup())

    response = client.post(
        f"/agents/{agent_id}?session_id={session_id}", json=RUN_INPUT_BODY
    )

    assert response.status_code == 200
    registry: FakeSandboxRegistry = wired_app.state.sandbox_registry
    assert registry.get_or_create_calls == [session_id]


def test_session_from_different_agent_rejected(wired_app, monkeypatch):
    monkeypatch.setattr(agent_run, "LangGraphAgent", FakeLangGraphAgent)
    client = TestClient(wired_app)
    storage = wired_app.state.storage

    async def _setup():
        agent_a = await _make_agent(storage)
        agent_b = await _make_agent(storage)
        foreign_session = await storage.create_session("agent", agent_b.agent_id)
        return agent_a.agent_id, foreign_session.session_id

    agent_id, foreign_session_id = asyncio.run(_setup())

    response = client.post(
        f"/agents/{agent_id}?session_id={foreign_session_id}", json=RUN_INPUT_BODY
    )

    assert response.status_code == 400
