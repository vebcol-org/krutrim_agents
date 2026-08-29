"""The active translator-plugin set.

`default_plugins()` is what `api/agent_run.py` and `api/chat_routes.py` pass to
`run_graph_as_agui`. Extra plugins (e.g. from `krutrim_agent_extensions`) register
at import time via `register_plugin`; the same module-level-list idiom as the
agent-profile registry.
"""

from __future__ import annotations

from krutrim_agent_backend.agui.plugins import AguiPlugin

_EXTRA: list[AguiPlugin] = []


def register_plugin(plugin: AguiPlugin) -> None:
    """Append a plugin to every subsequent `default_plugins()` result."""
    _EXTRA.append(plugin)


def default_plugins() -> list[AguiPlugin]:
    """Built-ins first, then anything `register_plugin`ed, in registration order."""
    return []
