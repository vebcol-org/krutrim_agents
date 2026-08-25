"""Agent instance CRUD, nested under a project.

Not to be confused with `agents_routes.py` (`GET /api/agents`, which lists
*registered profiles* — `research`/`trading`/`sales`, code-defined plugin
types). This file manages *instances* of those profiles: a project can hold
several agents sharing the same `agent_key` (e.g. two `research`-profile
agents named "Company Business Analysis" and "Company Finance Analysis"),
distinguished by `display_name` and each with their own sessions and sandbox
policy. Moving an agent to a different project isn't supported yet.

Also owns the agent-level sandbox sharing policy (`PUT .../sandbox-policy`)
— overrides the project's default; in particular, governs whether this
agent's sessions are reachable by sibling agents via `message_agent` (see
`agents/cross_agent.py`).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from krutrim_agent_management.base import Storage
from krutrim_agent_management.models import Agent, SessionInfo, SharingScope
from krutrim_agents_core.registry import get_profile
from pydantic import BaseModel

router = APIRouter(prefix="/api/projects/{project_id}/agents", tags=["agents"])


def _storage(request: Request) -> Storage:
    return request.app.state.storage


async def _get_agent_in_project(
    storage: Storage, project_id: str, agent_id: str
) -> Agent:
    try:
        agent = await storage.get_agent(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if agent.project_id != project_id:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown agent {agent_id!r} in project {project_id!r}",
        )
    return agent


class CreateAgentRequest(BaseModel):
    agent_key: str
    """Which registered profile this instance runs — see `GET /api/agents` for valid values."""
    display_name: str


class AgentDeletedResponse(BaseModel):
    status: str
    project_id: str
    agent_id: str


@router.post("")
async def create_agent(
    project_id: str, body: CreateAgentRequest, request: Request
) -> Agent:
    storage = _storage(request)
    try:
        get_profile(body.agent_key)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        agent = await storage.create_agent(
            project_id, body.agent_key, body.display_name
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return agent.model_dump()


@router.get("")
async def list_agents(project_id: str, request: Request) -> list[Agent]:
    storage = _storage(request)
    try:
        await storage.get_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [agent.model_dump() for agent in await storage.list_agents(project_id)]


@router.get("/{agent_id}")
async def get_agent(project_id: str, agent_id: str, request: Request) -> Agent:
    agent = await _get_agent_in_project(_storage(request), project_id, agent_id)
    return agent.model_dump()


class UpdateAgentRequest(BaseModel):
    display_name: str | None = None


@router.put("/{agent_id}")
async def update_agent(
    project_id: str, agent_id: str, body: UpdateAgentRequest, request: Request
) -> Agent:
    storage = _storage(request)
    await _get_agent_in_project(storage, project_id, agent_id)
    updated = await storage.update_agent(agent_id, display_name=body.display_name)
    return updated.model_dump()


@router.delete("/{agent_id}")
async def delete_agent(
    project_id: str, agent_id: str, request: Request
) -> AgentDeletedResponse:
    storage = _storage(request)
    await _get_agent_in_project(storage, project_id, agent_id)
    await storage.delete_agent(agent_id)
    return {"status": "deleted", "project_id": project_id, "agent_id": agent_id}


class AgentSandboxPolicyUpdate(BaseModel):
    """Unset (`None`) fields are left unchanged. `sharing=None` means "inherit
    the project's default" and is a valid, meaningful value here — unlike
    `Project`/`Session`, `Agent.sandbox_sharing` defaults to `None`, not
    `"isolated"` — but this route's own partial-update convention still
    treats an *omitted* field as "leave unchanged," so explicitly resetting
    an agent back to "inherit" isn't possible via this route today (same
    known gap as `Storage.update_project_sandbox_policy`)."""

    sharing: SharingScope | None = None
    idle_timeout_seconds: int | None = None
    resource_overrides: dict[str, int] | None = None


@router.put("/{agent_id}/sandbox-policy")
async def update_agent_sandbox_policy(
    project_id: str, agent_id: str, body: AgentSandboxPolicyUpdate, request: Request
) -> Agent:
    storage = _storage(request)
    await _get_agent_in_project(storage, project_id, agent_id)
    updated = await storage.update_agent_sandbox_policy(
        agent_id,
        sharing=body.sharing,
        idle_timeout_seconds=body.idle_timeout_seconds,
        resource_overrides=body.resource_overrides,
    )
    return updated.model_dump()


# -- sessions (owned by this agent) --------------------------------------
# Individual-session operations (get/rename/delete/messages/policy/embed)
# live in `sessions_routes.py`, addressed by session_id alone.


@router.post("/{agent_id}/sessions")
async def create_agent_session(
    project_id: str, agent_id: str, request: Request
) -> SessionInfo:
    storage = _storage(request)
    await _get_agent_in_project(storage, project_id, agent_id)
    session = await storage.create_session("agent", agent_id)
    return session.model_dump()


@router.get("/{agent_id}/sessions")
async def list_agent_sessions(
    project_id: str, agent_id: str, request: Request
) -> list[SessionInfo]:
    storage = _storage(request)
    await _get_agent_in_project(storage, project_id, agent_id)
    return [
        session.model_dump()
        for session in await storage.list_sessions("agent", agent_id)
    ]
