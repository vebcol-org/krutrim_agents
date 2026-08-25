"""Chat CRUD — a lightweight, non-agentic chat thread container.

Unlike `Agent`, a `Chat`'s `project_id` is optional: a standalone chat
(`project_id=None`) behaves exactly like today's plain `POST /api/chat`
flow, with no meaningful sandbox policy (nothing to share memory with).
Moving a chat in/out of a project (`POST .../move`) is a first-class,
explicit action — unlike `Agent`, which can't move projects yet.

`GET /api/chats?project_id=<id>` lists that project's chats;
`GET /api/chats` (no `project_id`) lists standalone chats — there is
currently no single call that lists every chat regardless of project (list
project-by-project, or list standalone, matching `Storage.list_chats`).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from krutrim_agent_management.base import Storage
from krutrim_agent_management.models import Chat, SessionInfo, SharingScope
from pydantic import BaseModel

from krutrim_agent_backend.chat.catalog import DEFAULT_CHAT_MODEL, is_known_chat_model

router = APIRouter(prefix="/api/chats", tags=["chats"])


def _storage(request: Request) -> Storage:
    return request.app.state.storage


class CreateChatRequest(BaseModel):
    display_name: str
    project_id: str | None = None
    provider: str | None = None
    model: str | None = None


class ChatDeletedResponse(BaseModel):
    status: str
    chat_id: str


@router.post("")
async def create_chat(body: CreateChatRequest, request: Request) -> Chat:
    storage = _storage(request)
    provider = body.provider or DEFAULT_CHAT_MODEL.provider
    model = body.model or DEFAULT_CHAT_MODEL.model
    if not is_known_chat_model(provider, model):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown chat model {provider}/{model}. See GET /api/models for supported models.",
        )
    try:
        chat = await storage.create_chat(
            body.display_name, provider, model, project_id=body.project_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return chat.model_dump()


@router.get("")
async def list_chats(request: Request, project_id: str | None = None) -> list[Chat]:
    return [
        chat.model_dump() for chat in await _storage(request).list_chats(project_id)
    ]


@router.get("/{chat_id}")
async def get_chat(chat_id: str, request: Request) -> Chat:
    try:
        return (await _storage(request).get_chat(chat_id)).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class UpdateChatRequest(BaseModel):
    display_name: str | None = None


@router.put("/{chat_id}")
async def update_chat(chat_id: str, body: UpdateChatRequest, request: Request) -> Chat:
    try:
        updated = await _storage(request).update_chat(
            chat_id, display_name=body.display_name
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return updated.model_dump()


@router.delete("/{chat_id}")
async def delete_chat(chat_id: str, request: Request) -> ChatDeletedResponse:
    try:
        await _storage(request).delete_chat(chat_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "deleted", "chat_id": chat_id}


class MoveChatRequest(BaseModel):
    project_id: str | None
    """The project to move this chat into, or `None` to detach it back to standalone."""


@router.post("/{chat_id}/move")
async def move_chat(chat_id: str, body: MoveChatRequest, request: Request) -> Chat:
    try:
        updated = await _storage(request).move_chat(chat_id, project_id=body.project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return updated.model_dump()


class ChatSandboxPolicyUpdate(BaseModel):
    """Unset (`None`) fields are left unchanged. Stored regardless of whether
    `project_id` is currently set, but only takes effect once it is — see
    `Chat`'s docstring."""

    sharing: SharingScope | None = None
    idle_timeout_seconds: int | None = None
    resource_overrides: dict[str, int] | None = None


@router.put("/{chat_id}/sandbox-policy")
async def update_chat_sandbox_policy(
    chat_id: str, body: ChatSandboxPolicyUpdate, request: Request
) -> Chat:
    try:
        updated = await _storage(request).update_chat_sandbox_policy(
            chat_id,
            sharing=body.sharing,
            idle_timeout_seconds=body.idle_timeout_seconds,
            resource_overrides=body.resource_overrides,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return updated.model_dump()


# -- sessions (owned by this chat) ---------------------------------------
# Individual-session operations (get/rename/delete/messages/policy/embed)
# live in `sessions_routes.py`, addressed by session_id alone.


@router.post("/{chat_id}/sessions")
async def create_chat_session(chat_id: str, request: Request) -> SessionInfo:
    storage = _storage(request)
    try:
        await storage.get_chat(chat_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session = await storage.create_session("chat", chat_id)
    return session.model_dump()


@router.get("/{chat_id}/sessions")
async def list_chat_sessions(chat_id: str, request: Request) -> list[SessionInfo]:
    storage = _storage(request)
    try:
        await storage.get_chat(chat_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [
        session.model_dump() for session in await storage.list_sessions("chat", chat_id)
    ]
