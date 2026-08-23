from __future__ import annotations

import pytest
from krutrim_agent_management.config import settings
from krutrim_agent_sandbox.docker_backend import DockerSandboxBackend
from krutrim_agent_sandbox.factory import _registry as _sandbox_registry
from krutrim_agent_sandbox.factory import (
    create_sandbox_backend,
    register_sandbox_runtime,
)


def test_docker_runtime_is_discoverable_without_being_invoked():
    """Importing `krutrim_agent_sandbox.docker_backend` (which self-registers
    `"docker"`) must not touch a real Docker daemon — only constructing a
    `DockerSandboxBackend` (via `docker.from_env()`) does that."""
    _sandbox_registry.discover_modules(settings.sandbox_runtime_sources)
    assert "docker" in _sandbox_registry.all()


def test_create_sandbox_backend_unknown_runtime_raises_keyerror():
    with pytest.raises(KeyError):
        create_sandbox_backend("owner-1", runtime="_nonexistent")


def test_create_sandbox_backend_resolves_a_newly_registered_runtime():
    calls: list[tuple[str, object]] = []

    def _fake_factory(owner_id, policy):
        calls.append((owner_id, policy))
        return "fake-backend"

    register_sandbox_runtime("_test_fake_runtime", _fake_factory)
    try:
        result = create_sandbox_backend("owner-1", runtime="_test_fake_runtime")
        assert result == "fake-backend"
        assert calls == [("owner-1", None)]
    finally:
        _sandbox_registry.discard("_test_fake_runtime")


def test_create_sandbox_backend_client_override_bypasses_the_registry():
    """The `client` kwarg is Docker-specific test-injection plumbing, handled
    as a special case before the registry lookup — a fake (non-real) client
    object is enough to prove the branch, since `DockerSandboxBackend`'s
    constructor never touches Docker itself, only later method calls do."""
    fake_client = object()
    backend = create_sandbox_backend("owner-1", client=fake_client)
    assert isinstance(backend, DockerSandboxBackend)
