"""Lists models available for the `chat` project type — the frontend never hardcodes this list."""

from __future__ import annotations

from fastapi import APIRouter

from krutrim_agent_backend.chat.catalog import CHAT_MODEL_CATALOG, ChatModelOption

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
def list_models() -> list[ChatModelOption]:
    return [
        {
            "provider": option.provider,
            "model": option.model,
            "display_name": option.display_name,
        }
        for option in CHAT_MODEL_CATALOG
    ]
