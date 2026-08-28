"""`POST /api/chat` — streams one message against a `Chat` (see
`krutrim_agent_management.models.Chat` / `chats_routes.py`).

Like `/agents/{agent_id}` this is now an **AG-UI SSE stream** (`text/event-stream`
of `ag_ui.core` events), driven by the same `run_graph_as_agui` translator — the
only differences from the agent route are the graph it runs (`chat/graph.py`'s
plain ReAct loop instead of a deepagents profile) and the "create on first
message" flow for the chat + its session.

Conversation history is persisted by LangGraph: each session gets a
`sessions/{session_id}/langgraph_checkpoint.sqlite` file keyed by
`thread_id == session_id`. Only the new user turn is sent; the `AsyncSqliteSaver`
checkpointer replays prior state and appends. Token usage is folded into
`usage.json` per turn via `run_graph_as_agui`'s `on_finish` hook (see
`chat/usage.py`), and `GET /api/sessions/{id}/messages` reads history straight
from the same checkpoint file.

RAG: when `KRUTRIM_AGENT_RAG_INJECTION_ENABLED` is true a `RagInjectionMiddleware`
is added to the graph — it retrieves top-k context for the latest user message
from this session's vector index and prepends it to the system prompt, with no
visible tool call. It reads the session id from the run's `thread_id`.
"""

from __future__ import annotations

from ag_ui.core import CustomEvent, EventType, RunErrorEvent
from ag_ui.core.types import RunAgentInput
from ag_ui.encoder import EventEncoder
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from krutrim_agent_management.base import Storage
from krutrim_agent_management.config import settings
from krutrim_agent_management.models import Chat, SessionInfo
from krutrim_agent_rag.middleware import RagInjectionMiddleware
from krutrim_agents_core.harness.prompts import load_prompt
from krutrim_agents_core.providers.registry import build_chat_model
from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from loguru import logger
from pydantic import BaseModel

from krutrim_agent_backend.agui import (
    AguiRunContext,
    run_graph_as_agui,
)
from krutrim_agent_backend.chat.catalog import DEFAULT_CHAT_MODEL, is_known_chat_model
from krutrim_agent_backend.chat.graph import build_chat_graph
from krutrim_agent_backend.chat.messages import derive_title
from krutrim_agent_backend.chat.usage import accumulate_usage

router = APIRouter(prefix="/api/chat", tags=["chat"])

CHECKPOINT_FILENAME = "langgraph_checkpoint.sqlite"

#: Name of the ``CUSTOM`` AG-UI event that announces the chat/session ids the
#: backend resolved (or created) for this run. Emitted **after** ``RUN_STARTED``
#: so the AG-UI client's "first event must be RUN_STARTED" check still passes;
#: the frontend stashes it and applies it on ``RUN_FINISHED``.
CHAT_SESSION_EVENT = "chat_session"

class ChatMessageRequest(BaseModel):
    """Only the fields `_get_or_create_chat` needs — the message text plus the
    optional chat-creation knobs. On the wire these ride in the `RunAgentInput`
    body's `forwardedProps` (see `send_message`); the body shape is otherwise
    identical to `/agents/{agent_id}`."""

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


def _latest_user_text(input_data: RunAgentInput) -> str:
    for message in reversed(input_data.messages or []):
        if getattr(message, "role", None) == "user":
            content = message.content
            return content if isinstance(content, str) else str(content)
    raise HTTPException(status_code=422, detail="No user message in the run input.")


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
    input_data: RunAgentInput, request: Request
) -> StreamingResponse:
    """Body is a `RunAgentInput` (same shape as `/agents/{agent_id}`). The
    chat/session identity + creation knobs (`chat_id`, `session_id`,
    `project_id`, `provider`, `model`, `chat_title`) ride in `forwardedProps`;
    the user turn is the last `user` message in `input_data.messages`."""
    storage = _storage(request)
    fp = input_data.forwarded_props or {}
    body = ChatMessageRequest(
        message=_latest_user_text(input_data),
        chat_id=fp.get("chat_id"),
        session_id=fp.get("session_id"),
        project_id=fp.get("project_id"),
        provider=fp.get("provider"),
        model=fp.get("model"),
        chat_title=fp.get("chat_title"),
    )
    chat = await _get_or_create_chat(storage, body)
    session = await _get_or_create_session(storage, chat.chat_id, body.session_id)

    checkpoint_path = storage.session_dir(session.session_id) / CHECKPOINT_FILENAME
    chat_model = build_chat_model({"provider": chat.provider, "model": chat.model})
    # Ask the provider to report token usage on the final streamed chunk so
    # `on_finish` can fold it into usage.json (ChatOpenAI/OpenRouter supports
    # this; guarded so a model without the field doesn't blow up).
    if "stream_usage" in type(chat_model).model_fields:
        chat_model.stream_usage = True

    middleware = []
    if settings.rag_injection_enabled:
        middleware.append(RagInjectionMiddleware())

    encoder = EventEncoder(accept=request.headers.get("accept"))

    logger.info(
        "chat: send_message chat={} session={} model={}/{} rag_injection={}",
        chat.chat_id,
        session.session_id,
        chat.provider,
        chat.model,
        settings.rag_injection_enabled,
    )
    logger.debug(
        "chat: user message ({} chars): {!r}", len(body.message), body.message[:200]
    )

    async def _record_usage(ctx: AguiRunContext) -> None:
        reply = ctx.final_message or AIMessage(content="")
        existing = await storage.read_usage(session.session_id)
        updated = accumulate_usage(existing, reply)
        await storage.write_usage(session.session_id, updated)
        logger.debug(
            "chat: session {} usage totals now {}",
            session.session_id,
            updated.get("totals"),
        )

    async def event_generator():
        try:
            async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
                graph = build_chat_graph(
                    chat_model,
                    system_prompt=load_prompt("chat", "main"),
                    checkpointer=checkpointer,
                    middleware=middleware,
                )
                async for event in run_graph_as_agui(
                    graph,
                    input_data,
                    thread_id=session.session_id,
                    on_finish=_record_usage,
                ):
                    yield encoder.encode(event)
                    # Announce the resolved ids right after RUN_STARTED — the
                    # client needs them to adopt a chat/session created on this
                    # first message (see `use-chat-stream.ts`).
                    if getattr(event, "type", None) == EventType.RUN_STARTED:
                        yield encoder.encode(
                            CustomEvent(
                                type=EventType.CUSTOM,
                                name=CHAT_SESSION_EVENT,
                                value={
                                    "chat_id": chat.chat_id,
                                    "session_id": session.session_id,
                                },
                            )
                        )
        except Exception as exc:  # noqa: BLE001 - headers already sent; surface as RUN_ERROR
            logger.exception("chat: stream for session {} failed", session.session_id)
            yield encoder.encode(
                RunErrorEvent(
                    type=EventType.RUN_ERROR, message=f"{type(exc).__name__}: {exc}"
                )
            )

    return StreamingResponse(event_generator(), media_type=encoder.get_content_type())
