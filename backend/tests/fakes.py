"""Shared test doubles for sandbox-lifecycle tests (`SandboxRegistry`, the
idle-container reaper) — plain in-memory stand-ins for the pieces of
`Storage`/a sandbox backend those modules call. Not a `Storage` subclass:
both callers only ever duck-type against `store`/`backend`, so implementing
the full `Storage` ABC isn't necessary here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from krutrim_agent_management.models import Agent, ContainerRecord, Project, SessionInfo


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FakeBackend:
    """Stands in for a real sandbox backend. `workspace_files` seeds what
    `execute()`'s workspace listing and `download_files()` report, so a test
    can simulate a container that already has content in it (the reaper's
    case) as well as tracking `hydrate()` calls (the registry's case)."""

    def __init__(
        self, owner_id: str, workspace_files: dict[str, bytes] | None = None
    ) -> None:
        self.owner_id = owner_id
        self.workspace_files: dict[str, bytes] = dict(workspace_files or {})
        self.hydrate_calls: list[list[tuple[str, bytes]]] = []
        self.execute_calls: list[str] = []
        self.closed = False

    def hydrate(self, files: list[tuple[str, bytes]]) -> None:
        self.hydrate_calls.append(files)
        for path, content in files:
            self.workspace_files[path] = content

    def execute(self, command: str, *, timeout: int | None = None) -> SimpleNamespace:
        self.execute_calls.append(command)
        listing = "\n".join(f"/workspace/{path}" for path in self.workspace_files)
        return SimpleNamespace(output=listing, exit_code=0, truncated=False)

    def download_files(self, paths: list[str]) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                path=path,
                content=self.workspace_files.get(path),
                error=None if path in self.workspace_files else "not_found",
            )
            for path in paths
        ]

    def close(self) -> None:
        self.closed = True


class FakeStore:
    """In-memory double covering project/agent/session/container/workspace-mirror
    operations — the surface `SandboxRegistry` and `reap_idle_containers_once`
    both call. Sessions are keyed by `session_id` alone (globally unique),
    matching the real `Storage` contract."""

    def __init__(self) -> None:
        self.projects: dict[str, Project] = {}
        self.agents: dict[str, Agent] = {}
        self.sessions: dict[str, SessionInfo] = {}
        self.containers: dict[str, ContainerRecord] = {}
        self.workspaces: dict[str, dict[str, bytes]] = {}

    def add_project(self, project_id: str, **overrides) -> Project:
        now = now_iso()
        project = Project(
            project_id=project_id,
            project_title="Test",
            created_at=now,
            updated_at=now,
            **overrides,
        )
        self.projects[project_id] = project
        return project

    def add_agent(
        self,
        agent_id: str,
        project_id: str,
        *,
        agent_key: str = "research",
        **overrides,
    ) -> Agent:
        now = now_iso()
        agent = Agent(
            agent_id=agent_id,
            project_id=project_id,
            agent_key=agent_key,
            display_name="Test Agent",
            created_at=now,
            updated_at=now,
            **overrides,
        )
        self.agents[agent_id] = agent
        return agent

    def add_session(
        self,
        session_id: str,
        *,
        owner_type: str = "agent",
        owner_id: str = "agent-1",
        project_id: str | None = "proj-1",
        attached_to_session_id: str | None = None,
        **overrides,
    ) -> SessionInfo:
        now = now_iso()
        session = SessionInfo(
            session_id=session_id,
            owner_type=owner_type,
            owner_id=owner_id,
            project_id=project_id,
            created_at=now,
            updated_at=now,
            attached_to_session_id=attached_to_session_id,
            **overrides,
        )
        self.sessions[session_id] = session
        return session

    async def get_project(self, project_id: str) -> Project:
        return self.projects[project_id]

    async def get_agent(self, agent_id: str) -> Agent:
        return self.agents[agent_id]

    async def get_session(self, session_id: str) -> SessionInfo:
        return self.sessions[session_id]

    async def get_container(self, owner_id: str) -> ContainerRecord | None:
        return self.containers.get(owner_id)

    async def upsert_container(self, record: ContainerRecord) -> None:
        self.containers[record.owner_id] = record

    async def list_containers(
        self, *, status: str | None = None
    ) -> list[ContainerRecord]:
        records = list(self.containers.values())
        if status is not None:
            records = [r for r in records if r.status == status]
        return records

    async def delete_container(self, owner_id: str) -> None:
        self.containers.pop(owner_id, None)

    async def read_workspace_files(self, session_id: str) -> list[str]:
        return list(self.workspaces.get(session_id, {}).keys())

    async def read_workspace_file(self, session_id: str, path: str) -> bytes | None:
        return self.workspaces.get(session_id, {}).get(path)

    async def sync_workspace_from_container(
        self, session_id: str, files: list[tuple[str, bytes]]
    ) -> None:
        bucket = self.workspaces.setdefault(session_id, {})
        for path, content in files:
            bucket[path] = content
