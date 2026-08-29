from __future__ import annotations

import re

from krutrim_agent_management.config import settings
from krutrim_agents_core import registry
from krutrim_agents_core.profile import AgentProfile
from krutrim_agents_core.registry import all_profiles, register_profile

KEY_PATTERN = re.compile(r"^[a-z0-9_-]+$")


def test_every_profile_has_a_url_safe_key():
    for key in all_profiles():
        assert KEY_PATTERN.match(key), f"agent key {key!r} is not URL-safe"


def test_every_profile_has_non_empty_roles():
    for key, profile in all_profiles().items():
        assert len(profile.roles) > 0, f"{key} declares no roles"


def test_every_profile_default_models_cover_its_roles():
    for key, profile in all_profiles().items():
        assert set(profile.default_models) == set(profile.roles), (
            f"{key}: default_models keys {set(profile.default_models)} don't match roles {set(profile.roles)}"
        )


def test_every_profile_harness_paths_exist_on_disk():
    for key in all_profiles():
        assert settings.prompts_dir(key).is_dir(), f"missing prompts dir for {key}"
        assert settings.agent_skills_dir(key).is_dir(), f"missing skills dir for {key}"
        assert settings.agent_memory_dir(key).is_dir(), f"missing memory dir for {key}"
        assert (settings.agent_memory_dir(key) / "AGENTS.md").is_file(), (
            f"missing AGENTS.md for {key}"
        )


def test_expected_profiles_are_registered():
    # `research` is the profile this pass ships with (others land later). Not
    # exhaustive by design - more can be added without touching this file.
    assert {"research"}.issubset(all_profiles())


def test_registry_discovers_a_new_profile_package_without_touching_registry_py(
    tmp_path, monkeypatch
):
    """Proves the plug-and-play claim: a brand-new profile subpackage is
    picked up purely by existing on disk under `krutrim_agents/profiles/` — nothing
    in `registry.py` (or anywhere else) needs to change.
    """
    import krutrim_agents.profiles as profiles_pkg

    throwaway_dir = tmp_path / "_test_throwaway_profile"
    throwaway_dir.mkdir()
    (throwaway_dir / "__init__.py").write_text(
        "from krutrim_agents_core.profile import AgentProfile\n"
        "from krutrim_agents_core.registry import register_profile\n"
        "register_profile(AgentProfile(\n"
        "    key='_test_throwaway',\n"
        "    display_name='Throwaway',\n"
        "    description='test-only profile proving auto-discovery',\n"
        "    roles=('main',),\n"
        "    default_models={},\n"
        "    main_system_prompt='test',\n"
        "    skills_sources=[],\n"
        "))\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        profiles_pkg, "__path__", [*profiles_pkg.__path__, str(tmp_path)]
    )

    try:
        profiles = all_profiles()
        assert "_test_throwaway" in profiles
        assert profiles["_test_throwaway"].display_name == "Throwaway"
    finally:
        # `register_profile` mutates registry.py's module-level `_registry`
        # (a `PluginRegistry`), which `monkeypatch` can't undo (it only
        # reverts the `__path__` patch) — remove it explicitly so this test
        # doesn't leak a fake agent into every test that runs after it.
        registry._registry.discard("_test_throwaway")


def test_register_profile_rejects_duplicate_key():
    existing = next(iter(all_profiles().values()))
    duplicate = AgentProfile(
        key=existing.key,
        display_name="dup",
        description="dup",
        roles=("main",),
        default_models={},
        main_system_prompt="x",
        skills_sources=[],
    )
    try:
        register_profile(duplicate)
        raised = False
    except ValueError:
        raised = True
    assert raised, "registering a duplicate agent key should raise ValueError"
