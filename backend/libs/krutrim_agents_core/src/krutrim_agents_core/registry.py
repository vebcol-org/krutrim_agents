"""Registry of agent profiles, auto-populated from every configured profile source.

To add a new agent type: create `krutrim_agents/profiles/<key>/__init__.py` and call
`register_profile(...)` at module level. This file never needs to change —
`_discover()` scans each configured source package's search path on every
access, so a newly added profile package is picked up automatically. The
source list itself (`settings.agent_profile_sources`, default
`["krutrim_agents.profiles"]`) is how a second, privately-distributed profile
package (e.g. a proprietary catalog) plugs in without editing this module.
"""

from __future__ import annotations

from krutrim_agent_management.config import settings
from krutrim_agent_utils.plugin_registry import PluginRegistry

from krutrim_agents_core.profile import AgentProfile

_registry: PluginRegistry[AgentProfile] = PluginRegistry(kind="agent")


def register_profile(profile: AgentProfile) -> None:
    _registry.register(profile.key, profile)


def _discover() -> None:
    _registry.discover_packages(settings.agent_profile_sources)


def all_profiles() -> dict[str, AgentProfile]:
    _discover()
    return _registry.all()


def get_profile(key: str) -> AgentProfile:
    _discover()
    return _registry.get(key)
