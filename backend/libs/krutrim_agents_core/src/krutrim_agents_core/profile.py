"""The contract every agent profile fills in.

An `AgentProfile` fully describes one pluggable agent type (research,
trading, sales, ...). Profiles are discovered automatically by
`registry.py` from `krutrim_agents/profiles/*` — nothing outside a profile's own
package needs to change to add one. This module defines the *shape*; it
never references a specific profile.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from deepagents.middleware.subagents import SubAgent
    from langchain_core.tools import BaseTool
    from langgraph.graph.state import CompiledStateGraph

    from krutrim_agents_core.builder import DeepAgentContext
    from krutrim_agents_core.providers.store import ProviderStore


@dataclass(frozen=True)
class RoleDefaults:
    """A profile's default provider/model choice for one role — seeds `ProviderStore`."""

    provider: str
    model: str
    temperature: float = 0.3
    max_tokens: int | None = None


@dataclass(frozen=True)
class AgentProfile:
    """One pluggable agent type — everything the platform needs to run it.

    `key` must be URL-safe (`^[a-z0-9_-]+$`): it shows up in the frontend URL
    (`?agent=<key>`), the AG-UI route (`/agents/<key>`), and the settings
    routes (`/api/providers/<key>/...`).
    """

    key: str
    display_name: str
    description: str
    roles: Sequence[str]
    default_models: dict[str, RoleDefaults]
    main_system_prompt: str
    skills_sources: Sequence[str]
    memory_sources: Sequence[str] = ()
    tools_factory: Callable[[], list[BaseTool]] | None = None
    subagents_factory: Callable[[ProviderStore], list[SubAgent]] | None = field(
        default=None
    )
    graph_pattern: Callable[[DeepAgentContext], CompiledStateGraph] | None = field(
        default=None
    )
    """Opt-in override of the graph topology `build_agent` compiles.

    `None` (default): `build_agent` compiles the standard deepagents ReAct
    loop (`DeepAgentContext.react_agent()`) — unchanged behavior.

    Set this to build a different pattern (planner/worker, supervisor,
    reflection loop, ...) instead. The callable receives a `DeepAgentContext`
    with everything `create_deep_agent` would have used (model, tools,
    system_prompt, subagents, skills, memory, backend, middleware,
    checkpointer, name) already assembled, and returns a compiled graph.
    Call `context.react_agent()` from inside it to still get a fully-wired
    deep agent as one node/tool of your custom graph — see
    `krutrim_agents_core.builder.DeepAgentContext` for the tradeoffs of not
    doing so.
    """

    def tools(self) -> list[BaseTool]:
        return self.tools_factory() if self.tools_factory else []

    def subagents(self, store: ProviderStore) -> list[SubAgent]:
        return self.subagents_factory(store) if self.subagents_factory else []
