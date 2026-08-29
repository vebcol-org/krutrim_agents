"""In-sandbox agent runtime: policy → docker kwargs, and the AgentRuntime
servicer's stream / interrupt behaviour (with the graph stubbed out)."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile

import grpc
import pytest
from krutrim_agent_grpc.proto import agent_runtime_pb2 as pb
from krutrim_agent_grpc.proto import agent_runtime_pb2_grpc as pbg
from krutrim_agent_grpc.run_config import RunConfig
from krutrim_agent_grpc.server import graph_runner
from krutrim_agent_grpc.server.servicer import AgentRuntimeServicer
from krutrim_agent_sandbox.policy import BindMount, SandboxPolicy


@pytest.fixture
def short_socket():
    # macOS caps AF_UNIX paths at ~103 chars — pytest's tmp_path is too deep.
    yield os.path.join(tempfile.mkdtemp(), "s.sock")


@pytest.fixture
def cfg():
    return RunConfig(agent_key="research", agent_id="a", project_id="p", session_id="s1")


# -- policy ----------------------------------------------------------------


def test_tool_backend_kwargs_unchanged():
    kw = SandboxPolicy().to_docker_run_kwargs(container_name="c")
    assert kw["command"] == ["sleep", "infinity"]
    assert kw["network_disabled"] is True
    assert kw["read_only"] is True
    assert "/workspace" in kw["tmpfs"]
    assert "volumes" not in kw


def test_in_sandbox_kwargs_bind_mounts_and_no_workspace_tmpfs():
    policy = SandboxPolicy(
        run_mode="in-sandbox",
        binds=[
            BindMount(host_path="/h/stage", container_path="/run/krutrim_agent"),
            BindMount(host_path="/h/stage/workspace", container_path="/workspace"),
            BindMount(
                host_path="/repo",
                container_path="/opt/krutrim_agent/src",
                read_only=True,
            ),
        ],
        env={"PYTHONPATH": "/opt/krutrim_agent/src/x/src"},
    )
    kw = policy.to_docker_run_kwargs(container_name="c")
    assert kw["command"] is None  # image CMD (the gRPC server)
    # a bare in-sandbox policy (network defaults to "none") still disables
    # networking here; the registry always overrides this to "egress-allowlist".
    assert kw["network_disabled"] is True
    assert "/workspace" not in kw["tmpfs"]  # comes from a bind mount now
    assert kw["volumes"]["/h/stage"] == {"bind": "/run/krutrim_agent", "mode": "rw"}
    assert kw["volumes"]["/repo"]["mode"] == "ro"
    assert kw["environment"] == {"PYTHONPATH": "/opt/krutrim_agent/src/x/src"}


def test_run_config_round_trips(tmp_path):
    cfg = RunConfig(
        agent_key="research",
        agent_id="a",
        project_id="p",
        session_id="s",
        runtime_bind="0.0.0.0:50051",
        host_bridge_dial="host.docker.internal:54321",
    )
    cfg.write(tmp_path)
    again = RunConfig.read(tmp_path)
    assert again.session_id == "s"
    assert again.host_bridge_dial == "host.docker.internal:54321"


def test_in_sandbox_policy_opens_networking_and_publishes_port():
    policy = SandboxPolicy(
        run_mode="in-sandbox",
        network="bridge",
        publish_ports={"50051/tcp": "127.0.0.1"},
        binds=[BindMount(host_path="/h", container_path="/run/krutrim_agent")],
    )
    kw = policy.to_docker_run_kwargs(container_name="c")
    assert kw["network_disabled"] is False  # in-sandbox gRPC needs networking
    assert kw["ports"] == {"50051/tcp": ("127.0.0.1", None)}


# -- servicer ------------------------------------------------------------


async def _start_servicer(cfg: RunConfig, socket_path: str):
    server = grpc.aio.server()
    pbg.add_AgentRuntimeServicer_to_server(
        AgentRuntimeServicer(cfg, asyncio.Event()), server
    )
    server.add_insecure_port(f"unix:{socket_path}")
    await server.start()
    return server


async def test_run_turn_streams_events(short_socket, monkeypatch, cfg):
    async def fake_stream_turn(_cfg, **_kw):
        yield json.dumps({"type": "RUN_STARTED"})
        yield json.dumps({"type": "TEXT_MESSAGE_CONTENT", "delta": "hi"})
        yield json.dumps({"type": "RUN_FINISHED"})

    monkeypatch.setattr(graph_runner, "stream_turn", fake_stream_turn)

    server = await _start_servicer(cfg, short_socket)
    try:
        async with grpc.aio.insecure_channel(f"unix:{short_socket}") as channel:
            stub = pbg.AgentRuntimeStub(channel)
            got = [
                json.loads(ev.agui_event_json)["type"]
                async for ev in stub.RunTurn(
                    pb.RunTurnRequest(thread_id="s1", user_message="go")
                )
            ]
        assert got == ["RUN_STARTED", "TEXT_MESSAGE_CONTENT", "RUN_FINISHED"]
    finally:
        await server.stop(grace=0)


async def test_interrupt_cancels_and_emits_terminal_event(short_socket, monkeypatch, cfg):
    started = asyncio.Event()

    async def hang_stream_turn(_cfg, **_kw):
        yield json.dumps({"type": "RUN_STARTED"})
        started.set()
        await asyncio.sleep(30)  # cancelled by Interrupt
        yield json.dumps({"type": "RUN_FINISHED"})  # never reached

    monkeypatch.setattr(graph_runner, "stream_turn", hang_stream_turn)

    server = await _start_servicer(cfg, short_socket)
    try:
        async with grpc.aio.insecure_channel(f"unix:{short_socket}") as channel:
            stub = pbg.AgentRuntimeStub(channel)

            async def _interrupt_once_started():
                await asyncio.wait_for(started.wait(), timeout=5)
                ack = await stub.Interrupt(pb.InterruptRequest(thread_id="s1"))
                assert ack.was_running is True

            interrupter = asyncio.create_task(_interrupt_once_started())
            events = [
                json.loads(ev.agui_event_json)
                async for ev in stub.RunTurn(
                    pb.RunTurnRequest(thread_id="s1", user_message="go")
                )
            ]
            await interrupter

        assert events[0]["type"] == "RUN_STARTED"
        assert events[-1]["type"] == "RUN_ERROR"
        assert "interrupt" in events[-1]["message"].lower()
    finally:
        await server.stop(grace=0)
