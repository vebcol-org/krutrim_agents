"""Lists registered agent profiles — the frontend never hardcodes this list."""

from __future__ import annotations

from fastapi import APIRouter, Request
from krutrim_agents_core.registry import all_profiles
from pydantic import BaseModel

router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentMeta(BaseModel):
    key: str
    display_name: str
    description: str
    roles: list[str]


@router.get("")
def list_agents(request: Request) -> list[AgentMeta]:
    # Set by ExtensionMiddleware; `None` (the community default — no
    # AgentVisibilityPolicy registered) means "no restriction, show every
    # profile", matching today's behavior exactly. `getattr(..., None)`
    # rather than direct attribute access since a route exercised without
    # the middleware installed (e.g. a test building a bare FastAPI app)
    # has no `visible_agent_keys` on `request.state` at all.
    visible_agent_keys = getattr(request.state, "visible_agent_keys", None)
    profiles = all_profiles()
    if visible_agent_keys is not None:
        profiles = {
            key: profile
            for key, profile in profiles.items()
            if key in visible_agent_keys
        }
    return [
        {
            "key": profile.key,
            "display_name": profile.display_name,
            "description": profile.description,
            "roles": list(profile.roles),
        }
        for profile in profiles.values()
    ]
