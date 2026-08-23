"""Basic (non-agentic) LangGraph chat graph: one node, no tools, no subagents.

Backs the `chat` project type — see `krutrim_agent_backend.api.chat_routes`. Unlike
the deepagents-based agent profiles (`krutrim_agents_core/builder.py`), this never
touches the sandbox and has no tool-calling loop: it's a single
system-prompt + message-history call to the configured chat model. It's
wired as a LangGraph graph (rather than a plain function call) so message
flow goes through the same graph abstraction as the rest of the platform,
and so it's easy to extend with more nodes later.

Compiled without a checkpointer: conversation history is persisted by
`Storage.write_checkpoint` between requests instead (see `chat_routes.py`),
so each call gets the full message history as its initial state rather than
relying on LangGraph's own checkpoint storage.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from krutrim_agents_core.tools import (
    get_current_date,
    get_current_datetime,
    get_current_time,
)
from langchain_core.messages import SystemMessage
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from langgraph.graph.state import CompiledStateGraph


def build_chat_graph(
    model: BaseChatModel, system_prompt: str
) -> CompiledStateGraph:
    tools = [get_current_date, get_current_time, get_current_datetime]
    model_with_tools = model.bind_tools(tools)

    async def call_model(state: MessagesState) -> dict:
        response = await model_with_tools.ainvoke(
            [SystemMessage(content=system_prompt), *state["messages"]]
        )
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("agent", call_model)
    builder.add_node("tools", ToolNode(tools))

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)  # routes to "tools" or END
    builder.add_edge("tools", "agent")

    return builder.compile()  # type: ignore
