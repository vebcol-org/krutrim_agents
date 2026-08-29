"""`RunLoggingMiddleware` — the in-graph half of the per-run audit trail.

`HostBridge` (in `krutrim_agent_grpc`) already logs every LLM completion and
host-side tool call the sandboxed agent makes *from the outside* — model, token
usage, latency, tool args/results. This middleware logs the same events *from
inside the graph*, so the transcript also covers calls that never leave the
container (frontend tools, structured-output helper calls, retries a wrapping
middleware absorbs) and carries the LangGraph tool-call ids that tie a request
to its result.

Attached via `build_agent(..., extra_middleware=[...])`. The in-sandbox runtime
(`krutrim_agent_grpc.server.graph_runner`) always attaches one, pointed at
`out/runs/<thread>.jsonl`; the in-process path attaches one pointed at the
host's `runs_dir`.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import AgentMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from langchain.agents.middleware import ModelRequest, ModelResponse
    from langchain.agents.middleware.types import ToolCallRequest
    from langchain_core.messages import BaseMessage

    from krutrim_agents_core.harness.runs import RunLogger


def _message_text(message: BaseMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return str(content)


class RunLoggingMiddleware(AgentMiddleware):
    """Logs one `model_request`/`model_response` pair per model call and one
    `tool_request`/`tool_response` pair per tool call to a `RunLogger`.

    Purely observational — it always forwards the request to `handler`
    unchanged and returns its result untouched; a logging failure is
    swallowed so it can never break a run.
    """

    def __init__(self, run_logger: RunLogger) -> None:
        super().__init__()
        self._log = run_logger

    @property
    def name(self) -> str:
        return "RunLoggingMiddleware"

    def _safe_log(self, event_type: str, payload: dict[str, Any]) -> None:
        try:
            self._log.log(event_type, payload)
        except Exception:  # noqa: BLE001, S110 - the transcript is best-effort
            pass

    # -- model calls --------------------------------------------------

    def _log_model_request(self, request: ModelRequest) -> None:
        self._safe_log(
            "model_request",
            {
                "source": "agent_graph",
                "messages": len(request.messages or []),
                "tools": [
                    getattr(t, "name", None) or (isinstance(t, dict) and t.get("name"))
                    for t in (request.tools or [])
                ],
            },
        )

    def _log_model_response(
        self, response: ModelResponse, *, latency_ms: int
    ) -> None:
        result = list(getattr(response, "result", None) or [])
        last = result[-1] if result else None
        tool_calls = [c.get("name") for c in getattr(last, "tool_calls", None) or []]
        usage = getattr(last, "usage_metadata", None)
        self._safe_log(
            "model_response",
            {
                "source": "agent_graph",
                "chars": len(_message_text(last)) if last is not None else 0,
                "tool_calls": tool_calls,
                "usage": dict(usage) if usage else None,
                "latency_ms": latency_ms,
            },
        )

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        self._log_model_request(request)
        started = time.monotonic()
        response = handler(request)
        self._log_model_response(
            response, latency_ms=round((time.monotonic() - started) * 1000)
        )
        return response

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        self._log_model_request(request)
        started = time.monotonic()
        response = await handler(request)
        self._log_model_response(
            response, latency_ms=round((time.monotonic() - started) * 1000)
        )
        return response

    # -- tool calls -------------------------------------------------

    def _log_tool_request(self, request: ToolCallRequest) -> None:
        call = request.tool_call or {}
        self._safe_log(
            "tool_request",
            {
                "source": "agent_graph",
                "tool": call.get("name"),
                "tool_call_id": call.get("id"),
                "args": call.get("args"),
            },
        )

    def _log_tool_response(
        self, request: ToolCallRequest, result: Any, *, latency_ms: int
    ) -> None:
        call = request.tool_call or {}
        content = getattr(result, "content", None)
        self._safe_log(
            "tool_response",
            {
                "source": "agent_graph",
                "tool": call.get("name"),
                "tool_call_id": call.get("id"),
                "chars": len(content) if isinstance(content, str) else None,
                "status": getattr(result, "status", None),
                "latency_ms": latency_ms,
            },
        )

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        self._log_tool_request(request)
        started = time.monotonic()
        result = handler(request)
        self._log_tool_response(
            request, result, latency_ms=round((time.monotonic() - started) * 1000)
        )
        return result

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        self._log_tool_request(request)
        started = time.monotonic()
        result = await handler(request)
        self._log_tool_response(
            request, result, latency_ms=round((time.monotonic() - started) * 1000)
        )
        return result
