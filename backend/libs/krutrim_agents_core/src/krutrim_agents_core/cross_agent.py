"""Cross-agent messaging bridge.

Lets the agent running in one session send a message to the agent running
in another session — within the same project — and get a real reply,
synchronously. This is deliberately **not** the same thing as sharing a
container: the two sessions keep their own separate sandboxes the whole
time (see `sandbox/registry.py::SandboxRegistry.resolve_owner_id`'s
docstring for that distinction, and `SessionInfo.attached_to_session_id`
for the mechanism that *does* share a container). "Sharing" here only ever
means "eligible to open this communication channel."

Only granted to a session's graph when its `sandbox_sharing != "isolated"`
and at least one eligible peer exists at graph-build time (`api/agent_run.py`
calls `find_eligible_peers` before deciding whether to pass the
`message_agent` tool into `krutrim_agents_core.builder.build_agent`'s `extra_tools`) — an
isolated session never sees this tool at all.

**Agent-owned sessions only.** Both sides of a `message_agent` exchange must
be sessions owned by an `Agent` (never a `Chat`) — a project's hierarchy is
`Project -> (Agent | Chat) -> Session` (see `krutrim_agent_management.models`), and
letting a `Chat` reach into a sibling `Agent` is a real, separate feature
(the plain `chat` graph has no tool-injection framework today) that's
explicitly not built yet. `_check_eligible` enforces this directly rather
than relying on `find_eligible_peers` alone, since `message_agent`'s
`container_id` argument is LLM-supplied and not guaranteed to come from the
peer list it was offered.

Bidirectional and synchronous: calling it triggers a real turn on the target
agent (spinning its sandbox up via `SandboxRegistry` if it's idle) and blocks
for the reply, bounded by `AppSettings.cross_agent_call_timeout_seconds`. The
target's own turn is checkpointed through the same durable, session-scoped
`AsyncSqliteSaver` its normal AG-UI requests use (not a separate persistence
path) — same `thread_id` convention as `api/agent_run.py` — so the exchange
shows up in that session's history the next time its human owner resumes it
normally.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from krutrim_agent_management.config import settings
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from krutrim_agents_core.builder import build_agent
from krutrim_agents_core.harness.recording_backend import RecordingFilesystemBackend
from krutrim_agents_core.harness.run_logging import RunLoggingMiddleware
from krutrim_agents_core.harness.runs import RunLogger
from krutrim_agents_core.registry import get_profile

if TYPE_CHECKING:
    from krutrim_agent_management.base import Storage
    from krutrim_agent_management.models import SessionInfo
    from krutrim_agent_sandbox.registry import SandboxRegistry
    from langchain_core.tools import BaseTool

    from krutrim_agents_core.providers.store import ProviderStore

MAX_CROSS_AGENT_CALL_DEPTH = 3
"""Maximum chain length before a message_agent call is refused outright,
independent of whether it would also be a cycle — bounds worst-case fan-out
of a chain of distinct sessions relaying through each other."""


def _check_eligible(caller: SessionInfo, target: SessionInfo) -> bool:
    """Two sessions can reach each other iff: both are owned by an `Agent`
    (never a `Chat` — see module docstring), both belong to the same
    (non-null) project, and either both `project-shared`, or both
    `session-shared` and mutually listed in each other's
    `linked_session_ids`. One-sided sharing (only one side opted in, or
    session-shared without a mutual listing) is never eligible — a session
    shouldn't receive messages it hasn't itself agreed to receive.
    """
    if caller.owner_type != "agent" or target.owner_type != "agent":
        return False
    if caller.project_id is None or caller.project_id != target.project_id:
        return False
    if (
        caller.sandbox_sharing == "project-shared"
        and target.sandbox_sharing == "project-shared"
    ):
        return True
    if (
        caller.sandbox_sharing == "session-shared"
        and target.sandbox_sharing == "session-shared"
    ):
        if (
            target.session_id in caller.linked_session_ids
            and caller.session_id in target.linked_session_ids
        ):
            return True
    return False


async def _list_agent_owned_sessions(
    store: Storage, project_id: str
) -> list[SessionInfo]:
    """Every session owned by any `Agent` in this project — the universe of
    possible `message_agent` peers/targets (`Chat`-owned sessions are never
    eligible, see module docstring)."""
    sessions: list[SessionInfo] = []
    for agent in await store.list_agents(project_id):
        sessions.extend(await store.list_sessions("agent", agent.agent_id))
    return sessions


async def find_eligible_peers(
    store: Storage, project_id: str, session: SessionInfo
) -> list[str]:
    """Session ids in this project `session` can currently message — used to
    decide whether to grant the `message_agent` tool at graph-build time at
    all (an isolated session, or one with no eligible peer yet, never sees
    it). `invoke_agent_turn` re-checks eligibility for the specific pair on
    every call regardless — this is a graph-build-time convenience, not the
    authoritative check.
    """
    if session.sandbox_sharing == "isolated":
        return []
    others = [
        s
        for s in await _list_agent_owned_sessions(store, project_id)
        if s.session_id != session.session_id
    ]
    return [peer.session_id for peer in others if _check_eligible(session, peer)]


async def invoke_agent_turn(
    *,
    store: Storage,
    provider_store: ProviderStore,
    sandbox_registry: SandboxRegistry,
    project_id: str,
    caller_session_id: str,
    target_session_id: str,
    message: str,
    call_chain: list[str],
) -> str:
    """The backend-side half of `message_agent`. Returns a plain string in
    every case — including failures — since this is what a tool call
    returns to the calling agent, not an HTTP response; there's no separate
    error channel to raise into.
    """
    if target_session_id == caller_session_id:
        return "Error: a session cannot message itself."
    if target_session_id in call_chain:
        return f"Error: messaging {target_session_id!r} would create a cycle (call chain so far: {call_chain})."
    if len(call_chain) >= MAX_CROSS_AGENT_CALL_DEPTH:
        return f"Error: cross-agent call depth limit ({MAX_CROSS_AGENT_CALL_DEPTH}) reached."

    try:
        caller = await store.get_session(caller_session_id)
        target = await store.get_session(target_session_id)
    except KeyError as exc:
        return f"Error: {exc}"

    if not _check_eligible(caller, target):
        return (
            f"Error: this session isn't eligible to message {target_session_id!r} "
            "(sharing policy doesn't make you mutually eligible, or the target isn't an agent session)."
        )

    # _check_eligible already guarantees target.owner_type == "agent".
    target_agent = await store.get_agent(target.owner_id)
    target_profile = get_profile(target_agent.agent_key)
    next_call_chain = [*call_chain, caller_session_id]

    handle = await sandbox_registry.get_or_create(target_session_id)
    try:
        checkpoint_path = (
            store.session_dir(target_session_id) / "langgraph_checkpoint.sqlite"
        )
        async with AsyncSqliteSaver.from_conn_string(
            str(checkpoint_path)
        ) as checkpointer:
            peer_ids = await find_eligible_peers(store, project_id, target)
            extra_tools: list[BaseTool] = []
            if peer_ids:
                extra_tools.append(
                    message_agent_tool(
                        store=store,
                        provider_store=provider_store,
                        sandbox_registry=sandbox_registry,
                        project_id=project_id,
                        caller_session_id=target_session_id,
                        call_chain=next_call_chain,
                    )
                )
            run_logger = RunLogger(target_agent.agent_key, target_session_id)
            graph = build_agent(
                target_profile,
                provider_store,
                RecordingFilesystemBackend(handle.backend, run_logger),
                checkpointer=checkpointer,
                extra_tools=extra_tools,
                extra_middleware=[RunLoggingMiddleware(run_logger)],
            )
            incoming = HumanMessage(
                content=message, name=f"peer_agent:{caller_session_id}"
            )
            try:
                result = await asyncio.wait_for(
                    graph.ainvoke(
                        {"messages": [incoming]},
                        config={"configurable": {"thread_id": target_session_id}},
                    ),
                    timeout=settings.cross_agent_call_timeout_seconds,
                )
            except TimeoutError:
                return (
                    f"Error: peer session {target_session_id!r} did not respond within "
                    f"{settings.cross_agent_call_timeout_seconds}s."
                )
            reply = result["messages"][-1]
            return str(reply.content)
    finally:
        await sandbox_registry.release(handle.owner_id)


def message_agent_tool(
    *,
    store: Storage,
    provider_store: ProviderStore,
    sandbox_registry: SandboxRegistry,
    project_id: str,
    caller_session_id: str,
    call_chain: list[str],
) -> BaseTool:
    """Builds a `message_agent` tool bound to one calling session's identity
    and call chain — constructed fresh per graph-build (see `build_agent`'s
    `extra_tools`), never shared across sessions, so the closure's
    `caller_session_id`/`call_chain` can never leak between them."""

    @tool
    async def message_agent(container_id: str, message: str) -> str:
        """Send a message to another agent session in this project and get its reply.

        `container_id` is the target session's id. Only works if this
        session's sharing policy makes you and the target mutually eligible
        to message each other (see project/session sandbox settings)."""
        return await invoke_agent_turn(
            store=store,
            provider_store=provider_store,
            sandbox_registry=sandbox_registry,
            project_id=project_id,
            caller_session_id=caller_session_id,
            target_session_id=container_id,
            message=message,
            call_chain=call_chain,
        )

    return message_agent
