"""App-wide exception handlers.

Without these, any exception that isn't already converted to an `HTTPException`
inside a route (e.g. an upstream `openai.AuthenticationError` from a bad
`OPENROUTER_API_KEY`, or a `ProviderConfigError` from a missing one) bubbles all
the way up through uvicorn as a raw traceback and a bare 500. Registering
handlers here means every route gets a logged, JSON error response for free
instead of each one needing its own try/except.
"""

from __future__ import annotations

import openai
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from krutrim_agents_core.providers.base import ProviderConfigError
from loguru import logger


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _handle_http_exception(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        logger.warning(
            "{} {} -> {} {}",
            request.method,
            request.url.path,
            exc.status_code,
            exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )

    @app.exception_handler(ProviderConfigError)
    async def _handle_provider_config_error(
        request: Request, exc: ProviderConfigError
    ) -> JSONResponse:
        logger.error(
            "{} {} -> provider config error: {}", request.method, request.url.path, exc
        )
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(openai.APIStatusError)
    async def _handle_model_provider_error(
        request: Request, exc: openai.APIStatusError
    ) -> JSONResponse:
        # Covers AuthenticationError, RateLimitError, BadRequestError, etc. —
        # all the errors the configured LLM provider (OpenRouter/OpenAI-compatible)
        # can raise. 502 because the failure is upstream, not this API's fault.
        logger.error(
            "{} {} -> model provider error {}: {}",
            request.method,
            request.url.path,
            exc.status_code,
            exc.message,
        )
        return JSONResponse(
            status_code=502,
            content={
                "detail": f"Model provider request failed ({exc.status_code}): {exc.message}"
            },
        )

    @app.exception_handler(Exception)
    async def _handle_unhandled_exception(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception(
            "{} {} -> unhandled {}",
            request.method,
            request.url.path,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": f"Internal server error ({type(exc).__name__}): {exc}"},
        )
