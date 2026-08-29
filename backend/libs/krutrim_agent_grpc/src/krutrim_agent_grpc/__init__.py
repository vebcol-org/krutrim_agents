"""gRPC contract + client/server for the in-sandbox agent runtime.

Two services (see `proto/agent_runtime.proto`), both over **TCP gRPC**:

- **AgentRuntime** — runs inside the sandbox container, bound to
  ``0.0.0.0:50051``. Drives one agent turn per `RunTurn` and cancels it with
  `Interrupt`. The host reaches it via a published host port or by container
  name on a shared Docker network.
- **HostBridge** — runs on the host for the life of a turn, bound to
  ``<bind_host>:<port>``. The sandboxed agent calls back through it for every
  LLM completion and host-side tool, keeping the host the sole egress point /
  audit trail. Direct egress (if any) is filtered by the host's
  `AllowlistEgressProxy`.

`STAGING_MOUNT` is the single bind mount into the container
(`<storage_root>/sandboxes/<owner_id>/` → `/run/krutrim_agent`); `run.json`
inside it carries the per-run config (no credentials).
"""

from __future__ import annotations

STAGING_MOUNT = "/run/krutrim_agent"
RUN_CONFIG_NAME = "run.json"


def __getattr__(name: str):
    # Lazy re-exports so `import krutrim_agent_grpc` stays cheap (no grpc /
    # langchain import) for callers that only need the constants above.
    if name == "AgentRuntimeClient":
        from krutrim_agent_grpc.client import AgentRuntimeClient

        return AgentRuntimeClient
    if name == "RunConfig":
        from krutrim_agent_grpc.run_config import RunConfig

        return RunConfig
    if name == "serve_host_bridge":
        from krutrim_agent_grpc.host import serve_host_bridge

        return serve_host_bridge
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "RUN_CONFIG_NAME",
    "STAGING_MOUNT",
    "AgentRuntimeClient",
    "RunConfig",
    "serve_host_bridge",
]
