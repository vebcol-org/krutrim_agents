"""Tests for the sandbox-policy PUT routes: project-level
sharing/idle-timeout/resource-override updates, and session-level sharing
override + explicit container-reuse (`attached_to_session_id`) with its
no-chained-attaches validation.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from krutrim_agent_backend.api.agent_instances_routes import (
    router as agent_instances_router,
)
from krutrim_agent_backend.api.projects_routes import router as projects_router
from krutrim_agent_backend.api.sessions_routes import router as sessions_router
from krutrim_agent_management import LocalStorage


@pytest.fixture
def client(tmp_path) -> TestClient:
    app = FastAPI()
    app.state.storage = LocalStorage(tmp_path)
    app.include_router(projects_router)
    app.include_router(agent_instances_router)
    app.include_router(sessions_router)
    return TestClient(app)


def _create_project(client: TestClient) -> str:
    storage = client.app.state.storage

    async def _create():
        project = await storage.create_project("P")
        return project.project_id

    return asyncio.run(_create())


def _create_session(client: TestClient, project_id: str) -> str:
    storage = client.app.state.storage

    async def _create():
        agent = await storage.create_agent(project_id, "research", "Test Agent")
        session = await storage.create_session("agent", agent.agent_id)
        return session.session_id

    return asyncio.run(_create())


# -- project-level sandbox policy ---------------------------------------------


def test_update_project_sandbox_policy(client):
    project_id = _create_project(client)

    response = client.put(
        f"/api/projects/{project_id}/sandbox-policy", json={"sharing": "project-shared"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sandbox_sharing"] == "project-shared"


def test_update_project_sandbox_policy_unknown_project(client):
    response = client.put(
        "/api/projects/nope/sandbox-policy", json={"sharing": "isolated"}
    )
    assert response.status_code == 404


def test_update_project_sandbox_policy_partial_update_preserves_other_fields(client):
    project_id = _create_project(client)
    client.put(
        f"/api/projects/{project_id}/sandbox-policy", json={"sharing": "project-shared"}
    )

    response = client.put(
        f"/api/projects/{project_id}/sandbox-policy", json={"idle_timeout_seconds": 120}
    )

    body = response.json()
    assert body["sandbox_sharing"] == "project-shared"  # untouched by the second call
    assert body["sandbox_idle_timeout_seconds"] == 120


# -- session-level sandbox policy ---------------------------------------------


def test_update_session_sandbox_policy_sets_sharing(client):
    project_id = _create_project(client)
    session_id = _create_session(client, project_id)

    response = client.put(
        f"/api/sessions/{session_id}/sandbox-policy", json={"sharing": "session-shared"}
    )

    assert response.status_code == 200
    assert response.json()["sandbox_sharing"] == "session-shared"


def test_attach_to_another_session_succeeds(client):
    project_id = _create_project(client)
    session_a = _create_session(client, project_id)
    session_b = _create_session(client, project_id)

    response = client.put(
        f"/api/sessions/{session_b}/sandbox-policy",
        json={"attached_to_session_id": session_a},
    )

    assert response.status_code == 200
    assert response.json()["attached_to_session_id"] == session_a


def test_attach_to_self_rejected(client):
    project_id = _create_project(client)
    session_id = _create_session(client, project_id)

    response = client.put(
        f"/api/sessions/{session_id}/sandbox-policy",
        json={"attached_to_session_id": session_id},
    )

    assert response.status_code == 400


def test_attach_to_unknown_session_returns_404(client):
    project_id = _create_project(client)
    session_id = _create_session(client, project_id)

    response = client.put(
        f"/api/sessions/{session_id}/sandbox-policy",
        json={"attached_to_session_id": "nope"},
    )

    assert response.status_code == 404


def test_chained_attach_rejected(client):
    project_id = _create_project(client)
    session_a = _create_session(client, project_id)
    session_b = _create_session(client, project_id)
    session_c = _create_session(client, project_id)

    # B attaches to A.
    r1 = client.put(
        f"/api/sessions/{session_b}/sandbox-policy",
        json={"attached_to_session_id": session_a},
    )
    assert r1.status_code == 200

    # C tries to attach to B (already itself attached) — must be rejected.
    r2 = client.put(
        f"/api/sessions/{session_c}/sandbox-policy",
        json={"attached_to_session_id": session_b},
    )
    assert r2.status_code == 400


def test_cannot_attach_when_others_already_depend_on_this_session(client):
    project_id = _create_project(client)
    session_a = _create_session(client, project_id)
    session_b = _create_session(client, project_id)
    session_c = _create_session(client, project_id)

    # B attaches to A, so A now has a dependent.
    r1 = client.put(
        f"/api/sessions/{session_b}/sandbox-policy",
        json={"attached_to_session_id": session_a},
    )
    assert r1.status_code == 200

    # A tries to attach to C — must be rejected, since B depends on A staying a root.
    r2 = client.put(
        f"/api/sessions/{session_a}/sandbox-policy",
        json={"attached_to_session_id": session_c},
    )
    assert r2.status_code == 400


def test_attach_across_projects_rejected(client):
    project_a = _create_project(client)
    project_b = _create_project(client)
    session_a = _create_session(client, project_a)
    session_b = _create_session(client, project_b)

    response = client.put(
        f"/api/sessions/{session_a}/sandbox-policy",
        json={"attached_to_session_id": session_b},
    )

    assert response.status_code == 400


def test_update_session_sandbox_policy_unknown_session_returns_404(client):
    response = client.put(
        "/api/sessions/nope/sandbox-policy", json={"sharing": "isolated"}
    )
    assert response.status_code == 404
