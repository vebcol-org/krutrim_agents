"""Check the health of in-sandbox AgentRuntime containers.

    uv run python scripts/sandbox_health.py               # every sandbox container
    uv run python scripts/sandbox_health.py <session-id>  # just one

For each container it prints Docker's own healthcheck verdict and the result of
calling the `AgentRuntime.Health` gRPC directly (over the published host port,
the way `SandboxRegistry` resolves it). Exit code is non-zero if any checked
runtime is not ready.
"""

from __future__ import annotations

import sys

import docker
import grpc
from krutrim_agent_grpc.proto import agent_runtime_pb2 as pb
from krutrim_agent_grpc.proto import agent_runtime_pb2_grpc as pbg

_PREFIX = "krutrim_agent-sandbox-"
_TCP_CONTAINER_PORT = "50051/tcp"


def _endpoint(container) -> str:
    """gRPC target for this container's AgentRuntime — its published host port
    for 50051/tcp."""
    ports = (container.attrs.get("NetworkSettings", {}).get("Ports") or {}).get(
        _TCP_CONTAINER_PORT
    )
    if ports:
        return f"127.0.0.1:{ports[0]['HostPort']}"
    return "127.0.0.1:50051"


def _grpc_health(target: str) -> tuple[bool, str]:
    try:
        with grpc.insecure_channel(target) as ch:
            reply = pbg.AgentRuntimeStub(ch).Health(pb.HealthRequest(), timeout=5)
        return bool(reply.ready), reply.detail or ""
    except grpc.RpcError as exc:
        return False, exc.details() or str(exc)


def main(argv: list[str]) -> int:
    client = docker.from_env()
    names = [f"{_PREFIX}{argv[0]}"] if argv else None
    containers = [
        c
        for c in client.containers.list(all=True)
        if c.name.startswith(_PREFIX) and (names is None or c.name in names)
    ]
    if not containers:
        print("no sandbox containers found" + (f" for {argv[0]}" if argv else ""))
        return 1

    worst = 0
    for c in containers:
        health = (c.attrs.get("State", {}).get("Health") or {}).get("Status", "n/a")
        target = _endpoint(c)
        ready, detail = _grpc_health(target)
        flag = "OK " if ready else "BAD"
        print(f"[{flag}] {c.name}")
        print(f"       status={c.status} docker-health={health}")
        print(f"       endpoint={target} grpc-ready={ready}" + (f" ({detail})" if detail else ""))
        if not ready:
            worst = 1
    return worst


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
