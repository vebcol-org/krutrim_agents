"""The `chat` project type: a plain system-prompt + LangGraph chat loop, with
no tools, subagents, or sandbox — as opposed to the deepagents-based agent
profiles under `krutrim_agents/profiles/`. See `graph.py` for the graph itself and
`krutrim_agent_backend.api.chat_routes` for how it's exposed over HTTP.
"""

from krutrim_agent_backend.chat.catalog import (
    CHAT_MODEL_CATALOG,
    DEFAULT_CHAT_MODEL,
    ChatModelOption,
    is_known_chat_model,
)
from krutrim_agent_backend.chat.graph import build_chat_graph

__all__ = [
    "CHAT_MODEL_CATALOG",
    "DEFAULT_CHAT_MODEL",
    "ChatModelOption",
    "build_chat_graph",
    "is_known_chat_model",
]
