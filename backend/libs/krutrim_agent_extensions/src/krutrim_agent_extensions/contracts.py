"""Security/governance hook contracts + their shipped no-op (community) defaults.

Every hook here is optional to override — a private deployment replaces
one or more via `krutrim_agent_extensions.registry.register_hook`, discovered from
`settings.extension_sources`. Nothing upstream (`krutrim_agent_backend`'s
routes, `krutrim_agents_core`) ever imports a concrete implementation directly —
only ever goes through `krutrim_agent_extensions.registry.get_*`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from starlette.requests import Request


@dataclass(frozen=True)
class Principal:
    """Who's making this request. `ANONYMOUS_PRINCIPAL` is the community
    default — there's no real identity system in the single-user OSS
    platform, so every request resolves to the same principal."""

    id: str
    display_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


ANONYMOUS_PRINCIPAL = Principal(id="anonymous", display_name="Anonymous")


@dataclass(frozen=True)
class AuditEvent:
    principal: Principal
    method: str
    path: str
    status_code: int


@runtime_checkable
class RequestAuthenticator(Protocol):
    async def authenticate(self, request: "Request") -> Principal: ...


@runtime_checkable
class AgentVisibilityPolicy(Protocol):
    def visible_agent_keys(self, principal: Principal) -> set[str] | None:
        """`None` means "no restriction" — every registered agent profile is visible."""
        ...


@runtime_checkable
class AuditSink(Protocol):
    async def record(self, event: AuditEvent) -> None: ...


class NoOpRequestAuthenticator:
    """Community default: every request resolves to the same anonymous
    principal — matches today's no-auth, single-user model exactly."""

    async def authenticate(self, request: "Request") -> Principal:
        return ANONYMOUS_PRINCIPAL


class NoOpAgentVisibilityPolicy:
    """Community default: every registered agent profile is visible to everyone."""

    def visible_agent_keys(self, principal: Principal) -> set[str] | None:
        return None


class NoOpAuditSink:
    """Community default: audit events are dropped, not recorded."""

    async def record(self, event: AuditEvent) -> None:
        return None
