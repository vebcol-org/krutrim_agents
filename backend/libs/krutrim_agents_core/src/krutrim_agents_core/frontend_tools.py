"""Bridges frontend-declared AG-UI tools into the model's tool list.

`ag_ui_langgraph`'s own default state merge already puts every tool the
frontend declared for this run (`RunAgentInput.tools`) into `state["tools"]`
on every invocation — that's core AG-UI plumbing, nothing CopilotKit-specific
about it. This middleware does the two things needed to make those tools
actually usable:

1. `wrap_model_call` — adds them to the bound tool list so the model can call
   them at all.
2. `after_model` / `after_agent` — a frontend tool has no backend
   implementation, so if LangGraph's `ToolNode` saw it in `AIMessage.tool_calls`
   it would error trying to execute it. `after_model` strips any such calls
   out of the message before the tool node runs (the turn then ends
   naturally, since nothing backend-side is left to execute); `after_agent`
   restores them onto the final message once the run is over, purely so they
   still stream to the client as ordinary `TOOL_CALL_*` AG-UI events.

This is a trimmed, direct port of `copilotkit.CopilotKitMiddleware`'s
`wrap_model_call`/`after_model`/`after_agent` hooks (which did the identical
thing reading `state["copilotkit"]["actions"]`, a same-shaped mirror of
`state["tools"]` that package populated) — dropping the CopilotKit-specific
extras we never used (A2UI generative-UI tool injection, Bedrock message
repair, forwarded-header propagation).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ModelRequest,
    ModelResponse,
)
from langchain_core.messages import AIMessage

if TYPE_CHECKING:
    from langgraph.runtime import Runtime


class _FrontendToolState(AgentState):
    """Extra state fields this middleware owns (`tools` is read-only here — written by `ag_ui_langgraph`, not us)."""

    intercepted_tool_calls: list[dict[str, Any]] | None
    original_ai_message_id: str | None


class FrontendToolBridgeMiddleware(AgentMiddleware[_FrontendToolState, Any]):
    state_schema = _FrontendToolState

    @property
    def name(self) -> str:
        return "FrontendToolBridgeMiddleware"

    def _merge_frontend_tools(self, request: ModelRequest) -> ModelRequest:
        frontend_tools = request.state.get("tools") or []
        if not frontend_tools:
            return request
        return request.override(tools=[*request.tools, *frontend_tools])

    def wrap_model_call(self, request: ModelRequest, handler) -> ModelResponse:
        return handler(self._merge_frontend_tools(request))

    async def awrap_model_call(self, request: ModelRequest, handler) -> ModelResponse:
        return await handler(self._merge_frontend_tools(request))

    def _split_tool_calls(self, state: _FrontendToolState) -> dict[str, Any] | None:
        frontend_tools = state.get("tools") or []
        if not frontend_tools:
            return None
        frontend_tool_names = {
            t.get("name") for t in frontend_tools if isinstance(t, dict)
        }

        messages = state.get("messages", [])
        if not messages:
            return None
        last_message = messages[-1]
        if not isinstance(last_message, AIMessage):
            return None
        tool_calls = getattr(last_message, "tool_calls", None) or []
        if not tool_calls:
            return None

        backend_tool_calls = [
            c for c in tool_calls if c.get("name") not in frontend_tool_names
        ]
        frontend_tool_calls = [
            c for c in tool_calls if c.get("name") in frontend_tool_names
        ]
        if not frontend_tool_calls:
            return None

        updated_ai_message = AIMessage(
            content=last_message.content,
            tool_calls=backend_tool_calls,
            id=last_message.id,
        )
        return {
            "messages": [*messages[:-1], updated_ai_message],
            "intercepted_tool_calls": frontend_tool_calls,
            "original_ai_message_id": last_message.id,
        }

    def after_model(
        self, state: _FrontendToolState, runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        return self._split_tool_calls(state)

    async def aafter_model(
        self, state: _FrontendToolState, runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        return self._split_tool_calls(state)

    def _restore_tool_calls(self, state: _FrontendToolState) -> dict[str, Any] | None:
        intercepted_tool_calls = state.get("intercepted_tool_calls")
        original_message_id = state.get("original_ai_message_id")
        if not intercepted_tool_calls or not original_message_id:
            return None

        messages = state.get("messages", [])
        updated_messages = []
        for msg in messages:
            if isinstance(msg, AIMessage) and msg.id == original_message_id:
                existing_tool_calls = getattr(msg, "tool_calls", None) or []
                updated_messages.append(
                    AIMessage(
                        content=msg.content,
                        tool_calls=[*existing_tool_calls, *intercepted_tool_calls],
                        id=msg.id,
                    )
                )
            else:
                updated_messages.append(msg)

        return {
            "messages": updated_messages,
            "intercepted_tool_calls": None,
            "original_ai_message_id": None,
        }

    def after_agent(
        self, state: _FrontendToolState, runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        return self._restore_tool_calls(state)

    async def aafter_agent(
        self, state: _FrontendToolState, runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        return self._restore_tool_calls(state)
