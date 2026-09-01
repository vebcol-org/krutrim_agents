"""Response models shared across more than one route file — kept here rather
than duplicated locally. Route-specific request/response models stay local
to their own route file (see e.g. `projects_routes.py`'s `CreateProjectRequest`).

Named to match `libs/shared-types/src/lib/shared-types.ts`, which already
hand-mirrors these backend response shapes for the frontend.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ToolCallView(BaseModel):
    """One tool invocation from an assistant turn, reconstructed from the
    checkpoint so a reloaded conversation can redraw the work-log panel."""

    id: str
    name: str
    args: str
    """The call arguments, JSON-encoded (sorted keys)."""
    result: str | None = None
    """The tool's output — `None` if the call never returned (run cut off)."""


class ChatApiMessage(BaseModel):
    """One turn's worth of chat history — matches `shared-types.ts`'s
    `ChatApiMessage`. `GET /api/sessions/{id}/messages` returns a list of
    these; `POST /api/chat` streams the live turn as AG-UI events instead.

    The route serializes with ``response_model_exclude_defaults=True``, so a
    plain text turn is just ``{role, content}`` and the extra fields appear
    only when they carry something."""

    role: Literal["user", "assistant"]
    content: str
    interrupted: bool = False
    """`True` only for an assistant turn that was stopped mid-generation — the
    frontend shows its text as a work-log entry, not a finished report."""
    tool_calls: list[ToolCallView] = []
    """Tools this assistant turn invoked, with their results folded in — lets a
    reload rebuild the activity trace the live stream showed."""


class ErrorResponse(BaseModel):
    """The uniform `{"detail": ...}` shape every handler in
    `error_handlers.py` produces. Defined for reuse but not yet wired into
    any route's `responses=` — see that module's docstring."""

    detail: str
