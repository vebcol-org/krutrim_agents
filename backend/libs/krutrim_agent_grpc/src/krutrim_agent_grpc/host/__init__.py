"""Host-side HostBridge server — the sandbox's audited route off-box.

`agent_run.py` starts one of these per run on a TCP port (``<bind_host>:<port>``)
the container dials back to. Every `ChatComplete` (proxied LLM) and
`InvokeHostTool` (web_search / fetch_url / rag) is executed here, on the host,
and logged — the container has no provider credentials and any direct egress is
filtered by the host's `AllowlistEgressProxy`.
"""

from krutrim_agent_grpc.host.bridge import HostBridgeServicer, serve_host_bridge

__all__ = ["HostBridgeServicer", "serve_host_bridge"]
