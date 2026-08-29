"""Host-side client for the in-sandbox `AgentRuntime` service.

`agent_run.py` uses this instead of building/streaming the graph in-process:
open a gRPC channel to the container's published AgentRuntime port, wait for
`Health`, then `run_turn(...)` and forward each AG-UI event JSON string onto the
SSE wire. `interrupt(...)` on client disconnect or an explicit stop request.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import grpc

from krutrim_agent_grpc.proto import agent_runtime_pb2 as pb
from krutrim_agent_grpc.proto import agent_runtime_pb2_grpc as pbg

# A gRPC control channel must never traverse an HTTP proxy (grpc otherwise
# honours ``http_proxy`` / ``no_proxy``); this is loopback / a private Docker
# network, not agent egress.
_CHANNEL_OPTIONS = (("grpc.enable_http_proxy", 0),)


class AgentRuntimeClient:
    def __init__(self, target: str) -> None:
        # gRPC TCP target: "127.0.0.1:<port>" (published host port) or
        # "<container-name>:50051" (shared Docker network).
        self._target = target
        self._channel: grpc.aio.Channel | None = None
        self._stub: pbg.AgentRuntimeStub | None = None

    async def __aenter__(self) -> AgentRuntimeClient:
        self._channel = grpc.aio.insecure_channel(self._target, options=_CHANNEL_OPTIONS)
        self._stub = pbg.AgentRuntimeStub(self._channel)
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None

    def _require_stub(self) -> pbg.AgentRuntimeStub:
        if self._stub is None:
            raise RuntimeError("AgentRuntimeClient used outside its async context")
        return self._stub

    async def wait_healthy(self, *, timeout: float = 30.0, interval: float = 0.25) -> None:
        """Poll `Health` until it reports ready or `timeout` elapses. The
        container's CMD starts the server as PID 1, so the port may refuse
        connections for the first few hundred ms after `containers.run()`."""
        stub = self._require_stub()
        deadline = asyncio.get_event_loop().time() + timeout
        last_err: Exception | None = None
        while asyncio.get_event_loop().time() < deadline:
            try:
                reply = await stub.Health(pb.HealthRequest(), timeout=interval * 4)
                if reply.ready:
                    return
            except grpc.aio.AioRpcError as exc:  # socket not up yet / transient
                last_err = exc
            await asyncio.sleep(interval)
        raise TimeoutError(
            f"AgentRuntime at {self._target} not healthy within {timeout}s"
            + (f" (last error: {last_err})" if last_err else "")
        )

    async def run_turn(
        self,
        *,
        thread_id: str,
        user_message: str,
        run_id: str = "",
        frontend_tools_json: str = "",
        cross_agent_enabled: bool = False,
    ) -> AsyncIterator[str]:
        """Yield each `RunEvent.agui_event_json` string for one turn."""
        stub = self._require_stub()
        request = pb.RunTurnRequest(
            thread_id=thread_id,
            run_id=run_id,
            user_message=user_message,
            frontend_tools_json=frontend_tools_json,
            cross_agent_enabled=cross_agent_enabled,
        )
        async for event in stub.RunTurn(request):
            yield event.agui_event_json

    async def interrupt(self, thread_id: str) -> bool:
        stub = self._require_stub()
        try:
            ack = await stub.Interrupt(
                pb.InterruptRequest(thread_id=thread_id), timeout=10.0
            )
            return ack.was_running
        except grpc.aio.AioRpcError:
            return False

    async def shutdown(self, *, flush: bool = True) -> None:
        stub = self._require_stub()
        try:
            await stub.Shutdown(pb.ShutdownRequest(flush=flush), timeout=30.0)
        except grpc.aio.AioRpcError:
            pass
