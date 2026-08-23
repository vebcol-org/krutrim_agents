"""Registry of security/governance hooks, seeded with the no-op community
defaults and overridden by whatever `settings.extension_sources`
discovers — same discovery shape as `krutrim_agents_core.registry` (agent profiles)
and `krutrim_agent_management`'s storage/vector-store factories, applied here to
security hooks instead. Unlike those two, every key here is pre-registered
with a default — an extension source module *replaces* one, it doesn't add
a new key (see `PluginRegistry.register(..., replace=True)`).
"""

from __future__ import annotations

from krutrim_agent_management.config import settings
from krutrim_agent_utils.plugin_registry import PluginRegistry

from krutrim_agent_extensions.contracts import (
    AgentVisibilityPolicy,
    AuditSink,
    NoOpAgentVisibilityPolicy,
    NoOpAuditSink,
    NoOpRequestAuthenticator,
    RequestAuthenticator,
)

_AUTHENTICATOR = "RequestAuthenticator"
_VISIBILITY_POLICY = "AgentVisibilityPolicy"
_AUDIT_SINK = "AuditSink"

_registry: PluginRegistry[object] = PluginRegistry(kind="extension hook")
_registry.register(_AUTHENTICATOR, NoOpRequestAuthenticator())
_registry.register(_VISIBILITY_POLICY, NoOpAgentVisibilityPolicy())
_registry.register(_AUDIT_SINK, NoOpAuditSink())


def register_hook(name: str, implementation: object) -> None:
    """Called by an extension-source module at import time to replace the
    shipped no-op default for one contract (`name` is one of
    `"RequestAuthenticator"`, `"AgentVisibilityPolicy"`, `"AuditSink"`)."""
    _registry.register(name, implementation, replace=True)


def _discover() -> None:
    _registry.discover_modules(settings.extension_sources)


def all_hooks() -> dict[str, object]:
    _discover()
    return _registry.all()


def get_authenticator() -> RequestAuthenticator:
    _discover()
    return _registry.get(_AUTHENTICATOR)  # type: ignore[return-value]


def get_agent_visibility_policy() -> AgentVisibilityPolicy:
    _discover()
    return _registry.get(_VISIBILITY_POLICY)  # type: ignore[return-value]


def get_audit_sink() -> AuditSink:
    _discover()
    return _registry.get(_AUDIT_SINK)  # type: ignore[return-value]
