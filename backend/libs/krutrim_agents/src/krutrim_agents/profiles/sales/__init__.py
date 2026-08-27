"""The `sales` agent profile: prospect research + outreach drafting.

This is a plugin package — see `krutrim_agents_core.profile.AgentProfile`
for the contract and `krutrim_agents_core.registry` for how it gets
auto-discovered. Nothing outside this package needed to change to add it.

Note this profile only declares three roles (no `critic`) — proof that a
profile can shape its own role set; the core provider store and settings
routes don't assume a fixed four-role structure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from deepagents.middleware.subagents import SubAgent
from krutrim_agent_management.config import settings
from krutrim_agents_core.harness.prompts import load_prompt
from krutrim_agents_core.profile import AgentProfile, RoleDefaults
from krutrim_agents_core.providers.registry import build_chat_model
from krutrim_agents_core.registry import register_profile
from krutrim_agents_core.tools import fetch_url, web_search

if TYPE_CHECKING:
    from krutrim_agents_core.providers.store import ProviderStore
    from langchain_core.tools import BaseTool

KEY = "sales"


def _tools() -> list[BaseTool]:
    return [web_search, fetch_url]


def _subagents(store: ProviderStore) -> list[SubAgent]:
    researcher: SubAgent = {
        "name": "researcher",
        "description": (
            "Looks up a prospect (company and, if named, a contact) via web search. Delegate to "
            "this before drafting any outreach."
        ),
        "system_prompt": load_prompt(KEY, "researcher"),
        "tools": [web_search, fetch_url],
        "model": build_chat_model(store.get(KEY, "researcher")),
    }
    writer: SubAgent = {
        "name": "writer",
        "description": "Turns prospect research into a short, personalized outreach draft.",
        "system_prompt": load_prompt(KEY, "writer"),
        "tools": [],
        "model": build_chat_model(store.get(KEY, "writer")),
    }
    return [researcher, writer]


register_profile(
    AgentProfile(
        key=KEY,
        display_name="Sales Agent",
        description="Prospect research and outreach drafting: researches a company/contact, drafts a personalized note.",
        roles=("main", "researcher", "writer"),
        default_models={
            "main": RoleDefaults(
                provider="openrouter",
                model=settings.default_model,
                temperature=0.4,
                max_tokens=4096,
            ),
            "researcher": RoleDefaults(
                provider="openrouter", model="openai/gpt-4.1-mini", temperature=0.2
            ),
            "writer": RoleDefaults(
                provider="openrouter",
                model=settings.default_model,
                temperature=0.5,
                max_tokens=2048,
            ),
        },
        main_system_prompt=load_prompt(KEY, "main"),
        skills_sources=["/skills/common/", f"/skills/{KEY}/"],
        memory_sources=["/memory/AGENTS.md"],
        tools_factory=_tools,
        subagents_factory=_subagents,
    )
)
