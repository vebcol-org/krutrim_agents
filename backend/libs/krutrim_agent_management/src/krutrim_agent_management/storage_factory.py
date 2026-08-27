"""Pluggable `Storage` backend selection — which implementation gets constructed, not the
`Storage` contract itself (`base.py`). `local.py` self-registers `"local"` at import time.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from krutrim_agent_utils.plugin_registry import PluginRegistry

if TYPE_CHECKING:
    from krutrim_agent_management.base import Storage
    from krutrim_agent_management.config import AppSettings

_registry: PluginRegistry[Callable[[], Storage]] = PluginRegistry(
    kind="storage backend"
)


def register_storage_backend(key: str, factory: Callable[[], Storage]) -> None:
    """`factory` is typically the implementation class itself, e.g. `LocalStorage`."""
    _registry.register(key, factory)


def create_storage(settings: AppSettings) -> Storage:
    _registry.discover_modules(settings.storage_backend_sources)
    return _registry.get(settings.storage_backend)()
