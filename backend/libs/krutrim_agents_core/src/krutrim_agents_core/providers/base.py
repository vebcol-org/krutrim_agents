"""Base types shared by every LLM provider."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


class ProviderConfigError(RuntimeError):
    """Raised when a provider can't build a chat model from its settings (e.g. missing API key)."""


class ModelSettings(BaseModel):
    """Fields common to every provider. Subclasses add provider-specific ones."""

    provider: str
    model: str
    temperature: float = 0.3
    max_tokens: int | None = Field(default=None, ge=1)
    top_p: float | None = Field(default=None, ge=0, le=1)
    timeout: float | None = Field(default=None, ge=0)


class Provider(ABC):
    """Turns a `ModelSettings` instance into a ready-to-use LangChain chat model."""

    key: str

    @abstractmethod
    def build_chat_model(self, settings: ModelSettings) -> BaseChatModel: ...
