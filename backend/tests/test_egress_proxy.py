"""`AllowlistEgressProxy` — host allowlisting for `SandboxPolicy.network ==
"egress-allowlist"`, plus the docker-run-kwargs it produces."""

from __future__ import annotations

import asyncio

import pytest
from krutrim_agent_sandbox import AllowlistEgressProxy, host_allowed, serve_egress_proxy
from krutrim_agent_sandbox.policy import SandboxPolicy


@pytest.mark.parametrize(
    ("host", "allowlist", "expected"),
    [
        ("example.com", ["example.com"], True),
        ("api.example.com", ["example.com"], True),
        ("api.example.com", [".example.com"], True),
        ("EXAMPLE.COM", ["example.com"], True),
        ("evil.com", ["example.com"], False),
        ("notexample.com", ["example.com"], False),
        ("example.com.evil.com", ["example.com"], False),
        ("anything", [], False),
        ("127.0.0.1", ["127.0.0.1"], True),
    ],
)
def test_host_allowed(host, allowlist, expected):
    assert host_allowed(host, allowlist) is expected


async def _echo_server():
    async def handle(reader, writer):
        while True:
            data = await reader.read(1024)
            if not data:
                break
            writer.write(data)
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


async def test_connect_tunnels_an_allowed_host():
    echo, echo_port = await _echo_server()
    events: list[dict] = []
    try:
        async with serve_egress_proxy(
            ["127.0.0.1"], on_event=events.append
        ) as proxy:
            reader, writer = await asyncio.open_connection(proxy.host, proxy.port)
            writer.write(
                f"CONNECT 127.0.0.1:{echo_port} HTTP/1.1\r\n\r\n".encode()
            )
            await writer.drain()
            status = await reader.readline()
            assert b"200" in status
            # drain the rest of the CONNECT response headers
            while (await reader.readline()) not in (b"\r\n", b""):
                pass
            writer.write(b"ping")
            await writer.drain()
            assert await reader.readexactly(4) == b"ping"
            writer.close()
    finally:
        echo.close()
    assert events and events[0]["type"] == "egress_allow"
    assert events[0]["host"] == "127.0.0.1"


async def test_connect_refuses_a_host_off_the_allowlist():
    echo, echo_port = await _echo_server()
    events: list[dict] = []
    try:
        async with serve_egress_proxy(
            ["example.com"], on_event=events.append
        ) as proxy:
            reader, writer = await asyncio.open_connection(proxy.host, proxy.port)
            writer.write(
                f"CONNECT 127.0.0.1:{echo_port} HTTP/1.1\r\n\r\n".encode()
            )
            await writer.drain()
            status = await reader.readline()
            assert b"403" in status
            writer.close()
    finally:
        echo.close()
    assert events and events[0]["type"] == "egress_deny"


async def test_proxy_endpoint_is_a_usable_http_url():
    proxy = AllowlistEgressProxy(["example.com"])
    host, port = await proxy.start()
    try:
        assert proxy.endpoint == f"http://{host}:{port}"
    finally:
        await proxy.stop()


def test_egress_allowlist_policy_injects_proxy_env_and_opens_networking():
    policy = SandboxPolicy(
        run_mode="in-sandbox",
        network="egress-allowlist",
        egress_allowlist=["pypi.org"],
        egress_proxy_endpoint="http://host.docker.internal:9123",
    )
    kw = policy.to_docker_run_kwargs(container_name="c")
    assert kw["network_disabled"] is False
    assert kw["extra_hosts"] == {"host.docker.internal": "host-gateway"}
    assert kw["environment"]["HTTPS_PROXY"] == "http://host.docker.internal:9123"
    # host.docker.internal is excluded so the gRPC call-home never proxies
    assert "host.docker.internal" in kw["environment"]["NO_PROXY"]


def test_egress_allowlist_without_endpoint_still_no_proxy_env():
    policy = SandboxPolicy(run_mode="in-sandbox", network="egress-allowlist")
    kw = policy.to_docker_run_kwargs(container_name="c")
    assert kw["network_disabled"] is False
    assert "environment" not in kw or "HTTP_PROXY" not in kw.get("environment", {})


def test_tool_backend_default_policy_has_no_networking_keys():
    kw = SandboxPolicy().to_docker_run_kwargs(container_name="c")
    assert kw["network_disabled"] is True
    assert "extra_hosts" not in kw
    assert "environment" not in kw
