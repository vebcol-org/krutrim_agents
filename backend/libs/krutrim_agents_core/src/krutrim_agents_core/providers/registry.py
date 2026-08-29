"""Maps a provider key to its settings class + implementation."""

from __future__ import annotations

import os
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

    if os.getenv("KRUTRIM_AGENT_RUNTIME_IN_SANDBOX"):
        # The whole graph is running inside the network-disabled sandbox: every
        # completion goes back to the host over `HostBridge.ChatComplete`, which
        # rebuilds the real provider model (adding the API key) and logs the
        # call. Lazy import — `krutrim_agent_grpc` ships only in the sandbox
        # image and depends back on this package.
        from krutrim_agent_grpc.proxy_model import build_proxy_chat_model

        return build_proxy_chat_model(settings)

    model = _PROVIDERS[settings.provider].build_chat_model(settings)
    handler = get_langfuse_handler()
    if handler:
        model.callbacks = [handler]
    return model
