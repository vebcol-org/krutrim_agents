"""Owner-scoped sandbox container registry.

Replaces `krutrim_agent_backend.main`'s old `{profile_key: DockerSandboxBackend}`
dict — containers are keyed by `owner_id` (resolved per session's sharing
policy via `resolve_owner_id`), not by agent profile. This module is the one
entry point `krutrim_agent_backend` request handlers call before any action that
needs a sandbox; nothing else in the app should construct a sandbox backend
directly.

Container-lifecycle *decisions* (idle teardown, hot-reload rehydration) are
made here and in the Celery reaper task, both reading/writing the same
`ContainerRecord` rows via `Storage` — this in-process `_backends` cache is
just a per-process shortcut to avoid reattaching to an already-known-warm
container on every call; the source of truth for whether a container exists
is always the `ContainerRecord`, never this cache alone.

Takes a bare `session_id` (not a `project_id`/`session_id` pair) — sessions
are keyed globally (see `krutrim_agent_management.base.Storage`), so a session_id
alone is enough to look one up regardless of whether its owner is an `Agent`
or a project-less `Chat`.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from deepagents.backends.sandbox import BaseSandbox
from krutrim_agent_management.models import ContainerRecord

from krutrim_agent_sandbox.factory import create_sandbox_backend
from krutrim_agent_sandbox.policy import SandboxPolicy
from krutrim_agent_sandbox.status_channel import PubSubBackend, publish_container_status

if TYPE_CHECKING:
    from krutrim_agent_management.base import Storage


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AttachHandle:
    backend: BaseSandbox
    owner_id: str


class SandboxRegistry:
    def __init__(
        self,
        store: Storage,
        policy_factory: Callable[[str], SandboxPolicy] | None = None,
        backend_factory: Callable[[str, SandboxPolicy], BaseSandbox] | None = None,
        pubsub: PubSubBackend | None = None,
    ) -> None:
        self._store = store
        self._policy_factory = policy_factory or (lambda owner_id: SandboxPolicy())
        # Injectable for tests (avoid touching real Docker); defaults to the
        # real runtime-selecting factory in production.
        self._backend_factory = backend_factory or create_sandbox_backend
        self._backends: dict[str, BaseSandbox] = {}
        self._lock = threading.Lock()
        # None (the default) means "no live-status publishing" — every
        # publish call site below checks for this, so the registry works
        # exactly as before if the caller doesn't wire a pub/sub backend in.
        self._pubsub = pubsub

    def _publish(self, owner_id: str, status: str, **extra) -> None:
        if self._pubsub is None:
            return
        try:
            publish_container_status(self._pubsub, owner_id, status, **extra)
        except Exception:  # noqa: BLE001 - live status is best-effort, must never break a real sandbox operation
            pass

    async def resolve_owner_id(self, session_id: str) -> tuple[str, str]:
        """(1) An explicit `attached_to_session_id` wins — the session's sandbox
        actions resolve to that other session's container. (2) Otherwise the
        session is its own owner (isolated by default).

        `sandbox_sharing` never affects container identity — "session-shared"/
        "project-shared" only gate the separate cross-agent messaging tool (a
        communication channel between two still-separate containers), not a
        merge of them. `owner_kind` is always "session" through this path;
        "project" is reserved and unused, "channel" (future bot integrations)
        is addressed directly by channel id, never resolved from a session.
        """
        session = await self._store.get_session(session_id)
        if session.attached_to_session_id:
            return session.attached_to_session_id, "session"
        return session_id, "session"

    async def get_or_create(self, session_id: str) -> AttachHandle:
        owner_id, owner_kind = await self.resolve_owner_id(session_id)
        record = await self._store.get_container(owner_id)

        if record is not None and record.status != "stopped":
            backend = self._backends.get(owner_id)
            if backend is None:
                # Process restarted (or this is a different process entirely)
                # but the container itself may still be running — reattach
                # rather than assuming it's gone.
                backend = self._backend_factory(
                    owner_id, self._policy_factory(owner_id)
                )
                self._backends[owner_id] = backend
            record.ref_count += 1
            record.status = "running"
            record.last_active_at = _now_iso()
            await self._store.upsert_container(record)
            self._publish(owner_id, "running", ref_count=record.ref_count)
            return AttachHandle(backend=backend, owner_id=owner_id)

        # Missing or stopped record: hot-reload from the persisted workspace mirror.
        self._publish(owner_id, "starting")
        policy = self._policy_factory(owner_id)
        backend = self._backend_factory(owner_id, policy)
        saved_paths = await self._store.read_workspace_files(owner_id)
        files: list[tuple[str, bytes]] = []
        for path in saved_paths:
            content = await self._store.read_workspace_file(owner_id, path)
            if content is not None:
                files.append((path, content))
        backend.hydrate(files)
        self._backends[owner_id] = backend

        now = _now_iso()
        owner_session = await self._store.get_session(owner_id)
        new_record = ContainerRecord(
            owner_id=owner_id,
            owner_kind=owner_kind,
            project_id=owner_session.project_id,
            container_name=f"krutrim_agent-sandbox-{owner_id}",
            status="running",
            ref_count=1,
            created_at=record.created_at if record is not None else now,
            last_active_at=now,
            policy_snapshot=policy.model_dump(),
        )
        await self._store.upsert_container(new_record)
        self._publish(owner_id, "running", ref_count=1)
        return AttachHandle(backend=backend, owner_id=owner_id)

    async def release(self, owner_id: str) -> None:
        record = await self._store.get_container(owner_id)
        if record is None:
            return
        record.ref_count = max(0, record.ref_count - 1)
        if record.ref_count == 0:
            record.status = "idle"
        await self._store.upsert_container(record)
        self._publish(owner_id, record.status, ref_count=record.ref_count)

    def local_backend(self, owner_id: str) -> BaseSandbox | None:
        return self._backends.get(owner_id)

    def close_all(self) -> None:
        """Best-effort teardown of every backend this process started —
        called on app shutdown. Not part of the idle-reaper's job (that's a
        separate, time-based policy in a Celery task); this is just
        "the process is exiting, don't leak running containers behind it"."""
        for backend in self._backends.values():
            close = getattr(backend, "close", None)
            if callable(close):
                close()
        self._backends.clear()
