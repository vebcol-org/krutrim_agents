"""Generic keyed plug-in registry with dotted-module-path discovery.

This is the one implementation of "scan a list of dotted module paths,
import each, let import-time side effects register things into a shared
dict" in the workspace. `krutrim_agents_core.registry` (agent profiles),
`krutrim_agent_management` (storage/vector-store backends), and `krutrim_agent_sandbox`
(sandbox runtimes) all build a `PluginRegistry` instance instead of
re-implementing this loop.

Two registration shapes are both supported by the same class:
- explicit key (`registry.register("docker", DockerSandboxBackend)`) — used
  wherever the key is a short config value chosen independently of the thing
  being registered (a runtime name, a storage backend name).
- self-describing key (`registry.register(profile.key, profile)`) — used
  wherever the registered object already carries its own key, as
  `AgentProfile.key` does.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Sequence
from typing import Generic, TypeVar

T = TypeVar("T")


class PluginRegistry(Generic[T]):
    """`kind` is a human-readable noun (e.g. `"agent profile"`, `"sandbox runtime"`)
    used only to make `register`/`get` error messages self-explanatory."""

    def __init__(self, *, kind: str) -> None:
        self._kind = kind
        self._items: dict[str, T] = {}

    def register(self, key: str, value: T, *, replace: bool = False) -> None:
        """Raises `ValueError` on a duplicate key unless `replace=True` — set
        that when `key` names a slot with a pre-seeded default meant to be
        overridden (e.g. a security hook), as opposed to a namespace where
        every key is expected to be registered exactly once (e.g. an agent
        profile's own `key`)."""
        if key in self._items and not replace:
            raise ValueError(f"{self._kind} {key!r} is already registered")
        self._items[key] = value

    def get(self, key: str) -> T:
        if key not in self._items:
            raise KeyError(
                f"Unknown {self._kind} {key!r}. Known {self._kind}s: {sorted(self._items)}"
            )
        return self._items[key]

    def all(self) -> dict[str, T]:
        return dict(self._items)

    def discard(self, key: str) -> None:
        """No-op if `key` isn't registered. Test-only escape hatch for
        undoing a `discover()`-triggered registration (`register_profile`
        mutates this registry as an import side effect, which nothing else
        can undo)."""
        self._items.pop(key, None)

    def discover_packages(self, sources: Sequence[str]) -> None:
        """Imports every submodule under each dotted *package* path in
        `sources` (e.g. `"krutrim_agents.profiles"`, which may hold many profile
        submodules — one new file registers a new profile, zero config
        changes). Re-importing an already-imported module is a
        `sys.modules` no-op, so calling this repeatedly (once per registry
        lookup, matching the existing `krutrim_agents_core.registry` convention) is
        cheap."""
        for source in sources:
            package = importlib.import_module(source)
            for module_info in pkgutil.iter_modules(package.__path__):
                importlib.import_module(f"{package.__name__}.{module_info.name}")

    def discover_modules(self, sources: Sequence[str]) -> None:
        """Imports each dotted *module* path in `sources` directly — for
        registries where each source is exactly one implementation (a
        storage backend, a sandbox runtime), not a package of many. No
        `__path__`/pkgutil scan involved, so a plain module (not a package)
        is a valid source."""
        for source in sources:
            importlib.import_module(source)
