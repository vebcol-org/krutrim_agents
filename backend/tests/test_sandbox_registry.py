"""SandboxRegistry tests against a fake store and fake backend factory — no
real Docker involved, unlike test_sandbox.py's `@requires_sandbox` tests.
Covers `resolve_owner_id`'s branches and `get_or_create`'s new/reuse/resume
paths, which is the machinery the AG-UI path and the idle reaper both build on.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fakes import FakeBackend, FakeStore
from krutrim_agent_management.models import ContainerRecord
from krutrim_agent_sandbox.registry import SandboxRegistry
from krutrim_agent_sandbox.status_channel import PubSubBackend


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FakePubSub(PubSubBackend):
    def __init__(self, *, raise_on_publish: bool = False) -> None:
        self.published: list[tuple[str, str]] = []
        self._raise_on_publish = raise_on_publish

    def publish(self, channel: str, message: str) -> None:
        if self._raise_on_publish:
            raise ConnectionError("redis is down")
        self.published.append((channel, message))


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


def _registry(store: FakeStore, pubsub: PubSubBackend | None = None) -> SandboxRegistry:
    return SandboxRegistry(
        store=store,
        backend_factory=lambda owner_id, policy: FakeBackend(owner_id),
        pubsub=pubsub,
    )


# -- resolve_owner_id ---------------------------------------------------------


async def test_resolve_owner_id_isolated_session_owns_itself(store):
    store.add_project("proj-1")
    store.add_session("sess-1", project_id="proj-1")
    registry = _registry(store)

    owner_id, owner_kind = await registry.resolve_owner_id("sess-1")

    assert owner_id == "sess-1"
    assert owner_kind == "session"


async def test_resolve_owner_id_explicit_attach_wins(store):
    store.add_project("proj-1")
    store.add_session("sess-1", project_id="proj-1")
    store.add_session("sess-2", project_id="proj-1", attached_to_session_id="sess-1")
    registry = _registry(store)

    owner_id, owner_kind = await registry.resolve_owner_id("sess-2")

    assert owner_id == "sess-1"
    assert owner_kind == "session"


# -- get_or_create: new container --------------------------------------------


async def test_get_or_create_new_owner_hydrates_from_empty_workspace(store):
    store.add_project("proj-1")
    store.add_session("sess-1", project_id="proj-1")
    registry = _registry(store)

    handle = await registry.get_or_create("sess-1")

    assert handle.owner_id == "sess-1"
    assert handle.backend.hydrate_calls == [[]]  # no persisted files yet
    record = store.containers["sess-1"]
    assert record.status == "running"
    assert record.ref_count == 1
    assert record.owner_kind == "session"
    assert record.project_id == "proj-1"


async def test_get_or_create_hydrates_persisted_workspace_files(store):
    store.add_project("proj-1")
    store.add_session("sess-1", project_id="proj-1")
    store.workspaces["sess-1"] = {"notes.txt": b"hello", "sub/data.json": b"{}"}
    registry = _registry(store)

    handle = await registry.get_or_create("sess-1")

    [files] = handle.backend.hydrate_calls
    assert dict(files) == {"notes.txt": b"hello", "sub/data.json": b"{}"}


# -- get_or_create: reuse a running container --------------------------------


async def test_get_or_create_reuses_cached_backend_and_bumps_ref_count(store):
    store.add_project("proj-1")
    store.add_session("sess-1", project_id="proj-1")
    registry = _registry(store)

    first = await registry.get_or_create("sess-1")
    second = await registry.get_or_create("sess-1")

    assert first.backend is second.backend  # same in-process instance, not rehydrated
    assert len(first.backend.hydrate_calls) == 1  # only hydrated once, on first create
    assert store.containers["sess-1"].ref_count == 2


async def test_get_or_create_reattaches_when_not_locally_cached(store):
    store.add_project("proj-1")
    store.add_session("sess-1", project_id="proj-1")
    now = _now_iso()
    store.containers["sess-1"] = ContainerRecord(
        owner_id="sess-1",
        owner_kind="session",
        project_id="proj-1",
        container_name="krutrim_agent-sandbox-sess-1",
        status="running",
        ref_count=1,
        created_at=now,
        last_active_at=now,
    )
    registry = _registry(
        store
    )  # fresh registry — nothing in its local `_backends` cache

    handle = await registry.get_or_create("sess-1")

    assert (
        handle.backend.hydrate_calls == []
    )  # reattached, not hydrated (record wasn't "stopped")
    assert store.containers["sess-1"].ref_count == 2


# -- get_or_create: resume a stopped container -------------------------------


async def test_get_or_create_rehydrates_stopped_container(store):
    store.add_project("proj-1")
    store.add_session("sess-1", project_id="proj-1")
    store.workspaces["sess-1"] = {"result.txt": b"prior output"}
    created_at = _now_iso()
    store.containers["sess-1"] = ContainerRecord(
        owner_id="sess-1",
        owner_kind="session",
        project_id="proj-1",
        container_name="krutrim_agent-sandbox-sess-1",
        status="stopped",
        ref_count=0,
        created_at=created_at,
        last_active_at=created_at,
    )
    registry = _registry(store)

    handle = await registry.get_or_create("sess-1")

    [files] = handle.backend.hydrate_calls
    assert dict(files) == {"result.txt": b"prior output"}
    record = store.containers["sess-1"]
    assert record.status == "running"
    assert record.ref_count == 1
    assert record.created_at == created_at  # preserved, not reset


# -- release ------------------------------------------------------------------


async def test_release_decrements_ref_count(store):
    store.add_project("proj-1")
    store.add_session("sess-1", project_id="proj-1")
    registry = _registry(store)
    await registry.get_or_create("sess-1")
    await registry.get_or_create("sess-1")

    await registry.release("sess-1")

    assert store.containers["sess-1"].ref_count == 1


async def test_release_floors_at_zero(store):
    store.add_project("proj-1")
    store.add_session("sess-1", project_id="proj-1")
    registry = _registry(store)
    await registry.get_or_create("sess-1")

    await registry.release("sess-1")
    await registry.release("sess-1")  # already at 0 — must not go negative

    assert store.containers["sess-1"].ref_count == 0


async def test_release_is_a_noop_for_unknown_owner(store):
    registry = _registry(store)
    await registry.release("never-created")  # must not raise


# -- local_backend --------------------------------------------------------------


async def test_local_backend_returns_none_before_create(store):
    registry = _registry(store)
    assert registry.local_backend("sess-1") is None


async def test_get_or_create_combines_ref_count_across_attached_sessions(store):
    store.add_project("proj-1")
    store.add_session("sess-a", project_id="proj-1")
    store.add_session("sess-b", project_id="proj-1", attached_to_session_id="sess-a")
    registry = _registry(store)

    handle_a = await registry.get_or_create("sess-a")
    handle_b = await registry.get_or_create("sess-b")

    assert handle_a.owner_id == "sess-a"
    assert handle_b.owner_id == "sess-a"  # B resolves to A's container, not its own
    assert handle_a.backend is handle_b.backend  # same cached backend instance
    assert store.containers["sess-a"].ref_count == 2
    assert "sess-b" not in store.containers  # no separate record ever created for B

    await registry.release(handle_b.owner_id)
    assert store.containers["sess-a"].ref_count == 1  # still attached via A itself
    await registry.release(handle_a.owner_id)
    assert store.containers["sess-a"].ref_count == 0


async def test_local_backend_returns_cached_instance_after_create(store):
    store.add_project("proj-1")
    store.add_session("sess-1", project_id="proj-1")
    registry = _registry(store)
    handle = await registry.get_or_create("sess-1")

    assert registry.local_backend("sess-1") is handle.backend


# -- live-status publishing ----------------------------------------------------


async def test_get_or_create_new_owner_publishes_starting_then_running(store):
    store.add_project("proj-1")
    store.add_session("sess-1", project_id="proj-1")
    pubsub = FakePubSub()
    registry = _registry(store, pubsub=pubsub)

    await registry.get_or_create("sess-1")

    statuses = [json.loads(msg)["status"] for _, msg in pubsub.published]
    assert statuses == ["starting", "running"]
    assert all(channel == "sandbox:container:sess-1" for channel, _ in pubsub.published)


async def test_get_or_create_reuse_publishes_running(store):
    store.add_project("proj-1")
    store.add_session("sess-1", project_id="proj-1")
    pubsub = FakePubSub()
    registry = _registry(store, pubsub=pubsub)
    await registry.get_or_create("sess-1")
    pubsub.published.clear()

    await registry.get_or_create("sess-1")

    statuses = [json.loads(msg)["status"] for _, msg in pubsub.published]
    assert statuses == ["running"]


async def test_release_to_zero_ref_count_publishes_idle(store):
    store.add_project("proj-1")
    store.add_session("sess-1", project_id="proj-1")
    pubsub = FakePubSub()
    registry = _registry(store, pubsub=pubsub)
    handle = await registry.get_or_create("sess-1")
    pubsub.published.clear()

    await registry.release(handle.owner_id)

    assert store.containers["sess-1"].status == "idle"
    channel, message = pubsub.published[-1]
    assert json.loads(message) == {"status": "idle", "ref_count": 0}


async def test_release_above_zero_ref_count_does_not_publish_idle(store):
    store.add_project("proj-1")
    store.add_session("sess-1", project_id="proj-1")
    pubsub = FakePubSub()
    registry = _registry(store, pubsub=pubsub)
    await registry.get_or_create("sess-1")
    await registry.get_or_create("sess-1")  # ref_count now 2
    pubsub.published.clear()

    await registry.release("sess-1")  # -> ref_count 1, still attached

    assert store.containers["sess-1"].status == "running"
    _, message = pubsub.published[-1]
    assert json.loads(message)["status"] == "running"


async def test_publish_failure_does_not_break_get_or_create(store):
    store.add_project("proj-1")
    store.add_session("sess-1", project_id="proj-1")
    pubsub = FakePubSub(raise_on_publish=True)
    registry = _registry(store, pubsub=pubsub)

    # Must not raise even though every publish() call fails.
    handle = await registry.get_or_create("sess-1")
    assert handle.owner_id == "sess-1"


async def test_no_pubsub_configured_is_a_silent_noop(store):
    store.add_project("proj-1")
    store.add_session("sess-1", project_id="proj-1")
    registry = _registry(store, pubsub=None)

    handle = await registry.get_or_create("sess-1")
    await registry.release(handle.owner_id)
    # No assertion beyond "did not raise" — absence of a pubsub backend
    # must be fully transparent to normal operation.
