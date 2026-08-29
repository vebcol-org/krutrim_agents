"""In-tree LangGraph -> AG-UI streaming translator + its plugin surface.

`run_graph_as_agui(graph, run_input, thread_id=..., plugins=default_plugins())`
is the drop-in replacement for `ag_ui_langgraph.LangGraphAgent(...).run(...)`,
used by both `api/agent_run.py` and `api/chat_routes.py`.
"""

from krutrim_agent_agui.plugins import AguiPlugin, AguiRunContext, PluginBase
from krutrim_agent_agui.registry import default_plugins, register_plugin
from krutrim_agent_agui.translator import run_graph_as_agui

__all__ = [
    "AguiPlugin",
    "AguiRunContext",
    "PluginBase",
    "default_plugins",
    "register_plugin",
    "run_graph_as_agui",
]
