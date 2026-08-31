"""`rag_tool` — the agent-initiated retrieval tool the research prompts
describe ("The user will supply domain-specific or private context via a
rag_tool ... you must query for it"). Tool-call semantics, not silent
injection: the agent decides when to call it and tags results `[RAG]` in its
own source log, per `research-agent-rag-prompt.md`.

Reads `session_id` from the LangGraph run's `thread_id` (via `get_config()`)
at call time rather than being pre-bound via a factory closure — this keeps
`rag_tool` a normal static tool registered once in a profile's `_tools()`,
with no need to widen `AgentProfile.tools_factory`'s no-argument signature.
`thread_id` is set to the session id for every real run (`agent_run.py`
passes the frontend's `threadId`, which the frontend sets to `sessionId`),
the same value the run's own checkpointer is keyed by.
"""

from __future__ import annotations

from krutrim_agent_management.config import settings
from krutrim_agent_management.storage_factory import create_storage
from langchain_core.tools import tool
from langgraph.config import get_config

from krutrim_agent_rag.retrieval import retrieve


def _current_session_id() -> str | None:
    config = get_config()
    return (config.get("configurable") or {}).get("thread_id")


@tool
async def rag_tool(query: str) -> str:
    """Query the user's uploaded/pasted research context for an answer.

    Use this BEFORE web_search for anything that sounds like a "this depends
    on their situation" fact — their documents, their data, their prior
    decisions. Ask a complete, self-contained question, not a fragment.
    Returns "No matching context found." if nothing relevant has been
    ingested yet — that's not an error, just an empty result.
    """
    session_id = _current_session_id()
    if not session_id:
        return "Error: no active session — rag_tool needs a running agent session."

    store = create_storage(settings)
    chunks = await _retrieve(store, session_id, query)
    if not chunks:
        return "No matching context found."

    lines = []
    for i, chunk in enumerate(chunks, start=1):
        lines.append(
            f"{i}. [source: {chunk.source or 'unknown'}, score: {chunk.score:.3f}]\n   {chunk.text}"
        )
    return "\n".join(lines)


async def _retrieve(store, session_id: str, query: str):
    import asyncio

    # `retrieve` does synchronous I/O (faisslite + the embedding HTTP call) —
    # offload it so the tool doesn't block the event loop, matching this
    # codebase's general async-tool convention (`web_search` uses the same
    # `asyncio.to_thread` pattern for its own sync DDGS call).
    return await asyncio.to_thread(retrieve, store, session_id, query)
