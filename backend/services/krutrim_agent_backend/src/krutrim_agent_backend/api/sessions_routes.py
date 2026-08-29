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
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from krutrim_agent_management.base import Storage
from krutrim_agent_management.models import SessionInfo, SharingScope
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from loguru import logger
from pydantic import BaseModel

from krutrim_agent_backend.api.chat_routes import CHECKPOINT_FILENAME
from krutrim_agent_backend.api.schemas import ChatApiMessage
from krutrim_agent_backend.celery_client import celery_client
from krutrim_agent_backend.chat.graph import build_chat_graph
from krutrim_agent_backend.chat.messages import to_display_messages

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

_MAX_RAG_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB — binary uploads have no natural
# bound the way a JSON text body does.


class RagTextRequest(BaseModel):
    text: str
    title: str | None = None

class SessionSandboxPolicyUpdate(BaseModel):
    sharing: SharingScope | None = None
    attached_to_session_id: str | None = None
    linked_session_ids: list[str] | None = None

class EmbedRequest(BaseModel):
    source_paths: list[str] | None = None

class UpdateSessionRequest(BaseModel):
    display_name: str | None = None


class SessionDeletedResponse(BaseModel):
    status: str
    session_id: str


class SessionMessagesResponse(BaseModel):
    messages: list[ChatApiMessage]


class EmbedResponse(BaseModel):
    status: str
    task_id: str
    job_id: str
    file_count: int


class RagTextResponse(BaseModel):
    status: str
    task_id: str
    job_id: str
    document_id: str


class RagDocument(BaseModel):
    document_id: str
    title: str
    filename: str | None = None
    source_path: str
    kind: str  # "file" | "text"
    created_at: str


class RagDocumentsResponse(BaseModel):
    documents: list[RagDocument]


class RagDocumentDeletedResponse(BaseModel):
    status: str
    document_id: str


def _storage(request: Request) -> Storage:
    return request.app.state.storage


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
async def get_session(session_id: str, request: Request) -> SessionInfo:
    return (await _get_session(_storage(request), session_id)).model_dump()




@router.put("/{session_id}")
async def update_session(
    session_id: str, body: UpdateSessionRequest, request: Request
) -> SessionInfo:
    storage = _storage(request)
    await _get_session(storage, session_id)
    updated = await storage.update_session(session_id, display_name=body.display_name)
    return updated.model_dump()


@router.delete("/{session_id}")
async def delete_session(session_id: str, request: Request) -> SessionDeletedResponse:
    storage = _storage(request)
    await _get_session(storage, session_id)
    logger.info("sessions: deleting session {} (cascades vector index)", session_id)
    await storage.delete_session(session_id)
    return {"status": "deleted", "session_id": session_id}


@router.get("/{session_id}/messages")
async def get_session_messages(session_id: str, request: Request) -> SessionMessagesResponse:
    """Reads history straight out of the session's LangGraph checkpoint
    (`langgraph_checkpoint.sqlite`), keyed by `thread_id == session_id`, and
    reduces it to the user-visible turns (see `to_display_messages`). Returns
    `[]` if the session has never been messaged (no checkpoint file yet).

    Works for both `Chat`-owned sessions (checkpoint written by `POST /api/chat`)
    and `Agent`-owned ones (in-sandbox run's checkpoint, synced back to the
    session dir by `SandboxRegistry.release` -> `import_scope`)."""
    storage = _storage(request)
    await _get_session(storage, session_id)

    checkpoint_path = storage.session_dir(session_id) / CHECKPOINT_FILENAME
    if not checkpoint_path.exists():
        return {"messages": []}

    # `build_chat_graph(object(), ...)` compiles fine and is only used here to
    # resolve `aget_state` — the model is never invoked on a read.
    config = {"configurable": {"thread_id": session_id}}
    async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as checkpointer:
        graph = build_chat_graph(object(), checkpointer=checkpointer)
        state = await graph.aget_state(config)
    lc_messages = (state.values or {}).get("messages", []) if state else []
    display = to_display_messages(lc_messages)
    logger.debug(
        "sessions: {} history has {} checkpoint message(s), {} visible",
        session_id,
        len(lc_messages),
        len(display),
    )
    return {"messages": display}




@router.put("/{session_id}/sandbox-policy")
async def update_session_sandbox_policy(
    session_id: str, body: SessionSandboxPolicyUpdate, request: Request
) -> SessionInfo:
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





@router.post("/{session_id}/embed")
async def trigger_embedding(
    session_id: str, body: EmbedRequest, request: Request
) -> EmbedResponse:
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
    logger.info(
        "rag: queued embedding precompute for session {} ({} file(s), task={}, job={})",
        session_id,
        len(source_paths),
        async_result.id,
        job_id,
    )
    return {
        "status": "queued",
        "task_id": async_result.id,
        "job_id": job_id,
        "file_count": len(source_paths),
    }





@router.post("/{session_id}/rag/text")
async def submit_rag_text(
    session_id: str, body: RagTextRequest, request: Request
) -> RagTextResponse:
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
    logger.info(
        "rag: ingesting pasted text for session {} ({} chars) as document {} ({!r})",
        session_id,
        len(body.text),
        document_id,
        title,
    )
    async_result = celery_client.send_task(
        "krutrim_agent_celery.process_rag_document",
        args=[session_id, document_id, source_path, title],
    )
    # Deterministic and per-document (unlike /embed's single per-session job
    # id) — a session can ingest multiple RAG documents over time, each with
    # its own progress stream at GET /api/status/jobs/{job_id}.
    job_id = f"{session_id}:rag:{document_id}"
    logger.debug("rag: queued process_rag_document task={} job={}", async_result.id, job_id)
    await storage.append_rag_manifest(
        session_id,
        {
            "document_id": document_id,
            "title": title,
            "filename": None,
            "source_path": source_path,
            "kind": "text",
            "created_at": _now_iso(),
        },
    )
    return {
        "status": "queued",
        "task_id": async_result.id,
        "job_id": job_id,
        "document_id": document_id,
    }


@router.post("/{session_id}/rag/file")
async def submit_rag_file(
    session_id: str,
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(None),
) -> RagTextResponse:
    """Real (binary-capable) document upload — the counterpart to
    `/rag/text` for files that aren't pasted text: PDF, DOCX, and anything
    else `krutrim_agent_doc`'s parser registry supports. The file's
    extension is preserved (unlike `/rag/text`'s hardcoded `.txt`) so
    `process_rag_document`'s Celery task can dispatch to the right parser
    by suffix. Dispatches the same task and job-id scheme as `/rag/text` —
    ingestion is unified once content is on disk."""
    storage = _storage(request)
    await _get_session(storage, session_id)

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > _MAX_RAG_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {_MAX_RAG_UPLOAD_BYTES // (1024 * 1024)}MB upload limit.",
        )

    document_id = uuid.uuid4().hex
    suffix = Path(file.filename or "").suffix or ".txt"
    source_path = f"_rag_uploads/{document_id}{suffix}"
    await storage.sync_workspace_from_container(session_id, [(source_path, content)])

    title = title or file.filename or document_id
    logger.info(
        "rag: ingesting uploaded file {!r} for session {} ({} bytes, suffix={}) as document {}",
        file.filename,
        session_id,
        len(content),
        suffix,
        document_id,
    )
    async_result = celery_client.send_task(
        "krutrim_agent_celery.process_rag_document",
        args=[session_id, document_id, source_path, title],
    )
    job_id = f"{session_id}:rag:{document_id}"
    logger.debug("rag: queued process_rag_document task={} job={}", async_result.id, job_id)
    await storage.append_rag_manifest(
        session_id,
        {
            "document_id": document_id,
            "title": title,
            "filename": file.filename,
            "source_path": source_path,
            "kind": "file",
            "created_at": _now_iso(),
        },
    )
    return {
        "status": "queued",
        "task_id": async_result.id,
        "job_id": job_id,
        "document_id": document_id,
    }


@router.get("/{session_id}/rag/documents")
async def list_rag_documents(session_id: str, request: Request) -> RagDocumentsResponse:
    """Every document ingested into this session's RAG index (newest last),
    read from `sessions/{id}/rag/manifest.json`. Backs the composer's
    attachment bar so uploads stay visible after the first message / a reload."""
    storage = _storage(request)
    await _get_session(storage, session_id)
    return {"documents": await storage.read_rag_manifest(session_id)}


@router.delete("/{session_id}/rag/documents/{document_id}")
async def delete_rag_document(
    session_id: str, document_id: str, request: Request
) -> RagDocumentDeletedResponse:
    """Drops the document from the session manifest so it no longer shows in
    the attachment bar. The already-indexed vectors are left in place — they
    stop being addressable from the UI and are swept when the session is
    deleted (`krutrim_agent_rag.cleanup.drop_session_vectors`). Idempotent."""
    storage = _storage(request)
    await _get_session(storage, session_id)
    await storage.remove_rag_manifest_entry(session_id, document_id)
    logger.info("rag: removed document {} from session {} manifest", document_id, session_id)
    return {"status": "deleted", "document_id": document_id}
