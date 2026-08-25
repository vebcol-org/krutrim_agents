"""Project CRUD — the top-level container in the `Project -> (Agent | Chat)
-> Session` hierarchy (see `krutrim_agent_management.models`).

Creating a project (`POST`) also auto-creates one default `Chat` inside it
(`display_name="General"`), so there's always a place to ask project-scoped
questions without prompting for it every time — see the hierarchy plan for
the reasoning. Creating an `Agent` inside a project is a separate call
(`POST /api/projects/{project_id}/agents`, see `agent_instances_routes.py`).

Also owns the project-level sandbox sharing policy (`PUT .../sandbox-policy`)
— the default every `Agent`/`Chat` in this project inherits unless it sets
its own override. The `Agent`/`Chat`/`Session`-level equivalents live in
`agent_instances_routes.py`, `chats_routes.py`, and `sessions_routes.py`
respectively.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from krutrim_agent_management.base import Storage
from krutrim_agent_management.models import Project, SharingScope
from pydantic import BaseModel

from krutrim_agent_backend.chat.catalog import DEFAULT_CHAT_MODEL

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _storage(request: Request) -> Storage:
    return request.app.state.storage


class CreateProjectRequest(BaseModel):
    project_title: str
    project_information: str = ""


class ProjectDeletedResponse(BaseModel):
    status: str
    project_id: str


@router.post("")
async def create_project(body: CreateProjectRequest, request: Request) -> Project:
    storage = _storage(request)
    project = await storage.create_project(body.project_title, body.project_information)
    await storage.create_chat(
        display_name="General",
        provider=DEFAULT_CHAT_MODEL.provider,
        model=DEFAULT_CHAT_MODEL.model,
        project_id=project.project_id,
    )
    return project.model_dump()


@router.get("")
async def list_projects(request: Request) -> list[Project]:
    return [project.model_dump() for project in await _storage(request).list_projects()]


@router.get("/{project_id}")
async def get_project(project_id: str, request: Request) -> Project:
    try:
        return (await _storage(request).get_project(project_id)).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class UpdateProjectRequest(BaseModel):
    """Unset (`None`) fields are left unchanged."""

    project_title: str | None = None
    project_information: str | None = None


@router.put("/{project_id}")
async def update_project(
    project_id: str, body: UpdateProjectRequest, request: Request
) -> Project:
    try:
        updated = await _storage(request).update_project(
            project_id,
            project_title=body.project_title,
            project_information=body.project_information,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return updated.model_dump()


@router.delete("/{project_id}")
async def delete_project(project_id: str, request: Request) -> ProjectDeletedResponse:
    try:
        await _storage(request).delete_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"status": "deleted", "project_id": project_id}


class ProjectSandboxPolicyUpdate(BaseModel):
    """Unset (`None`) fields are left unchanged — same partial-update
    convention as `update_project`."""

    sharing: SharingScope | None = None
    idle_timeout_seconds: int | None = None
    resource_overrides: dict[str, int] | None = None


@router.put("/{project_id}/sandbox-policy")
async def update_project_sandbox_policy(
    project_id: str, body: ProjectSandboxPolicyUpdate, request: Request
) -> Project:
    try:
        updated = await _storage(request).update_project_sandbox_policy(
            project_id,
            sharing=body.sharing,
            idle_timeout_seconds=body.idle_timeout_seconds,
            resource_overrides=body.resource_overrides,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return updated.model_dump()
