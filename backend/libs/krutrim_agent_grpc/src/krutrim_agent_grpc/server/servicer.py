"""`AgentRuntimeServicer` — one turn per `RunTurn`, cancellable via `Interrupt`.

The turn runs as an `asyncio.Task` feeding a queue that the RPC response stream
drains, so a concurrent `Interrupt` RPC can cancel it cleanly. On cancel the
stream still emits one terminal event (a `RUN_ERROR` carrying "interrupted") so
the browser sees a definite end, then closes.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from krutrim_agent_grpc.proto import agent_runtime_pb2 as pb
from krutrim_agent_grpc.proto import agent_runtime_pb2_grpc as pbg
from krutrim_agent_grpc.run_config import RunConfig
from krutrim_agent_grpc.server import graph_runner

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

# AG-UI event types worth keeping in the per-run transcript (the in-graph
# structure; host-side LLM/tool calls are logged separately by HostBridge).
_TRANSCRIPT_EVENT_TYPES = {
    "RUN_STARTED",
    "RUN_FINISHED",
    "RUN_ERROR",
    "STEP_STARTED",
    "STEP_FINISHED",
    "TOOL_CALL_START",
    "TOOL_CALL_END",
}


def _run_error_json(run_id: str, message: str) -> str:  # noqa: ARG001 - run_id kept for call-site symmetry
    # Shape must match `graph_runner`'s events: AG-UI `RUN_ERROR` is just
    # {type, message, code?} — no `runId` — and unset optionals are omitted,
    # not sent as `null` (@ag-ui/client's `.optional()` Zod schemas reject it).
    return json.dumps({"type": "RUN_ERROR", "message": message})


def _tee_transcript(runs_dir: str, thread_id: str, ev_json: str) -> None:
    try:
        event = json.loads(ev_json)
    except json.JSONDecodeError:
        return
    if event.get("type") not in _TRANSCRIPT_EVENT_TYPES:
        return
    path = Path(runs_dir) / f"{thread_id}.jsonl"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "ts": datetime.now(UTC).isoformat(),
                        "source": "agent_runtime",
                        **event,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:  # noqa: BLE001 - transcript is best-effort, never break the stream
        pass


class AgentRuntimeServicer(pbg.AgentRuntimeServicer):
    def __init__(self, cfg: RunConfig, stop_event: asyncio.Event) -> None:
        self._cfg = cfg
        self._stop_event = stop_event
        self._tasks: dict[str, asyncio.Task] = {}

    # -- RunTurn ---------------------------------------------------------

    async def RunTurn(  # noqa: N802 - gRPC generated name
        self, request: pb.RunTurnRequest, context
    ) -> AsyncIterator[pb.RunEvent]:
        thread_id = request.thread_id or self._cfg.session_id
        run_id = request.run_id or uuid.uuid4().hex
        queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()

        async def _produce() -> None:
            try:
                async for ev_json in graph_runner.stream_turn(
                    self._cfg,
                    thread_id=thread_id,
                    run_id=run_id,
                    user_message=request.user_message,
                    frontend_tools_json=request.frontend_tools_json,
                    cross_agent_enabled=request.cross_agent_enabled,
                ):
                    await queue.put(("event", ev_json))
            except asyncio.CancelledError:
                await queue.put(
                    ("event", _run_error_json(run_id, "Run interrupted by user."))
                )
                raise
            except Exception as exc:  # noqa: BLE001 - surface as a protocol event, never crash the server
                logger.exception("in-sandbox run {} failed", run_id)
                await queue.put(
                    ("event", _run_error_json(run_id, f"{type(exc).__name__}: {exc}"))
                )
            finally:
                await queue.put(("done", None))

        task = asyncio.create_task(_produce())
        self._tasks[thread_id] = task
        try:
            while True:
                kind, payload = await queue.get()
                if kind == "done":
                    break
                if payload:
                    _tee_transcript(self._cfg.runs_dir, thread_id, payload)
                yield pb.RunEvent(agui_event_json=payload or "")
        finally:
            self._tasks.pop(thread_id, None)
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    # -- Interrupt -----------------------------------------------------

    async def Interrupt(  # noqa: N802
        self, request: pb.InterruptRequest, context
    ) -> pb.InterruptAck:
        task = self._tasks.get(request.thread_id or self._cfg.session_id)
        running = task is not None and not task.done()
        if running:
            task.cancel()
        return pb.InterruptAck(was_running=running)

    # -- Health / Shutdown ------------------------------------------------

    async def Health(self, request: pb.HealthRequest, context) -> pb.HealthReply:  # noqa: N802
        return pb.HealthReply(ready=True, detail="ok")

    async def Shutdown(  # noqa: N802
        self, request: pb.ShutdownRequest, context
    ) -> pb.ShutdownAck:
        for task in list(self._tasks.values()):
            if not task.done():
                task.cancel()
        for task in list(self._tasks.values()):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._stop_event.set()
        return pb.ShutdownAck()
