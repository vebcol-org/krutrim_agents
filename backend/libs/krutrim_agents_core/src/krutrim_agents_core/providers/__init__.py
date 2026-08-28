"""Pluggable LLM provider settings system.

Each supported backend (OpenRouter, ...) gets a `ModelSettings`
subclass describing its configurable fields plus a `Provider` that turns
those settings into a LangChain `BaseChatModel`. `registry.py` ties the two
together by a `provider` string key; `store.py` persists one named
`ModelSettings` per agent role (main/researcher/critic/writer) to disk.
"""

from krutrim_agents_core.providers.base import (
    ModelSettings,
    Provider,
    ProviderConfigError,
)
from krutrim_agents_core.providers.registry import (
    build_chat_model,
    parse_model_settings,
)

__all__ = [
    "ModelSettings",
    "Provider",
    "ProviderConfigError",
    "build_chat_model",
    "parse_model_settings",
]
