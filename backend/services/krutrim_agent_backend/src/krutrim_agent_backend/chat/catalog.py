"""Models available for the plain `chat` project type.

Distinct from `ProviderStore` (which configures per-role models for the
deepagents-based agent profiles): chat has no roles, just one model per
project, chosen from this fixed catalog at creation time. Add entries here
as more are vetted for the chat feature.
"""

from __future__ import annotations

from dataclasses import dataclass

from krutrim_agent_management.config import settings


@dataclass(frozen=True)
class ChatModelOption:
    provider: str
    model: str
    display_name: str


CHAT_MODEL_CATALOG: list[ChatModelOption] = [
    ChatModelOption(
        provider="openrouter",
        model=settings.default_model,
        display_name="DeepSeek V4 Flash (OpenRouter)",
    ),
]

DEFAULT_CHAT_MODEL = CHAT_MODEL_CATALOG[0]


def is_known_chat_model(provider: str, model: str) -> bool:
    return any(
        option.provider == provider and option.model == model
        for option in CHAT_MODEL_CATALOG
    )
