"""One-time migration: converts an old-shape `STORAGE_ROOT` (`Project.project_type`
/`provider`/`model`, one `session.db` per project under `projects/{id}/sessions/`)
into the new `Project -> (Agent | Chat) -> Session` hierarchy (global
`agents.db`/`chats.db`/`sessions.db`, session files under top-level
`sessions/{id}/`). See `backend/docs/libs/krutrim_agent_management.md` for the new
shape this produces.

Run once, with the backend and Celery worker both stopped, from `backend/`:

    uv run python scripts/migrate_storage_to_hierarchy.py [--storage-root PATH]

Safe to re-run — it detects an already-migrated `project.db` (no `project_type`
column left) and exits without touching anything.

What it does, per existing project:
- `project_type == "chat"` -> wraps it in one new `Chat` (`display_name="General"`,
  keeping the project's old `provider`/`model`), owning that project's old sessions.
- any other `project_type` (a registered agent profile key, e.g. "research") ->
  wraps it in one new `Agent` (`agent_key=project_type`, `display_name` titleized
  from the key), owning that project's old sessions.
- Every migrated session keeps its original `session_id` (and therefore its
  sandbox container/checkpoint/usage/workspace references stay valid) — only
  its storage location moves, from `projects/{project_id}/sessions/{session_id}/`
  to the new global `sessions/{session_id}/`.
- `project.db` is rebuilt without `project_type`/`provider`/`model`.
- `containers.db` is left untouched — it has no foreign key into the tables
  this script rewrites, and its now-unused `project_type` column is harmless.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(
        row[1] == column
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    )


def _col(row: sqlite3.Row, name: str, default: object) -> object:
    return row[name] if name in row.keys() else default


def migrate(storage_root: Path) -> None:
    project_db_path = storage_root / "project.db"
    if not project_db_path.exists():
        print(f"No project.db at {project_db_path} — nothing to migrate.")
        return

    old_conn = _connect(project_db_path)
    if not _has_column(old_conn, "projects", "project_type"):
        print("project.db has no `project_type` column — already migrated.")
        old_conn.close()
        return

    old_projects = old_conn.execute("SELECT * FROM projects").fetchall()
    print(f"Found {len(old_projects)} project(s) to migrate.")

    agents_conn = _connect(storage_root / "agents.db")
    agents_conn.execute(
        """CREATE TABLE IF NOT EXISTS agents (
            agent_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, agent_key TEXT NOT NULL,
            display_name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            sandbox_sharing TEXT, sandbox_idle_timeout_seconds INTEGER, sandbox_resource_overrides TEXT
        )"""
    )
    chats_conn = _connect(storage_root / "chats.db")
    chats_conn.execute(
        """CREATE TABLE IF NOT EXISTS chats (
            chat_id TEXT PRIMARY KEY, project_id TEXT, display_name TEXT NOT NULL,
            provider TEXT NOT NULL, model TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            sandbox_sharing TEXT, sandbox_idle_timeout_seconds INTEGER, sandbox_resource_overrides TEXT
        )"""
    )
    sessions_conn = _connect(storage_root / "sessions.db")
    sessions_conn.execute(
        """CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY, owner_type TEXT NOT NULL, owner_id TEXT NOT NULL,
            project_id TEXT, display_name TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            sandbox_sharing TEXT NOT NULL DEFAULT 'isolated', attached_to_session_id TEXT,
            linked_session_ids TEXT NOT NULL DEFAULT '[]'
        )"""
    )
    (storage_root / "sessions").mkdir(parents=True, exist_ok=True)

    for project_row in old_projects:
        project_id = project_row["project_id"]
        project_type = project_row["project_type"]
        provider = project_row["provider"]
        model = project_row["model"]

        project_session_db = storage_root / "projects" / project_id / "session.db"
        old_sessions: list[sqlite3.Row] = []
        if project_session_db.exists():
            sconn = _connect(project_session_db)
            old_sessions = sconn.execute("SELECT * FROM sessions").fetchall()
            sconn.close()

        now = _now_iso()
        if project_type == "chat":
            chat_id = str(uuid.uuid4())
            chats_conn.execute(
                "INSERT INTO chats (chat_id, project_id, display_name, provider, model, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (chat_id, project_id, "General", provider, model, now, now),
            )
            owner_type, owner_id = "chat", chat_id
            print(f"  project {project_id} (chat) -> chat {chat_id}")
        else:
            agent_id = str(uuid.uuid4())
            agents_conn.execute(
                "INSERT INTO agents (agent_id, project_id, agent_key, display_name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    agent_id,
                    project_id,
                    project_type,
                    project_type.replace("_", " ").title(),
                    now,
                    now,
                ),
            )
            owner_type, owner_id = "agent", agent_id
            print(
                f"  project {project_id} (agent_key={project_type}) -> agent {agent_id}"
            )

        for srow in old_sessions:
            session_id = srow["session_id"]
            sessions_conn.execute(
                "INSERT OR IGNORE INTO sessions "
                "(session_id, owner_type, owner_id, project_id, created_at, updated_at, sandbox_sharing, "
                "attached_to_session_id, linked_session_ids) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    owner_type,
                    owner_id,
                    project_id,
                    srow["created_at"],
                    srow["updated_at"],
                    _col(srow, "sandbox_sharing", "isolated"),
                    _col(srow, "attached_to_session_id", None),
                    _col(srow, "linked_session_ids", "[]"),
                ),
            )
            old_session_dir = (
                storage_root / "projects" / project_id / "sessions" / session_id
            )
            new_session_dir = storage_root / "sessions" / session_id
            if old_session_dir.exists() and not new_session_dir.exists():
                shutil.move(str(old_session_dir), str(new_session_dir))

        old_sessions_dir = storage_root / "projects" / project_id / "sessions"
        if old_sessions_dir.exists():
            shutil.rmtree(old_sessions_dir, ignore_errors=True)
        if project_session_db.exists():
            project_session_db.unlink()

    agents_conn.commit()
    chats_conn.commit()
    sessions_conn.commit()
    agents_conn.close()
    chats_conn.close()
    sessions_conn.close()

    # Rebuild project.db without project_type/provider/model.
    new_rows = [
        (
            r["project_id"],
            r["project_title"],
            r["project_information"],
            r["created_at"],
            r["updated_at"],
            _col(r, "sandbox_sharing", "isolated"),
            _col(r, "sandbox_idle_timeout_seconds", None),
            _col(r, "sandbox_resource_overrides", None),
        )
        for r in old_projects
    ]
    old_conn.close()
    project_db_path.unlink()
    new_conn = _connect(project_db_path)
    new_conn.execute(
        """CREATE TABLE projects (
            project_id TEXT PRIMARY KEY, project_title TEXT NOT NULL, project_information TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, sandbox_sharing TEXT NOT NULL DEFAULT 'isolated',
            sandbox_idle_timeout_seconds INTEGER, sandbox_resource_overrides TEXT
        )"""
    )
    new_conn.executemany(
        "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?)", new_rows
    )
    new_conn.commit()
    new_conn.close()

    print(f"Migration complete. {len(old_projects)} project(s) migrated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--storage-root",
        type=Path,
        default=None,
        help="Defaults to krutrim_agent_management's configured storage_root (KRUTRIM_AGENT_STORAGE_ROOT or ~/.krutrim_agent).",
    )
    args = parser.parse_args()
    root = args.storage_root
    if root is None:
        from krutrim_agent_management.config import settings

        root = settings.storage_root
    migrate(root)
