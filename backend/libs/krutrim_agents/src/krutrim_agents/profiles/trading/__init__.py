"""The `trading` agent profile: trading/market research analysis.

This is a plugin package — see `krutrim_agents_core.profile.AgentProfile`
for the contract and `krutrim_agents_core.registry` for how it gets
auto-discovered. Nothing outside this package needed to change to add it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from deepagents.middleware.subagents import SubAgent
from krutrim_agents_core.harness.prompts import load_prompt
from krutrim_agents_core.profile import AgentProfile, RoleDefaults
from krutrim_agents_core.providers.registry import build_chat_model
from krutrim_agents_core.registry import register_profile
from krutrim_agents_core.tools import fetch_url, web_search

if TYPE_CHECKING:
    from krutrim_agents_core.providers.store import ProviderStore
    from langchain_core.tools import BaseTool

KEY = "trading"


def _tools() -> list[BaseTool]:
    return [web_search, fetch_url]


def _subagents(store: ProviderStore) -> list[SubAgent]:
    researcher: SubAgent = {
        "name": "researcher",
        "description": (
            "Gathers and verifies facts (prices, filings, news) via web search. Delegate to this "
            "whenever you need current information you don't already have."
        ),
        "system_prompt": load_prompt(KEY, "researcher"),
        "tools": [web_search, fetch_url],
        "model": build_chat_model(store.get(KEY, "researcher")),
    }
    critic: SubAgent = {
        "name": "critic",
        "description": (
            "Reviews a draft analysis or research notes for unsupported claims, one-sidedness, "
            "and missing risks. Delegate to this before finalizing any non-trivial analysis."
        ),
        "system_prompt": load_prompt(KEY, "critic"),
        "tools": [],
        "model": build_chat_model(store.get(KEY, "critic")),
    }
    writer: SubAgent = {
        "name": "writer",
        "description": "Turns research notes and critique feedback into the final structured analysis report.",
        "system_prompt": load_prompt(KEY, "writer"),
        "tools": [],
        "model": build_chat_model(store.get(KEY, "writer")),
    }
    return [researcher, critic, writer]


register_profile(
    AgentProfile(
        key=KEY,
        display_name="Trading Agent",
        description="Trading and market research analysis: researches, analyzes, and reports on tickers and trade ideas.",
        roles=("main", "researcher", "critic", "writer"),
        default_models={
            "main": RoleDefaults(
                provider="openrouter",
                model="deepseek/deepseek-v4-flash-0731",
                temperature=0.3,
                max_tokens=4096,
            ),
            "researcher": RoleDefaults(
                provider="openrouter", model="openai/gpt-4.1-mini", temperature=0.2
            ),
            "critic": RoleDefaults(
                provider="ollama", model="llama3.1", temperature=0.0
            ),
            "writer": RoleDefaults(
                provider="openrouter",
                model="deepseek/deepseek-v4-flash-0731",
                temperature=0.4,
                max_tokens=8192,
            ),
        },
        main_system_prompt=load_prompt(KEY, "main"),
        skills_sources=["/skills/common/", f"/skills/{KEY}/"],
        memory_sources=["/memory/AGENTS.md"],
        tools_factory=_tools,
        subagents_factory=_subagents,
    )
)
