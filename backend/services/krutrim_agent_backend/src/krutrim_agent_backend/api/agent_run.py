"""Mounts every registered agent profile behind ONE parameterized AG-UI route.

`POST /agents/{agent_id}` — a single FastAPI handler, not one route per
agent. `agent_id` is an **`Agent` instance id** (`krutrim_agent_management.models.Agent`,
created via `POST /api/projects/{project_id}/agents` — see
`agent_instances_routes.py`), not a profile key: a project can hold multiple
instances of the same profile (e.g. two `agent_key="research"` agents with
different `display_name`s and independent sessions/policy), so a profile key
alone is no longer enough to identify which agent a run belongs to. The
route still fans out to whichever profile a given instance was built from
(`krutrim_agents_core.registry.get_profile(agent.agent_key)`), so adding a new agent type
never means adding a new route.

The frontend talks straight to this endpoint via `@ag-ui/client`'s
`HttpAgent` — no CopilotKit, no intermediary runtime process. (As of this
writing the frontend's AG-UI wiring isn't connected yet — see
`docs/frontend/README.md` — but the route contract here is what it will call.)

The graph is built fresh per request: its sandbox comes from
`SandboxRegistry.get_or_create` — one container per session by default
(`sandbox/registry.py`) — and its LangGraph checkpointer is a dedicated
SQLite file under that session's directory in `STORAGE_ROOT`, so conversation
state survives a process restart.

The session also gets the cross-agent `message_agent` tool (see
`agents/cross_agent.py`) grafted in via `build_agent`'s `extra_tools`, but
only when its sharing policy actually makes at least one sibling agent in
the same project reachable — an isolated session (the default) never sees
this tool.
"""

from __future__ import annotations

from ag_ui.core import RunErrorEvent
from ag_ui.core.types import RunAgentInput
from ag_ui.encoder import EventEncoder
from ag_ui_langgraph import LangGraphAgent
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from krutrim_agent_management.base import Storage
from krutrim_agent_management.models import Agent, SessionInfo
from krutrim_agents_core.builder import build_agent
from krutrim_agents_core.cross_agent import find_eligible_peers, message_agent_tool
from krutrim_agents_core.registry import get_profile
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from loguru import logger
from pydantic import BaseModel

AGENT_RUN_PATH_PREFIX = "/agents"


class AgentRunAgentInfo(BaseModel):
    id: str
    agent_key: str


class AgentRunHealthResponse(BaseModel):
    status: str
    agent: AgentRunAgentInfo


async def _get_agent(storage: Storage, agent_id: str) -> Agent:
    try:
        return await storage.get_agent(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _check_agent_key_visible(request: Request, agent_key: str) -> None:
    """404s (not 403 — an invisible agent should look like it doesn't exist,
    same as an unknown `agent_id`) if `AgentVisibilityPolicy` restricts this
    principal's visible profiles and `agent_key` isn't among them. `None`
    (community default) means no restriction — see `agents_routes.py`."""
    visible_agent_keys = getattr(request.state, "visible_agent_keys", None)
    if visible_agent_keys is not None and agent_key not in visible_agent_keys:
        raise HTTPException(
            status_code=404, detail=f"Unknown agent profile {agent_key!r}."
        )


async def _get_or_create_run_session(
    storage: Storage, agent: Agent, session_id: str | None
) -> SessionInfo:
    if session_id is None:
        return await storage.create_session("agent", agent.agent_id)
    try:
        session = await storage.get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if session.owner_type != "agent" or session.owner_id != agent.agent_id:
        raise HTTPException(
            status_code=400,
            detail=f"Session {session_id!r} does not belong to agent {agent.agent_id!r}.",
        )
    return session


def mount_agent_run_endpoint(app: FastAPI) -> None:
    @app.post(f"{AGENT_RUN_PATH_PREFIX}/{{agent_id}}")
    async def agent_run_endpoint(
        agent_id: str,
        input_data: RunAgentInput,
        request: Request,
        session_id: str | None = None,
    ):
        storage: Storage = request.app.state.storage
        agent = await _get_agent(storage, agent_id)
        _check_agent_key_visible(request, agent.agent_key)
        try:
            profile = get_profile(agent.agent_key)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        session = await _get_or_create_run_session(storage, agent, session_id)

        provider_store = request.app.state.provider_store
        sandbox_registry = request.app.state.sandbox_registry

        encoder = EventEncoder(accept=request.headers.get("accept"))
        checkpoint_path = (
            storage.session_dir(session.session_id) / "langgraph_checkpoint.sqlite"
        )

        async def event_generator():
            handle = None
            try:
                handle = await sandbox_registry.get_or_create(session.session_id)
                async with AsyncSqliteSaver.from_conn_string(
                    str(checkpoint_path)
                ) as checkpointer:
                    peer_ids = await find_eligible_peers(
                        storage, agent.project_id, session
                    )
                    extra_tools = (
                        [
                            message_agent_tool(
                                store=storage,
                                provider_store=provider_store,
                                sandbox_registry=sandbox_registry,
                                project_id=agent.project_id,
                                caller_session_id=session.session_id,
                                call_chain=[],
                            )
                        ]
                        if peer_ids
                        else []
                    )
                    graph = build_agent(
                        profile,
                        provider_store,
                        handle.backend,
                        checkpointer=checkpointer,
                        extra_tools=extra_tools,
                    )
                    request_agent = LangGraphAgent(
                        name=agent.agent_key,
                        graph=graph,
                        description=profile.description,
                    )
                    async for event in request_agent.run(input_data):
                        yield encoder.encode(event)
            except Exception as exc:
                # Headers are already sent by this point, so a raised exception
                # can't become a clean HTTP error response (see error_handlers.py
                # for that path on non-streaming routes) — emit it as an AG-UI
                # RUN_ERROR event instead so the frontend sees a real message.
                logger.exception("Agent run {!r} failed mid-stream: {}", agent_id, exc)
                yield encoder.encode(
                    RunErrorEvent(message=f"{type(exc).__name__}: {exc}")
                )
            finally:
                if handle is not None:
                    await sandbox_registry.release(handle.owner_id)

        return StreamingResponse(
            event_generator(), media_type=encoder.get_content_type()
        )

    @app.get(f"{AGENT_RUN_PATH_PREFIX}/{{agent_id}}/health")
    async def agent_run_health(agent_id: str, request: Request) -> AgentRunHealthResponse:
        storage: Storage = request.app.state.storage
        agent = await _get_agent(storage, agent_id)
        _check_agent_key_visible(request, agent.agent_key)
        return {
            "status": "ok",
            "agent": {"id": agent.agent_id, "agent_key": agent.agent_key},
        }
