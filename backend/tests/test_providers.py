from __future__ import annotations

import pytest
from krutrim_agents_core.providers.base import ProviderConfigError
from krutrim_agents_core.providers.ollama import OllamaModelSettings
from krutrim_agents_core.providers.openrouter import OpenRouterModelSettings
from krutrim_agents_core.providers.registry import (
    build_chat_model,
    known_providers,
    parse_model_settings,
)
from krutrim_agents_core.providers.store import ProviderStore


def test_known_providers():
    assert known_providers() == ["ollama", "openrouter"]


def test_parse_openrouter_settings():
    settings = parse_model_settings(
        {"provider": "openrouter", "model": "deepseek/deepseek-v4-flash-0731"}
    )
    assert isinstance(settings, OpenRouterModelSettings)
    assert settings.base_url == "https://openrouter.ai/api/v1"


def test_parse_ollama_settings():
    settings = parse_model_settings({"provider": "ollama", "model": "llama3.1"})
    assert isinstance(settings, OllamaModelSettings)
    assert settings.base_url == "http://localhost:11434"


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


def test_build_chat_model_ollama_needs_no_key():
    model = build_chat_model({"provider": "ollama", "model": "llama3.1"})
    assert model.model == "llama3.1"


def test_provider_store_seeds_from_registry(tmp_path):
    store = ProviderStore(tmp_path / "settings.json")
    all_research = store.get_all("research")
    assert set(all_research) == {"main", "researcher", "critic", "writer"}
    all_sales = store.get_all("sales")
    assert set(all_sales) == {
        "main",
        "researcher",
        "writer",
    }  # sales has no critic role


def test_provider_store_set_and_get(tmp_path):
    store = ProviderStore(tmp_path / "settings.json")
    store.set(
        "trading",
        "critic",
        {"provider": "ollama", "model": "mistral", "temperature": 0.9},
    )
    updated = store.get("trading", "critic")
    assert updated.model == "mistral"
    assert updated.temperature == 0.9


def test_provider_store_set_unknown_agent_raises(tmp_path):
    store = ProviderStore(tmp_path / "settings.json")
    with pytest.raises(KeyError, match="Unknown agent"):
        store.set("not-an-agent", "main", {"provider": "ollama", "model": "x"})


def test_provider_store_set_unknown_role_raises(tmp_path):
    store = ProviderStore(tmp_path / "settings.json")
    with pytest.raises(ValueError, match="Unknown role"):
        store.set(
            "sales", "critic", {"provider": "ollama", "model": "x"}
        )  # sales has no critic


def test_provider_store_reset(tmp_path):
    store = ProviderStore(tmp_path / "settings.json")
    original = store.get("trading", "writer")
    store.set("trading", "writer", {"provider": "ollama", "model": "mistral"})
    store.reset("trading", "writer")
    assert store.get("trading", "writer") == original


def test_provider_store_isolated_per_agent(tmp_path):
    store = ProviderStore(tmp_path / "settings.json")
    store.set("trading", "main", {"provider": "ollama", "model": "trading-model"})
    # research's "main" role must be untouched by trading's change
    assert store.get("research", "main").model != "trading-model"


def test_provider_store_new_agent_seeded_without_overwriting_existing(tmp_path):
    path = tmp_path / "settings.json"
    store = ProviderStore(path)
    store.set("trading", "main", {"provider": "ollama", "model": "customized"})
    # Re-opening the store (simulates a backend restart) must not clobber the customization.
    store2 = ProviderStore(path)
    assert store2.get("trading", "main").model == "customized"
