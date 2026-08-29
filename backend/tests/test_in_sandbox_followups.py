"""In-sandbox follow-ups: cross-agent `message_agent` proxied over HostBridge,
and the in-graph `RunLoggingMiddleware`."""

from __future__ import annotations

import json
import os
import tempfile

import grpc
import pytest
from krutrim_agent_grpc.host import serve_host_bridge
from krutrim_agent_grpc.proto import agent_runtime_pb2 as pb
from krutrim_agent_grpc.proto import agent_runtime_pb2_grpc as pbg
from krutrim_agent_grpc.proxy_tools import build_message_agent_proxy
from krutrim_agents_core.harness.run_logging import RunLoggingMiddleware


@pytest.fixture
def short_socket():
    # macOS caps AF_UNIX paths at ~103 chars — pytest's tmp_path is too deep.
    yield os.path.join(tempfile.mkdtemp(), "hb.sock")


async def _invoke_host_tool(sock: str, tool: str, args: dict):
    async with grpc.aio.insecure_channel(f"unix:{sock}") as ch:
        stub = pbg.HostBridgeStub(ch)
        return await stub.InvokeHostTool(
            pb.HostToolRequest(
                tool=tool, args_json=json.dumps(args), thread_id="s1"
            ),
            timeout=10,
        )


# -- message_agent over HostBridge --------------------------------------


async def test_message_agent_unavailable_without_a_handler(short_socket):
    async with serve_host_bridge(f"unix:{short_socket}", thread_id="s1"):
        reply = await _invoke_host_tool(
            short_socket, "message_agent", {"container_id": "s2", "message": "hi"}
        )
    assert reply.error and "not available" in reply.error


async def test_message_agent_routes_to_the_bound_handler(short_socket):
    seen: dict[str, str] = {}

    async def handler(target: str, message: str) -> str:
        seen["target"], seen["message"] = target, message
        return f"reply from {target}"

    async with serve_host_bridge(
        f"unix:{short_socket}", thread_id="s1", message_agent_handler=handler
    ):
        reply = await _invoke_host_tool(
            short_socket, "message_agent", {"container_id": "s2", "message": "ping"}
        )
    assert reply.error == ""
    assert json.loads(reply.result_json) == "reply from s2"
    assert seen == {"target": "s2", "message": "ping"}


async def test_message_agent_handler_error_is_returned_not_raised(short_socket):
    async def handler(_target: str, _message: str) -> str:
        raise RuntimeError("peer exploded")

    async with serve_host_bridge(
        f"unix:{short_socket}", thread_id="s1", message_agent_handler=handler
    ):
        reply = await _invoke_host_tool(
            short_socket, "message_agent", {"container_id": "s2", "message": "x"}
        )
    assert "peer exploded" in reply.error


def test_message_agent_proxy_tool_matches_the_real_signature():
    tool = build_message_agent_proxy()
    assert tool.name == "message_agent"
    assert set(tool.args) == {"container_id", "message"}


def test_run_turn_request_carries_the_cross_agent_flag():
    assert pb.RunTurnRequest(thread_id="s1", cross_agent_enabled=True).cross_agent_enabled


# -- RunLoggingMiddleware ---------------------------------------------


class _CapLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict]] = []

    def log(self, event_type: str, payload: dict) -> None:
        self.records.append((event_type, payload))


class _FakeModelReq:
    def __init__(self) -> None:
        self.messages = [1, 2, 3]
        self.tools: list = []


class _FakeAIMessage:
    def __init__(self) -> None:
        self.content = "hello world"
        self.tool_calls: list = []
        self.usage_metadata = {"input_tokens": 10, "output_tokens": 5}


class _FakeModelResp:
    def __init__(self) -> None:
        self.result = [_FakeAIMessage()]


async def test_middleware_logs_a_model_request_response_pair():
    cap = _CapLogger()
    mw = RunLoggingMiddleware(cap)

    async def handler(_req):
        return _FakeModelResp()

    resp = await mw.awrap_model_call(_FakeModelReq(), handler)

    assert isinstance(resp, _FakeModelResp)
    assert [t for t, _ in cap.records] == ["model_request", "model_response"]
    _, payload = cap.records[1]
    assert payload["chars"] == len("hello world")
    assert payload["usage"] == {"input_tokens": 10, "output_tokens": 5}
    assert payload["source"] == "agent_graph"


class _FakeToolReq:
    def __init__(self) -> None:
        self.tool_call = {"name": "web_search", "id": "call_1", "args": {"query": "x"}}
        self.tool = None
        self.state: dict = {}
        self.runtime = None


class _FakeToolResult:
    def __init__(self) -> None:
        self.content = "some result text"
        self.status = "success"


async def test_middleware_logs_a_tool_request_response_pair():
    cap = _CapLogger()
    mw = RunLoggingMiddleware(cap)

    async def handler(_req):
        return _FakeToolResult()

    await mw.awrap_tool_call(_FakeToolReq(), handler)

    assert [t for t, _ in cap.records] == ["tool_request", "tool_response"]
    assert cap.records[0][1]["tool"] == "web_search"
    assert cap.records[0][1]["args"] == {"query": "x"}
    assert cap.records[0][1]["tool_call_id"] == "call_1"
    assert cap.records[1][1]["chars"] == len("some result text")
    assert cap.records[1][1]["status"] == "success"


async def test_middleware_never_breaks_a_run_when_logging_fails():
    class _Boom:
        def log(self, *_a, **_k):
            raise OSError("disk full")

    mw = RunLoggingMiddleware(_Boom())

    async def handler(_req):
        return _FakeModelResp()

    # must not raise despite every log() call blowing up
    assert isinstance(await mw.awrap_model_call(_FakeModelReq(), handler), _FakeModelResp)


def test_run_logger_accepts_an_explicit_path(tmp_path):
    from krutrim_agents_core.harness.runs import RunLogger

    path = tmp_path / "nested" / "s1.jsonl"
    rl = RunLogger("research", "s1", path=path)
    rl.log("model_request", {"messages": 2})
    line = json.loads(path.read_text().splitlines()[0])
    assert line["type"] == "model_request" and line["messages"] == 2


def test_build_agent_accepts_extra_middleware(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    from krutrim_agent_sandbox.docker_backend import DockerSandboxBackend
    from krutrim_agents_core.builder import build_agent
    from krutrim_agents_core.providers.store import ProviderStore
    from krutrim_agents_core.registry import all_profiles

    store = ProviderStore(tmp_path / "s.json")
    key, profile = next(iter(all_profiles().items()))
    graph = build_agent(
        profile,
        store,
        DockerSandboxBackend(owner_id=key),
        extra_middleware=[RunLoggingMiddleware(_CapLogger())],
    )
    assert graph.name == key
