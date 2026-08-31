"""Resolves the *effective* `ModelSettings` for every role of an agent profile.

Precedence, highest first:

1. session override   — the per-session pick (chat-composer model switcher);
                        `Storage.read_model_settings(session_id)`
2. agent override     — the per-agent-instance pick (agent settings panel);
                        `Storage.read_agent_model_settings(agent_id)`
3. profile default    — `AgentProfile.default_models[role]` (declared in code)
4. profile "main"     — falls back to the profile's main-role default
5. global default     — `AppSettings.default_model` on OpenRouter

Each override layer may be *partial* (`{"temperature": 0.1}` alone is valid)
— it's merged key-by-key onto the resolved lower layer. Overrides are plain
dicts as persisted on disk, shaped `{role: {provider, model, ...}}`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from krutrim_agent_management.config import settings

from krutrim_agents_core.profile import AgentProfile, RoleDefaults
from krutrim_agents_core.providers.base import ModelSettings
from krutrim_agents_core.providers.registry import parse_model_settings

OverrideMap = Mapping[str, Mapping[str, Any]]

MAIN_ROLE = "main"


def _role_defaults_to_dict(defaults: RoleDefaults) -> dict[str, Any]:
    return {
        "provider": defaults.provider,
        "model": defaults.model,
        "temperature": defaults.temperature,
        "max_tokens": defaults.max_tokens,
    }


def _base_for_role(profile: AgentProfile, role: str) -> dict[str, Any]:
    defaults = profile.default_models.get(role) or profile.default_models.get(MAIN_ROLE)
    if defaults is not None:
        return _role_defaults_to_dict(defaults)
    return {
        "provider": "openrouter",
        "model": settings.default_model,
        "temperature": 0.3,
        "max_tokens": None,
    }


def _apply(base: dict[str, Any], override: Mapping[str, Any] | None) -> dict[str, Any]:
    if not override:
        return base
    return {**base, **{k: v for k, v in override.items() if v is not None}}


def resolve_role_settings(
    profile: AgentProfile,
    role: str,
    *,
    agent_overrides: OverrideMap | None = None,
    session_overrides: OverrideMap | None = None,
) -> ModelSettings:
    data = _base_for_role(profile, role)
    data = _apply(data, (agent_overrides or {}).get(role))
    data = _apply(data, (session_overrides or {}).get(role))
    return parse_model_settings(data)


def resolve_models(
    profile: AgentProfile,
    *,
    agent_overrides: OverrideMap | None = None,
    session_overrides: OverrideMap | None = None,
) -> dict[str, ModelSettings]:
    """`{role: ModelSettings}` for every role the profile declares."""
    roles = list(profile.roles) or [MAIN_ROLE]
    return {
        role: resolve_role_settings(
            profile,
            role,
            agent_overrides=agent_overrides,
            session_overrides=session_overrides,
        )
        for role in roles
    }


def effective_role_sources(
    profile: AgentProfile,
    *,
    agent_overrides: OverrideMap | None = None,
    session_overrides: OverrideMap | None = None,
) -> dict[str, str]:
    """`{role: "session" | "agent" | "profile"}` — where each role's value came from.

    Used by the settings API so the UI can show "inherited" vs "overridden".
    """
    agent_overrides = agent_overrides or {}
    session_overrides = session_overrides or {}
    out: dict[str, str] = {}
    for role in list(profile.roles) or [MAIN_ROLE]:
        if role in session_overrides:
            out[role] = "session"
        elif role in agent_overrides:
            out[role] = "agent"
        else:
            out[role] = "profile"
    return out
