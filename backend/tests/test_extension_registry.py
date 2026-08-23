from __future__ import annotations

import pytest
from krutrim_agent_extensions.contracts import (
    NoOpAgentVisibilityPolicy,
    NoOpAuditSink,
    NoOpRequestAuthenticator,
    Principal,
)
from krutrim_agent_extensions.registry import (
    get_agent_visibility_policy,
    get_audit_sink,
    get_authenticator,
    register_hook,
)
from krutrim_agent_extensions.selfcheck import run_startup_selfcheck
from krutrim_agent_management.config import settings


def test_default_hooks_are_noop():
    assert isinstance(get_authenticator(), NoOpRequestAuthenticator)
    assert isinstance(get_agent_visibility_policy(), NoOpAgentVisibilityPolicy)
    assert isinstance(get_audit_sink(), NoOpAuditSink)


def test_default_visibility_policy_restricts_nothing():
    assert (
        get_agent_visibility_policy().visible_agent_keys(Principal(id="anyone")) is None
    )


def test_register_hook_replaces_the_default():
    class FakeAuthenticator:
        async def authenticate(self, request):
            return Principal(id="fake")

    fake = FakeAuthenticator()
    try:
        register_hook("RequestAuthenticator", fake)
        assert get_authenticator() is fake
    finally:
        # `register_hook` mutates registry.py's module-level `_registry` —
        # restore the shipped default so this test doesn't leak into others.
        register_hook("RequestAuthenticator", NoOpRequestAuthenticator())


def test_startup_selfcheck_passes_for_community_default(monkeypatch):
    monkeypatch.setattr(settings, "edition", "community")
    status = run_startup_selfcheck(settings)
    assert status.edition == "community"
    assert status.hooks["RequestAuthenticator"] == "NoOpRequestAuthenticator"


def test_startup_selfcheck_fails_closed_for_extended_without_real_authenticator(
    monkeypatch,
):
    monkeypatch.setattr(settings, "edition", "extended")
    with pytest.raises(RuntimeError, match="refusing to start"):
        run_startup_selfcheck(settings)


def test_startup_selfcheck_passes_for_extended_with_real_authenticator(monkeypatch):
    class FakeAuthenticator:
        async def authenticate(self, request):
            return Principal(id="fake")

    monkeypatch.setattr(settings, "edition", "extended")
    try:
        register_hook("RequestAuthenticator", FakeAuthenticator())
        status = run_startup_selfcheck(settings)
        assert status.edition == "extended"
        assert status.hooks["RequestAuthenticator"] == "FakeAuthenticator"
    finally:
        register_hook("RequestAuthenticator", NoOpRequestAuthenticator())
