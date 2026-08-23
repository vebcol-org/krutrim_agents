from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from krutrim_agent_extensions.contracts import NoOpAgentVisibilityPolicy, NoOpAuditSink
from krutrim_agent_extensions.middleware import ExtensionMiddleware
from krutrim_agent_extensions.registry import register_hook


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(ExtensionMiddleware)

    @app.get("/probe")
    def probe(request: Request) -> dict:
        visible = request.state.visible_agent_keys
        return {
            "principal_id": request.state.principal.id,
            "visible_agent_keys": sorted(visible) if visible is not None else None,
        }

    return app


def test_extension_middleware_default_is_pure_noop_passthrough():
    """Community ships all-no-op hooks — every request resolves to the
    anonymous principal, with no agent-visibility restriction, matching
    today's behavior exactly (no auth, single-user)."""
    client = TestClient(_build_app())
    response = client.get("/probe")
    assert response.status_code == 200
    body = response.json()
    assert body["principal_id"] == "anonymous"
    assert body["visible_agent_keys"] is None


def test_extension_middleware_uses_a_registered_visibility_policy():
    class RestrictingVisibilityPolicy:
        def visible_agent_keys(self, principal):
            return {"research"}

    register_hook("AgentVisibilityPolicy", RestrictingVisibilityPolicy())
    try:
        client = TestClient(_build_app())
        response = client.get("/probe")
        assert response.json()["visible_agent_keys"] == ["research"]
    finally:
        register_hook("AgentVisibilityPolicy", NoOpAgentVisibilityPolicy())


def test_extension_middleware_fires_audit_sink_after_the_response():
    events = []

    class RecordingAuditSink:
        async def record(self, event):
            events.append(event)

    register_hook("AuditSink", RecordingAuditSink())
    try:
        client = TestClient(_build_app())
        client.get("/probe")
        assert len(events) == 1
        assert events[0].method == "GET"
        assert events[0].path == "/probe"
        assert events[0].status_code == 200
        assert events[0].principal.id == "anonymous"
    finally:
        register_hook("AuditSink", NoOpAuditSink())
