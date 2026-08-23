from __future__ import annotations

import sys

import pytest
from krutrim_agent_utils.plugin_registry import PluginRegistry


def test_register_and_get_roundtrip():
    registry = PluginRegistry(kind="widget")
    registry.register("a", 1)
    assert registry.get("a") == 1


def test_register_duplicate_without_replace_raises():
    registry = PluginRegistry(kind="widget")
    registry.register("a", 1)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("a", 2)


def test_register_duplicate_with_replace_overwrites():
    registry = PluginRegistry(kind="widget")
    registry.register("a", 1)
    registry.register("a", 2, replace=True)
    assert registry.get("a") == 2


def test_get_unknown_key_raises_keyerror_listing_known_keys():
    registry = PluginRegistry(kind="widget")
    registry.register("a", 1)
    with pytest.raises(KeyError) as exc_info:
        registry.get("b")
    assert "Unknown widget 'b'" in str(exc_info.value)
    assert "'a'" in str(exc_info.value)


def test_all_returns_a_copy_not_the_live_dict():
    registry = PluginRegistry(kind="widget")
    registry.register("a", 1)
    snapshot = registry.all()
    snapshot["b"] = 2
    assert registry.all() == {"a": 1}


def test_discard_is_a_noop_when_absent():
    registry = PluginRegistry(kind="widget")
    registry.discard("missing")  # must not raise


def test_discard_removes_a_registered_key():
    registry = PluginRegistry(kind="widget")
    registry.register("a", 1)
    registry.discard("a")
    with pytest.raises(KeyError):
        registry.get("a")


def test_discover_packages_imports_every_submodule(tmp_path, monkeypatch):
    """`discover_packages` scans a *package* path — many implementations per
    source, matching `krutrim_agents_core.registry`'s use for agent profiles."""
    monkeypatch.syspath_prepend(str(tmp_path))
    pkg_dir = tmp_path / "_test_discover_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("")
    (pkg_dir / "state.py").write_text(
        "from krutrim_agent_utils.plugin_registry import PluginRegistry\nregistry = PluginRegistry(kind='thing')\n"
    )
    (pkg_dir / "plugin_a.py").write_text(
        "from _test_discover_pkg.state import registry\nregistry.register('a', 'value-a')\n"
    )
    (pkg_dir / "plugin_b.py").write_text(
        "from _test_discover_pkg.state import registry\nregistry.register('b', 'value-b')\n"
    )

    try:
        from _test_discover_pkg import state

        state.registry.discover_packages(["_test_discover_pkg"])
        assert state.registry.all() == {"a": "value-a", "b": "value-b"}
    finally:
        for name in [n for n in sys.modules if n.startswith("_test_discover_pkg")]:
            del sys.modules[name]


def test_discover_modules_imports_each_module_directly(tmp_path, monkeypatch):
    """`discover_modules` imports each *module* path directly, no `__path__`
    scan — matching how storage backends, vector-store backends, sandbox
    runtimes, and extension hooks are each discovered."""
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / "_test_discover_mod_registry.py").write_text(
        "from krutrim_agent_utils.plugin_registry import PluginRegistry\nregistry = PluginRegistry(kind='thing')\n"
    )
    (tmp_path / "_test_discover_mod_a.py").write_text(
        "from _test_discover_mod_registry import registry\nregistry.register('a', 'value-a')\n"
    )

    try:
        import _test_discover_mod_registry as reg_mod

        reg_mod.registry.discover_modules(["_test_discover_mod_a"])
        assert reg_mod.registry.all() == {"a": "value-a"}
    finally:
        for name in ("_test_discover_mod_registry", "_test_discover_mod_a"):
            sys.modules.pop(name, None)
