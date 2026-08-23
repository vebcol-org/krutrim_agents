"""REST CRUD for per-`(agent_key, role)` provider/model settings — consumed by the frontend Settings panel.

Note: the compiled agent graphs are built once at process startup from
whatever `ProviderStore` returns at that moment. Changes made here are
persisted immediately but only take effect for the *running* agent after a
backend restart — there's no hot-reload of the compiled graph in this v1.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from krutrim_agents_core.providers.registry import known_providers

router = APIRouter(prefix="/api/providers", tags=["providers"])

RESTART_NOTE = (
    "Saved. Restart the backend for this change to take effect in the running agent."
)


def _store(request: Request):
    return request.app.state.provider_store


@router.get("/meta")
def list_meta() -> dict[str, Any]:
    return {"providers": known_providers()}


@router.get("/{agent_key}")
def list_settings(agent_key: str, request: Request) -> dict[str, dict[str, Any]]:
    try:
        return {
            role: model_settings.model_dump()
            for role, model_settings in _store(request).get_all(agent_key).items()
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{agent_key}/{role}")
def get_settings(agent_key: str, role: str, request: Request) -> dict[str, Any]:
    try:
        return _store(request).get(agent_key, role).model_dump()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{agent_key}/{role}")
def update_settings(
    agent_key: str, role: str, data: dict[str, Any], request: Request
) -> dict[str, Any]:
    try:
        updated = _store(request).set(agent_key, role, data)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"settings": updated.model_dump(), "note": RESTART_NOTE}


@router.post("/{agent_key}/{role}/reset")
def reset_settings(agent_key: str, role: str, request: Request) -> dict[str, Any]:
    store = _store(request)
    try:
        store.reset(agent_key, role)
        return {
            "settings": store.get(agent_key, role).model_dump(),
            "note": RESTART_NOTE,
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
