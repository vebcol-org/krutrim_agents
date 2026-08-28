from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from deepagents import DeepAgentState
from deepagents.backends import StateBackend
from langchain.agents.middleware.types import (
    AgentMiddleware,
    ExtendedModelResponse,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.config import get_config
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import get_runtime

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from deepagents.backends.protocol import BackendProtocol
    from deepagents.middleware.filesystem import FilesystemPermission
    from deepagents.middleware.subagents import CompiledSubAgent, SubAgent
    from langchain.agents.middleware.types import ToolCallRequest
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AnyMessage
    from langchain_core.tools import BaseTool
    from langgraph.cache.base import BaseCache
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.store.base import BaseStore


# 1. Middleware hook runner


def _overrides(mw: AgentMiddleware, hook_name: str) -> bool:
    """True if `mw` actually implements `hook_name` (base default raises, not no-ops)."""
    return getattr(type(mw), hook_name) is not getattr(AgentMiddleware, hook_name)


def _hook_accepts_config(mw: AgentMiddleware, hook_name: str) -> bool:
    """True if `mw`'s override of `hook_name` declares a `config` parameter.

    `AgentMiddleware`'s base hooks take only `(state, runtime)`, but some
    deepagents middleware (`SkillsMiddleware`/`MemoryMiddleware`'s
    `before_agent`) override with an extra `config: RunnableConfig` param —
    calling those without it raises `TypeError`.
    """
    return "config" in inspect.signature(getattr(type(mw), hook_name)).parameters


def _run_state_hooks(
    middlewares: Sequence[AgentMiddleware], hook_name: str, state: dict[str, Any]
) -> dict[str, Any]:
    """Run a hook (before_agent/before_model/after_model) across middlewares, merging updates."""
    runtime = get_runtime()
    updates: dict[str, Any] = {}
    for mw in middlewares:
        if not _overrides(mw, hook_name):
            continue
        kwargs = {"config": get_config()} if _hook_accepts_config(mw, hook_name) else {}
        result = getattr(mw, hook_name)({**state, **updates}, runtime, **kwargs)
        if result:
            updates.update(result)
    return updates


def _compose_wrap_model_call(
    middlewares: Sequence[AgentMiddleware], base_handler
) -> Any:
    """Chain `wrap_model_call` hooks: first middleware in the list becomes outermost."""
    chain = base_handler
    for mw in reversed([m for m in middlewares if _overrides(m, "wrap_model_call")]):

        def step(request: ModelRequest, _next=chain, _mw=mw) -> ModelResponse:
            return _mw.wrap_model_call(request, _next)

        chain = step
    return chain


def _compose_wrap_tool_call(middlewares: Sequence[AgentMiddleware]):
    """Chain `wrap_tool_call` hooks; `None` if none defined, so `ToolNode` uses its default."""
    wrapping = [m for m in middlewares if _overrides(m, "wrap_tool_call")]
    if not wrapping:
        return None

    def composed(request: ToolCallRequest, handler):
        chain = handler
        for mw in reversed(wrapping):

            def step(req: ToolCallRequest, _next=chain, _mw=mw):
                return _mw.wrap_tool_call(req, _next)

            chain = step
        return chain(request)

    return composed


def _normalize_model_result(result) -> ModelResponse:
    """`wrap_model_call` handlers may return `ModelResponse | AIMessage | ExtendedModelResponse`."""
    if isinstance(result, AIMessage):
        return ModelResponse(result=[result])
    if isinstance(result, ExtendedModelResponse):
        # `.command` is intentionally dropped — see design doc.
        return result.model_response
    return result


# 2. Graph nodes


def _make_model_node(
    model: BaseChatModel,
    middlewares: Sequence[AgentMiddleware],
    all_tools: list[BaseTool],
    system_prompt: str | None,
    system_prompt_fn: Callable[[dict[str, Any]], str] | None = None,
):
    def base_handler(request: ModelRequest) -> ModelResponse:
        messages: list[AnyMessage] = (
            [request.system_message] if request.system_message else []
        ) + request.messages
        bound_model = (
            request.model.bind_tools(request.tools) if request.tools else request.model
        )
        ai_message = bound_model.invoke(messages)
        return ModelResponse(result=[ai_message])

    wrap_chain = _compose_wrap_model_call(middlewares, base_handler)

    def model_node(state: dict[str, Any]) -> dict[str, Any]:
        before_updates = _run_state_hooks(middlewares, "before_model", state)
        working_state = {**state, **before_updates}

        # `system_prompt_fn`, when supplied, re-renders the prompt from live
        # state on every model call — used by the research profile so its
        # Runtime Context block (research_state/known/unknown information)
        # stays fresh instead of frozen at profile-registration time. Falls
        # back to the static `system_prompt` string when absent, matching
        # every other profile's behavior.
        prompt_text = (
            system_prompt_fn(working_state) if system_prompt_fn else system_prompt
        )

        request = ModelRequest(
            model=model,
            messages=working_state["messages"],
            system_message=SystemMessage(content=prompt_text) if prompt_text else None,
            tools=all_tools,
            state=working_state,
            runtime=get_runtime(),
        )
        response = _normalize_model_result(wrap_chain(request))

        after_updates = _run_state_hooks(middlewares, "after_model", working_state)
        return {**before_updates, **after_updates, "messages": response.result}

    return model_node


def _route_after_model(state: dict[str, Any]) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


def build_chat_graph(
    model: BaseChatModel,
    tools: Sequence[BaseTool] | None = None,
    *,
    system_prompt: str | None = None,
    system_prompt_fn: Callable[[dict[str, Any]], str] | None = None,
    middleware: Sequence[AgentMiddleware] | None = None,
    subagents: Sequence[SubAgent | CompiledSubAgent] | None = None,
    skills: list[str] | None = None,
    memory: list[str] | None = None,
    permissions: list[FilesystemPermission] | None = None,
    backend: BackendProtocol | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
    context_schema: type | None = None,
    state_schema: type | None = None,
    debug: bool = False,
    name: str | None = None,
    cache: BaseCache | None = None,
) -> CompiledStateGraph:
    """Compile a ReAct agent by hand; same param names as `deepagents.create_deep_agent`.

    `system_prompt_fn`, when supplied, takes precedence over the static
    `system_prompt` string and is re-invoked with the graph's working state
    on every model-node call — see `_make_model_node`.
    """
    backend = backend or StateBackend()

    stack: list[AgentMiddleware] = []
    stack.extend(middleware or [])

    # every middleware may contribute tools (e.g. SubAgentMiddleware -> `task`)
    all_tools: list[BaseTool] = [*(tools or [])]
    for mw in stack:
        all_tools.extend(getattr(mw, "tools", None) or [])

    graph_state_schema = state_schema or DeepAgentState
    graph = StateGraph(graph_state_schema, context_schema=context_schema)

    graph.add_node(
        "before_agent", lambda state: _run_state_hooks(stack, "before_agent", state)
    )
    graph.add_node(
        "model",
        _make_model_node(model, stack, all_tools, system_prompt, system_prompt_fn),
    )
    graph.add_edge(START, "before_agent")
    graph.add_edge("before_agent", "model")

    if all_tools:
        graph.add_node(
            "tools", ToolNode(all_tools, wrap_tool_call=_compose_wrap_tool_call(stack))
        )
        graph.add_conditional_edges(
            "model", _route_after_model, {"tools": "tools", END: END}
        )
        graph.add_edge("tools", "model")
    else:
        graph.add_edge("model", END)

    return graph.compile(
        checkpointer=checkpointer, store=store, cache=cache, debug=debug, name=name
    )
