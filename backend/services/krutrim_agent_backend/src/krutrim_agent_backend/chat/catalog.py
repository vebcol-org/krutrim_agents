"""Models offered for the plain `chat` project type.

Chat has no roles — one model per chat, picked at creation from this list.
The list is now a *view* of the single shared catalog
(`krutrim_agents_core.providers.catalog`) filtered to chat models, so there
is only one place to add a model. `ChatModelOption` is kept as the narrow
shape the chat API and its tests already depend on.
"""

from __future__ import annotations

from dataclasses import dataclass

from krutrim_agents_core.providers.catalog import chat_models, default_chat_model


@dataclass(frozen=True)
class ChatModelOption:
    provider: str
    model: str
    display_name: str


def _to_option(card) -> ChatModelOption:
    suffix = " (OpenRouter)" if card.provider == "openrouter" else ""
    return ChatModelOption(
        provider=card.provider,
        model=card.id,
        display_name=f"{card.label}{suffix}",
    )


CHAT_MODEL_CATALOG: list[ChatModelOption] = [_to_option(c) for c in chat_models()]

DEFAULT_CHAT_MODEL = _to_option(default_chat_model())


def is_known_chat_model(provider: str, model: str) -> bool:
    return any(
        option.provider == provider and option.model == model
        for option in CHAT_MODEL_CATALOG
    )
