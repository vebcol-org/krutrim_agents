"""FastAPI entrypoint: `uv run uvicorn krutrim_agent_backend.main:app --reload --port 8000`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from krutrim_agent_extensions.middleware import ExtensionMiddleware
from krutrim_agent_extensions.selfcheck import run_startup_selfcheck
from krutrim_agent_management.config import settings
from loguru import logger

from krutrim_agent_backend.api.agent_instances_routes import (
    router as agent_instances_router,
)
from krutrim_agent_backend.api.agent_run import mount_agent_run_endpoint
from krutrim_agent_backend.api.agents_routes import router as agents_router
from krutrim_agent_backend.api.chat_routes import router as chat_router
from krutrim_agent_backend.api.chats_routes import router as chats_router
from krutrim_agent_backend.api.error_handlers import register_exception_handlers
from krutrim_agent_backend.api.health import router as health_router
from krutrim_agent_backend.api.models_routes import router as models_router
from krutrim_agent_backend.api.projects_routes import router as projects_router
from krutrim_agent_backend.api.sessions_routes import router as sessions_router
from krutrim_agent_backend.api.settings_routes import router as settings_router
from krutrim_agent_backend.api.status_routes import router as status_router
from krutrim_agent_backend.api.system_routes import router as system_router
from krutrim_agent_backend.bootstrap import build_app_state, install_app_state
from krutrim_agent_backend.logging_config import configure_logging

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting krutrim-agent backend")
    state = await build_app_state(settings)
    install_app_state(app, state)

    try:
        yield
    finally:
        logger.info("Shutting down krutrim-agent backend")
        state.sandbox_registry.close_all()


def create_app() -> FastAPI:
    # Fails CLOSED, not open: refuses to construct the app at all if
    # settings.edition == "extended" but no real RequestAuthenticator was
    # registered — see krutrim_agent_extensions/selfcheck.py.
    run_startup_selfcheck(settings)

    app = FastAPI(title="Krutrim Agent Backend", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Resolves request.state.principal/visible_agent_keys for every request
    # (agents_routes.py, agent_run.py read the latter). Community ships
    # all-no-op hooks, so this is a pure pass-through today.
    app.add_middleware(ExtensionMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(agents_router)
    app.include_router(settings_router)
    app.include_router(projects_router)
    app.include_router(agent_instances_router)
    app.include_router(chats_router)
    app.include_router(sessions_router)
    app.include_router(chat_router)
    app.include_router(models_router)
    app.include_router(status_router)
    app.include_router(system_router)
    mount_agent_run_endpoint(app)
    logger.info(f"DEV_MODE: {settings.dev_mode}")
    return app


app = create_app()
