"""Abstract, storage-agnostic contract every backend must satisfy. `LocalStorage` (see
`local.py`) is the only implementation today. Hierarchy: `Project` -> (`Agent` | `Chat`)
-> `SessionInfo`, keyed by `session_id` alone; see `models.py` for field-level shape.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from krutrim_agent_management.models import (
    Agent,
    Chat,
    OwnerType,
    Project,
    SessionInfo,
    SharingScope,
)


class Storage(ABC):
    """Persists projects, agents, chats, sessions (+ their checkpoints/usage),
    per-project agent memory, and a generic result cache for MCP/RAG/tool calls.
    """

    # -- Projects -------------------------------------------------------

    @abstractmethod
    async def create_project(
        self, project_title: str, project_information: str = ""
    ) -> Project: ...

    @abstractmethod
    async def get_project(self, project_id: str) -> Project:
        """Raises `KeyError` if `project_id` is unknown."""

    @abstractmethod
    async def list_projects(self) -> list[Project]: ...

    @abstractmethod
    async def update_project(
        self,
        project_id: str,
        *,
        project_title: str | None = None,
        project_information: str | None = None,
    ) -> Project:
        """Raises `KeyError` if `project_id` is unknown. Unset fields are left unchanged."""

    @abstractmethod
    async def delete_project(self, project_id: str) -> None:
        """Raises `KeyError` if `project_id` is unknown. Cascades: every `Agent` and `Chat` in
        this project, and transitively every one of their `Session`s, plus memory and cache."""

    # -- Agents (named instances of a registered profile, live inside one project) --

    @abstractmethod
    async def create_agent(
        self, project_id: str, agent_key: str, display_name: str
    ) -> Agent:
        """Raises `KeyError` if `project_id` is unknown."""

    @abstractmethod
    async def get_agent(self, agent_id: str) -> Agent:
        """Raises `KeyError` if `agent_id` is unknown."""

    @abstractmethod
    async def list_agents(self, project_id: str) -> list[Agent]: ...

    @abstractmethod
    async def update_agent(
        self, agent_id: str, *, display_name: str | None = None
    ) -> Agent:
        """Raises `KeyError` if `agent_id` is unknown. Unset fields are left unchanged."""

    @abstractmethod
    async def delete_agent(self, agent_id: str) -> None:
        """Raises `KeyError` if `agent_id` is unknown. Cascades: every `Session` owned by this agent."""

    @abstractmethod
    async def update_agent_sandbox_policy(
        self,
        agent_id: str,
        *,
        sharing: SharingScope | None = None,
        idle_timeout_seconds: int | None = None,
        resource_overrides: dict[str, int] | None = None,
    ) -> Agent:
        """Raises `KeyError` if `agent_id` is unknown. Unset fields are left unchanged."""

    # -- Chats (optionally project-scoped, non-agentic) ------------------

    @abstractmethod
    async def create_chat(
        self,
        display_name: str,
        provider: str,
        model: str,
        project_id: str | None = None,
    ) -> Chat:
        """Raises `KeyError` if `project_id` is given but unknown. `project_id=None` creates a
        standalone chat (today's plain `/api/chat` behavior)."""

    @abstractmethod
    async def get_chat(self, chat_id: str) -> Chat:
        """Raises `KeyError` if `chat_id` is unknown."""

    @abstractmethod
    async def list_chats(self, project_id: str | None = None) -> list[Chat]:
        """`project_id=None` lists standalone chats (no project); otherwise lists that
        project's chats. There is currently no "list every chat regardless of project" call."""

    @abstractmethod
    async def update_chat(
        self, chat_id: str, *, display_name: str | None = None
    ) -> Chat:
        """Raises `KeyError` if `chat_id` is unknown. Unset fields are left unchanged."""

    @abstractmethod
    async def move_chat(self, chat_id: str, *, project_id: str | None) -> Chat:
        """Sets (or, passing `None`, clears) this chat's project. Raises `KeyError` if `chat_id`
        is unknown, or if `project_id` is given but unknown."""

    @abstractmethod
    async def delete_chat(self, chat_id: str) -> None:
        """Raises `KeyError` if `chat_id` is unknown. Cascades: every `Session` owned by this chat."""

    @abstractmethod
    async def update_chat_sandbox_policy(
        self,
        chat_id: str,
        *,
        sharing: SharingScope | None = None,
        idle_timeout_seconds: int | None = None,
        resource_overrides: dict[str, int] | None = None,
    ) -> Chat:
        """Raises `KeyError` if `chat_id` is unknown. Unset fields are left unchanged. Has no
        effect on sandbox behavior while the chat's `project_id` is `None` (see `Chat` docstring)
        but is still stored, so it takes effect immediately if the chat is later moved into a project."""

    # -- Sandbox sharing policy (project-level default) -------------------

    @abstractmethod
    async def update_project_sandbox_policy(
        self,
        project_id: str,
        *,
        sharing: SharingScope | None = None,
        idle_timeout_seconds: int | None = None,
        resource_overrides: dict[str, int] | None = None,
    ) -> Project:
        """Raises `KeyError` if `project_id` is unknown. Unset fields are left unchanged
        (same partial-update convention as `update_project`) — there is currently no way
        to explicitly reset `idle_timeout_seconds`/`resource_overrides` back to "use server
        default" once set to a specific value; a future `reset_*` method would be additive."""

    @abstractmethod
    async def update_session_sandbox_policy(
        self,
        session_id: str,
        *,
        sharing: SharingScope | None = None,
        attached_to_session_id: str | None = None,
        linked_session_ids: list[str] | None = None,
    ) -> SessionInfo:
        """Raises `KeyError` if `session_id` is unknown. Unset fields are left unchanged — note this
        means an existing `attached_to_session_id` cannot be cleared via this method today."""

    # -- Agent memory (projects/{project_id}/MEMORY.md) -----------------

    @abstractmethod
    async def read_memory(self, project_id: str) -> str:
        """Returns "" if no memory has been written yet."""

    @abstractmethod
    async def write_memory(self, project_id: str, content: str) -> None: ...

    # -- Sessions (owned by exactly one Agent or Chat; keyed by session_id alone) --

    @abstractmethod
    async def create_session(self, owner_type: OwnerType, owner_id: str) -> SessionInfo:
        """Raises `KeyError` if the owning agent/chat is unknown. `project_id` on the resulting
        `SessionInfo` is resolved from the owner (may be `None` for a project-less chat)."""

    @abstractmethod
    async def get_session(self, session_id: str) -> SessionInfo:
        """Raises `KeyError` if `session_id` is unknown."""

    @abstractmethod
    async def list_sessions(
        self, owner_type: OwnerType, owner_id: str
    ) -> list[SessionInfo]: ...

    @abstractmethod
    async def update_session(
        self, session_id: str, *, display_name: str | None = None
    ) -> SessionInfo:
        """Raises `KeyError` if `session_id` is unknown. Unset fields are left unchanged."""

    @abstractmethod
    async def delete_session(self, session_id: str) -> None:
        """Raises `KeyError` if `session_id` is unknown."""

    # -- Checkpointer (sessions/{session_id}/checkpointer.json) ---------

    @abstractmethod
    async def read_checkpoint(self, session_id: str) -> dict[str, Any] | None:
        """Returns None if no checkpoint has been written yet."""

    @abstractmethod
    async def write_checkpoint(self, session_id: str, data: dict[str, Any]) -> None: ...

    # -- Usage (sessions/{session_id}/usage.json) ------------------------

    @abstractmethod
    async def read_usage(self, session_id: str) -> dict[str, Any] | None:
        """Returns None if no usage has been recorded yet."""

    @abstractmethod
    async def write_usage(self, session_id: str, data: dict[str, Any]) -> None: ...

    # -- Model settings overrides --------------------------------------
    # Per-role provider/model picks, shaped `{role: {provider, model,
    # temperature?, max_tokens?}}` and possibly partial per role. Two scopes:
    # per agent instance (`agents/{agent_id}/model_settings.json`, set from the
    # agent settings panel) and per session (`sessions/{session_id}/
    # model_settings.json`, the chat-composer model switcher). Neither is the
    # source of truth for *what can be picked* (that's the static
    # `krutrim_agents_core.providers.catalog`); `providers.resolver` merges
    # profile defaults < agent < session into the effective `ModelSettings`.

    @abstractmethod
    async def read_agent_model_settings(self, agent_id: str) -> dict[str, Any] | None:
        """Returns None if this agent instance has no per-role overrides."""

    @abstractmethod
    async def write_agent_model_settings(
        self, agent_id: str, data: dict[str, Any]
    ) -> None: ...

    @abstractmethod
    async def read_model_settings(self, session_id: str) -> dict[str, Any] | None:
        """Returns None if this session has no per-role overrides."""

    @abstractmethod
    async def write_model_settings(
        self, session_id: str, data: dict[str, Any]
    ) -> None: ...

    # -- RAG document manifest (sessions/{session_id}/rag/manifest.json) --
    # A small append-only record of every document ingested into a session's
    # vector index (`document_id`, `title`, `filename`, `source_path`,
    # `created_at`, `kind`). The vectors themselves live in the store; this is
    # just what the UI needs to show "files in this session" after a reload.

    @abstractmethod
    async def read_rag_manifest(self, session_id: str) -> list[dict[str, Any]]:
        """Every RAG document ingested into this session, oldest first (`[]` if none)."""

    @abstractmethod
    async def append_rag_manifest(
        self, session_id: str, entry: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Append one entry (de-duped on `document_id`); returns the full updated list."""

    @abstractmethod
    async def remove_rag_manifest_entry(
        self, session_id: str, document_id: str
    ) -> list[dict[str, Any]]:
        """Drop the entry with this `document_id` (no-op if absent); returns the updated list."""

    # -- Cache (MCP / RAG / tool result caching) -------------------------

    @abstractmethod
    async def cache_get(self, project_id: str, namespace: str, key: str) -> Any | None:
        """Returns None on a cache miss. `namespace` separates callers (e.g. one per MCP server or tool)."""

    @abstractmethod
    async def cache_set(
        self, project_id: str, namespace: str, key: str, value: Any
    ) -> None: ...

    # -- Session workspace (sessions/{session_id}/workspace/) -----
    # The agent's working directory for a session. The in-process
    # `FilesystemBackend` (see `krutrim_agent_sandbox.registry`) reads and
    # writes it directly; RAG ingestion and the sessions file API read it
    # through these methods.

    @abstractmethod
    async def read_workspace_files(self, session_id: str) -> list[str]:
        """Lists relative paths under the session's workspace mirror. Empty list if none synced yet."""

    @abstractmethod
    async def read_workspace_file(self, session_id: str, path: str) -> bytes | None:
        """Returns None if `path` isn't present in the mirror."""

    @abstractmethod
    async def sync_workspace_from_container(
        self, session_id: str, files: list[tuple[str, bytes]]
    ) -> None:
        """Overwrites (or creates) each given path in the session's workspace mirror."""

    # -- Per-run scoped export / import (in-sandbox agent runtime) --------
    # `export_scope` writes a self-contained snapshot of exactly ONE
    # project/agent/session into a staging directory the sandbox container
    # bind-mounts — nothing from any other project, agent, or session, and no
    # provider credentials. `import_scope` folds the container's writes
    # (checkpoint, usage, workspace, run logs) back in.

    @abstractmethod
    async def export_scope(
        self,
        project_id: str,
        agent_id: str,
        session_id: str,
        staging_dir: Path,
    ) -> None:
        """Populate ``staging_dir`` with:

        - ``store/`` — a mini storage root (`LocalStorage`-openable) holding
          only this project/agent/session's rows + the session's checkpoint,
          usage, and RAG manifest, plus the project's ``MEMORY.md``.
        - ``workspace/`` — the session's ``/workspace`` mirror contents.
        - ``out/`` — created empty; the container flushes its writes here.

        Raises ``KeyError`` if any of the three ids is unknown or they don't
        form a valid project→agent→session chain.
        """

    @abstractmethod
    async def import_scope(self, session_id: str, staging_dir: Path) -> None:
        """Fold a finished container's ``staging_dir/out/`` and
        ``staging_dir/workspace/`` back into this session's stored state
        (checkpoint sqlite, ``usage.json``, RAG manifest, workspace mirror,
        and any ``runs/*.jsonl`` transcripts). Missing pieces are skipped, not
        an error. Raises ``KeyError`` if ``session_id`` is unknown."""
