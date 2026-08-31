from __future__ import annotations

import pytest
from krutrim_agents_core.providers import catalog as catalog_mod
from krutrim_agents_core.providers.base import ModelSettings, ProviderConfigError
from krutrim_agents_core.providers.catalog import (
    chat_models,
    default_chat_model,
    is_known_model,
    list_models,
    provider_cards,
    vision_models,
)
from krutrim_agents_core.providers.openrouter import OpenRouterModelSettings
from krutrim_agents_core.providers.registry import (
    _PROVIDERS,
    ProviderSpec,
    build_chat_model,
    known_providers,
    parse_model_settings,
    provider_available,
)
from krutrim_agents_core.providers.resolver import (
    effective_role_sources,
    resolve_models,
)
from krutrim_agents_core.registry import get_profile


def test_known_providers():
    assert known_providers() == ["openrouter"]


def test_parse_openrouter_settings():
    settings = parse_model_settings(
        {"provider": "openrouter", "model": "deepseek/deepseek-v4-flash-0731"}
    )
    assert isinstance(settings, OpenRouterModelSettings)
    assert settings.model == "deepseek/deepseek-v4-flash-0731"
    assert settings.base_url  # env-configurable; just has to be set


def test_parse_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown provider"):
        parse_model_settings({"provider": "does-not-exist", "model": "x"})


def test_build_chat_model_openrouter_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ProviderConfigError, match="OPENROUTER_API_KEY"):
        build_chat_model(
            {"provider": "openrouter", "model": "deepseek/deepseek-v4-flash-0731"}
        )


def test_build_chat_model_openrouter_succeeds_with_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    model = build_chat_model(
        {
            "provider": "openrouter",
            "model": "deepseek/deepseek-v4-flash-0731",
            "temperature": 0.5,
        }
    )
    assert model.model_name == "deepseek/deepseek-v4-flash-0731"
    assert model.temperature == 0.5


# ── catalog ──────────────────────────────────────────────────────────────
def test_catalog_chat_models_exclude_embeddings():
    chat = chat_models()
    assert chat, "expected at least one chat model in the catalog"
    assert all(m.kind == "chat" for m in chat)
    assert any(m.kind == "embedding" for m in list_models(kind="embedding"))


def test_catalog_default_chat_model_is_the_global_default():
    from krutrim_agent_management.config import settings

    assert default_chat_model().id == settings.default_model


def test_is_known_model_strict_on_kind_and_provider():
    default = default_chat_model()
    assert is_known_model(default.provider, default.id)
    assert not is_known_model("openrouter", "totally-made-up")
    assert not is_known_model("some-other-provider", default.id)
    # an embedding id is not a known *chat* model
    embedding = list_models(kind="embedding")[0]
    assert not is_known_model(embedding.provider, embedding.id, kind="chat")


def test_provider_cards_report_configured_from_env(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert all(not c.configured for c in provider_cards() if c.key == "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    assert any(c.configured for c in provider_cards() if c.key == "openrouter")


# ── lazy init: provider availability ─────────────────────────────────────
def test_provider_available_true_for_core_provider():
    provider_available.cache_clear()
    assert provider_available("openrouter") is True
    assert provider_available("does-not-exist") is False


def test_provider_available_false_when_optional_dep_missing(monkeypatch):
    spec = ProviderSpec(
        key="faux",
        settings_cls=ModelSettings,
        build=lambda s: None,
        requires=("a_package_that_is_definitely_not_installed",),
    )
    monkeypatch.setitem(_PROVIDERS, "faux", spec)
    provider_available.cache_clear()
    assert provider_available("faux") is False
    provider_available.cache_clear()


def test_list_models_hides_models_of_unavailable_provider(monkeypatch):
    monkeypatch.setattr(catalog_mod, "provider_available", lambda k: k != "openrouter")
    assert list_models(kind="chat") == []
    assert list_models(kind="chat", include_unavailable=True)


def test_build_chat_model_reports_missing_optional_dep(monkeypatch):
    spec = ProviderSpec(
        key="faux",
        settings_cls=ModelSettings,
        build=lambda s: None,
        requires=("a_package_that_is_definitely_not_installed",),
    )
    monkeypatch.setitem(_PROVIDERS, "faux", spec)
    provider_available.cache_clear()
    with pytest.raises(ProviderConfigError, match="pip install"):
        build_chat_model({"provider": "faux", "model": "x"})
    provider_available.cache_clear()


# ── vision is a flag, not a separate list ───────────────────────────────
def test_vision_models_are_a_subset_of_chat_models():
    v = vision_models()
    assert v, "expected some vision-capable chat models"
    assert all(m.kind == "chat" and m.supports_vision for m in v)
    chat_ids = {m.id for m in chat_models()}
    assert {m.id for m in v} <= chat_ids


# ── resolver ─────────────────────────────────────────────────────────────
def test_resolve_models_falls_back_to_profile_defaults():
    profile = get_profile("research")
    models = resolve_models(profile)
    assert set(models) == set(profile.roles)
    assert models["main"].model == profile.default_models["main"].model


def test_resolve_models_session_overrides_agent_overrides_profile():
    profile = get_profile("research")
    agent_overrides = {"main": {"provider": "openrouter", "model": "agent-pick"}}
    session_overrides = {"main": {"model": "session-pick"}}

    only_agent = resolve_models(profile, agent_overrides=agent_overrides)
    assert only_agent["main"].model == "agent-pick"

    both = resolve_models(
        profile,
        agent_overrides=agent_overrides,
        session_overrides=session_overrides,
    )
    # partial session override changes model, keeps provider from the agent layer
    assert both["main"].model == "session-pick"
    assert both["main"].provider == "openrouter"


def test_resolve_models_partial_override_keeps_other_fields():
    profile = get_profile("research")
    base_temp = profile.default_models["critic"].temperature
    models = resolve_models(
        profile, agent_overrides={"critic": {"temperature": base_temp + 0.4}}
    )
    assert models["critic"].temperature == pytest.approx(base_temp + 0.4)
    assert models["critic"].model == profile.default_models["critic"].model


def test_effective_role_sources_labels_each_layer():
    profile = get_profile("research")
    sources = effective_role_sources(
        profile,
        agent_overrides={"researcher": {"provider": "openrouter", "model": "x"}},
        session_overrides={"main": {"model": "y"}},
    )
    assert sources["main"] == "session"
    assert sources["researcher"] == "agent"
    assert sources["critic"] == "profile"


def test_experiment_profile_single_role_resolves():
    profile = get_profile("experiment")
    models = resolve_models(profile)
    assert set(models) == {"main"}
