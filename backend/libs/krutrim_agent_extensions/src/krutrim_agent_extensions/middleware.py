"""ASGI middleware that resolves the active extension hooks for every
request. Community ships with all-no-op hooks, so this is a pure
pass-through — it adds `request.state.principal` /
`request.state.visible_agent_keys` without changing any response, and every
route that wants edition-aware behavior (`agents_routes.py`, `agent_run.py`)
reads those instead of importing `krutrim_agent_extensions` hooks directly.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from krutrim_agent_extensions.contracts import AuditEvent
from krutrim_agent_extensions.registry import (
    get_agent_visibility_policy,
    get_audit_sink,
    get_authenticator,
)


class ExtensionMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        authenticator = get_authenticator()
        visibility_policy = get_agent_visibility_policy()
        audit_sink = get_audit_sink()

        principal = await authenticator.authenticate(request)
        request.state.principal = principal
        request.state.visible_agent_keys = visibility_policy.visible_agent_keys(
            principal
        )

        response = await call_next(request)

        await audit_sink.record(
            AuditEvent(
                principal=principal,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
            )
        )
        return response
