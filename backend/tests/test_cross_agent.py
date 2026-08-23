"""Tests for the cross-agent messaging bridge: eligibility rules,
`invoke_agent_turn`'s guard clauses (self-message, cycle, depth limit,
ineligibility, non-agent target) — all cheap to test since they return
before touching a real graph/sandbox — plus one happy-path test with
`build_agent` monkeypatched to a fake graph, proving the full plumbing
(eligible pair, real checkpoint file creation, reply round-trip, sandbox
release) without needing a real LLM or Docker.
"""

from __future__ import annotations

import pytest
from krutrim_agent_management import LocalStorage
from krutrim_agent_management.models import SessionInfo
from krutrim_agents_core import cross_agent
from krutrim_agents_core.cross_agent import (
    MAX_CROSS_AGENT_CALL_DEPTH,
    _check_eligible,
    find_eligible_peers,
    invoke_agent_turn,
)
from langchain_core.messages import AIMessage


def _session(
    session_id: str,
    project_id: str = "p",
    *,
    owner_type="agent",
    owner_id="agent-1",
    sharing="isolated",
    linked=None,
) -> SessionInfo:
    return SessionInfo(
        session_id=session_id,
        owner_type=owner_type,
        owner_id=owner_id,
        project_id=project_id,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        sandbox_sharing=sharing,
        linked_session_ids=linked or [],
    )


async def _make_agent_session(
    storage: LocalStorage, project_id: str, agent_key: str = "research"
):
    agent = await storage.create_agent(project_id, agent_key, "Test Agent")
    return await storage.create_session("agent", agent.agent_id)


# -- _check_eligible ------------------------------------------------------


def test_check_eligible_both_project_shared():
    caller = _session("a", sharing="project-shared")
    target = _session("b", sharing="project-shared")
    assert _check_eligible(caller, target) is True


def test_check_eligible_mutual_session_shared():
    caller = _session("a", sharing="session-shared", linked=["b"])
    target = _session("b", sharing="session-shared", linked=["a"])
    assert _check_eligible(caller, target) is True


def test_check_eligible_one_sided_session_shared_not_eligible():
    caller = _session("a", sharing="session-shared", linked=["b"])
    target = _session(
        "b", sharing="session-shared", linked=[]
    )  # doesn't list caller back
    assert _check_eligible(caller, target) is False


def test_check_eligible_isolated_not_eligible():
    caller = _session("a", sharing="project-shared")
    target = _session("b", sharing="isolated")
    assert _check_eligible(caller, target) is False


def test_check_eligible_mismatched_scopes_not_eligible():
    caller = _session("a", sharing="project-shared")
    target = _session("b", sharing="session-shared", linked=["a"])
    assert _check_eligible(caller, target) is False


def test_check_eligible_chat_owned_target_not_eligible():
    caller = _session("a", sharing="project-shared")
    target = _session(
        "b", sharing="project-shared", owner_type="chat", owner_id="chat-1"
    )
    assert _check_eligible(caller, target) is False


def test_check_eligible_different_projects_not_eligible():
    caller = _session("a", project_id="p1", sharing="project-shared")
    target = _session("b", project_id="p2", sharing="project-shared")
    assert _check_eligible(caller, target) is False


# -- find_eligible_peers ----------------------------------------------------


async def test_find_eligible_peers_empty_for_isolated_session(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    session = await _make_agent_session(storage, project.project_id)

    peers = await find_eligible_peers(storage, project.project_id, session)

    assert peers == []


async def test_find_eligible_peers_finds_project_shared_peers(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    session_a = await _make_agent_session(storage, project.project_id)
    session_b = await _make_agent_session(storage, project.project_id)
    session_c = await _make_agent_session(storage, project.project_id)  # stays isolated
    await storage.update_session_sandbox_policy(
        session_a.session_id, sharing="project-shared"
    )
    await storage.update_session_sandbox_policy(
        session_b.session_id, sharing="project-shared"
    )
    refreshed_a = await storage.get_session(session_a.session_id)

    peers = await find_eligible_peers(storage, project.project_id, refreshed_a)

    assert peers == [session_b.session_id]
    assert session_c.session_id not in peers


# -- invoke_agent_turn guard clauses -----------------------------------------


async def test_invoke_agent_turn_rejects_self_message(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    session = await _make_agent_session(storage, project.project_id)

    result = await invoke_agent_turn(
        store=storage,
        provider_store=None,
        sandbox_registry=None,
        project_id=project.project_id,
        caller_session_id=session.session_id,
        target_session_id=session.session_id,
        message="hi",
        call_chain=[],
    )

    assert "cannot message itself" in result.lower()


async def test_invoke_agent_turn_rejects_cycle(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    session_a = await _make_agent_session(storage, project.project_id)
    session_b = await _make_agent_session(storage, project.project_id)

    result = await invoke_agent_turn(
        store=storage,
        provider_store=None,
        sandbox_registry=None,
        project_id=project.project_id,
        caller_session_id=session_a.session_id,
        target_session_id=session_b.session_id,
        message="hi",
        call_chain=[session_b.session_id],  # B already visited -> cycle
    )

    assert "cycle" in result.lower()


async def test_invoke_agent_turn_rejects_depth_limit(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    session_a = await _make_agent_session(storage, project.project_id)
    session_b = await _make_agent_session(storage, project.project_id)

    result = await invoke_agent_turn(
        store=storage,
        provider_store=None,
        sandbox_registry=None,
        project_id=project.project_id,
        caller_session_id=session_a.session_id,
        target_session_id=session_b.session_id,
        message="hi",
        call_chain=["x"] * MAX_CROSS_AGENT_CALL_DEPTH,
    )

    assert "depth limit" in result.lower()


async def test_invoke_agent_turn_rejects_ineligible_pair(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    session_a = await _make_agent_session(storage, project.project_id)
    session_b = await _make_agent_session(storage, project.project_id)
    # both default to "isolated" -> never eligible

    result = await invoke_agent_turn(
        store=storage,
        provider_store=None,
        sandbox_registry=None,
        project_id=project.project_id,
        caller_session_id=session_a.session_id,
        target_session_id=session_b.session_id,
        message="hi",
        call_chain=[],
    )

    assert "isn't eligible" in result.lower()


async def test_invoke_agent_turn_unknown_target_returns_error_not_exception(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    session_a = await _make_agent_session(storage, project.project_id)

    result = await invoke_agent_turn(
        store=storage,
        provider_store=None,
        sandbox_registry=None,
        project_id=project.project_id,
        caller_session_id=session_a.session_id,
        target_session_id="nope",
        message="hi",
        call_chain=[],
    )

    assert result.startswith("Error:")


# -- happy path (build_agent monkeypatched, no real LLM/Docker) -------------


class FakeHandle:
    def __init__(self, owner_id: str) -> None:
        self.backend = object()
        self.owner_id = owner_id


class FakeRegistry:
    def __init__(self) -> None:
        self.released: list[str] = []

    async def get_or_create(self, session_id: str) -> FakeHandle:
        return FakeHandle(session_id)

    async def release(self, owner_id: str) -> None:
        self.released.append(owner_id)


class FakeGraph:
    def __init__(self, reply_text: str) -> None:
        self.reply_text = reply_text
        self.invocations: list[dict] = []

    async def ainvoke(self, state, config=None):
        self.invocations.append({"state": state, "config": config})
        return {"messages": [AIMessage(content=self.reply_text)]}


async def test_invoke_agent_turn_happy_path_returns_reply_and_releases_sandbox(
    tmp_path, monkeypatch
):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    caller = await _make_agent_session(storage, project.project_id)
    target = await _make_agent_session(storage, project.project_id)
    await storage.update_session_sandbox_policy(
        caller.session_id, sharing="project-shared"
    )
    await storage.update_session_sandbox_policy(
        target.session_id, sharing="project-shared"
    )

    fake_graph = FakeGraph("reply from peer")
    monkeypatch.setattr(cross_agent, "build_agent", lambda *a, **kw: fake_graph)

    registry = FakeRegistry()
    reply = await invoke_agent_turn(
        store=storage,
        provider_store=object(),
        sandbox_registry=registry,
        project_id=project.project_id,
        caller_session_id=caller.session_id,
        target_session_id=target.session_id,
        message="hello peer",
        call_chain=[],
    )

    assert reply == "reply from peer"
    assert registry.released == [target.session_id]
    assert len(fake_graph.invocations) == 1
    assert fake_graph.invocations[0]["config"] == {
        "configurable": {"thread_id": target.session_id}
    }
    # A real, durable checkpoint file gets created at the target's session dir,
    # even though nothing was actually written into it by the fake graph.
    checkpoint_path = (
        storage.session_dir(target.session_id) / "langgraph_checkpoint.sqlite"
    )
    assert checkpoint_path.exists()


async def test_invoke_agent_turn_releases_sandbox_even_if_graph_raises(
    tmp_path, monkeypatch
):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    caller = await _make_agent_session(storage, project.project_id)
    target = await _make_agent_session(storage, project.project_id)
    await storage.update_session_sandbox_policy(
        caller.session_id, sharing="project-shared"
    )
    await storage.update_session_sandbox_policy(
        target.session_id, sharing="project-shared"
    )

    class RaisingGraph:
        async def ainvoke(self, state, config=None):
            raise RuntimeError("boom")

    monkeypatch.setattr(cross_agent, "build_agent", lambda *a, **kw: RaisingGraph())
    registry = FakeRegistry()

    with pytest.raises(RuntimeError):
        await invoke_agent_turn(
            store=storage,
            provider_store=object(),
            sandbox_registry=registry,
            project_id=project.project_id,
            caller_session_id=caller.session_id,
            target_session_id=target.session_id,
            message="hello peer",
            call_chain=[],
        )

    assert registry.released == [target.session_id]  # finally-block guarantee holds
