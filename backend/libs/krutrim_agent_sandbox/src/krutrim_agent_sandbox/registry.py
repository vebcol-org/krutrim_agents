"""Owner-scoped sandbox registry — the lightweight, in-process form.

The Docker + gRPC in-sandbox runtime has been removed. Every agent run now
executes in the backend process against a plain deepagents
`FilesystemBackend` scoped to the session's workspace directory — no shell
`execute`, no container, no isolation. This is a deliberate placeholder; a
real isolated runtime will be reintroduced later.

`SandboxRegistry` stays as the single entry point request handlers call
before anything that needs a "sandbox": it resolves the owning session
(honouring `attached_to_session_id`) and hands back a filesystem backend
rooted at ``<storage_root>/sessions/<owner_id>/workspace``. With the default
`LocalBlobStore`, that path is the exact same bytes on disk as the blob key
`Storage.read_workspace_file` / `sync_workspace_from_container` use, so RAG
and the sessions file API see the agent's writes with no sync step.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from deepagents.backends.filesystem import FilesystemBackend

if TYPE_CHECKING:
    from krutrim_agent_management.base import Storage


@dataclass
class AttachHandle:
    backend: FilesystemBackend
    owner_id: str


class SandboxRegistry:
    def __init__(self, store: Storage) -> None:
        self._store = store
        self._backends: dict[str, FilesystemBackend] = {}
        self._lock = threading.Lock()

    async def resolve_owner_id(self, session_id: str) -> tuple[str, str]:
        """(1) An explicit `attached_to_session_id` wins — the session's
        sandbox actions resolve to that other session's workspace. (2)
        Otherwise the session is its own owner (isolated by default).

        `sandbox_sharing` never affects workspace identity — it only gates the
        separate cross-agent `message_agent` tool.
        """
        session = await self._store.get_session(session_id)
        if session.attached_to_session_id:
            return session.attached_to_session_id, "session"
        return session_id, "session"

    async def get_or_create(self, session_id: str) -> AttachHandle:
        owner_id, _ = await self.resolve_owner_id(session_id)
        workspace_dir = self._store.session_dir(owner_id) / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            backend = self._backends.get(owner_id)
            if backend is None:
                backend = FilesystemBackend(
                    root_dir=str(workspace_dir), virtual_mode=True
                )
                self._backends[owner_id] = backend
        return AttachHandle(backend=backend, owner_id=owner_id)

    async def release(self, owner_id: str) -> None:
        """No-op: the workspace is a real directory on disk, already durable."""

    async def interrupt(self, session_id: str) -> bool:
        """Nothing runs server-side to cancel in the in-process model."""
        return False

    def local_backend(self, owner_id: str) -> FilesystemBackend | None:
        return self._backends.get(owner_id)

    def close_all(self) -> None:
        with self._lock:
            self._backends.clear()
