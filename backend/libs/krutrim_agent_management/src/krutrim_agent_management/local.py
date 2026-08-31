"""SQLite + filesystem `Storage` backend — the only implementation that ships today.

Layout under `STORAGE_ROOT` (see `paths.default_storage_root`):

    project.db / agents.db / chats.db / sessions.db  -- one global table each
    projects/{project_id}/MEMORY.md, cache/{namespace}/{sha256(key)}.json
    sessions/{session_id}/checkpointer.json, usage.json, workspace/, embeddings/

Non-relational artifacts go through `BlobStore` (`blobstore.py`), not raw filesystem calls.
Writes are serialized with a per-db-file lock; not safe for two processes sharing one
`STORAGE_ROOT` concurrently — no cross-process locking.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from krutrim_agent_management.base import Storage
from krutrim_agent_management.blobstore import LocalBlobStore
from krutrim_agent_management.hooks import run_session_delete_hooks
from krutrim_agent_management.models import (
    Agent,
    Chat,
    OwnerType,
    Project,
    SessionInfo,
    SharingScope,
)
from krutrim_agent_management.storage_factory import register_storage_backend


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_columns(
    conn: sqlite3.Connection, table: str, columns: dict[str, str]
) -> None:
    """Idempotent `ALTER TABLE ADD COLUMN` for columns introduced after a table
    already existed on disk — so opening an older `STORAGE_ROOT` upgrades in place."""
    existing = {
        row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for name, ddl_type in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}")


def _row_to_project(row: sqlite3.Row) -> Project:
    data = dict(row)
    overrides = data.get("sandbox_resource_overrides")
    data["sandbox_resource_overrides"] = json.loads(overrides) if overrides else None
    return Project(**data)


def _row_to_agent(row: sqlite3.Row) -> Agent:
    data = dict(row)
    overrides = data.get("sandbox_resource_overrides")
    data["sandbox_resource_overrides"] = json.loads(overrides) if overrides else None
    return Agent(**data)


def _row_to_chat(row: sqlite3.Row) -> Chat:
    data = dict(row)
    overrides = data.get("sandbox_resource_overrides")
    data["sandbox_resource_overrides"] = json.loads(overrides) if overrides else None
    return Chat(**data)


def _row_to_session(row: sqlite3.Row) -> SessionInfo:
    data = dict(row)
    linked = data.get("linked_session_ids")
    data["linked_session_ids"] = json.loads(linked) if linked else []
    return SessionInfo(**data)


class _LocalStorageImpl:
    """Synchronous implementation; `LocalStorage` below dispatches each call to a worker
    thread via `asyncio.to_thread` to satisfy the async `Storage` contract."""

    def __init__(self, root: Path | None = None):
        if root is None:
            from krutrim_agent_management.config import (
                settings,
            )  # deferred: avoid import-order coupling

            root = settings.storage_root
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)
        self._blobs = LocalBlobStore(self._root)
        self._project_db_lock = threading.Lock()
        self._agents_db_lock = threading.Lock()
        self._chats_db_lock = threading.Lock()
        self._sessions_db_lock = threading.Lock()
        self._init_project_db()
        self._init_agents_db()
        self._init_chats_db()
        self._init_sessions_db()

    # -- paths ----------------------------------------------------------

    @property
    def _project_db_path(self) -> Path:
        return self._root / "project.db"

    @property
    def _agents_db_path(self) -> Path:
        return self._root / "agents.db"

    @property
    def _chats_db_path(self) -> Path:
        return self._root / "chats.db"

    @property
    def _sessions_db_path(self) -> Path:
        return self._root / "sessions.db"

    def project_dir(self, project_id: str) -> Path:
        return self._root / "projects" / project_id

    def session_dir(self, session_id: str) -> Path:
        return self._root / "sessions" / session_id

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    # -- blob keys (relative paths handed to `BlobStore`, not filesystem paths) --

    @staticmethod
    def _memory_key(project_id: str) -> str:
        return f"projects/{project_id}/MEMORY.md"

    @staticmethod
    def _checkpoint_key(session_id: str) -> str:
        return f"sessions/{session_id}/checkpointer.json"

    @staticmethod
    def _usage_key(session_id: str) -> str:
        return f"sessions/{session_id}/usage.json"

    @staticmethod
    def _cache_key(project_id: str, namespace: str, key: str) -> str:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return f"projects/{project_id}/cache/{namespace}/{digest}.json"

    @staticmethod
    def _workspace_prefix(session_id: str) -> str:
        return f"sessions/{session_id}/workspace"

    # -- schema -------------------------------------------------------------

    def _init_project_db(self) -> None:
        with self._project_db_lock, self._connect(self._project_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    project_title TEXT NOT NULL,
                    project_information TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            _ensure_columns(
                conn,
                "projects",
                {
                    "sandbox_sharing": "TEXT NOT NULL DEFAULT 'isolated'",
                    "sandbox_idle_timeout_seconds": "INTEGER",
                    "sandbox_resource_overrides": "TEXT",
                },
            )

    def _init_agents_db(self) -> None:
        with self._agents_db_lock, self._connect(self._agents_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    agent_key TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    sandbox_sharing TEXT,
                    sandbox_idle_timeout_seconds INTEGER,
                    sandbox_resource_overrides TEXT
                )
                """
            )

    def _init_chats_db(self) -> None:
        with self._chats_db_lock, self._connect(self._chats_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chats (
                    chat_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    display_name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    sandbox_sharing TEXT,
                    sandbox_idle_timeout_seconds INTEGER,
                    sandbox_resource_overrides TEXT
                )
                """
            )

    def _init_sessions_db(self) -> None:
        with self._sessions_db_lock, self._connect(self._sessions_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    owner_type TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    project_id TEXT,
                    display_name TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    sandbox_sharing TEXT NOT NULL DEFAULT 'isolated',
                    attached_to_session_id TEXT,
                    linked_session_ids TEXT NOT NULL DEFAULT '[]'
                )
                """
            )

    # -- projects -------------------------------------------------------

    def create_project(
        self, project_title: str, project_information: str = ""
    ) -> Project:
        project_id = str(uuid.uuid4())
        now = _now_iso()
        with self._project_db_lock, self._connect(self._project_db_path) as conn:
            conn.execute(
                "INSERT INTO projects "
                "(project_id, project_title, project_information, created_at, updated_at, "
                "sandbox_sharing, sandbox_idle_timeout_seconds, sandbox_resource_overrides) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    project_title,
                    project_information,
                    now,
                    now,
                    "isolated",
                    None,
                    None,
                ),
            )
        self.project_dir(project_id).mkdir(parents=True, exist_ok=True)
        return Project(
            project_id=project_id,
            project_title=project_title,
            project_information=project_information,
            created_at=now,
            updated_at=now,
        )

    def get_project(self, project_id: str) -> Project:
        with self._project_db_lock, self._connect(self._project_db_path) as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown project {project_id!r}")
        return _row_to_project(row)

    def list_projects(self) -> list[Project]:
        with self._project_db_lock, self._connect(self._project_db_path) as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY created_at").fetchall()
        return [_row_to_project(row) for row in rows]

    def update_project(
        self,
        project_id: str,
        *,
        project_title: str | None = None,
        project_information: str | None = None,
    ) -> Project:
        current = self.get_project(project_id)
        new_title = current.project_title if project_title is None else project_title
        new_information = (
            current.project_information
            if project_information is None
            else project_information
        )
        now = _now_iso()
        with self._project_db_lock, self._connect(self._project_db_path) as conn:
            conn.execute(
                "UPDATE projects SET project_title = ?, project_information = ?, updated_at = ? WHERE project_id = ?",
                (new_title, new_information, now, project_id),
            )
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> None:
        self.get_project(project_id)  # raises KeyError if unknown
        for agent in self.list_agents(project_id):
            self.delete_agent(agent.agent_id)
        for chat in self.list_chats(project_id):
            self.delete_chat(chat.chat_id)
        with self._project_db_lock, self._connect(self._project_db_path) as conn:
            conn.execute("DELETE FROM projects WHERE project_id = ?", (project_id,))
        project_dir = self.project_dir(project_id)
        if project_dir.exists():
            shutil.rmtree(project_dir)

    # -- agents -----------------------------------------------------------

    def create_agent(self, project_id: str, agent_key: str, display_name: str) -> Agent:
        self.get_project(project_id)  # raises KeyError if unknown
        agent_id = str(uuid.uuid4())
        now = _now_iso()
        with self._agents_db_lock, self._connect(self._agents_db_path) as conn:
            conn.execute(
                "INSERT INTO agents "
                "(agent_id, project_id, agent_key, display_name, created_at, updated_at, "
                "sandbox_sharing, sandbox_idle_timeout_seconds, sandbox_resource_overrides) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    agent_id,
                    project_id,
                    agent_key,
                    display_name,
                    now,
                    now,
                    None,
                    None,
                    None,
                ),
            )
        return Agent(
            agent_id=agent_id,
            project_id=project_id,
            agent_key=agent_key,
            display_name=display_name,
            created_at=now,
            updated_at=now,
        )

    def get_agent(self, agent_id: str) -> Agent:
        with self._agents_db_lock, self._connect(self._agents_db_path) as conn:
            row = conn.execute(
                "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown agent {agent_id!r}")
        return _row_to_agent(row)

    def list_agents(self, project_id: str) -> list[Agent]:
        with self._agents_db_lock, self._connect(self._agents_db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM agents WHERE project_id = ? ORDER BY created_at",
                (project_id,),
            ).fetchall()
        return [_row_to_agent(row) for row in rows]

    def update_agent(self, agent_id: str, *, display_name: str | None = None) -> Agent:
        current = self.get_agent(agent_id)
        new_name = current.display_name if display_name is None else display_name
        now = _now_iso()
        with self._agents_db_lock, self._connect(self._agents_db_path) as conn:
            conn.execute(
                "UPDATE agents SET display_name = ?, updated_at = ? WHERE agent_id = ?",
                (new_name, now, agent_id),
            )
        return self.get_agent(agent_id)

    def delete_agent(self, agent_id: str) -> None:
        self.get_agent(agent_id)  # raises KeyError if unknown
        for session in self.list_sessions("agent", agent_id):
            self.delete_session(session.session_id)
        with self._agents_db_lock, self._connect(self._agents_db_path) as conn:
            conn.execute("DELETE FROM agents WHERE agent_id = ?", (agent_id,))

    def update_agent_sandbox_policy(
        self,
        agent_id: str,
        *,
        sharing: SharingScope | None = None,
        idle_timeout_seconds: int | None = None,
        resource_overrides: dict[str, int] | None = None,
    ) -> Agent:
        current = self.get_agent(agent_id)
        new_sharing = current.sandbox_sharing if sharing is None else sharing
        new_timeout = (
            current.sandbox_idle_timeout_seconds
            if idle_timeout_seconds is None
            else idle_timeout_seconds
        )
        new_overrides = (
            current.sandbox_resource_overrides
            if resource_overrides is None
            else resource_overrides
        )
        now = _now_iso()
        with self._agents_db_lock, self._connect(self._agents_db_path) as conn:
            conn.execute(
                "UPDATE agents SET sandbox_sharing = ?, sandbox_idle_timeout_seconds = ?, "
                "sandbox_resource_overrides = ?, updated_at = ? WHERE agent_id = ?",
                (
                    new_sharing,
                    new_timeout,
                    json.dumps(new_overrides) if new_overrides is not None else None,
                    now,
                    agent_id,
                ),
            )
        return self.get_agent(agent_id)

    # -- chats --------------------------------------------------------------

    def create_chat(
        self,
        display_name: str,
        provider: str,
        model: str,
        project_id: str | None = None,
    ) -> Chat:
        if project_id is not None:
            self.get_project(project_id)  # raises KeyError if unknown
        chat_id = str(uuid.uuid4())
        now = _now_iso()
        with self._chats_db_lock, self._connect(self._chats_db_path) as conn:
            conn.execute(
                "INSERT INTO chats "
                "(chat_id, project_id, display_name, provider, model, created_at, updated_at, "
                "sandbox_sharing, sandbox_idle_timeout_seconds, sandbox_resource_overrides) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chat_id,
                    project_id,
                    display_name,
                    provider,
                    model,
                    now,
                    now,
                    None,
                    None,
                    None,
                ),
            )
        return Chat(
            chat_id=chat_id,
            project_id=project_id,
            display_name=display_name,
            provider=provider,
            model=model,
            created_at=now,
            updated_at=now,
        )

    def get_chat(self, chat_id: str) -> Chat:
        with self._chats_db_lock, self._connect(self._chats_db_path) as conn:
            row = conn.execute(
                "SELECT * FROM chats WHERE chat_id = ?", (chat_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown chat {chat_id!r}")
        return _row_to_chat(row)

    def list_chats(self, project_id: str | None = None) -> list[Chat]:
        with self._chats_db_lock, self._connect(self._chats_db_path) as conn:
            if project_id is None:
                rows = conn.execute(
                    "SELECT * FROM chats WHERE project_id IS NULL ORDER BY created_at"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM chats WHERE project_id = ? ORDER BY created_at",
                    (project_id,),
                ).fetchall()
        return [_row_to_chat(row) for row in rows]

    def update_chat(self, chat_id: str, *, display_name: str | None = None) -> Chat:
        current = self.get_chat(chat_id)
        new_name = current.display_name if display_name is None else display_name
        now = _now_iso()
        with self._chats_db_lock, self._connect(self._chats_db_path) as conn:
            conn.execute(
                "UPDATE chats SET display_name = ?, updated_at = ? WHERE chat_id = ?",
                (new_name, now, chat_id),
            )
        return self.get_chat(chat_id)

    def move_chat(self, chat_id: str, *, project_id: str | None) -> Chat:
        self.get_chat(chat_id)  # raises KeyError if unknown
        if project_id is not None:
            self.get_project(project_id)  # raises KeyError if unknown
        now = _now_iso()
        with self._chats_db_lock, self._connect(self._chats_db_path) as conn:
            conn.execute(
                "UPDATE chats SET project_id = ?, updated_at = ? WHERE chat_id = ?",
                (project_id, now, chat_id),
            )
        chat = self.get_chat(chat_id)
        # A moved chat's sessions are denormalized onto the new project_id too,
        # so cascade-delete / project-scoped listing stays correct without a join.
        with self._sessions_db_lock, self._connect(self._sessions_db_path) as conn:
            conn.execute(
                "UPDATE sessions SET project_id = ? WHERE owner_type = 'chat' AND owner_id = ?",
                (project_id, chat_id),
            )
        return chat

    def delete_chat(self, chat_id: str) -> None:
        self.get_chat(chat_id)  # raises KeyError if unknown
        sessions = self.list_sessions("chat", chat_id)
        logger.info(
            "deleting chat {} and its {} session(s) (incl. vector indexes)",
            chat_id,
            len(sessions),
        )
        for session in sessions:
            self.delete_session(session.session_id)
        with self._chats_db_lock, self._connect(self._chats_db_path) as conn:
            conn.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))

    def update_chat_sandbox_policy(
        self,
        chat_id: str,
        *,
        sharing: SharingScope | None = None,
        idle_timeout_seconds: int | None = None,
        resource_overrides: dict[str, int] | None = None,
    ) -> Chat:
        current = self.get_chat(chat_id)
        new_sharing = current.sandbox_sharing if sharing is None else sharing
        new_timeout = (
            current.sandbox_idle_timeout_seconds
            if idle_timeout_seconds is None
            else idle_timeout_seconds
        )
        new_overrides = (
            current.sandbox_resource_overrides
            if resource_overrides is None
            else resource_overrides
        )
        now = _now_iso()
        with self._chats_db_lock, self._connect(self._chats_db_path) as conn:
            conn.execute(
                "UPDATE chats SET sandbox_sharing = ?, sandbox_idle_timeout_seconds = ?, "
                "sandbox_resource_overrides = ?, updated_at = ? WHERE chat_id = ?",
                (
                    new_sharing,
                    new_timeout,
                    json.dumps(new_overrides) if new_overrides is not None else None,
                    now,
                    chat_id,
                ),
            )
        return self.get_chat(chat_id)

    # -- sandbox sharing policy (project default) --------------------------

    def update_project_sandbox_policy(
        self,
        project_id: str,
        *,
        sharing: SharingScope | None = None,
        idle_timeout_seconds: int | None = None,
        resource_overrides: dict[str, int] | None = None,
    ) -> Project:
        current = self.get_project(project_id)
        new_sharing = current.sandbox_sharing if sharing is None else sharing
        new_timeout = (
            current.sandbox_idle_timeout_seconds
            if idle_timeout_seconds is None
            else idle_timeout_seconds
        )
        new_overrides = (
            current.sandbox_resource_overrides
            if resource_overrides is None
            else resource_overrides
        )
        now = _now_iso()
        with self._project_db_lock, self._connect(self._project_db_path) as conn:
            conn.execute(
                "UPDATE projects SET sandbox_sharing = ?, sandbox_idle_timeout_seconds = ?, "
                "sandbox_resource_overrides = ?, updated_at = ? WHERE project_id = ?",
                (
                    new_sharing,
                    new_timeout,
                    json.dumps(new_overrides) if new_overrides is not None else None,
                    now,
                    project_id,
                ),
            )
        return self.get_project(project_id)

    def update_session_sandbox_policy(
        self,
        session_id: str,
        *,
        sharing: SharingScope | None = None,
        attached_to_session_id: str | None = None,
        linked_session_ids: list[str] | None = None,
    ) -> SessionInfo:
        current = self.get_session(session_id)
        new_sharing = current.sandbox_sharing if sharing is None else sharing
        new_attached = (
            current.attached_to_session_id
            if attached_to_session_id is None
            else attached_to_session_id
        )
        new_linked = (
            current.linked_session_ids
            if linked_session_ids is None
            else linked_session_ids
        )
        now = _now_iso()
        with self._sessions_db_lock, self._connect(self._sessions_db_path) as conn:
            conn.execute(
                "UPDATE sessions SET sandbox_sharing = ?, attached_to_session_id = ?, "
                "linked_session_ids = ?, updated_at = ? WHERE session_id = ?",
                (new_sharing, new_attached, json.dumps(new_linked), now, session_id),
            )
        return self.get_session(session_id)

    # -- agent memory -----------------------------------------------------

    def read_memory(self, project_id: str) -> str:
        self.get_project(project_id)  # raises KeyError if unknown
        data = self._blobs.read(self._memory_key(project_id))
        return data.decode("utf-8") if data is not None else ""

    def write_memory(self, project_id: str, content: str) -> None:
        self.get_project(project_id)  # raises KeyError if unknown
        self._blobs.write(self._memory_key(project_id), content.encode("utf-8"))

    # -- sessions -------------------------------------------------------

    def _resolve_owner_project_id(
        self, owner_type: OwnerType, owner_id: str
    ) -> str | None:
        if owner_type == "agent":
            return self.get_agent(owner_id).project_id  # raises KeyError if unknown
        return self.get_chat(
            owner_id
        ).project_id  # raises KeyError if unknown; may be None

    def create_session(self, owner_type: OwnerType, owner_id: str) -> SessionInfo:
        project_id = self._resolve_owner_project_id(owner_type, owner_id)
        session_id = str(uuid.uuid4())
        now = _now_iso()
        with self._sessions_db_lock, self._connect(self._sessions_db_path) as conn:
            conn.execute(
                "INSERT INTO sessions "
                "(session_id, owner_type, owner_id, project_id, display_name, created_at, updated_at, "
                "sandbox_sharing, attached_to_session_id, linked_session_ids) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    owner_type,
                    owner_id,
                    project_id,
                    None,
                    now,
                    now,
                    "isolated",
                    None,
                    "[]",
                ),
            )
        self.session_dir(session_id).mkdir(parents=True, exist_ok=True)
        return SessionInfo(
            session_id=session_id,
            owner_type=owner_type,
            owner_id=owner_id,
            project_id=project_id,
            created_at=now,
            updated_at=now,
        )

    def get_session(self, session_id: str) -> SessionInfo:
        with self._sessions_db_lock, self._connect(self._sessions_db_path) as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown session {session_id!r}")
        return _row_to_session(row)

    def list_sessions(self, owner_type: OwnerType, owner_id: str) -> list[SessionInfo]:
        with self._sessions_db_lock, self._connect(self._sessions_db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM sessions WHERE owner_type = ? AND owner_id = ? ORDER BY created_at",
                (owner_type, owner_id),
            ).fetchall()
        return [_row_to_session(row) for row in rows]

    def update_session(
        self, session_id: str, *, display_name: str | None = None
    ) -> SessionInfo:
        current = self.get_session(session_id)
        new_name = current.display_name if display_name is None else display_name
        now = _now_iso()
        with self._sessions_db_lock, self._connect(self._sessions_db_path) as conn:
            conn.execute(
                "UPDATE sessions SET display_name = ?, updated_at = ? WHERE session_id = ?",
                (new_name, now, session_id),
            )
        return self.get_session(session_id)

    def delete_session(self, session_id: str) -> None:
        self.get_session(session_id)  # raises KeyError if unknown
        # External per-session teardown (e.g. krutrim_agent_rag dropping this
        # session's Qdrant collection / FAISS index) runs before the row and
        # directory go away. Best-effort — see hooks.run_session_delete_hooks.
        run_session_delete_hooks(session_id)
        with self._sessions_db_lock, self._connect(self._sessions_db_path) as conn:
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        session_dir = self.session_dir(session_id)
        if session_dir.exists():
            shutil.rmtree(session_dir)
        logger.debug("deleted session {} (row + {})", session_id, session_dir)

    # -- checkpointer -------------------------------------------------------

    def read_checkpoint(self, session_id: str) -> dict[str, Any] | None:
        data = self._blobs.read(self._checkpoint_key(session_id))
        return json.loads(data) if data is not None else None

    def write_checkpoint(self, session_id: str, data: dict[str, Any]) -> None:
        payload = json.dumps(data, indent=2, sort_keys=True, default=str).encode(
            "utf-8"
        )
        self._blobs.write(self._checkpoint_key(session_id), payload)

    # -- usage --------------------------------------------------------------

    def read_usage(self, session_id: str) -> dict[str, Any] | None:
        data = self._blobs.read(self._usage_key(session_id))
        return json.loads(data) if data is not None else None

    def write_usage(self, session_id: str, data: dict[str, Any]) -> None:
        payload = json.dumps(data, indent=2, sort_keys=True, default=str).encode(
            "utf-8"
        )
        self._blobs.write(self._usage_key(session_id), payload)

    # -- rag document manifest --------------------------------------------

    @staticmethod
    def _rag_manifest_key(session_id: str) -> str:
        return f"sessions/{session_id}/rag/manifest.json"

    def read_rag_manifest(self, session_id: str) -> list[dict[str, Any]]:
        data = self._blobs.read(self._rag_manifest_key(session_id))
        if data is None:
            return []
        try:
            items = json.loads(data)
        except json.JSONDecodeError:
            return []
        return items if isinstance(items, list) else []

    def _write_rag_manifest(self, session_id: str, items: list[dict[str, Any]]) -> None:
        payload = json.dumps(items, indent=2, default=str).encode("utf-8")
        self._blobs.write(self._rag_manifest_key(session_id), payload)

    def append_rag_manifest(
        self, session_id: str, entry: dict[str, Any]
    ) -> list[dict[str, Any]]:
        items = [
            e
            for e in self.read_rag_manifest(session_id)
            if e.get("document_id") != entry.get("document_id")
        ]
        items.append(entry)
        self._write_rag_manifest(session_id, items)
        return items

    def remove_rag_manifest_entry(
        self, session_id: str, document_id: str
    ) -> list[dict[str, Any]]:
        items = [
            e
            for e in self.read_rag_manifest(session_id)
            if e.get("document_id") != document_id
        ]
        self._write_rag_manifest(session_id, items)
        return items

    # -- cache (mcp / rag / tool result caching) -----------------------

    def cache_get(self, project_id: str, namespace: str, key: str) -> Any | None:
        data = self._blobs.read(self._cache_key(project_id, namespace, key))
        return json.loads(data)["value"] if data is not None else None

    def cache_set(self, project_id: str, namespace: str, key: str, value: Any) -> None:
        payload = {"key": key, "value": value, "cached_at": _now_iso()}
        encoded = json.dumps(payload, indent=2, sort_keys=True, default=str).encode(
            "utf-8"
        )
        self._blobs.write(self._cache_key(project_id, namespace, key), encoded)

    # -- session workspace --------------------------------------------------

    def read_workspace_files(self, session_id: str) -> list[str]:
        self.get_session(session_id)  # raises KeyError if unknown
        return self._blobs.list(self._workspace_prefix(session_id))

    def read_workspace_file(self, session_id: str, path: str) -> bytes | None:
        self.get_session(session_id)
        return self._blobs.read(f"{self._workspace_prefix(session_id)}/{path}")

    def sync_workspace_from_container(
        self, session_id: str, files: list[tuple[str, bytes]]
    ) -> None:
        self.get_session(session_id)
        prefix = self._workspace_prefix(session_id)
        for path, content in files:
            self._blobs.write(f"{prefix}/{path}", content)

    # -- per-run scoped export / import (in-sandbox agent runtime) ---------

    @staticmethod
    def _copy_scoped_row(
        src_db: Path, dst_db: Path, table: str, id_col: str, id_val: str
    ) -> None:
        """Copy exactly one row (matched on `id_col`) between two sqlite files
        of the same schema. `table`/`id_col` are module-internal constants, not
        caller input."""
        with _LocalStorageImpl._connect(src_db) as src:
            row = src.execute(
                f"SELECT * FROM {table} WHERE {id_col} = ?", (id_val,)
            ).fetchone()
        if row is None:
            raise KeyError(f"{table}.{id_col}={id_val!r} not found for scope export")
        cols = list(row.keys())
        collist = ", ".join(cols)
        placeholders = ", ".join("?" for _ in cols)
        with _LocalStorageImpl._connect(dst_db) as dst:
            dst.execute(
                f"INSERT OR REPLACE INTO {table} ({collist}) VALUES ({placeholders})",
                tuple(row[c] for c in cols),
            )

    def export_scope(
        self, project_id: str, agent_id: str, session_id: str, staging_dir: Path
    ) -> None:
        self.get_project(project_id)  # KeyError if unknown
        agent = self.get_agent(agent_id)
        session = self.get_session(session_id)
        if agent.project_id != project_id:
            raise KeyError(
                f"Agent {agent_id!r} is not in project {project_id!r} — refusing scope export"
            )
        if session.owner_type != "agent" or session.owner_id != agent_id:
            raise KeyError(
                f"Session {session_id!r} does not belong to agent {agent_id!r} — refusing scope export"
            )

        staging_dir = Path(staging_dir)
        store_root = staging_dir / "store"
        workspace_dir = staging_dir / "workspace"
        out_dir = staging_dir / "out"
        for d in (store_root, workspace_dir, out_dir):
            d.mkdir(parents=True, exist_ok=True)

        dest = _LocalStorageImpl(store_root)  # writes the empty schema

        self._copy_scoped_row(
            self._project_db_path, dest._project_db_path, "projects", "project_id", project_id
        )
        self._copy_scoped_row(
            self._agents_db_path, dest._agents_db_path, "agents", "agent_id", agent_id
        )
        self._copy_scoped_row(
            self._sessions_db_path,
            dest._sessions_db_path,
            "sessions",
            "session_id",
            session_id,
        )

        # Session blob subtree (checkpointer.json, usage.json, rag/,
        # langgraph_checkpoint.sqlite) — everything under sessions/<id>/ EXCEPT
        # the workspace mirror, which is exposed separately as a real dir the
        # container mounts at /workspace.
        src_session_dir = self.session_dir(session_id)
        dest_session_dir = dest.session_dir(session_id)
        dest_session_dir.mkdir(parents=True, exist_ok=True)
        if src_session_dir.exists():
            for item in src_session_dir.iterdir():
                if item.name == "workspace":
                    continue
                target = dest_session_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target)

        src_workspace = src_session_dir / "workspace"
        if src_workspace.exists():
            shutil.copytree(src_workspace, workspace_dir, dirs_exist_ok=True)

        memory = self._blobs.read(self._memory_key(project_id))
        if memory is not None:
            dest._blobs.write(dest._memory_key(project_id), memory)

    def import_scope(self, session_id: str, staging_dir: Path) -> None:
        self.get_session(session_id)  # KeyError if unknown
        staging_dir = Path(staging_dir)
        workspace_dir = staging_dir / "workspace"
        out_dir = staging_dir / "out"
        session_dir = self.session_dir(session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        if workspace_dir.exists():
            files = [
                (str(p.relative_to(workspace_dir)), p.read_bytes())
                for p in workspace_dir.rglob("*")
                if p.is_file()
            ]
            if files:
                self.sync_workspace_from_container(session_id, files)

        if not out_dir.exists():
            return

        checkpoint = out_dir / "langgraph_checkpoint.sqlite"
        if checkpoint.is_file():
            shutil.copy2(checkpoint, session_dir / "langgraph_checkpoint.sqlite")

        usage = out_dir / "usage.json"
        if usage.is_file():
            self._blobs.write(self._usage_key(session_id), usage.read_bytes())

        rag_manifest = out_dir / "rag" / "manifest.json"
        if rag_manifest.is_file():
            self._blobs.write(self._rag_manifest_key(session_id), rag_manifest.read_bytes())

        runs_dir = out_dir / "runs"
        if runs_dir.is_dir():
            dest_runs = session_dir / "runs"
            dest_runs.mkdir(parents=True, exist_ok=True)
            for jsonl in runs_dir.glob("*.jsonl"):
                dest = dest_runs / jsonl.name
                if dest.exists() and dest.stat().st_size:
                    # The host's HostBridge already wrote its own lines to this
                    # file during the run (every LLM / host-tool call). The
                    # container's copy carries the in-graph + structural lines.
                    # Append rather than overwrite so neither side is lost.
                    existing = dest.read_bytes()
                    sep = b"" if existing.endswith(b"\n") else b"\n"
                    with dest.open("ab") as out:
                        out.write(sep + jsonl.read_bytes())
                else:
                    shutil.copy2(jsonl, dest)


class LocalStorage(Storage):
    """Async `Storage` implementation; each method dispatches to a worker thread running
    the corresponding `_LocalStorageImpl` method."""

    def __init__(self, root: Path | None = None):
        self._impl = _LocalStorageImpl(root)

    # -- paths (sync helpers, no I/O) --------------------------------------

    def project_dir(self, project_id: str) -> Path:
        return self._impl.project_dir(project_id)

    def session_dir(self, session_id: str) -> Path:
        return self._impl.session_dir(session_id)

    # -- projects -----------------------------------------------------------

    async def create_project(
        self, project_title: str, project_information: str = ""
    ) -> Project:
        return await asyncio.to_thread(
            self._impl.create_project, project_title, project_information
        )

    async def get_project(self, project_id: str) -> Project:
        return await asyncio.to_thread(self._impl.get_project, project_id)

    async def list_projects(self) -> list[Project]:
        return await asyncio.to_thread(self._impl.list_projects)

    async def update_project(
        self,
        project_id: str,
        *,
        project_title: str | None = None,
        project_information: str | None = None,
    ) -> Project:
        return await asyncio.to_thread(
            self._impl.update_project,
            project_id,
            project_title=project_title,
            project_information=project_information,
        )

    async def delete_project(self, project_id: str) -> None:
        return await asyncio.to_thread(self._impl.delete_project, project_id)

    # -- agents -------------------------------------------------------------

    async def create_agent(
        self, project_id: str, agent_key: str, display_name: str
    ) -> Agent:
        return await asyncio.to_thread(
            self._impl.create_agent, project_id, agent_key, display_name
        )

    async def get_agent(self, agent_id: str) -> Agent:
        return await asyncio.to_thread(self._impl.get_agent, agent_id)

    async def list_agents(self, project_id: str) -> list[Agent]:
        return await asyncio.to_thread(self._impl.list_agents, project_id)

    async def update_agent(
        self, agent_id: str, *, display_name: str | None = None
    ) -> Agent:
        return await asyncio.to_thread(
            self._impl.update_agent, agent_id, display_name=display_name
        )

    async def delete_agent(self, agent_id: str) -> None:
        return await asyncio.to_thread(self._impl.delete_agent, agent_id)

    async def update_agent_sandbox_policy(
        self,
        agent_id: str,
        *,
        sharing: SharingScope | None = None,
        idle_timeout_seconds: int | None = None,
        resource_overrides: dict[str, int] | None = None,
    ) -> Agent:
        return await asyncio.to_thread(
            self._impl.update_agent_sandbox_policy,
            agent_id,
            sharing=sharing,
            idle_timeout_seconds=idle_timeout_seconds,
            resource_overrides=resource_overrides,
        )

    # -- chats ----------------------------------------------------------

    async def create_chat(
        self,
        display_name: str,
        provider: str,
        model: str,
        project_id: str | None = None,
    ) -> Chat:
        return await asyncio.to_thread(
            self._impl.create_chat, display_name, provider, model, project_id
        )

    async def get_chat(self, chat_id: str) -> Chat:
        return await asyncio.to_thread(self._impl.get_chat, chat_id)

    async def list_chats(self, project_id: str | None = None) -> list[Chat]:
        return await asyncio.to_thread(self._impl.list_chats, project_id)

    async def update_chat(
        self, chat_id: str, *, display_name: str | None = None
    ) -> Chat:
        return await asyncio.to_thread(
            self._impl.update_chat, chat_id, display_name=display_name
        )

    async def move_chat(self, chat_id: str, *, project_id: str | None) -> Chat:
        return await asyncio.to_thread(
            self._impl.move_chat, chat_id, project_id=project_id
        )

    async def delete_chat(self, chat_id: str) -> None:
        return await asyncio.to_thread(self._impl.delete_chat, chat_id)

    async def update_chat_sandbox_policy(
        self,
        chat_id: str,
        *,
        sharing: SharingScope | None = None,
        idle_timeout_seconds: int | None = None,
        resource_overrides: dict[str, int] | None = None,
    ) -> Chat:
        return await asyncio.to_thread(
            self._impl.update_chat_sandbox_policy,
            chat_id,
            sharing=sharing,
            idle_timeout_seconds=idle_timeout_seconds,
            resource_overrides=resource_overrides,
        )

    # -- sandbox sharing policy (project default) --------------------------

    async def update_project_sandbox_policy(
        self,
        project_id: str,
        *,
        sharing: SharingScope | None = None,
        idle_timeout_seconds: int | None = None,
        resource_overrides: dict[str, int] | None = None,
    ) -> Project:
        return await asyncio.to_thread(
            self._impl.update_project_sandbox_policy,
            project_id,
            sharing=sharing,
            idle_timeout_seconds=idle_timeout_seconds,
            resource_overrides=resource_overrides,
        )

    async def update_session_sandbox_policy(
        self,
        session_id: str,
        *,
        sharing: SharingScope | None = None,
        attached_to_session_id: str | None = None,
        linked_session_ids: list[str] | None = None,
    ) -> SessionInfo:
        return await asyncio.to_thread(
            self._impl.update_session_sandbox_policy,
            session_id,
            sharing=sharing,
            attached_to_session_id=attached_to_session_id,
            linked_session_ids=linked_session_ids,
        )

    # -- agent memory ---------------------------------------------------

    async def read_memory(self, project_id: str) -> str:
        return await asyncio.to_thread(self._impl.read_memory, project_id)

    async def write_memory(self, project_id: str, content: str) -> None:
        return await asyncio.to_thread(self._impl.write_memory, project_id, content)

    # -- sessions -------------------------------------------------------

    async def create_session(self, owner_type: OwnerType, owner_id: str) -> SessionInfo:
        return await asyncio.to_thread(self._impl.create_session, owner_type, owner_id)

    async def get_session(self, session_id: str) -> SessionInfo:
        return await asyncio.to_thread(self._impl.get_session, session_id)

    async def list_sessions(
        self, owner_type: OwnerType, owner_id: str
    ) -> list[SessionInfo]:
        return await asyncio.to_thread(self._impl.list_sessions, owner_type, owner_id)

    async def update_session(
        self, session_id: str, *, display_name: str | None = None
    ) -> SessionInfo:
        return await asyncio.to_thread(
            self._impl.update_session, session_id, display_name=display_name
        )

    async def delete_session(self, session_id: str) -> None:
        return await asyncio.to_thread(self._impl.delete_session, session_id)

    # -- checkpointer -----------------------------------------------------

    async def read_checkpoint(self, session_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._impl.read_checkpoint, session_id)

    async def write_checkpoint(self, session_id: str, data: dict[str, Any]) -> None:
        return await asyncio.to_thread(self._impl.write_checkpoint, session_id, data)

    # -- usage ------------------------------------------------------------

    async def read_usage(self, session_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._impl.read_usage, session_id)

    async def write_usage(self, session_id: str, data: dict[str, Any]) -> None:
        return await asyncio.to_thread(self._impl.write_usage, session_id, data)

    # -- rag document manifest ------------------------------------------

    async def read_rag_manifest(self, session_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._impl.read_rag_manifest, session_id)

    async def append_rag_manifest(
        self, session_id: str, entry: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._impl.append_rag_manifest, session_id, entry
        )

    async def remove_rag_manifest_entry(
        self, session_id: str, document_id: str
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._impl.remove_rag_manifest_entry, session_id, document_id
        )

    # -- cache (mcp / rag / tool result caching) -----------------------

    async def cache_get(self, project_id: str, namespace: str, key: str) -> Any | None:
        return await asyncio.to_thread(self._impl.cache_get, project_id, namespace, key)

    async def cache_set(
        self, project_id: str, namespace: str, key: str, value: Any
    ) -> None:
        return await asyncio.to_thread(
            self._impl.cache_set, project_id, namespace, key, value
        )

    # -- session workspace ------------------------------------------------

    async def read_workspace_files(self, session_id: str) -> list[str]:
        return await asyncio.to_thread(self._impl.read_workspace_files, session_id)

    async def read_workspace_file(self, session_id: str, path: str) -> bytes | None:
        return await asyncio.to_thread(self._impl.read_workspace_file, session_id, path)

    async def sync_workspace_from_container(
        self, session_id: str, files: list[tuple[str, bytes]]
    ) -> None:
        return await asyncio.to_thread(
            self._impl.sync_workspace_from_container, session_id, files
        )

    # -- per-run scoped export / import (in-sandbox agent runtime) ---------

    async def export_scope(
        self,
        project_id: str,
        agent_id: str,
        session_id: str,
        staging_dir: Path,
    ) -> None:
        return await asyncio.to_thread(
            self._impl.export_scope, project_id, agent_id, session_id, staging_dir
        )

    async def import_scope(self, session_id: str, staging_dir: Path) -> None:
        return await asyncio.to_thread(
            self._impl.import_scope, session_id, staging_dir
        )


register_storage_backend("local", LocalStorage)
