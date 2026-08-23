"""Tests for the idle-container reaper's core logic
(`reap_idle_containers_once`) against a fake store and fake sandbox backend
— no real Docker, Redis, or Celery involved. The Celery task wrapper itself
(`reap_idle_containers`) is a two-line adapter over this function supplying
real dependencies; it isn't separately tested here.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fakes import FakeBackend, FakeStore
from krutrim_agent_celery.tasks.reap_idle_containers import reap_idle_containers_once
from krutrim_agent_management.models import ContainerRecord
from krutrim_agent_sandbox.status_channel import PubSubBackend


class FakePubSub(PubSubBackend):
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    def publish(self, channel: str, message: str) -> None:
        self.published.append((channel, message))


DEFAULT_TIMEOUT = 600


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _add_container(
    store: FakeStore,
    owner_id: str,
    *,
    project_id: str | None,
    idle_for_seconds: float,
    ref_count: int = 0,
    owner_kind: str = "session",
    policy_snapshot: dict | None = None,
) -> ContainerRecord:
    now = datetime.now(timezone.utc)
    record = ContainerRecord(
        owner_id=owner_id,
        owner_kind=owner_kind,
        project_id=project_id,
        container_name=f"krutrim_agent-sandbox-{owner_id}",
        status="running",
        ref_count=ref_count,
        created_at=_iso(now - timedelta(seconds=idle_for_seconds)),
        last_active_at=_iso(now - timedelta(seconds=idle_for_seconds)),
        policy_snapshot=policy_snapshot,
    )
    store.containers[owner_id] = record
    return record


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


def _factory(backends: dict[str, FakeBackend]):
    def factory(owner_id: str, policy) -> FakeBackend:
        return backends.setdefault(owner_id, FakeBackend(owner_id))

    return factory


# -- skip conditions ----------------------------------------------------------


async def test_skips_container_with_positive_ref_count(store):
    store.add_project("proj-1")
    _add_container(
        store, "sess-1", project_id="proj-1", idle_for_seconds=9999, ref_count=1
    )

    result = await reap_idle_containers_once(
        store, idle_timeout_seconds=DEFAULT_TIMEOUT
    )

    assert result["reaped"] == []
    assert "sess-1" in store.containers  # untouched


async def test_skips_channel_owner_kind_regardless_of_idle_time(store):
    _add_container(
        store,
        "general-channel",
        project_id=None,
        idle_for_seconds=9999,
        owner_kind="channel",
    )

    result = await reap_idle_containers_once(
        store, idle_timeout_seconds=DEFAULT_TIMEOUT
    )

    assert result["reaped"] == []
    assert "general-channel" in store.containers


async def test_skips_container_not_yet_idle(store):
    store.add_project("proj-1")
    _add_container(
        store, "sess-1", project_id="proj-1", idle_for_seconds=10, ref_count=0
    )

    result = await reap_idle_containers_once(
        store, idle_timeout_seconds=DEFAULT_TIMEOUT
    )

    assert result["reaped"] == []
    assert "sess-1" in store.containers


# -- reaping --------------------------------------------------------------------


async def test_reaps_idle_container_and_persists_workspace(store):
    store.add_project("proj-1")
    _add_container(
        store, "sess-1", project_id="proj-1", idle_for_seconds=9999, ref_count=0
    )
    backends = {
        "sess-1": FakeBackend(
            "sess-1", workspace_files={"notes.txt": b"hello", "sub/data.json": b"{}"}
        )
    }

    result = await reap_idle_containers_once(
        store, idle_timeout_seconds=DEFAULT_TIMEOUT, backend_factory=_factory(backends)
    )

    assert result["reaped"] == ["sess-1"]
    assert "sess-1" not in store.containers  # removed
    assert store.workspaces["sess-1"] == {"notes.txt": b"hello", "sub/data.json": b"{}"}
    assert backends["sess-1"].closed is True


async def test_reaps_container_with_empty_workspace(store):
    store.add_project("proj-1")
    _add_container(
        store, "sess-1", project_id="proj-1", idle_for_seconds=9999, ref_count=0
    )
    backends = {"sess-1": FakeBackend("sess-1")}  # no files

    result = await reap_idle_containers_once(
        store, idle_timeout_seconds=DEFAULT_TIMEOUT, backend_factory=_factory(backends)
    )

    assert result["reaped"] == ["sess-1"]
    assert "sess-1" not in store.workspaces  # nothing to sync, nothing written
    assert backends["sess-1"].closed is True


async def test_reaps_multiple_eligible_containers_independently(store):
    store.add_project("proj-1")
    _add_container(
        store, "sess-1", project_id="proj-1", idle_for_seconds=9999, ref_count=0
    )
    _add_container(
        store, "sess-2", project_id="proj-1", idle_for_seconds=9999, ref_count=1
    )  # in-use, skipped
    _add_container(
        store, "sess-3", project_id="proj-1", idle_for_seconds=5, ref_count=0
    )  # too fresh, skipped
    backends = {"sess-1": FakeBackend("sess-1")}

    result = await reap_idle_containers_once(
        store, idle_timeout_seconds=DEFAULT_TIMEOUT, backend_factory=_factory(backends)
    )

    assert result["reaped"] == ["sess-1"]
    assert set(store.containers) == {"sess-2", "sess-3"}


# -- per-project idle timeout override ----------------------------------------


async def test_project_override_shorter_than_default_reaps_earlier(store):
    store.add_project("proj-1", sandbox_idle_timeout_seconds=30)
    _add_container(
        store, "sess-1", project_id="proj-1", idle_for_seconds=60, ref_count=0
    )
    backends = {"sess-1": FakeBackend("sess-1")}

    # Idle 60s: past the project's 30s override, but well under the 600s default.
    result = await reap_idle_containers_once(
        store, idle_timeout_seconds=DEFAULT_TIMEOUT, backend_factory=_factory(backends)
    )

    assert result["reaped"] == ["sess-1"]


async def test_project_override_longer_than_default_delays_reaping(store):
    store.add_project("proj-1", sandbox_idle_timeout_seconds=3600)
    _add_container(
        store, "sess-1", project_id="proj-1", idle_for_seconds=900, ref_count=0
    )

    # Idle 900s: past the 600s default, but under the project's 3600s override.
    result = await reap_idle_containers_once(
        store, idle_timeout_seconds=DEFAULT_TIMEOUT
    )

    assert result["reaped"] == []
    assert "sess-1" in store.containers


async def test_falls_back_to_default_when_project_no_longer_exists(store):
    # project_id points at a project that's since been deleted — must not crash.
    _add_container(
        store,
        "sess-1",
        project_id="deleted-project",
        idle_for_seconds=9999,
        ref_count=0,
    )
    backends = {"sess-1": FakeBackend("sess-1")}

    result = await reap_idle_containers_once(
        store, idle_timeout_seconds=DEFAULT_TIMEOUT, backend_factory=_factory(backends)
    )

    assert result["reaped"] == ["sess-1"]


# -- policy reconstruction -----------------------------------------------------


async def test_reconstructs_policy_from_snapshot_for_backend_factory(store):
    store.add_project("proj-1")
    _add_container(
        store,
        "sess-1",
        project_id="proj-1",
        idle_for_seconds=9999,
        ref_count=0,
        policy_snapshot={"image": "custom-image:latest", "memory_mb": 256},
    )
    seen_policies = []

    def factory(owner_id, policy):
        seen_policies.append(policy)
        return FakeBackend(owner_id)

    await reap_idle_containers_once(
        store, idle_timeout_seconds=DEFAULT_TIMEOUT, backend_factory=factory
    )

    assert seen_policies[0].image == "custom-image:latest"
    assert seen_policies[0].memory_mb == 256


# -- idle-status containers (release()'s idle transition) --------------------


async def test_reaps_container_with_idle_status_not_just_running(store):
    """Regression: SandboxRegistry.release() now sets status="idle" when
    ref_count hits 0 (see registry.py) — the reaper must not filter these
    out by only scanning status="running"."""
    store.add_project("proj-1")
    _add_container(
        store,
        "sess-1",
        project_id="proj-1",
        idle_for_seconds=9999,
        ref_count=0,
        owner_kind="session",
    )
    store.containers["sess-1"].status = "idle"
    backends = {"sess-1": FakeBackend("sess-1")}

    result = await reap_idle_containers_once(
        store, idle_timeout_seconds=DEFAULT_TIMEOUT, backend_factory=_factory(backends)
    )

    assert result["reaped"] == ["sess-1"]


# -- live-status publishing ----------------------------------------------------


async def test_reap_publishes_tearing_down_then_stopped(store):
    store.add_project("proj-1")
    _add_container(
        store, "sess-1", project_id="proj-1", idle_for_seconds=9999, ref_count=0
    )
    backends = {"sess-1": FakeBackend("sess-1")}
    pubsub = FakePubSub()

    await reap_idle_containers_once(
        store,
        idle_timeout_seconds=DEFAULT_TIMEOUT,
        backend_factory=_factory(backends),
        pubsub=pubsub,
    )

    statuses = [json.loads(msg)["status"] for _, msg in pubsub.published]
    assert statuses == ["tearing_down", "stopped"]
    assert all(channel == "sandbox:container:sess-1" for channel, _ in pubsub.published)


async def test_reap_skipped_container_does_not_publish(store):
    store.add_project("proj-1")
    _add_container(
        store, "sess-1", project_id="proj-1", idle_for_seconds=5, ref_count=0
    )  # too fresh
    pubsub = FakePubSub()

    await reap_idle_containers_once(
        store, idle_timeout_seconds=DEFAULT_TIMEOUT, pubsub=pubsub
    )

    assert pubsub.published == []


async def test_reap_publish_failure_does_not_break_teardown(store):
    class RaisingPubSub(PubSubBackend):
        def publish(self, channel: str, message: str) -> None:
            raise ConnectionError("redis is down")

    store.add_project("proj-1")
    _add_container(
        store, "sess-1", project_id="proj-1", idle_for_seconds=9999, ref_count=0
    )
    backends = {"sess-1": FakeBackend("sess-1")}

    result = await reap_idle_containers_once(
        store,
        idle_timeout_seconds=DEFAULT_TIMEOUT,
        backend_factory=_factory(backends),
        pubsub=RaisingPubSub(),
    )

    assert result["reaped"] == [
        "sess-1"
    ]  # teardown still completed despite publish failures
