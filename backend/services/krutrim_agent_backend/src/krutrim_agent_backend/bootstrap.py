"""Reusable `app.state` construction — extracted from `main.py`'s `lifespan()`
so a second FastAPI app (e.g. a separate deployment wrapping this same
platform with its own extra routes/middleware) gets the exact same startup
wiring without re-deriving it. `main.py`'s `lifespan()` is now just:

    state = await build_app_state(settings)
    install_app_state(app, state)
    ...
    state.sandbox_registry.close_all()

and that other app's own lifespan does the same two calls, then
`app.include_router(agents_router)` etc. straight from `krutrim_agent_backend.api.*`
(already plain `APIRouter`s) plus whatever routes/middleware it adds itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from krutrim_agent_management.storage_factory import create_storage
from krutrim_agent_sandbox.policy import SandboxPolicy
from krutrim_agent_sandbox.registry import SandboxRegistry
from krutrim_agent_sandbox.status_channel import RedisPubSubBackend
from krutrim_agents_core.providers.store import ProviderStore

if TYPE_CHECKING:
    from fastapi import FastAPI
    from krutrim_agent_management.base import Storage
    from krutrim_agent_management.config import AppSettings


@dataclass
class AppState:
    provider_store: ProviderStore
    storage: Storage
    # Owner-scoped sandbox registry — one container per session by default
    # (see krutrim_agent_sandbox/registry.py), replacing the old pooled-per-agent-
    # profile model. Every route that needs a sandbox (the AG-UI agent-run
    # path; eventually the chat path too) goes through this, never
    # constructs a sandbox backend directly.
    sandbox_registry: SandboxRegistry


async def build_app_state(settings: AppSettings) -> AppState:
    provider_store = ProviderStore(settings.provider_settings_path)
    storage = create_storage(settings)
    sandbox_registry = SandboxRegistry(
        store=storage,
        policy_factory=lambda _owner_id: SandboxPolicy(image=settings.sandbox_image),
        pubsub=RedisPubSubBackend(settings.redis_url),
        provider_store=provider_store,
        # Profiles listed in settings.in_sandbox_agent_profiles (research) run
        # their whole graph inside the container over gRPC; every other profile
        # keeps the in-process tool-backend path.
        enable_in_sandbox=True,
    )
    return AppState(
        provider_store=provider_store,
        storage=storage,
        sandbox_registry=sandbox_registry,
    )


def install_app_state(app: FastAPI, state: AppState) -> None:
    app.state.provider_store = state.provider_store
    app.state.storage = state.storage
    app.state.sandbox_registry = state.sandbox_registry
