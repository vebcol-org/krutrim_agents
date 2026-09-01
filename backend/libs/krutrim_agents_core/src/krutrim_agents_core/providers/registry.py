"""Provider registry: key -> settings class + a lazily-importing builder.

Each `ProviderSpec.build` imports its own SDK *inside* the call, so a provider
with an optional dependency (e.g. Ollama) never breaks import/startup for
deployments that don't install it. `provider_available()` probes those
optional deps once so unavailable providers can be hidden from the UI.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING, Any

from krutrim_agents_core.observability import get_langfuse_handler
from krutrim_agents_core.providers.base import ModelSettings, ProviderConfigError
from krutrim_agents_core.providers.openrouter import (
    OpenRouterModelSettings,
    OpenRouterProvider,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    settings_cls: type[ModelSettings]
    build: Callable[[ModelSettings], BaseChatModel]  # imports its SDK lazily
    api_key_env: str = ""
    requires: tuple[str, ...] = ()  # importable modules that must be installed


_PROVIDERS: dict[str, ProviderSpec] = {
    "openrouter": ProviderSpec(
        key="openrouter",
        settings_cls=OpenRouterModelSettings,
        build=OpenRouterProvider().build_chat_model,
        api_key_env="OPENROUTER_API_KEY",
        requires=(),  # langchain-openai is a core dep — nothing optional to probe
    ),
}


def known_providers() -> list[str]:
    """Every registered provider key, regardless of availability."""
    return sorted(_PROVIDERS)


def provider_spec(key: str) -> ProviderSpec | None:
    return _PROVIDERS.get(key)


@cache
def provider_available(key: str) -> bool:
    """True if the provider is registered and its optional deps import.
    Probed once per process — installed packages don't change at runtime."""
    spec = _PROVIDERS.get(key)
    if spec is None:
        return False
    return all(importlib.util.find_spec(m) is not None for m in spec.requires)


def parse_model_settings(data: dict[str, Any] | ModelSettings) -> ModelSettings:
    if isinstance(data, ModelSettings):
        return data
    provider = data.get("provider")
    spec = _PROVIDERS.get(provider)
    if spec is None:
        raise ValueError(
            f"Unknown provider {provider!r}. Known providers: {known_providers()}"
        )
    return spec.settings_cls.model_validate(data)


def build_chat_model(data: dict[str, Any] | ModelSettings) -> BaseChatModel:
    settings = parse_model_settings(data)
    spec = _PROVIDERS.get(settings.provider)
    if spec is None:
        raise ValueError(f"Unknown provider {settings.provider!r}.")
    if not provider_available(settings.provider):
        raise ProviderConfigError(
            f"Provider {settings.provider!r} needs: pip install "
            + " ".join(spec.requires)
        )
    model = spec.build(settings)  # SDK import happens here, not at module load
    handler = get_langfuse_handler()
    if handler:
        model.callbacks = [handler]
    return model
