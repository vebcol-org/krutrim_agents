"""SandboxRegistry tests — the slim, in-process form.

The registry now just resolves a session to its owner and hands back a
`FilesystemBackend` rooted at that session's workspace dir. No Docker, no
container records, no idle reaper.
"""

from __future__ import annotations

from deepagents.backends.filesystem import FilesystemBackend
from krutrim_agent_management import LocalStorage
from krutrim_agent_sandbox.registry import SandboxRegistry


async def _session(storage: LocalStorage, *, attached_to: str | None = None):
    project = await storage.create_project("P")
    agent = await storage.create_agent(project.project_id, "research", "A")
    session = await storage.create_session("agent", agent.agent_id)
    if attached_to is not None:
        session = await storage.update_session_sandbox_policy(
            session.session_id, attached_to_session_id=attached_to
        )
    return session


# -- resolve_owner_id -------------------------------------------------------


async def test_resolve_owner_id_isolated_session_owns_itself(tmp_path):
    storage = LocalStorage(tmp_path)
    session = await _session(storage)
    registry = SandboxRegistry(store=storage)

    owner_id, owner_kind = await registry.resolve_owner_id(session.session_id)

    assert owner_id == session.session_id
    assert owner_kind == "session"


async def test_resolve_owner_id_explicit_attach_wins(tmp_path):
    storage = LocalStorage(tmp_path)
    target = await _session(storage)
    attached = await _session(storage, attached_to=target.session_id)
    registry = SandboxRegistry(store=storage)

    owner_id, _ = await registry.resolve_owner_id(attached.session_id)

    assert owner_id == target.session_id


# -- get_or_create --------------------------------------------------------


async def test_get_or_create_returns_filesystem_backend_rooted_at_workspace(tmp_path):
    storage = LocalStorage(tmp_path)
    session = await _session(storage)
    registry = SandboxRegistry(store=storage)

    handle = await registry.get_or_create(session.session_id)

    assert handle.owner_id == session.session_id
    assert isinstance(handle.backend, FilesystemBackend)
    workspace = storage.session_dir(session.session_id) / "workspace"
    assert workspace.is_dir()
    assert handle.backend.cwd == workspace.resolve()


async def test_get_or_create_caches_backend_per_owner(tmp_path):
    storage = LocalStorage(tmp_path)
    session = await _session(storage)
    registry = SandboxRegistry(store=storage)

    first = await registry.get_or_create(session.session_id)
    second = await registry.get_or_create(session.session_id)

    assert first.backend is second.backend
    assert registry.local_backend(session.session_id) is first.backend


async def test_attached_session_shares_the_owner_workspace(tmp_path):
    storage = LocalStorage(tmp_path)
    target = await _session(storage)
    attached = await _session(storage, attached_to=target.session_id)
    registry = SandboxRegistry(store=storage)

    handle_target = await registry.get_or_create(target.session_id)
    handle_attached = await registry.get_or_create(attached.session_id)

    assert handle_attached.owner_id == target.session_id
    assert handle_attached.backend is handle_target.backend


async def test_writes_land_in_the_session_workspace_and_persist(tmp_path):
    storage = LocalStorage(tmp_path)
    session = await _session(storage)
    registry = SandboxRegistry(store=storage)

    handle = await registry.get_or_create(session.session_id)
    handle.backend.write("/notes.txt", "hello")

    # Same bytes the sessions/RAG file API reads through Storage.
    assert await storage.read_workspace_file(session.session_id, "notes.txt") == b"hello"

    # Survives a fresh registry (a process restart) — it's just a directory.
    registry.close_all()
    fresh = SandboxRegistry(store=storage)
    handle2 = await fresh.get_or_create(session.session_id)
    assert handle2.backend.read("/notes.txt").file_data["content"] == "hello"


# -- release / interrupt / local_backend --------------------------------


async def test_release_and_interrupt_are_noops(tmp_path):
    storage = LocalStorage(tmp_path)
    session = await _session(storage)
    registry = SandboxRegistry(store=storage)
    handle = await registry.get_or_create(session.session_id)

    await registry.release(handle.owner_id)  # must not raise
    assert await registry.interrupt(session.session_id) is False
    assert registry.local_backend(session.session_id) is handle.backend


async def test_local_backend_is_none_before_create(tmp_path):
    storage = LocalStorage(tmp_path)
    registry = SandboxRegistry(store=storage)
    assert registry.local_backend("nope") is None
