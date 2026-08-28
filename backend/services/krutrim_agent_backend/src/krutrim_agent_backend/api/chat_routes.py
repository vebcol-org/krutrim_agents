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

Conversation history is persisted by LangGraph itself: each session gets a
`sessions/{session_id}/langgraph_checkpoint.sqlite` file, keyed by
`thread_id == session_id`. A call passes only the new user turn; the
`AsyncSqliteSaver` checkpointer replays the prior state and appends. Token
usage is still folded into `usage.json` per turn (see `chat/usage.py`), and
`GET /api/sessions/{id}/messages` reads history straight from the same
checkpoint file.

RAG: when `KRUTRIM_AGENT_RAG_INJECTION_ENABLED` is true, a
`RagInjectionMiddleware` is added to the graph — it retrieves top-k context
for the latest user message from this session's vector index and prepends it
to the system prompt, with no visible tool call. It reads the session id
from the run's `thread_id`, which is why `config={"configurable":
{"thread_id": session_id}}` is always passed to `ainvoke`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from krutrim_agent_management.base import Storage
from krutrim_agent_management.config import settings
from krutrim_agent_management.models import Chat, SessionInfo
from krutrim_agent_rag.middleware import RagInjectionMiddleware
from krutrim_agents_core.harness.prompts import load_prompt
from krutrim_agents_core.providers.registry import build_chat_model
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from loguru import logger
from pydantic import BaseModel

from krutrim_agent_backend.api.schemas import ChatApiMessage
from krutrim_agent_backend.chat.catalog import DEFAULT_CHAT_MODEL, is_known_chat_model
from krutrim_agent_backend.chat.graph import build_chat_graph
from krutrim_agent_backend.chat.messages import derive_title
from krutrim_agent_backend.chat.usage import accumulate_usage

router = APIRouter(prefix="/api/chat", tags=["chat"])

CHECKPOINT_FILENAME = "langgraph_checkpoint.sqlite"


class SendChatMessageResponse(BaseModel):
    chat_id: str
    session_id: str
    message: ChatApiMessage


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


def _as_text(content: object) -> str:
    return content if isinstance(content, str) else str(content)


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
        chat = await storage.create_chat(
            body.chat_title or derive_title(body.message),
            provider,
            model,
            project_id=body.project_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    logger.info(
        "chat: created chat {} (provider={}, model={}, project_id={})",
        chat.chat_id,
        provider,
        model,
        body.project_id,
    )
    return chat


async def _get_or_create_session(
    storage: Storage, chat_id: str, session_id: str | None
) -> SessionInfo:
    if session_id is None:
        session = await storage.create_session("chat", chat_id)
        logger.info("chat: created session {} for chat {}", session.session_id, chat_id)
        return session
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
async def send_message(
    body: ChatMessageRequest, request: Request
) -> SendChatMessageResponse:
    storage = _storage(request)
    chat = await _get_or_create_chat(storage, body)
    session = await _get_or_create_session(storage, chat.chat_id, body.session_id)

    checkpoint_path = storage.session_dir(session.session_id) / CHECKPOINT_FILENAME
    config = {"configurable": {"thread_id": session.session_id}}
    chat_model = build_chat_model({"provider": chat.provider, "model": chat.model})

    middleware = []
    if settings.rag_injection_enabled:
        middleware.append(RagInjectionMiddleware())

    logger.info(
        "chat: send_message chat={} session={} model={}/{} rag_injection={}",
        chat.chat_id,
        session.session_id,
        chat.provider,
        chat.model,
        settings.rag_injection_enabled,
    )
    logger.debug("chat: user message ({} chars): {!r}", len(body.message), body.message[:200])

    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        graph = build_chat_graph(
            chat_model,
            system_prompt=load_prompt("chat", "main"),
            checkpointer=checkpointer,
            middleware=middleware,
        )
        prior_state = await graph.aget_state(config)
        prior_count = len((prior_state.values or {}).get("messages", [])) if prior_state else 0
        logger.debug(
            "chat: session {} has {} prior message(s) in checkpoint",
            session.session_id,
            prior_count,
        )

        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=body.message)]}, config=config
        )
        reply: AIMessage = result["messages"][-1]

    reply_text = _as_text(reply.content)
    logger.info(
        "chat: reply for session {} ({} chars, {} total messages)",
        session.session_id,
        len(reply_text),
        len(result["messages"]),
    )

    existing_usage = await storage.read_usage(session.session_id)
    updated_usage = accumulate_usage(existing_usage, reply)
    await storage.write_usage(session.session_id, updated_usage)
    logger.debug(
        "chat: session {} usage totals now {}",
        session.session_id,
        updated_usage.get("totals"),
    )

    return {
        "chat_id": chat.chat_id,
        "session_id": session.session_id,
        "message": {"role": "assistant", "content": reply_text},
    }
