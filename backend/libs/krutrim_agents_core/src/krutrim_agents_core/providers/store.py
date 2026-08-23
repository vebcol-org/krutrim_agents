"""Persists one named `ModelSettings` per `(agent_key, role)`.

Backed by a plain JSON file under `harness/memory/settings.json` (gitignored
— it's local config, not source), shaped as `{agent_key: {role: settings}}`.
Seeded from each registered agent profile's own `default_models` — this
store has no per-agent knowledge itself, and picks up newly added profiles
automatically on the next backend start (existing agent keys are never
overwritten). API keys are never written here, only the *name* of the
environment variable to read them from (see `OpenRouterModelSettings.api_key_env`).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from krutrim_agent_utils.atomic_write import atomic_write_json

from krutrim_agents_core.providers.base import ModelSettings
from krutrim_agents_core.providers.registry import parse_model_settings

if TYPE_CHECKING:
    from krutrim_agents_core.profile import AgentProfile

ConfigDict = dict[str, dict[str, dict[str, Any]]]


def _default_config() -> ConfigDict:
    from krutrim_agents_core.registry import (
        all_profiles,
    )  # deferred: avoid import-order coupling

    return {
        profile.key: {
            role: {
                "provider": defaults.provider,
                "model": defaults.model,
                "temperature": defaults.temperature,
                "max_tokens": defaults.max_tokens,
            }
            for role, defaults in profile.default_models.items()
        }
        for profile in all_profiles().values()
    }


class ProviderStore:
    """Thread-safe, file-backed CRUD for per-`(agent_key, role)` model settings."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        if not self._path.exists():
            self._write(_default_config())
        else:
            self._merge_new_agents()

    def _read(self) -> ConfigDict:
        with self._path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data: ConfigDict) -> None:
        atomic_write_json(self._path, data)

    def _merge_new_agents(self) -> None:
        with self._lock:
            raw = self._read()
            changed = False
            for agent_key, roles in _default_config().items():
                if agent_key not in raw:
                    raw[agent_key] = roles
                    changed = True
            if changed:
                self._write(raw)

    def _require_profile(self, agent_key: str) -> AgentProfile:
        from krutrim_agents_core.registry import get_profile

        return get_profile(agent_key)  # raises KeyError if unknown

    def get_all(self, agent_key: str) -> dict[str, ModelSettings]:
        self._require_profile(agent_key)
        with self._lock:
            raw = self._read()
        roles = raw.get(agent_key, {})
        return {role: parse_model_settings(data) for role, data in roles.items()}

    def get(self, agent_key: str, role: str) -> ModelSettings:
        profile = self._require_profile(agent_key)
        if role not in profile.roles:
            raise ValueError(
                f"Unknown role {role!r} for agent {agent_key!r}. Known roles: {list(profile.roles)}"
            )
        with self._lock:
            raw = self._read()
        roles = raw.get(agent_key, {})
        if role not in roles:
            raise KeyError(
                f"No model settings configured yet for {agent_key!r}/{role!r}."
            )
        return parse_model_settings(roles[role])

    def set(self, agent_key: str, role: str, data: dict[str, Any]) -> ModelSettings:
        profile = self._require_profile(agent_key)
        if role not in profile.roles:
            raise ValueError(
                f"Unknown role {role!r} for agent {agent_key!r}. Known roles: {list(profile.roles)}"
            )
        settings = parse_model_settings(data)
        with self._lock:
            raw = self._read()
            raw.setdefault(agent_key, {})[role] = settings.model_dump()
            self._write(raw)
        return settings

    def reset(self, agent_key: str, role: str | None = None) -> None:
        self._require_profile(agent_key)
        defaults = _default_config().get(agent_key, {})
        with self._lock:
            raw = self._read()
            if role is None:
                raw[agent_key] = dict(defaults)
            else:
                if role not in defaults:
                    raise ValueError(
                        f"No default for role {role!r} on agent {agent_key!r}"
                    )
                raw.setdefault(agent_key, {})[role] = dict(defaults[role])
            self._write(raw)
