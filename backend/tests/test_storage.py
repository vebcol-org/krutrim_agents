from __future__ import annotations

import pytest
from krutrim_agent_management import ContainerRecord, LocalStorage
from krutrim_agent_management.local import _now_iso
from krutrim_agent_management.paths import default_storage_root


def test_default_storage_root_is_under_home(monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    root = default_storage_root()
    assert "krutrim_agent" in str(root).lower()


# -- projects -----------------------------------------------------------------


async def test_create_project_creates_row_and_dir(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("Research on X", "some info")
    assert project.project_title == "Research on X"
    assert project.project_information == "some info"
    assert storage.project_dir(project.project_id).is_dir()
    assert (tmp_path / "project.db").is_file()


async def test_get_unknown_project_raises(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(KeyError):
        await storage.get_project("does-not-exist")


async def test_list_projects(tmp_path):
    storage = LocalStorage(tmp_path)
    await storage.create_project("A")
    await storage.create_project("B")
    titles = {p.project_title for p in await storage.list_projects()}
    assert titles == {"A", "B"}


async def test_update_project_partial_update(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("Original", "orig info")
    updated = await storage.update_project(project.project_id, project_title="Renamed")
    assert updated.project_title == "Renamed"
    assert updated.project_information == "orig info"  # untouched


async def test_delete_project_removes_row_and_dir(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("Gone soon")
    project_dir = storage.project_dir(project.project_id)
    await storage.delete_project(project.project_id)
    with pytest.raises(KeyError):
        await storage.get_project(project.project_id)
    assert not project_dir.exists()


# -- agents ---------------------------------------------------------------


async def test_create_agent_row(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    agent = await storage.create_agent(
        project.project_id, "research", "Business Analysis"
    )
    assert agent.project_id == project.project_id
    assert agent.agent_key == "research"
    assert agent.display_name == "Business Analysis"
    assert agent.sandbox_sharing is None  # inherits project default


async def test_create_agent_for_unknown_project_raises(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(KeyError):
        await storage.create_agent("nope", "research", "X")


async def test_list_agents_scoped_to_project(tmp_path):
    storage = LocalStorage(tmp_path)
    project_a = await storage.create_project("A")
    project_b = await storage.create_project("B")
    await storage.create_agent(project_a.project_id, "research", "A1")
    await storage.create_agent(project_a.project_id, "research", "A2")
    await storage.create_agent(project_b.project_id, "trading", "B1")

    assert {
        a.display_name for a in await storage.list_agents(project_a.project_id)
    } == {"A1", "A2"}
    assert {
        a.display_name for a in await storage.list_agents(project_b.project_id)
    } == {"B1"}


async def test_update_agent_renames(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    agent = await storage.create_agent(project.project_id, "research", "Original")
    updated = await storage.update_agent(agent.agent_id, display_name="Renamed")
    assert updated.display_name == "Renamed"


async def test_delete_agent_cascades_sessions(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    agent = await storage.create_agent(project.project_id, "research", "A")
    session = await storage.create_session("agent", agent.agent_id)

    await storage.delete_agent(agent.agent_id)

    with pytest.raises(KeyError):
        await storage.get_agent(agent.agent_id)
    with pytest.raises(KeyError):
        await storage.get_session(session.session_id)


async def test_delete_project_cascades_agents_and_their_sessions(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    agent = await storage.create_agent(project.project_id, "research", "A")
    session = await storage.create_session("agent", agent.agent_id)

    await storage.delete_project(project.project_id)

    with pytest.raises(KeyError):
        await storage.get_agent(agent.agent_id)
    with pytest.raises(KeyError):
        await storage.get_session(session.session_id)


# -- chats ------------------------------------------------------------------


async def test_create_standalone_chat(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat(
        "General", "openrouter", "deepseek/deepseek-v4-flash-0731"
    )
    assert chat.project_id is None
    assert chat.display_name == "General"


async def test_create_project_scoped_chat(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    chat = await storage.create_chat(
        "Q&A",
        "openrouter",
        "deepseek/deepseek-v4-flash-0731",
        project_id=project.project_id,
    )
    assert chat.project_id == project.project_id


async def test_create_chat_for_unknown_project_raises(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(KeyError):
        await storage.create_chat("X", "openrouter", "m", project_id="nope")


async def test_list_chats_standalone_vs_project_scoped(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    await storage.create_chat("Standalone", "openrouter", "m")
    await storage.create_chat(
        "Scoped", "openrouter", "m", project_id=project.project_id
    )

    assert {c.display_name for c in await storage.list_chats(None)} == {"Standalone"}
    assert {c.display_name for c in await storage.list_chats(project.project_id)} == {
        "Scoped"
    }


async def test_move_chat_into_and_out_of_project(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    chat = await storage.create_chat("C", "openrouter", "m")
    session = await storage.create_session("chat", chat.chat_id)
    assert session.project_id is None

    moved = await storage.move_chat(chat.chat_id, project_id=project.project_id)
    assert moved.project_id == project.project_id
    # Sessions already under the chat are re-scoped to the new project too.
    assert (
        await storage.get_session(session.session_id)
    ).project_id == project.project_id

    detached = await storage.move_chat(chat.chat_id, project_id=None)
    assert detached.project_id is None
    assert (await storage.get_session(session.session_id)).project_id is None


async def test_move_chat_unknown_target_project_raises(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat("C", "openrouter", "m")
    with pytest.raises(KeyError):
        await storage.move_chat(chat.chat_id, project_id="nope")


async def test_delete_chat_cascades_sessions(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat("C", "openrouter", "m")
    session = await storage.create_session("chat", chat.chat_id)

    await storage.delete_chat(chat.chat_id)

    with pytest.raises(KeyError):
        await storage.get_chat(chat.chat_id)
    with pytest.raises(KeyError):
        await storage.get_session(session.session_id)


async def test_delete_project_cascades_chats_and_their_sessions(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    chat = await storage.create_chat(
        "C", "openrouter", "m", project_id=project.project_id
    )
    session = await storage.create_session("chat", chat.chat_id)

    await storage.delete_project(project.project_id)

    with pytest.raises(KeyError):
        await storage.get_chat(chat.chat_id)
    with pytest.raises(KeyError):
        await storage.get_session(session.session_id)


# -- agent memory ---------------------------------------------------------


async def test_memory_roundtrip(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("Mem test")
    assert await storage.read_memory(project.project_id) == ""
    await storage.write_memory(project.project_id, "# Memory\nlearned something")
    assert (
        await storage.read_memory(project.project_id) == "# Memory\nlearned something"
    )


async def test_memory_for_unknown_project_raises(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(KeyError):
        await storage.read_memory("nope")


# -- sessions -----------------------------------------------------------------


async def test_session_lifecycle_under_agent(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("Sessions")
    agent = await storage.create_agent(project.project_id, "research", "A")
    session = await storage.create_session("agent", agent.agent_id)
    assert session.owner_type == "agent"
    assert session.owner_id == agent.agent_id
    assert session.project_id == project.project_id
    assert await storage.get_session(session.session_id) == session
    assert [
        s.session_id for s in await storage.list_sessions("agent", agent.agent_id)
    ] == [session.session_id]
    await storage.delete_session(session.session_id)
    with pytest.raises(KeyError):
        await storage.get_session(session.session_id)


async def test_session_under_standalone_chat_has_no_project(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat("C", "openrouter", "m")
    session = await storage.create_session("chat", chat.chat_id)
    assert session.owner_type == "chat"
    assert session.project_id is None


async def test_create_session_for_unknown_owner_raises(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(KeyError):
        await storage.create_session("agent", "nope")


async def test_update_session_renames(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat("C", "openrouter", "m")
    session = await storage.create_session("chat", chat.chat_id)
    updated = await storage.update_session(
        session.session_id, display_name="Scoped run"
    )
    assert updated.display_name == "Scoped run"


async def test_checkpoint_roundtrip(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat("C", "openrouter", "m")
    session = await storage.create_session("chat", chat.chat_id)
    assert await storage.read_checkpoint(session.session_id) is None
    await storage.write_checkpoint(session.session_id, {"step": 3})
    assert await storage.read_checkpoint(session.session_id) == {"step": 3}


async def test_usage_roundtrip(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat("C", "openrouter", "m")
    session = await storage.create_session("chat", chat.chat_id)
    assert await storage.read_usage(session.session_id) is None
    await storage.write_usage(session.session_id, {"input_tokens": 100})
    assert await storage.read_usage(session.session_id) == {"input_tokens": 100}


# -- cache (still project-scoped) --------------------------------------------


async def test_cache_roundtrip(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("Cache")
    assert await storage.cache_get(project.project_id, "search", "query:foo") is None
    await storage.cache_set(
        project.project_id, "search", "query:foo", {"results": [1, 2, 3]}
    )
    assert await storage.cache_get(project.project_id, "search", "query:foo") == {
        "results": [1, 2, 3]
    }


async def test_cache_is_namespaced(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("Cache NS")
    await storage.cache_set(project.project_id, "mcp", "same-key", "mcp-value")
    await storage.cache_set(project.project_id, "rag", "same-key", "rag-value")
    assert await storage.cache_get(project.project_id, "mcp", "same-key") == "mcp-value"
    assert await storage.cache_get(project.project_id, "rag", "same-key") == "rag-value"


async def test_reopening_storage_preserves_data(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("Persisted")
    await storage.write_memory(project.project_id, "remember me")

    reopened = LocalStorage(tmp_path)
    assert (await reopened.get_project(project.project_id)).project_title == "Persisted"
    assert await reopened.read_memory(project.project_id) == "remember me"


# -- sandbox sharing policy ------------------------------------------------


async def test_new_project_and_session_default_to_isolated(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("Defaults")
    agent = await storage.create_agent(project.project_id, "research", "A")
    session = await storage.create_session("agent", agent.agent_id)
    assert project.sandbox_sharing == "isolated"
    assert project.sandbox_idle_timeout_seconds is None
    assert project.sandbox_resource_overrides is None
    assert agent.sandbox_sharing is None
    assert session.sandbox_sharing == "isolated"
    assert session.attached_to_session_id is None
    assert session.linked_session_ids == []


async def test_update_project_sandbox_policy_partial_update(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("Policy")
    updated = await storage.update_project_sandbox_policy(
        project.project_id, sharing="project-shared", idle_timeout_seconds=120
    )
    assert updated.sandbox_sharing == "project-shared"
    assert updated.sandbox_idle_timeout_seconds == 120
    assert updated.sandbox_resource_overrides is None  # untouched

    with_overrides = await storage.update_project_sandbox_policy(
        project.project_id, resource_overrides={"memory_mb": 1024}
    )
    assert with_overrides.sandbox_sharing == "project-shared"  # untouched by this call
    assert with_overrides.sandbox_resource_overrides == {"memory_mb": 1024}


async def test_update_project_sandbox_policy_unknown_project_raises(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(KeyError):
        await storage.update_project_sandbox_policy("nope", sharing="isolated")


async def test_update_agent_sandbox_policy_roundtrip(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("P")
    agent = await storage.create_agent(project.project_id, "research", "A")
    updated = await storage.update_agent_sandbox_policy(
        agent.agent_id, sharing="project-shared"
    )
    assert updated.sandbox_sharing == "project-shared"


async def test_update_chat_sandbox_policy_roundtrip(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat("C", "openrouter", "m")
    updated = await storage.update_chat_sandbox_policy(
        chat.chat_id, sharing="project-shared"
    )
    assert (
        updated.sandbox_sharing == "project-shared"
    )  # stored even though project_id is None


async def test_update_session_sandbox_policy_roundtrip(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("Session Policy")
    agent = await storage.create_agent(project.project_id, "research", "A")
    session_a = await storage.create_session("agent", agent.agent_id)
    session_b = await storage.create_session("agent", agent.agent_id)

    updated = await storage.update_session_sandbox_policy(
        session_a.session_id, attached_to_session_id=session_b.session_id
    )
    assert updated.attached_to_session_id == session_b.session_id
    assert updated.sandbox_sharing == "isolated"  # untouched

    linked = await storage.update_session_sandbox_policy(
        session_a.session_id,
        sharing="session-shared",
        linked_session_ids=[session_b.session_id],
    )
    assert linked.sandbox_sharing == "session-shared"
    assert linked.linked_session_ids == [session_b.session_id]
    assert (
        linked.attached_to_session_id == session_b.session_id
    )  # untouched by this call


async def test_update_session_sandbox_policy_unknown_raises(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(KeyError):
        await storage.update_session_sandbox_policy("nope", sharing="isolated")


# -- sandbox containers ------------------------------------------------------


def _make_container_record(owner_id: str, **overrides) -> ContainerRecord:
    now = _now_iso()
    defaults = dict(
        owner_id=owner_id,
        owner_kind="session",
        project_id="proj-1",
        container_name=f"krutrim_agent-sandbox-{owner_id}",
        status="running",
        ref_count=1,
        created_at=now,
        last_active_at=now,
    )
    defaults.update(overrides)
    return ContainerRecord(**defaults)


async def test_get_container_returns_none_for_unknown_owner(tmp_path):
    storage = LocalStorage(tmp_path)
    assert await storage.get_container("nope") is None


async def test_upsert_and_get_container_roundtrip(tmp_path):
    storage = LocalStorage(tmp_path)
    record = _make_container_record("session-1", policy_snapshot={"memory_mb": 512})
    await storage.upsert_container(record)
    fetched = await storage.get_container("session-1")
    assert fetched == record


async def test_upsert_container_overwrites_existing_row(tmp_path):
    storage = LocalStorage(tmp_path)
    await storage.upsert_container(
        _make_container_record("session-1", status="starting")
    )
    await storage.upsert_container(
        _make_container_record("session-1", status="running", ref_count=2)
    )
    fetched = await storage.get_container("session-1")
    assert fetched.status == "running"
    assert fetched.ref_count == 2


async def test_list_containers_filters_by_status(tmp_path):
    storage = LocalStorage(tmp_path)
    await storage.upsert_container(
        _make_container_record("session-1", status="running")
    )
    await storage.upsert_container(_make_container_record("session-2", status="idle"))
    running = await storage.list_containers(status="running")
    assert [c.owner_id for c in running] == ["session-1"]
    everything = await storage.list_containers()
    assert {c.owner_id for c in everything} == {"session-1", "session-2"}


async def test_channel_owner_kind_roundtrips(tmp_path):
    storage = LocalStorage(tmp_path)
    record = _make_container_record(
        "general-channel", owner_kind="channel", project_id=None
    )
    await storage.upsert_container(record)
    fetched = await storage.get_container("general-channel")
    assert fetched.owner_kind == "channel"
    assert fetched.project_id is None


async def test_delete_container_removes_row_and_is_idempotent(tmp_path):
    storage = LocalStorage(tmp_path)
    await storage.upsert_container(_make_container_record("session-1"))
    await storage.delete_container("session-1")
    assert await storage.get_container("session-1") is None
    await storage.delete_container("session-1")  # no-op, not an error


# -- session workspace mirror -------------------------------------------------


async def test_workspace_files_empty_for_fresh_session(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat("C", "openrouter", "m")
    session = await storage.create_session("chat", chat.chat_id)
    assert await storage.read_workspace_files(session.session_id) == []
    assert await storage.read_workspace_file(session.session_id, "missing.txt") is None


async def test_sync_workspace_from_container_then_read(tmp_path):
    storage = LocalStorage(tmp_path)
    chat = await storage.create_chat("C", "openrouter", "m")
    session = await storage.create_session("chat", chat.chat_id)

    await storage.sync_workspace_from_container(
        session.session_id, [("notes.txt", b"hello"), ("sub/data.json", b'{"a": 1}')]
    )

    files = await storage.read_workspace_files(session.session_id)
    assert sorted(files) == ["notes.txt", "sub/data.json"]
    assert (
        await storage.read_workspace_file(session.session_id, "notes.txt") == b"hello"
    )


async def test_workspace_methods_for_unknown_session_raise(tmp_path):
    storage = LocalStorage(tmp_path)
    with pytest.raises(KeyError):
        await storage.read_workspace_files("nope")


async def test_reopening_storage_preserves_sandbox_policy_and_containers(tmp_path):
    storage = LocalStorage(tmp_path)
    project = await storage.create_project("Persisted Policy")
    await storage.update_project_sandbox_policy(
        project.project_id, sharing="project-shared"
    )
    agent = await storage.create_agent(project.project_id, "research", "A")
    session = await storage.create_session("agent", agent.agent_id)
    await storage.update_session_sandbox_policy(
        session.session_id, linked_session_ids=["peer-1"]
    )
    await storage.upsert_container(_make_container_record(session.session_id))

    reopened = LocalStorage(tmp_path)
    reopened_project = await reopened.get_project(project.project_id)
    reopened_session = await reopened.get_session(session.session_id)
    assert reopened_project.sandbox_sharing == "project-shared"
    assert reopened_session.linked_session_ids == ["peer-1"]
    assert (await reopened.get_container(session.session_id)) is not None
