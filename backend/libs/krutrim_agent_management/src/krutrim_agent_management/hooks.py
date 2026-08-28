"""Lightweight extension points fired from inside `Storage` operations.

Today there is exactly one: `session_delete` hooks, run by
`LocalStorage.delete_session` (and therefore by every cascade —
`delete_chat`, `delete_project`) just before a session's row and directory
are removed. `krutrim_agent_rag.cleanup` registers a hook here to drop the
session's vector index (a Qdrant collection, or the on-disk FAISS files)
when its chat is deleted.

The indirection exists so `krutrim_agent_management` never has to import
`krutrim_agent_rag` (which depends on `krutrim_agent_management` — importing
back the other way would be circular). A process that wants the RAG cleanup
imports `krutrim_agent_rag.cleanup` once at startup; a process that never
touches RAG (e.g. the Celery reaper) simply has no hook registered and
`run_session_delete_hooks` is a no-op.
"""

from __future__ import annotations

from collections.abc import Callable

from loguru import logger

SessionDeleteHook = Callable[[str], None]

_session_delete_hooks: list[SessionDeleteHook] = []


def register_session_delete_hook(hook: SessionDeleteHook) -> None:
    """Idempotent — registering the same callable twice is ignored."""
    if hook not in _session_delete_hooks:
        _session_delete_hooks.append(hook)
        logger.debug("registered session-delete hook: {}", getattr(hook, "__name__", hook))


def run_session_delete_hooks(session_id: str) -> None:
    """Best-effort: a failing hook is logged and skipped, never allowed to
    block the actual session deletion."""
    for hook in _session_delete_hooks:
        name = getattr(hook, "__name__", repr(hook))
        try:
            logger.debug("running session-delete hook {} for session {}", name, session_id)
            hook(session_id)
        except Exception as exc:  # noqa: BLE001 - cleanup must not break deletion
            logger.warning(
                "session-delete hook {} failed for session {}: {}", name, session_id, exc
            )
