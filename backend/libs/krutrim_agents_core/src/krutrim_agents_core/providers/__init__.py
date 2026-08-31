"""Pluggable LLM provider settings system.

Each supported backend (OpenRouter, ...) gets a `ModelSettings` subclass
describing its configurable fields plus a `Provider` that turns those
settings into a LangChain `BaseChatModel`. `registry.py` ties the two
together by a `provider` string key.

`catalog.py` is the static, code-owned list of *selectable* providers/models
(what the frontend pickers show); `resolver.py` turns a profile + the
per-agent / per-session picks a user made into the effective `ModelSettings`
for each role. There is no on-disk provider store anymore — the selection is
persisted per agent instance / per session by `krutrim_agent_management`.
"""

from krutrim_agents_core.providers.base import (
    ModelSettings,
    Provider,
    ProviderConfigError,
)
from krutrim_agents_core.providers.catalog import (
    ModelCard,
    ProviderCard,
    chat_models,
    get_model_card,
    is_known_model,
    list_models,
    provider_cards,
    vision_models,
)
from krutrim_agents_core.providers.registry import (
    build_chat_model,
    known_providers,
    parse_model_settings,
    provider_available,
)
from krutrim_agents_core.providers.resolver import resolve_models, resolve_role_settings

__all__ = [
    "ModelCard",
    "ModelSettings",
    "Provider",
    "ProviderCard",
    "ProviderConfigError",
    "build_chat_model",
    "chat_models",
    "get_model_card",
    "is_known_model",
    "known_providers",
    "list_models",
    "parse_model_settings",
    "provider_available",
    "provider_cards",
    "resolve_models",
    "resolve_role_settings",
    "vision_models",
]
