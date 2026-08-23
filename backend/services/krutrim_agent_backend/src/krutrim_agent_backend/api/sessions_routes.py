"""Session operations keyed by `session_id` alone (sessions are globally
unique — see `krutrim_agent_management.base.Storage` — so no owner/project prefix is
needed to address one). Creating and listing sessions is owner-scoped
instead, living next to their owner: `POST/GET /api/projects/{project_id}/agents/{agent_id}/sessions`
(`agent_instances_routes.py`) and `POST/GET /api/chats/{chat_id}/sessions`
(`chats_routes.py`).

Also owns the session-level sandbox sharing policy (`PUT .../sandbox-policy`)
— overriding the owner's default sharing scope, explicit container reuse
(`attached_to_session_id`), and cross-agent-messaging peer links
(`linked_session_ids`). See `sandbox/registry.py::resolve_owner_id` for how
`attached_to_session_id` actually takes effect, and the read-only message
history endpoint the frontend uses to reload a past conversation.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from krutrim_agent_management.base import Storage
from krutrim_agent_management.models import SessionInfo, SharingScope
from pydantic import BaseModel

from krutrim_agent_backend.celery_client import celery_client

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _storage(request: Request) -> Storage:
    return request.app.state.storage


async def _get_session(storage: Storage, session_id: str) -> SessionInfo:
    try:
        return await storage.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _list_project_sessions(
    storage: Storage, project_id: str
) -> list[SessionInfo]:
    """Every session in this project, across every `Agent` and `Chat` — used
    only for the attach-chain validation below, not exposed as its own route."""
    sessions: list[SessionInfo] = []
    for agent in await storage.list_agents(project_id):
        sessions.extend(await storage.list_sessions("agent", agent.agent_id))
    for chat in await storage.list_chats(project_id):
        sessions.extend(await storage.list_sessions("chat", chat.chat_id))
    return sessions


@router.get("/{session_id}")
async def get_session(session_id: str, request: Request) -> dict:
    return (await _get_session(_storage(request), session_id)).model_dump()


class UpdateSessionRequest(BaseModel):
    display_name: str | None = None


@router.put("/{session_id}")
async def update_session(
    session_id: str, body: UpdateSessionRequest, request: Request
) -> dict:
    storage = _storage(request)
    await _get_session(storage, session_id)
    updated = await storage.update_session(session_id, display_name=body.display_name)
    return updated.model_dump()


@router.delete("/{session_id}")
async def delete_session(session_id: str, request: Request) -> dict:
    storage = _storage(request)
    await _get_session(storage, session_id)
    await storage.delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}


@router.get("/{session_id}/messages")
async def get_session_messages(session_id: str, request: Request) -> dict:
    storage = _storage(request)
    await _get_session(storage, session_id)
    checkpoint = await storage.read_checkpoint(session_id)
    return {"messages": (checkpoint or {}).get("messages", [])}


class SessionSandboxPolicyUpdate(BaseModel):
    """Unset (`None`) fields are left unchanged. There's currently no way to
    clear an existing `attached_to_session_id` back to "not attached" through
    this route — a real gap, not silently worked around; see
    `Storage.update_session_sandbox_policy`'s own docstring."""

    sharing: SharingScope | None = None
    attached_to_session_id: str | None = None
    linked_session_ids: list[str] | None = None


@router.put("/{session_id}/sandbox-policy")
async def update_session_sandbox_policy(
    session_id: str, body: SessionSandboxPolicyUpdate, request: Request
) -> dict:
    storage = _storage(request)
    current = await _get_session(storage, session_id)

    if body.attached_to_session_id is not None:
        if body.attached_to_session_id == session_id:
            raise HTTPException(
                status_code=400, detail="A session cannot attach to itself."
            )
        target = await _get_session(storage, body.attached_to_session_id)
        if current.project_id is None or target.project_id != current.project_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot attach to a session outside this session's project.",
            )
        if target.attached_to_session_id is not None:
            raise HTTPException(
                status_code=400,
                detail="Cannot attach to a session that is itself attached to another session "
                "(no chained attaches).",
            )
        # Symmetric check: this session can't become an attacher itself if
        # someone else already depends on *it* as their attach target — same
        # "no chaining" invariant, guarded from the other direction.
        dependents = [
            s.session_id
            for s in await _list_project_sessions(storage, current.project_id)
            if s.attached_to_session_id == session_id
        ]
        if dependents:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot attach: session(s) {dependents} are already attached to this one.",
            )

    updated = await storage.update_session_sandbox_policy(
        session_id,
        sharing=body.sharing,
        attached_to_session_id=body.attached_to_session_id,
        linked_session_ids=body.linked_session_ids,
    )
    return updated.model_dump()


class EmbedRequest(BaseModel):
    source_paths: list[str] | None = None
    """Workspace-mirror-relative paths to embed (see `Storage.read_workspace_files`).
    If omitted, every file currently in the session's persisted workspace
    mirror is used — note this is the *mirror*, synced on teardown; if the
    session's container is still running with unsynced changes, those
    won't be picked up until it's torn down or explicitly re-synced."""


@router.post("/{session_id}/embed")
async def trigger_embedding(
    session_id: str, body: EmbedRequest, request: Request
) -> dict:
    storage = _storage(request)
    await _get_session(storage, session_id)

    source_paths = body.source_paths
    if source_paths is None:
        source_paths = await storage.read_workspace_files(session_id)

    async_result = celery_client.send_task(
        "krutrim_agent_celery.precompute_embeddings", args=[session_id, source_paths]
    )
    # Deterministic, matching krutrim_agent_celery.tasks.precompute_embeddings' own
    # job_id construction — lets the caller subscribe to
    # GET /api/status/jobs/{job_id} immediately, without waiting on Celery's
    # result backend to learn it.
    job_id = f"{session_id}:embed"
    return {
        "status": "queued",
        "task_id": async_result.id,
        "job_id": job_id,
        "file_count": len(source_paths),
    }


class RagTextRequest(BaseModel):
    text: str
    """Raw text to ingest — pasted directly, or a `.txt` file's contents read
    client-side (v1 RAG ingestion is text-only; there's no separate binary
    file-upload endpoint). Empty/whitespace-only text is rejected."""

    title: str | None = None
    """Human-readable label for citations (e.g. the original filename).
    Defaults to the document id if omitted."""


@router.post("/{session_id}/rag/text")
async def submit_rag_text(
    session_id: str, body: RagTextRequest, request: Request
) -> dict:
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="text must not be empty.")

    storage = _storage(request)
    await _get_session(storage, session_id)

    document_id = uuid.uuid4().hex
    source_path = f"_rag_uploads/{document_id}.txt"
    await storage.sync_workspace_from_container(
        session_id, [(source_path, body.text.encode("utf-8"))]
    )

    title = body.title or document_id
    async_result = celery_client.send_task(
        "krutrim_agent_celery.process_rag_document",
        args=[session_id, document_id, source_path, title],
    )
    # Deterministic and per-document (unlike /embed's single per-session job
    # id) — a session can ingest multiple RAG documents over time, each with
    # its own progress stream at GET /api/status/jobs/{job_id}.
    job_id = f"{session_id}:rag:{document_id}"
    return {
        "status": "queued",
        "task_id": async_result.id,
        "job_id": job_id,
        "document_id": document_id,
    }
