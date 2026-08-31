"""Pydantic models shared by every `Storage` implementation.

Hierarchy: `Project` -> (`Agent` | `Chat`) -> `SessionInfo`. `Agent` always belongs to one
project; `Chat` is optionally project-scoped (`project_id` may be `None`); `SessionInfo`
belongs to exactly one `Agent` or `Chat` (`owner_type`/`owner_id`), never directly to a
`Project`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

SharingScope = Literal["isolated", "session-shared", "project-shared"]

OwnerType = Literal["agent", "chat"]


class Project(BaseModel):
    project_id: str
    project_title: str
    project_information: str = ""
    created_at: str
    updated_at: str
    sandbox_sharing: SharingScope = "isolated"
    """Default inherited by every `Agent`/`Chat` in this project unless overridden."""
    sandbox_idle_timeout_seconds: int | None = None
    """Per-project override of the idle-teardown timeout. None = server default."""
    sandbox_resource_overrides: dict[str, int] | None = None
    """Human-set `SandboxPolicy` overrides (memory_mb, nano_cpus, ...) via the Settings API only."""


class Agent(BaseModel):
    """A named instance of a registered `AgentProfile`, living inside exactly one project.
    Multiple `Agent` rows can share the same `agent_key`, distinguished by `display_name`."""

    agent_id: str
    project_id: str
    agent_key: str
    """Which registered profile this instance runs; not itself unique, see class docstring."""
    display_name: str
    created_at: str
    updated_at: str
    sandbox_sharing: SharingScope | None = None
    """`None` = inherit the project's default."""
    sandbox_idle_timeout_seconds: int | None = None
    sandbox_resource_overrides: dict[str, int] | None = None


class Chat(BaseModel):
    """A lightweight, non-agentic chat thread. `project_id` is optional; a standalone chat
    has no meaningful sandbox policy until moved into a project."""

    chat_id: str
    project_id: str | None = None
    display_name: str
    provider: str
    model: str
    created_at: str
    updated_at: str
    sandbox_sharing: SharingScope | None = None
    """Only takes effect while `project_id` is set."""
    sandbox_idle_timeout_seconds: int | None = None
    sandbox_resource_overrides: dict[str, int] | None = None


class SessionInfo(BaseModel):
    session_id: str
    owner_type: OwnerType
    owner_id: str
    """`Agent.agent_id` or `Chat.chat_id`, per `owner_type`."""
    project_id: str | None = None
    """Denormalized from the owner, so callers can filter/cascade without an extra lookup."""
    display_name: str | None = None
    """`None` means "unnamed"; callers show a positional fallback (e.g. "Session 2")."""
    created_at: str
    updated_at: str
    sandbox_sharing: SharingScope = "isolated"
    """Overrides the owner's (and transitively the project's) default for this session only."""
    attached_to_session_id: str | None = None
    """Explicit ad-hoc container reuse, independent of `sandbox_sharing`."""
    linked_session_ids: list[str] = []
    """Peers reachable via `message_agent` when `sandbox_sharing == "session-shared"`;
    eligibility is symmetric."""
