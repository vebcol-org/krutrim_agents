"""Idle-container reaper: the background half of the sandbox lifecycle.

Runs on a Celery beat schedule (see `celery_app.app`), entirely separate
from the request path — `SandboxRegistry.get_or_create`/`release` (the
request-time half, `sandbox/registry.py`) only ever adjust `ref_count` and
`last_active_at`; this task is the only thing that actually tears a
container down for being idle.

`reap_idle_containers_once` is the testable core: a plain async function
with injectable `store`/`backend_factory`, so tests exercise the real
skip/teardown logic against a fake store and a fake sandbox backend, without
needing Redis, Celery, or a real Docker daemon. `reap_idle_containers` is
the thin Celery-task wrapper that supplies real dependencies.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from deepagents.backends.sandbox import BaseSandbox
from krutrim_agent_management.config import settings
from krutrim_agent_management.storage_factory import create_storage
from krutrim_agent_sandbox.factory import create_sandbox_backend
from krutrim_agent_sandbox.policy import SandboxPolicy
from krutrim_agent_sandbox.status_channel import (
    PubSubBackend,
    RedisPubSubBackend,
    publish_container_status,
)

from krutrim_agent_celery.app import celery_app
from krutrim_agent_celery.config import celery_settings

if TYPE_CHECKING:
    from krutrim_agent_management.base import Storage
    from krutrim_agent_management.models import ContainerRecord

# Recursive listing of everything under /workspace, one absolute path per
# line. Deliberately plain Python (`python3 -c ...`) rather than `find` —
# the sandbox image guarantees Python (it's the base image), not
# `findutils`, and this runs inside the very container being torn down.
_LIST_WORKSPACE_FILES_CMD = (
    'python3 -c "import os\n'
    "for root, _, files in os.walk('/workspace'):\n"
    "    for name in files:\n"
    '        print(os.path.join(root, name))"'
)


def _download_workspace_files(backend: BaseSandbox) -> list[tuple[str, bytes]]:
    """Best-effort: an empty/failed listing just means nothing gets persisted
    for this container, not a reaper crash — the container is still torn
    down either way (see caller). Output is also subject to the sandbox
    policy's `max_output_bytes` truncation cap, same as any other `execute()`
    call — a very large workspace listing could be cut off; a known,
    documented limitation, not solved here."""
    listing = backend.execute(_LIST_WORKSPACE_FILES_CMD)
    if listing.exit_code != 0:
        return []
    raw_paths = [line.strip() for line in listing.output.splitlines() if line.strip()]
    relative_paths = [
        p.removeprefix("/workspace/") for p in raw_paths if p.startswith("/workspace/")
    ]
    if not relative_paths:
        return []
    downloaded = backend.download_files(relative_paths)
    return [
        (resp.path, resp.content)
        for resp in downloaded
        if resp.error is None and resp.content is not None
    ]


def _publish_safe(pubsub: PubSubBackend | None, owner_id: str, status: str) -> None:
    """Live status is best-effort — a Redis hiccup must never fail a real
    teardown/reap operation, so publish failures are swallowed here rather
    than at every call site."""
    if pubsub is None:
        return
    try:
        publish_container_status(pubsub, owner_id, status)
    except Exception:  # noqa: BLE001
        pass


async def _resolve_idle_timeout(
    store: Storage, record: ContainerRecord, default_timeout: int
) -> int:
    if record.project_id is None:
        return default_timeout
    try:
        project = await store.get_project(record.project_id)
    except KeyError:
        return default_timeout
    return (
        project.sandbox_idle_timeout_seconds
        if project.sandbox_idle_timeout_seconds is not None
        else default_timeout
    )


async def reap_idle_containers_once(
    store: Storage,
    *,
    idle_timeout_seconds: int,
    backend_factory: Callable[
        [str, SandboxPolicy], BaseSandbox
    ] = create_sandbox_backend,
    pubsub: PubSubBackend | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    reaped: list[str] = []
    # No status filter: "running" and "idle" (set by SandboxRegistry.release()
    # when ref_count hits 0 — see registry.py) both need scanning, and a
    # record stuck at "tearing_down" from a crashed prior run is retried
    # here too, since ref_count/idle-time still gate it the same way.
    for record in await store.list_containers():
        if record.owner_kind == "channel":
            continue  # static, never-torn-down containers (future bot integrations)
        if record.ref_count > 0:
            continue  # actively attached — never tear down mid-use, regardless of idle time
        last_active = datetime.fromisoformat(record.last_active_at)
        effective_timeout = await _resolve_idle_timeout(
            store, record, idle_timeout_seconds
        )
        if (now - last_active).total_seconds() < effective_timeout:
            continue

        await store.upsert_container(
            record.model_copy(update={"status": "tearing_down"})
        )
        _publish_safe(pubsub, record.owner_id, "tearing_down")
        policy = (
            SandboxPolicy(**record.policy_snapshot)
            if record.policy_snapshot
            else SandboxPolicy()
        )
        backend = backend_factory(record.owner_id, policy)
        try:
            files = _download_workspace_files(backend)
            if files:
                # `record.owner_id` is a session_id for every kind this reaper
                # currently produces work for ("channel" is skipped above;
                # "project" is reserved and unused — see ContainerRecord's
                # docstring). An explicitly-attached session sharing this same
                # container isn't synced into its own separate workspace
                # mirror here — revisit once that feature actually creates
                # such sessions.
                await store.sync_workspace_from_container(record.owner_id, files)
            close = getattr(backend, "close", None)
            if callable(close):
                close()
        finally:
            await store.delete_container(record.owner_id)
            _publish_safe(pubsub, record.owner_id, "stopped")
        reaped.append(record.owner_id)
    return {"reaped": reaped}


@celery_app.task(name="krutrim_agent_celery.reap_idle_containers")
def reap_idle_containers() -> dict:
    return asyncio.run(
        reap_idle_containers_once(
            create_storage(settings),
            idle_timeout_seconds=celery_settings.idle_timeout_seconds,
            pubsub=RedisPubSubBackend(settings.redis_url),
        )
    )
