"""`POST /api/chat` — sends one message against a `Chat` (see
`krutrim_agent_management.models.Chat` / `chats_routes.py`).

Unlike `/agents/{agent_id}` (AG-UI, streaming, deepagents-based — see
`agent_run.py`), this is a single request/response JSON endpoint backing a
basic LangGraph chat loop (`chat/graph.py`). It also owns the "create on
first message" flow for both the chat and its session: the caller doesn't
have to create either up front — it sends `chat_id`/`session_id` if it has
them, and omits them to have this endpoint create a new one automatically
(optionally scoped to a project via `project_id`, if given, on first
creation — otherwise a standalone chat, same as today's behavior before the
`Chat` entity existed).

Conversation history isn't kept in memory between requests: each call reads
the session's `checkpointer.json` back out of storage, appends the new
turn, invokes the graph with the full history, and writes the updated
history (plus accumulated token usage) back before responding.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from krutrim_agent_management.base import Storage
from krutrim_agent_management.models import Chat, SessionInfo
from krutrim_agents_core.harness.prompts import load_prompt
from krutrim_agents_core.providers.registry import build_chat_model
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from krutrim_agent_backend.chat.catalog import DEFAULT_CHAT_MODEL, is_known_chat_model
from krutrim_agent_backend.chat.graph import build_chat_graph
from krutrim_agent_backend.chat.messages import (
    derive_title,
    from_lc_messages,
    to_lc_messages,
)
from krutrim_agent_backend.chat.usage import accumulate_usage

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessageRequest(BaseModel):
    message: str
    chat_id: str | None = None
    session_id: str | None = None
    project_id: str | None = None
    """Only consulted when `chat_id` is omitted — scopes the newly-created chat
    to this project instead of leaving it standalone. Ignored if `chat_id` is given."""
    chat_title: str | None = None
    provider: str | None = None
    model: str | None = None


def _storage(request: Request) -> Storage:
    return request.app.state.storage


async def _get_or_create_chat(storage: Storage, body: ChatMessageRequest) -> Chat:
    if body.chat_id is not None:
        try:
            return await storage.get_chat(body.chat_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    provider = body.provider or DEFAULT_CHAT_MODEL.provider
    model = body.model or DEFAULT_CHAT_MODEL.model
    if not is_known_chat_model(provider, model):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown chat model {provider}/{model}. See GET /api/models for supported models.",
        )
    try:
        return await storage.create_chat(
            body.chat_title or derive_title(body.message),
            provider,
            model,
            project_id=body.project_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _get_or_create_session(
    storage: Storage, chat_id: str, session_id: str | None
) -> SessionInfo:
    if session_id is None:
        return await storage.create_session("chat", chat_id)
    try:
        session = await storage.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if session.owner_type != "chat" or session.owner_id != chat_id:
        raise HTTPException(
            status_code=400,
            detail=f"Session {session_id!r} does not belong to chat {chat_id!r}.",
        )
    return session


@router.post("")
async def send_message(body: ChatMessageRequest, request: Request) -> dict:
    storage = _storage(request)
    chat = await _get_or_create_chat(storage, body)
    session = await _get_or_create_session(storage, chat.chat_id, body.session_id)

    checkpoint = await storage.read_checkpoint(session.session_id)
    history = to_lc_messages((checkpoint or {}).get("messages", []))
    history.append(HumanMessage(content=body.message))

    chat_model = build_chat_model({"provider": chat.provider, "model": chat.model})
    graph = build_chat_graph(chat_model, load_prompt("chat", "main"))
    result = await graph.ainvoke({"messages": history})
    reply = result["messages"][-1]

    await storage.write_checkpoint(
        session.session_id, {"messages": from_lc_messages(result["messages"])}
    )
    existing_usage = await storage.read_usage(session.session_id)
    await storage.write_usage(
        session.session_id, accumulate_usage(existing_usage, reply)
    )

    return {
        "chat_id": chat.chat_id,
        "session_id": session.session_id,
        "message": {"role": "assistant", "content": reply.content},
    }
