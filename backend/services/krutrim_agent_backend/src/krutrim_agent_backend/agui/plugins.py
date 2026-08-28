"""Plugin surface for the LangGraph -> AG-UI translator (`translator.py`).

A plugin observes every AG-UI event the translator emits and may inject its
own — around the run (`before_run` / `after_run`) or inline (`on_event`). This
is the extension point for cross-cutting run instrumentation: timing, token
accounting, cost, tracing hand-off. Built-ins live in `stats.py`; the active
set is assembled in `registry.py`.

Kept intentionally small: no ordering guarantees beyond "registry list order",
no way for a plugin to suppress a core event (only add). A plugin that raises
is logged and skipped for that hook — it never breaks the stream.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ag_ui.core import BaseEvent
    from ag_ui.core.types import RunAgentInput
    from langchain_core.messages import AIMessage


@dataclass
class AguiRunContext:
    """Per-run scratch space shared with every plugin for one `run_graph_as_agui` call."""

    thread_id: str
    run_id: str
    input: RunAgentInput
    started_at: float = field(default_factory=time.monotonic)
    scratch: dict[str, Any] = field(default_factory=dict)
    #: Populated by the translator once the graph has finished, before `after_run`.
    final_state: dict[str, Any] | None = None
    final_message: AIMessage | None = None

    @property
    def elapsed_ms(self) -> int:
        return round((time.monotonic() - self.started_at) * 1000)


@runtime_checkable
class AguiPlugin(Protocol):
    """Implement any subset of the three hooks; the others no-op via `_PluginBase`."""

    async def before_run(self, ctx: AguiRunContext) -> AsyncIterator[BaseEvent]: ...

    async def on_event(
        self, event: BaseEvent, ctx: AguiRunContext
    ) -> AsyncIterator[BaseEvent]: ...

    async def after_run(self, ctx: AguiRunContext) -> AsyncIterator[BaseEvent]: ...


class PluginBase:
    """Base with no-op hooks — subclass and override only what you need."""

    async def before_run(self, ctx: AguiRunContext) -> AsyncIterator[BaseEvent]:
        return
        yield  # pragma: no cover - makes this an async generator

    async def on_event(
        self, event: BaseEvent, ctx: AguiRunContext
    ) -> AsyncIterator[BaseEvent]:
        yield event

    async def after_run(self, ctx: AguiRunContext) -> AsyncIterator[BaseEvent]:
        return
        yield  # pragma: no cover - makes this an async generator
