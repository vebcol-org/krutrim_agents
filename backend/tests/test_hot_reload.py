"""End-to-end hot-reload test: `SandboxRegistry` + real Docker + real
`LocalStorage` + the idle-container reaper, wired together exactly as they
are in the running app — proving a session can be torn down and resumed
transparently.

This is deliberately not the same thing as:
- `test_sandbox.py`'s `test_hydrate_restores_files_after_teardown`, which
  tests `DockerSandboxBackend.hydrate()` in isolation, bypassing the registry
  and storage entirely.
- `test_sandbox_registry.py`'s `test_get_or_create_rehydrates_stopped_container`,
  which tests the registry's stopped-record branch against a fake backend.

Requires the real sandbox image — see `test_sandbox.py`'s `requires_sandbox`
marker, reused here so both files skip/run under the same condition.
"""

from __future__ import annotations

import pytest
from krutrim_agent_celery.tasks.reap_idle_containers import reap_idle_containers_once
from krutrim_agent_management import LocalStorage
from krutrim_agent_sandbox.registry import SandboxRegistry
from test_sandbox import requires_sandbox


@pytest.fixture
def storage(tmp_path) -> LocalStorage:
    return LocalStorage(tmp_path)


@requires_sandbox
async def test_hot_reload_round_trip_through_registry(storage):
    registry = SandboxRegistry(store=storage)
    project = await storage.create_project("Hot Reload")
    agent = await storage.create_agent(project.project_id, "research", "Test Agent")
    session = await storage.create_session("agent", agent.agent_id)
    resumed = None
    try:
        # First attach: starts a fresh container, write something into it.
        handle = await registry.get_or_create(session.session_id)
        write_result = handle.backend.write(
            "/workspace/result.txt", "computed before teardown"
        )
        assert write_result.error is None
        record = await storage.get_container(handle.owner_id)
        assert record.status == "running"
        assert record.ref_count == 1

        # Release (no longer attached), then force it reap-eligible —
        # idle_timeout_seconds=0 means "any idle time at all qualifies".
        await registry.release(handle.owner_id)
        reap_result = await reap_idle_containers_once(storage, idle_timeout_seconds=0)
        assert reap_result["reaped"] == [handle.owner_id]
        assert await storage.get_container(handle.owner_id) is None  # torn down
        assert await storage.read_workspace_files(session.session_id) == ["result.txt"]

        # Resume: same session, container is gone — must transparently
        # hot-reload from the persisted workspace mirror rather than starting
        # empty, and be indistinguishable from the caller's point of view.
        resumed = await registry.get_or_create(session.session_id)
        assert resumed.owner_id == handle.owner_id
        read_result = resumed.backend.read("/workspace/result.txt")
        assert read_result.file_data is not None
        assert "computed before teardown" in read_result.file_data["content"]
        resumed_record = await storage.get_container(handle.owner_id)
        assert resumed_record.status == "running"
        assert resumed_record.ref_count == 1
    finally:
        handle.backend.close()  # no-op if the reaper already removed it
        if resumed is not None:
            resumed.backend.close()


@requires_sandbox
async def test_hot_reload_starts_a_genuinely_new_container(storage):
    registry = SandboxRegistry(store=storage)
    project = await storage.create_project("Hot Reload New Container")
    agent = await storage.create_agent(project.project_id, "research", "Test Agent")
    session = await storage.create_session("agent", agent.agent_id)
    resumed = None
    try:
        handle = await registry.get_or_create(session.session_id)
        handle.backend.execute(
            "echo warm-up"
        )  # ensure the container actually exists before reading its id
        original_container_id = handle.backend._container.id

        await registry.release(handle.owner_id)
        await reap_idle_containers_once(storage, idle_timeout_seconds=0)

        resumed = await registry.get_or_create(session.session_id)
        resumed.backend.execute("echo warm-up")
        new_container_id = resumed.backend._container.id

        assert new_container_id != original_container_id
    finally:
        handle.backend.close()
        if resumed is not None:
            resumed.backend.close()
