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
from krutrim_agent_sandbox.registry import SandboxRegistry

if TYPE_CHECKING:
    from fastapi import FastAPI
    from krutrim_agent_management.base import Storage
    from krutrim_agent_management.config import AppSettings


@dataclass
class AppState:
    storage: Storage
    # Owner-scoped sandbox registry — resolves a session to its workspace dir
    # and hands back an in-process `FilesystemBackend` rooted there (see
    # krutrim_agent_sandbox/registry.py). Every route that needs a sandbox
    # goes through this and never constructs a backend directly.
    sandbox_registry: SandboxRegistry


async def build_app_state(settings: AppSettings) -> AppState:
    storage = create_storage(settings)
    sandbox_registry = SandboxRegistry(store=storage)
    return AppState(
        storage=storage,
        sandbox_registry=sandbox_registry,
    )


def install_app_state(app: FastAPI, state: AppState) -> None:
    app.state.storage = state.storage
    app.state.sandbox_registry = state.sandbox_registry
