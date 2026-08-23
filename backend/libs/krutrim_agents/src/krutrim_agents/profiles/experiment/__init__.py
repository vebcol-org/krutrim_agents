"""The `experiment` agent profile: a minimal, single-role test agent.

Not a real agent type — purpose-built to exercise the AG-UI streaming path
(`POST /agents/{agent_id}`, see `krutrim_agent_backend/api/agent_run.py`) end-to-end
from the frontend, since nothing else registered here is small enough to be
a convenient manual test target. Follows the same plugin pattern as every
other profile (`krutrim_agents_core.profile.AgentProfile`, auto-discovered by
`krutrim_agents_core.registry`) — no core file needed to change to add it, and none
would need to change to remove it later either.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from krutrim_agents_core.harness.prompts import load_prompt
from krutrim_agents_core.profile import AgentProfile, RoleDefaults
from krutrim_agents_core.registry import register_profile
from krutrim_agents_core.tools import fetch_url, web_search

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

KEY = "experiment"


def _tools() -> list[BaseTool]:
    return [web_search, fetch_url]


register_profile(
    AgentProfile(
        key=KEY,
        display_name="Experiment Agent",
        description="Minimal single-role test agent — used to verify the AG-UI streaming integration, not a real agent type.",
        roles=("main",),
        default_models={
            "main": RoleDefaults(
                provider="openrouter",
                model="deepseek/deepseek-v4-flash-0731",
                temperature=0.3,
                max_tokens=4096,
            ),
        },
        main_system_prompt=load_prompt(KEY, "main"),
        skills_sources=["/skills/common/"],
        memory_sources=["/memory/AGENTS.md"],
        tools_factory=_tools,
    )
)
