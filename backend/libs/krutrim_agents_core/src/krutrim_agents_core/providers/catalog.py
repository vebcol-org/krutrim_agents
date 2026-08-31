"""Static, code-owned catalog of selectable providers and models.

Replaces the old file-backed `ProviderStore` (`harness/memory/settings.json`)
as the source of truth for *what can be picked*. Nothing here is persisted or
mutated at runtime — the frontend model pickers read this list via
`/api/providers` / `/api/providers/models` and never hardcode it, and the
per-role selection a user makes is stored elsewhere (per agent instance /
per session — see `krutrim_agent_management.Storage.read_model_settings`).

To add a model: append a `ModelCard` below. To add a provider: register it in
`krutrim_agents_core.providers.registry` and add a `ProviderCard` here.
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel

from krutrim_agents_core.providers.registry import (
    known_providers,
    provider_available,
    provider_spec,
)

ModelKind = Literal["chat", "embedding"]


class ProviderCard(BaseModel):
    """One selectable provider. `available` = its optional deps are installed;
    `configured` = its API key env var is set. Visible in a picker = both."""

    key: str
    label: str
    api_key_env: str
    available: bool
    configured: bool


class ModelCard(BaseModel):
    """One selectable model. `id` is the exact string passed as `ModelSettings.model`."""

    id: str
    label: str
    provider: str
    vendor: str
    kind: ModelKind = "chat"
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_temperature: bool = True
    supports_vision: bool = False
    default: bool = False


# Display names only — everything else about a provider lives in registry.py.
_PROVIDER_LABELS: dict[str, str] = {"openrouter": "OpenRouter", "ollama": "Ollama"}


# ── Models ───────────────────────────────────────────────────────────────
# Every entry routes through OpenRouter's OpenAI-compatible API today, so
# `provider="openrouter"` throughout; `vendor` is just for grouping in the UI.
_MODELS: list[ModelCard] = [
    ModelCard(
        id="deepseek/deepseek-v4-flash-0731",
        label="DeepSeek V4 Flash",
        provider="openrouter",
        vendor="deepseek",
        context_window=131_072,
        max_output_tokens=32_768,
        default=True,
    ),
    ModelCard(
        id="deepseek/deepseek-r1",
        label="DeepSeek R1",
        provider="openrouter",
        vendor="deepseek",
        context_window=131_072,
    ),
    ModelCard(
        id="anthropic/claude-sonnet-4.5",
        label="Claude Sonnet 4.5",
        provider="openrouter",
        vendor="anthropic",
        context_window=200_000,
        max_output_tokens=64_000,
        supports_vision=True,
    ),
    ModelCard(
        id="anthropic/claude-opus-4.1",
        label="Claude Opus 4.1",
        provider="openrouter",
        vendor="anthropic",
        context_window=200_000,
        max_output_tokens=32_000,
        supports_vision=True,
    ),
    ModelCard(
        id="anthropic/claude-3.5-haiku",
        label="Claude 3.5 Haiku",
        provider="openrouter",
        vendor="anthropic",
        context_window=200_000,
        supports_vision=True,
    ),
    ModelCard(
        id="openai/gpt-5",
        label="GPT-5",
        provider="openrouter",
        vendor="openai",
        context_window=400_000,
        supports_temperature=False,
        supports_vision=True,
    ),
    ModelCard(
        id="openai/gpt-4.1",
        label="GPT-4.1",
        provider="openrouter",
        vendor="openai",
        context_window=1_047_576,
        supports_vision=True,
    ),
    ModelCard(
        id="openai/o4-mini",
        label="o4-mini",
        provider="openrouter",
        vendor="openai",
        context_window=200_000,
        supports_temperature=False,
        supports_vision=True,
    ),
    ModelCard(
        id="google/gemini-2.5-pro",
        label="Gemini 2.5 Pro",
        provider="openrouter",
        vendor="google",
        context_window=1_048_576,
        supports_vision=True,
    ),
    ModelCard(
        id="google/gemini-2.5-flash",
        label="Gemini 2.5 Flash",
        provider="openrouter",
        vendor="google",
        context_window=1_048_576,
        supports_vision=True,
    ),
    ModelCard(
        id="meta-llama/llama-4-maverick",
        label="Llama 4 Maverick",
        provider="openrouter",
        vendor="meta",
        context_window=1_048_576,
        supports_vision=True,
    ),
    ModelCard(
        id="qwen/qwen3-235b-a22b",
        label="Qwen3 235B A22B",
        provider="openrouter",
        vendor="qwen",
        context_window=131_072,
    ),
    ModelCard(
        id="mistralai/mistral-large",
        label="Mistral Large",
        provider="openrouter",
        vendor="mistral",
        context_window=131_072,
    ),
    # ── embeddings (not user-selectable per role; listed for completeness) ──
    ModelCard(
        id="qwen/qwen3-embedding-8b",
        label="Qwen3 Embedding 8B",
        provider="openrouter",
        vendor="qwen",
        kind="embedding",
    ),
    ModelCard(
        id="openai/text-embedding-3-large",
        label="OpenAI text-embedding-3-large",
        provider="openrouter",
        vendor="openai",
        kind="embedding",
    ),
]

_MODELS_BY_ID: dict[str, ModelCard] = {m.id: m for m in _MODELS}


def provider_cards() -> list[ProviderCard]:
    """Every registered provider; `available`/`configured` reflect the live env."""
    cards: list[ProviderCard] = []
    for key in known_providers():
        spec = provider_spec(key)
        api_key_env = spec.api_key_env if spec else ""
        cards.append(
            ProviderCard(
                key=key,
                label=_PROVIDER_LABELS.get(key, key.title()),
                api_key_env=api_key_env,
                available=provider_available(key),
                configured=bool(api_key_env and os.environ.get(api_key_env)),
            )
        )
    return cards


def list_models(
    kind: ModelKind | None = None,
    provider: str | None = None,
    *,
    vision_only: bool = False,
    include_unavailable: bool = False,
) -> list[ModelCard]:
    """Catalog models, minus any whose provider's optional deps aren't installed
    (unless `include_unavailable`)."""
    return [
        m
        for m in _MODELS
        if (kind is None or m.kind == kind)
        and (provider is None or m.provider == provider)
        and (not vision_only or m.supports_vision)
        and (include_unavailable or provider_available(m.provider))
    ]


def chat_models() -> list[ModelCard]:
    return list_models(kind="chat")


def vision_models() -> list[ModelCard]:
    """View over chat models that also accept images — not a separate list."""
    return list_models(kind="chat", vision_only=True)


def get_model_card(model_id: str) -> ModelCard | None:
    return _MODELS_BY_ID.get(model_id)


def default_chat_model() -> ModelCard:
    # code-level floor — availability isn't considered (it's always openrouter)
    chats = [m for m in _MODELS if m.kind == "chat"]
    for m in chats:
        if m.default:
            return m
    return chats[0]


def is_known_model(provider: str, model: str, *, kind: ModelKind | None = "chat") -> bool:
    card = _MODELS_BY_ID.get(model)
    return card is not None and card.provider == provider and (kind is None or card.kind == kind)
