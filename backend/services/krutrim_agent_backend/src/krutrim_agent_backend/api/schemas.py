"""Response models shared across more than one route file — kept here rather
than duplicated locally. Route-specific request/response models stay local
to their own route file (see e.g. `projects_routes.py`'s `CreateProjectRequest`).

Named to match `libs/shared-types/src/lib/shared-types.ts`, which already
hand-mirrors these backend response shapes for the frontend.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ChatApiMessage(BaseModel):
    """One turn's worth of chat history — matches `shared-types.ts`'s
    `ChatApiMessage` and `chat/messages.py::from_lc_messages`'s output
    exactly. Used both by `POST /api/chat`'s reply and
    `GET /api/sessions/{id}/messages`'s history."""

    role: Literal["user", "assistant"]
    content: str


class ErrorResponse(BaseModel):
    """The uniform `{"detail": ...}` shape every handler in
    `error_handlers.py` produces. Defined for reuse but not yet wired into
    any route's `responses=` — see that module's docstring."""

    detail: str
