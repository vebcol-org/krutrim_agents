"""Loads system prompts from `harness/prompts/<agent_key>/*.md`."""

from __future__ import annotations

from functools import cache

from krutrim_agent_management.config import settings


@cache
def load_prompt(agent_key: str, name: str) -> str:
    path = settings.prompts_dir(agent_key) / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"No prompt file at {path}")
    return path.read_text(encoding="utf-8").strip()
