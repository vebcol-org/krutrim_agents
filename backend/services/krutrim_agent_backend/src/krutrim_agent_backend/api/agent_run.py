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

import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path

from ag_ui.core import RunErrorEvent
from ag_ui.core.types import RunAgentInput
from ag_ui.encoder import EventEncoder
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from krutrim_agent_agui import run_graph_as_agui
from krutrim_agent_grpc import AgentRuntimeClient, serve_host_bridge
from krutrim_agent_management.base import Storage
from krutrim_agent_management.models import Agent, SessionInfo
from krutrim_agent_sandbox import serve_egress_proxy
from krutrim_agents_core.builder import build_agent
from krutrim_agents_core.cross_agent import (
    find_eligible_peers,
    invoke_agent_turn,
    message_agent_tool,
)
from krutrim_agents_core.harness.run_logging import RunLoggingMiddleware
from krutrim_agents_core.harness.runs import RunLogger
from krutrim_agents_core.registry import get_profile
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from loguru import logger
from pydantic import BaseModel


def _append_jsonl(path: Path, record: dict) -> None:
    """Best-effort append of one line to the per-run transcript — used for the
    egress-proxy allow/deny events (HostBridge writes its own lines)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"ts": datetime.now(UTC).isoformat(), **record},
                    default=str,
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:  # noqa: BLE001, S110 - the transcript is best-effort
        pass


def _last_user_message(input_data: RunAgentInput) -> str:
    for message in reversed(input_data.messages or []):
        if getattr(message, "role", None) == "user":
            content = message.content
            return content if isinstance(content, str) else str(content)
    return ""

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

        async def _run_in_process(handle):
            """Historical path: build + stream the graph in this process; only
            the agent's shell/file tool calls run in the container."""
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
                run_logger = RunLogger(agent.agent_key, session.session_id)
                graph = build_agent(
                    profile,
                    provider_store,
                    handle.backend,
                    checkpointer=checkpointer,
                    extra_tools=extra_tools,
                    extra_middleware=[RunLoggingMiddleware(run_logger)],
                )
                async for event in run_graph_as_agui(
                    graph, input_data, thread_id=session.session_id
                ):
                    yield encoder.encode(event)

        async def _run_in_sandbox(runtime):
            """In-sandbox path: the whole graph runs inside the container. We
            serve HostBridge (its only egress route) and stream RunTurn events
            straight onto the SSE wire. A client disconnect / error interrupts
            the in-flight turn."""
            transcript = storage.session_dir(session.session_id) / "runs" / (
                f"{session.session_id}.jsonl"
            )
            frontend_tools_json = json.dumps(
                [t.model_dump() for t in (input_data.tools or [])]
            )

            # `message_agent` runs entirely on the host (it needs the full
            # Storage / ProviderStore / SandboxRegistry); the container reaches
            # it through HostBridge. Only offered when a sibling agent is
            # actually reachable — mirrors the in-process path's gate.
            peer_ids = await find_eligible_peers(
                storage, agent.project_id, session
            )

            async def _message_agent(target_session_id: str, message: str) -> str:
                return await invoke_agent_turn(
                    store=storage,
                    provider_store=provider_store,
                    sandbox_registry=sandbox_registry,
                    project_id=agent.project_id,
                    caller_session_id=session.session_id,
                    target_session_id=target_session_id,
                    message=message,
                    call_chain=[],
                )

            async with contextlib.AsyncExitStack() as stack:
                # Allowlist egress proxy for the in-sandbox container's
                # HTTP(S)_PROXY, bound to the port the registry pinned into the
                # container env. Always runs; the allowlist
                # (settings.sandbox_egress_allowlist) is often empty → deny-all.
                if runtime.egress_proxy_bind:
                    proxy_host, proxy_port = runtime.egress_proxy_bind.rsplit(":", 1)

                    def _log_egress(ev: dict) -> None:
                        _append_jsonl(
                            transcript, {"source": "egress_proxy", **ev}
                        )

                    await stack.enter_async_context(
                        serve_egress_proxy(
                            runtime.egress_allowlist,
                            bind_host=proxy_host,
                            bind_port=int(proxy_port),
                            on_event=_log_egress,
                        )
                    )
                await stack.enter_async_context(
                    serve_host_bridge(
                        runtime.host_bridge_bind,
                        thread_id=session.session_id,
                        transcript_path=transcript,
                        message_agent_handler=_message_agent if peer_ids else None,
                    )
                )
                async with AgentRuntimeClient(runtime.run_endpoint) as client:
                    try:
                        async for ev_json in client.run_turn(
                            thread_id=session.session_id,
                            user_message=_last_user_message(input_data),
                            run_id=input_data.run_id or "",
                            frontend_tools_json=frontend_tools_json,
                            cross_agent_enabled=bool(peer_ids),
                        ):
                            yield f"data: {ev_json}\n\n"
                    except BaseException:
                        await client.interrupt(session.session_id)
                        raise

        async def event_generator():
            handle = None
            try:
                handle = await sandbox_registry.get_or_create(session.session_id)
                if handle.runtime is not None:
                    async for chunk in _run_in_sandbox(handle.runtime):
                        yield chunk
                else:
                    async for chunk in _run_in_process(handle):
                        yield chunk
            except Exception as exc:
                # Backstop for failures *around* the stream (sandbox / checkpointer
                # setup). `run_graph_as_agui` converts failures during the graph
                # run into a RUN_ERROR event itself and does not raise. Headers
                # are already sent by this point, so a raised exception can't
                # become a clean HTTP error response (see error_handlers.py for
                # that path on non-streaming routes) — emit RUN_ERROR instead.
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

    @app.post(f"{AGENT_RUN_PATH_PREFIX}/{{agent_id}}/interrupt")
    async def agent_run_interrupt(
        agent_id: str, request: Request, session_id: str
    ) -> dict:
        """Cancel the in-flight turn of an in-sandbox agent session. No-op for
        tool-backend sessions (nothing to interrupt server-side there)."""
        storage: Storage = request.app.state.storage
        agent = await _get_agent(storage, agent_id)
        _check_agent_key_visible(request, agent.agent_key)
        try:
            session = await storage.get_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if session.owner_type != "agent" or session.owner_id != agent.agent_id:
            raise HTTPException(
                status_code=400,
                detail=f"Session {session_id!r} does not belong to agent {agent_id!r}.",
            )
        was_running = await request.app.state.sandbox_registry.interrupt(session_id)
        return {"status": "ok", "interrupted": was_running}

    @app.get(f"{AGENT_RUN_PATH_PREFIX}/{{agent_id}}/health")
    async def agent_run_health(agent_id: str, request: Request) -> AgentRunHealthResponse:
        storage: Storage = request.app.state.storage
        agent = await _get_agent(storage, agent_id)
        _check_agent_key_visible(request, agent.agent_key)
        return {
            "status": "ok",
            "agent": {"id": agent.agent_id, "agent_key": agent.agent_key},
        }
