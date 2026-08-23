"""GET /api/system/extensions — reports which extension hooks, storage
backend, and sandbox runtime are actually active. Read-only status, never
raises on edition drift (that's `krutrim_agent_extensions.selfcheck`'s job, run once
at startup) — this is what an external monitor or the frontend
self-check polls to catch a hook silently reverting to its community
default after a bad deploy/config change. Nothing returned here is
sensitive (implementation class names and config strings, no secrets), so
it's ungated — same posture as `/api/health` and `/api/agents`.
"""

from __future__ import annotations

from fastapi import APIRouter
from krutrim_agent_extensions.registry import all_hooks
from krutrim_agent_management.config import settings

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/extensions")
def get_extension_status() -> dict:
    hooks = all_hooks()
    return {
        "edition": settings.edition,
        "hooks": {name: type(impl).__name__ for name, impl in hooks.items()},
        "storage_backend": settings.storage_backend,
        "sandbox_runtime": settings.sandbox_runtime,
    }
