"""Generic graph assembly — the same wiring for every agent profile.

Reads whatever a profile declares (prompts, tools, subagents, skills,
memory, roles) and assembles a deepagents graph. Never imports a specific
profile module — profiles are the plugin surface, this is core.

Wiring, in one place:

- `backend`: a `CompositeBackend` routing `/skills/common/`, `/skills/<key>/`,
  and `/memory/` to read-only host directories (this profile's harness
  content, scoped so it can't see other profiles' memory) and everything
  else (in particular `/workspace`) to the caller-supplied filesystem
  backend — an in-process `FilesystemBackend` scoped to the session's
  workspace dir (see `krutrim_agent_sandbox.registry`). No shell `execute`
  today; a non-`SandboxBackendProtocol` backend simply doesn't get that tool.
- the skills/memory routes use `ReadOnlyFilesystemBackend`, which refuses
  `write`/`edit`/`delete` outright, so the agent can read harness content but
  never mutate it. (deepagents' `permissions` rules can't be combined with a
  sandbox-execute backend — see `krutrim_agents_core.harness.readonly_backend` —
  so read-only enforcement lives at the backend level instead.)
- `middleware=[FrontendToolBridgeMiddleware()]`: bridges frontend-defined
  tools (the shared `render_content` action) into the model's tool list, and
  routes their execution back to the frontend.
- `checkpointer`: required by the AG-UI stream translator
  (`krutrim_agent_agui.run_graph_as_agui` calls `graph.aget_state()` to
  read the final message per `threadId` after a run). Callers
  pass a durable, session-scoped saver (see `api/agent_run.py` — a dedicated
  SQLite file per session, not shared across sessions); an `InMemorySaver()`
  is used only when no checkpointer is supplied, e.g. by tests that just need
  the graph to compile.
- `extra_tools`: additional tools appended after `profile.tools()` — used by
  `api/agent_run.py` to grant the cross-agent `message_agent` tool
  (`agents/cross_agent.py`) only to sessions whose sharing policy and peer
  set actually make it usable, without profiles needing to know this tool
  exists at all.
- `extra_middleware`: `AgentMiddleware` appended after
  `FrontendToolBridgeMiddleware` — used to attach `RunLoggingMiddleware`
  (`krutrim_agents_core.harness.run_logging`) so every model/tool call lands
  in the per-run JSONL transcript, without profiles knowing it exists.
- `graph_pattern`: a profile may override the compiled topology (see
  `DeepAgentContext` below). Every profile without one keeps compiling
  through `create_deep_agent`'s ReAct loop exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend
from krutrim_agent_management.config import settings
from langgraph.checkpoint.memory import InMemorySaver

from krutrim_agents_core.frontend_tools import FrontendToolBridgeMiddleware
from krutrim_agents_core.harness.readonly_backend import ReadOnlyFilesystemBackend
from krutrim_agents_core.providers.registry import build_chat_model

if TYPE_CHECKING:
    from deepagents.backends.protocol import BackendProtocol
    from deepagents.middleware.subagents import SubAgent
    from langchain.agents.middleware.types import AgentMiddleware
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph

    from krutrim_agents_core.profile import AgentProfile
    from krutrim_agents_core.providers.store import ProviderStore


@dataclass
class DeepAgentContext:
    """Everything `create_deep_agent` would consume, assembled once by `build_agent`.

    Handed to `profile.graph_pattern` instead of a raw `create_deep_agent(...)`
    call, so a profile that wants a different graph topology (planner/worker,
    supervisor, reflection loop, ...) can still reuse the model, tools,
    prompt, subagents, skills, memory, backend, middleware, and checkpointer
    that `build_agent` already wired up — without recomputing any of it.

    Call `.react_agent()` to get a fully-wired deepagents ReAct graph
    (filesystem/subagent/skills/memory middleware, prompt assembly,
    `DeepAgentState`, `FrontendToolBridgeMiddleware`) as a single compiled
    node — LangGraph compiled graphs are plain runnables, so it can be
    dropped into a hand-built `StateGraph` with `graph.add_node("worker",
    context.react_agent())`.

    Skipping `.react_agent()` entirely (building nodes by hand instead) means
    re-earning, on your own, everything `create_deep_agent` gives you for
    free:

    - filesystem/skills/memory/subagent tool wiring — these middleware
      classes are coupled to `create_agent`'s fixed `model`/`tools` node
      shape and don't attach to an arbitrary `StateGraph` node on their own.
    - `FrontendToolBridgeMiddleware` — only fires inside a `create_agent`-built
      model node; a hand-written node silently won't bridge frontend tools
      unless you replicate that wiring yourself.
    - checkpointer/state compatibility — the AG-UI translator
      (`krutrim_agent_agui`) calls `graph.aget_state()` keyed by
      `threadId`; a custom graph must be compiled with the same `checkpointer`
      and keep a `messages` key
      shaped like `DeepAgentState` (it uses a `DeltaChannel` reducer to keep
      checkpoint growth linear) or streaming/resume breaks.
    - the `recursion_limit`/tracing `.with_config(...)` that `create_deep_agent`
      applies at the end — a custom top-level graph needs its own equivalent.

    None of this applies to nodes built via `.react_agent()` — only to graph
    nodes you construct by hand instead of using it.
    """

    model: BaseChatModel
    tools: list[BaseTool]
    system_prompt: str
    subagents: list[SubAgent]
    skills: list[str]
    memory: list[str]
    backend: BackendProtocol
    middleware: list[AgentMiddleware[Any, Any, Any]]
    checkpointer: BaseCheckpointSaver
    name: str

    def react_agent(self, **overrides: Any) -> CompiledStateGraph:
        """Compile the standard deepagents ReAct graph from this context.

        Pass keyword overrides (e.g. `tools=`, `system_prompt=`) to compile a
        variant — e.g. a planner or critic node with a narrower tool set —
        without hand-rolling the rest of the wiring.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "tools": self.tools,
            "system_prompt": self.system_prompt,
            "subagents": self.subagents,
            "skills": self.skills,
            "memory": self.memory,
            "backend": self.backend,
            "middleware": self.middleware,
            "checkpointer": self.checkpointer,
            "name": self.name,
        }
        kwargs.update(overrides)
        return create_deep_agent(**kwargs)


def build_agent(
    profile: AgentProfile,
    store: ProviderStore,
    sandbox: BackendProtocol,
    checkpointer: BaseCheckpointSaver | None = None,
    extra_tools: list[BaseTool] | None = None,
    extra_middleware: list[AgentMiddleware[Any, Any, Any]] | None = None,
) -> CompiledStateGraph:
    backend = CompositeBackend(
        default=sandbox,
        routes={
            "/skills/common/": ReadOnlyFilesystemBackend(
                root_dir=settings.common_skills_dir, virtual_mode=True
            ),
            f"/skills/{profile.key}/": ReadOnlyFilesystemBackend(
                root_dir=settings.agent_skills_dir(profile.key), virtual_mode=True
            ),
            "/memory/": ReadOnlyFilesystemBackend(
                root_dir=settings.agent_memory_dir(profile.key), virtual_mode=True
            ),
        },
    )

    context = DeepAgentContext(
        model=build_chat_model(store.get(profile.key, "main")),
        tools=[*profile.tools(), *(extra_tools or [])],
        system_prompt=profile.main_system_prompt,
        subagents=profile.subagents(store),
        skills=list(profile.skills_sources),
        memory=list(profile.memory_sources),
        backend=backend,
        middleware=[FrontendToolBridgeMiddleware(), *(extra_middleware or [])],
        checkpointer=checkpointer or InMemorySaver(),
        name=profile.key,
    )

    if profile.graph_pattern is not None:
        return profile.graph_pattern(context)

    return context.react_agent()
