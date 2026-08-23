"""OpenRouter provider: routes to any model OpenRouter proxies via its OpenAI-compatible API."""

from __future__ import annotations

import os
from typing import Literal

from langchain_openai import ChatOpenAI
from pydantic import Field

from krutrim_agents_core.providers.base import (
    ModelSettings,
    Provider,
    ProviderConfigError,
)

OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"


class OpenRouterModelSettings(ModelSettings):
    provider: Literal["openrouter"] = "openrouter"
    model: str = "deepseek/deepseek-v4-flash-0731"
    api_key_env: str = "OPENROUTER_API_KEY"
    base_url: str = OPENROUTER_BASE_URL
    site_url: str | None = Field(
        default=None,
        description="Sent as HTTP-Referer for OpenRouter analytics/rankings.",
    )
    app_name: str = "krutrim-agent"


class OpenRouterProvider(Provider):
    key = "openrouter"

    def build_chat_model(self, settings: ModelSettings) -> ChatOpenAI:
        assert isinstance(settings, OpenRouterModelSettings)
        api_key = os.environ.get(settings.api_key_env)
        if not api_key:
            raise ProviderConfigError(
                f"OpenRouter model '{settings.model}' requires the '{settings.api_key_env}' environment variable to be set."
            )
        default_headers = {"X-Title": settings.app_name}
        if settings.site_url:
            default_headers["HTTP-Referer"] = settings.site_url
        return ChatOpenAI(
            model=settings.model,
            api_key=api_key,
            base_url=settings.base_url,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            top_p=settings.top_p,
            timeout=settings.timeout,
            default_headers=default_headers,
        )
