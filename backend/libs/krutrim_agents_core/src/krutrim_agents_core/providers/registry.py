"""Maps a provider key to its settings class + implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from krutrim_agents_core.observability import get_langfuse_handler
from krutrim_agents_core.providers.base import ModelSettings, Provider
from krutrim_agents_core.providers.openrouter import (
    OpenRouterModelSettings,
    OpenRouterProvider,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

_SETTINGS_CLASSES: dict[str, type[ModelSettings]] = {
    "openrouter": OpenRouterModelSettings
}

_PROVIDERS: dict[str, Provider] = {
    "openrouter": OpenRouterProvider(),
}


def known_providers() -> list[str]:
    return sorted(_SETTINGS_CLASSES)


def parse_model_settings(data: dict[str, Any]) -> ModelSettings:
    provider = data.get("provider")
    settings_cls = _SETTINGS_CLASSES.get(provider)
    if settings_cls is None:
        raise ValueError(
            f"Unknown provider {provider!r}. Known providers: {known_providers()}"
        )
    return settings_cls.model_validate(data)


def build_chat_model(data: dict[str, Any] | ModelSettings) -> BaseChatModel:
    settings = data if isinstance(data, ModelSettings) else parse_model_settings(data)
    model = _PROVIDERS[settings.provider].build_chat_model(settings)
    handler = get_langfuse_handler()
    if handler:
        model.callbacks = [handler]
    return model
