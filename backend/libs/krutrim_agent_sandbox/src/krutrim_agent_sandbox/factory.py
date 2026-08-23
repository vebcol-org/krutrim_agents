"""The one place that decides which sandbox runtime backs a given owner_id.

`SandboxRegistry` calls `create_sandbox_backend` instead of constructing
`DockerSandboxBackend` directly, so a future alternative runtime (Podman,
Firecracker, a remote sandbox API — anything satisfying `BaseSandbox`'s
`execute`/`upload_files`/`download_files`/`id` contract) registers itself
under its own module (added to `settings.sandbox_runtime_sources`) instead
of needing a new branch here — this file doesn't change to add one, matching
how a new agent profile doesn't touch `krutrim_agents_core/registry.py`. Selected
via `AppSettings.sandbox_runtime` (default `"docker"`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from deepagents.backends.sandbox import BaseSandbox
from krutrim_agent_utils.plugin_registry import PluginRegistry

from krutrim_agent_sandbox.policy import SandboxPolicy

if TYPE_CHECKING:
    import docker

_registry: PluginRegistry[Callable[[str, SandboxPolicy | None], BaseSandbox]] = (
    PluginRegistry(kind="sandbox runtime")
)


def register_sandbox_runtime(
    key: str, factory: Callable[[str, SandboxPolicy | None], BaseSandbox]
) -> None:
    """`factory(owner_id, policy) -> BaseSandbox` — the same two positional
    args `SandboxRegistry` already calls its `backend_factory` with."""
    _registry.register(key, factory)


def create_sandbox_backend(
    owner_id: str,
    policy: SandboxPolicy | None = None,
    *,
    client: docker.DockerClient | None = None,
    runtime: str | None = None,
) -> BaseSandbox:
    from krutrim_agent_management.config import (
        settings,
    )  # deferred: avoid import-order coupling

    effective_runtime = runtime or settings.sandbox_runtime
    _registry.discover_modules(settings.sandbox_runtime_sources)

    if effective_runtime == "docker" and client is not None:
        # `client` is Docker-specific test-injection plumbing (a fake/real
        # `docker.DockerClient`), not part of the generic
        # `(owner_id, policy) -> BaseSandbox` registry contract every
        # runtime implements — handled here rather than forcing every
        # future runtime's registered factory to accept a Docker-shaped param.
        from krutrim_agent_sandbox.docker_backend import DockerSandboxBackend

        return DockerSandboxBackend(policy=policy, owner_id=owner_id, client=client)

    return _registry.get(effective_runtime)(owner_id, policy)
