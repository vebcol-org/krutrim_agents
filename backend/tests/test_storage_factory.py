from __future__ import annotations

import pytest
from krutrim_agent_management import LocalStorage
from krutrim_agent_management.config import settings
from krutrim_agent_management.storage_factory import _registry as _storage_registry
from krutrim_agent_management.storage_factory import (
    create_storage,
    register_storage_backend,
)


def test_create_storage_default_resolves_to_local(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    storage = create_storage(settings)
    assert isinstance(storage, LocalStorage)


def test_create_storage_unknown_backend_raises_keyerror(monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "_nonexistent")
    with pytest.raises(KeyError):
        create_storage(settings)


def test_create_storage_resolves_a_newly_registered_backend(monkeypatch):
    register_storage_backend("_test_fake_storage", lambda: "fake-storage-instance")
    try:
        monkeypatch.setattr(settings, "storage_backend", "_test_fake_storage")
        assert create_storage(settings) == "fake-storage-instance"
    finally:
        _storage_registry.discard("_test_fake_storage")
