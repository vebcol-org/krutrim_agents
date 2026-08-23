"""The `research` agent profile: general-purpose research, not tied to any one subject.

This is a plugin package — see `krutrim_agents_core.profile.AgentProfile`
for the contract and `krutrim_agents_core.registry` for how it gets
auto-discovered. Nothing outside this package needed to change to add it.

Unlike every other profile, `research` overrides `graph_pattern` to compile
through `agent.create_research_agent` (a from-scratch LangGraph builder, not
`deepagents.create_deep_agent` directly) with a `system_prompt_fn` closure
that re-renders the system prompt from `prompts.render_system_prompt` on
every model call — see that module's docstring for why.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from deepagents.middleware.subagents import SubAgent
from krutrim_agent_rag.tool import rag_tool
from krutrim_agents_core.harness.prompts import load_prompt
from krutrim_agents_core.profile import AgentProfile, RoleDefaults
from krutrim_agents_core.providers.registry import build_chat_model
from krutrim_agents_core.registry import register_profile
from krutrim_agents_core.tools import fetch_url, web_search

from .agent import create_research_agent
from .prompts import render_system_prompt

if TYPE_CHECKING:
    from collections.abc import Sequence

    from deepagents.backends.protocol import BackendProtocol
    from krutrim_agents_core.builder import DeepAgentContext
    from krutrim_agents_core.providers.store import ProviderStore
    from langchain_core.messages import AnyMessage
    from langchain_core.tools import BaseTool
    from langgraph.graph.state import CompiledStateGraph

KEY = "research"

_SCRATCHPAD_DIR = "/workspace/.research"
_STATE_PATH = f"{_SCRATCHPAD_DIR}/state.md"
_KNOWN_PATH = f"{_SCRATCHPAD_DIR}/known.md"
_UNKNOWN_PATH = f"{_SCRATCHPAD_DIR}/unknown.md"

_NO_STATE_YET = (
    "(not started yet — no research_state written to /workspace/.research/state.md)"
)
_NO_KNOWN_YET = "(nothing confirmed yet — no known_information written to /workspace/.research/known.md)"
_NO_UNKNOWN_YET = "(no open questions logged yet — no unknown_information written to /workspace/.research/unknown.md)"
_NO_REQUEST_YET = "(no user request found in the conversation yet)"
_NO_CONVERSATION_YET = "(this is the start of the conversation)"

_RECENT_MESSAGE_WINDOW = 8


def _tools() -> list[BaseTool]:
    return [web_search, fetch_url, rag_tool]


def _subagents(store: ProviderStore) -> list[SubAgent]:
    researcher: SubAgent = {
        "name": "researcher",
        "description": (
            "Gathers and verifies facts via web search. Delegate to this whenever you need "
            "current information you don't already have."
        ),
        "system_prompt": load_prompt(KEY, "researcher"),
        "tools": [web_search, fetch_url],
        "model": build_chat_model(store.get(KEY, "researcher")),
    }
    critic: SubAgent = {
        "name": "critic",
        "description": (
            "Reviews a draft report or research notes for unsupported claims, one-sidedness, "
            "and gaps. Delegate to this before finalizing any non-trivial report."
        ),
        "system_prompt": load_prompt(KEY, "critic"),
        "tools": [],
        "model": build_chat_model(store.get(KEY, "critic")),
    }
    writer: SubAgent = {
        "name": "writer",
        "description": "Turns research notes and critique feedback into the final structured report.",
        "system_prompt": load_prompt(KEY, "writer"),
        "tools": [],
        "model": build_chat_model(store.get(KEY, "writer")),
    }
    return [researcher, critic, writer]


def _message_text(message: AnyMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return " ".join(p for p in parts if p)
    return str(content)


def _first_user_request(messages: Sequence[AnyMessage]) -> str:
    for message in messages:
        if getattr(message, "type", None) == "human":
            text = _message_text(message).strip()
            if text:
                return text
    return _NO_REQUEST_YET


def _summarize_recent_conversation(
    messages: Sequence[AnyMessage], *, window: int = _RECENT_MESSAGE_WINDOW
) -> str:
    lines: list[str] = []
    for message in messages[-window:]:
        text = _message_text(message).strip()
        if not text:
            continue
        role = getattr(message, "type", message.__class__.__name__)
        lines.append(f"{role}: {text}")
    return "\n".join(lines) if lines else _NO_CONVERSATION_YET


def _read_scratchpad_file(
    backend: BackendProtocol, path: str, placeholder: str
) -> str:
    """Best-effort read of an agent-maintained scratchpad file.

    The agent writes these itself via its ordinary filesystem tools
    (`FilesystemMiddleware` grants write/edit access to `/workspace`) — this
    just reads them back so the Runtime Context block reflects live state
    on every turn instead of being frozen at profile-registration time.
    Any read failure (file doesn't exist yet, backend error) falls back to
    `placeholder` rather than raising — a research run in progress must
    never break because the agent hasn't written a scratchpad section yet.
    """
    try:
        result = backend.read(path)
    except Exception:  # noqa: BLE001 - scratchpad absence must never break a turn
        return placeholder
    if result.error or result.file_data is None:
        return placeholder
    content = result.file_data.get("content", "").strip()
    return content or placeholder


def _describe_tools(tools: Sequence[BaseTool]) -> str:
    lines = [
        f"- {tool.name}: {tool.description}"
        for tool in tools
        if getattr(tool, "name", None)
    ]
    return "\n".join(lines) if lines else "(no tools registered)"


def _make_system_prompt_fn(context: DeepAgentContext):
    tools_description = _describe_tools(context.tools)

    def _system_prompt_fn(state: dict[str, Any]) -> str:
        messages = state.get("messages", [])
        return render_system_prompt(
            user_request=_first_user_request(messages),
            conversation_context=_summarize_recent_conversation(messages),
            research_state=_read_scratchpad_file(
                context.backend, _STATE_PATH, _NO_STATE_YET
            ),
            known_information=_read_scratchpad_file(
                context.backend, _KNOWN_PATH, _NO_KNOWN_YET
            ),
            unknown_information=_read_scratchpad_file(
                context.backend, _UNKNOWN_PATH, _NO_UNKNOWN_YET
            ),
            available_tools=tools_description,
            topology="swarm_agent",
        )

    return _system_prompt_fn


def _graph_pattern(context: DeepAgentContext) -> CompiledStateGraph:
    return create_research_agent(
        model=context.model,
        tools=context.tools,
        system_prompt_fn=_make_system_prompt_fn(context),
        middleware=context.middleware,
        subagents=context.subagents,
        skills=context.skills,
        memory=context.memory,
        backend=context.backend,
        checkpointer=context.checkpointer,
        name=context.name,
    )


register_profile(
    AgentProfile(
        key=KEY,
        display_name="Research Agent",
        description="General-purpose research: gathers, critiques, and reports on any topic.",
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
        # Static fallback/doc string only — build_agent() calls graph_pattern
        # (set below), which uses agent.py's system_prompt_fn to render the
        # real system prompt dynamically per turn (see prompts.py). This
        # value is never actually sent to the model.
        main_system_prompt=(
            "Research agent — system prompt is rendered dynamically per turn "
            "from harness/prompts/research/ fragments; see prompts.py:render_system_prompt."
        ),
        skills_sources=["/skills/common/", f"/skills/{KEY}/"],
        memory_sources=["/memory/AGENTS.md"],
        tools_factory=_tools,
        subagents_factory=_subagents,
        graph_pattern=_graph_pattern,
    )
)
