"""`RagInjectionMiddleware` — opt-in, silent retrieval injection.

This is the literal "middleware inject into our agent" piece: retrieves
top-k context for the latest user message and prepends it to the system
message on every model call, with no tool call visible in the trace.

Off by default for the `research` profile, since its prompts (see
`research-agent-rag-prompt.md`) describe `rag_tool` as something the agent
explicitly calls and tags `[RAG]` in its own source log — tool-call
semantics, not silent injection. Available for other profiles, or a future
`research` "always augment" mode, that want context injected without the
model having to ask for it. Shares its retrieval core with `tool.rag_tool`
(`retrieval.retrieve`) so both mechanisms stay consistent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from krutrim_agent_management.config import settings
from krutrim_agent_management.storage_factory import create_storage
from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.config import get_config

from krutrim_agent_rag.retrieval import retrieve

if TYPE_CHECKING:
    from langchain.agents.middleware.types import ModelRequest, ModelResponse
    from langchain_core.messages import AnyMessage


def _current_session_id() -> str | None:
    config = get_config()
    return (config.get("configurable") or {}).get("thread_id")


def _latest_user_text(messages: list[AnyMessage]) -> str | None:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            return content if isinstance(content, str) else str(content)
    return None


class RagInjectionMiddleware(AgentMiddleware[Any, Any]):
    def __init__(self, *, k: int = 5) -> None:
        self._k = k

    def wrap_model_call(self, request: ModelRequest, handler: Any) -> ModelResponse:
        session_id = _current_session_id()
        query = _latest_user_text(request.messages)
        if not session_id or not query:
            return handler(request)

        store = create_storage(settings)
        chunks = retrieve(store, session_id, query, k=self._k)
        if not chunks:
            return handler(request)

        context_block = "\n\n".join(
            f"[source: {chunk.source or 'unknown'}, score: {chunk.score:.3f}]\n{chunk.text}"
            for chunk in chunks
        )
        prefix = f"<retrieved_context>\n{context_block}\n</retrieved_context>\n\n"
        existing = request.system_message.content if request.system_message else ""
        request.system_message = SystemMessage(content=f"{prefix}{existing}")
        return handler(request)
