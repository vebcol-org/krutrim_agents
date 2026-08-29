"""Fixed, server-side sandbox policy.

This is constructed once from application config (per owner, via
`SandboxRegistry`'s `policy_factory`) and handed to `DockerSandboxBackend`. It
is never built from model/tool-call input — the `execute` tool the agent sees
only ever takes a `command` string, and the gRPC agent-runtime surface
(`krutrim_agent_grpc`) never accepts a policy field either — so there is no
code path for the agent to loosen these limits. Mounts and network mode are
operator-plane, resolved the same way `Project.sandbox_resource_overrides`.

Two run modes:

- ``"tool-backend"`` (default, unchanged): the agent graph runs in the host
  process and only its `execute`/filesystem tool calls are routed into the
  container. `/workspace` is an in-memory tmpfs, no host bind mounts.
- ``"in-sandbox"``: the whole agent graph runs *inside* the container via the
  `krutrim_agent_grpc` runtime server (TCP gRPC). `/workspace` and a per-owner
  staging directory are bind-mounted from the host. The container has a network
  interface (needed for the gRPC call-home) but runs behind the host's
  `AllowlistEgressProxy`, so its only unfiltered path off-box is the audited
  `HostBridge` call-home for LLM/tool egress.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class BindMount(BaseModel):
    """One host→container bind mount. `read_only` maps to docker-py's
    `mode: "ro"`. Used only in ``run_mode="in-sandbox"``."""

    host_path: str
    container_path: str
    read_only: bool = False


class SandboxPolicy(BaseModel):
    image: str = "krutrim_agent-sandbox:latest"

    timeout_seconds: int = 30
    """Hard wall-clock limit per `execute()` call, enforced via the `timeout` coreutil."""

    memory_mb: int = 512
    nano_cpus: int = 1_000_000_000
    """1e9 nano_cpus == 1 full CPU core."""

    pids_limit: int = 128

    network: Literal["none", "egress-allowlist", "bridge"] = "none"
    """``"none"`` — no egress at all; the default, used by
    ``run_mode="tool-backend"`` (the agent graph runs on the host, only its
    shell/file tool calls enter the container, so the container never needs a
    network). ``"egress-allowlist"`` — the container runs on a bridge network
    with ``HTTP(S)_PROXY`` pointed at the host's
    `krutrim_agent_sandbox.egress_proxy.AllowlistEgressProxy`, which forwards
    only connections whose host matches `egress_allowlist` and refuses the rest;
    this is what ``run_mode="in-sandbox"`` always uses (the allowlist is often
    empty — deny-all — leaving only the audited `HostBridge` call-home).
    ``"bridge"`` — normal, unfiltered Docker networking; an explicit escape
    hatch, not used by default."""

    egress_allowlist: list[str] = []
    """Hosts the ``"egress-allowlist"`` proxy will forward to — exact or
    dot-suffix match (``example.com`` also allows ``api.example.com``)."""

    egress_proxy_endpoint: str | None = None
    """``http://host:port`` of the host-side allowlist proxy, resolved by
    `SandboxRegistry` when it starts one. Injected as ``HTTP(S)_PROXY`` into the
    container only when ``network == "egress-allowlist"``."""

    publish_ports: dict[str, str] = {}
    """``{"<port>/tcp": "<host-ip>"}`` → docker-py ``ports=`` with a random host
    port. Used by the in-sandbox runtime to expose the AgentRuntime server on
    ``bind_host``."""

    network_name: str | None = None
    """User-defined Docker network to join (docker-py ``network=``). When set,
    the in-sandbox runtime reaches the container by name on this network instead
    of via a published host port — used when the backend itself is containerised
    (`AppSettings.sandbox_network`)."""

    workspace_tmpfs_mb: int = 256
    """In-memory /workspace for ``run_mode="tool-backend"`` — no host bind mount,
    so the sandbox has zero host filesystem access in that mode."""

    tmp_tmpfs_mb: int = 64

    max_output_bytes: int = 200_000
    """Per-command output cap; excess is truncated, not silently dropped."""

    run_mode: Literal["tool-backend", "in-sandbox"] = "tool-backend"

    binds: list[BindMount] = []
    """Host bind mounts for ``run_mode="in-sandbox"`` (staging dir, workspace,
    optional read-only agent source). Empty and ignored in ``"tool-backend"``."""

    runtime_command: list[str] | None = None
    """Container command for ``run_mode="in-sandbox"``. ``None`` → the image's
    own `CMD` (the gRPC runtime server). Ignored in ``"tool-backend"`` (which
    always runs ``sleep infinity``)."""

    env: dict[str, str] = {}
    """Extra environment for ``run_mode="in-sandbox"`` (e.g. a ``PYTHONPATH``
    when a dev agent-source dir is bind-mounted over the baked libs)."""

    working_dir: str = "/workspace"

    def to_docker_run_kwargs(self, *, container_name: str) -> dict[str, Any]:
        """Every kwarg for `docker.DockerClient.containers.run(image, **kwargs)`
        except the positional `image`. Covers both run modes; unit-tested per
        variant. The hardening set (read-only rootfs, non-root `sandbox` user,
        `cap_drop=ALL`, `no-new-privileges`, mem/cpu/pids caps) is identical
        across modes."""
        kwargs: dict[str, Any] = {
            "detach": True,
            "name": container_name,
            "network_disabled": self.network == "none" and not self.network_name,
            "mem_limit": f"{self.memory_mb}m",
            "nano_cpus": self.nano_cpus,
            "pids_limit": self.pids_limit,
            "read_only": True,
            "working_dir": self.working_dir,
            "user": "sandbox",
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges"],
            "auto_remove": False,
        }
        tmpfs = {"/tmp": f"size={self.tmp_tmpfs_mb}m,uid=1000,gid=1000,mode=1777"}

        if self.run_mode == "tool-backend":
            # In-memory /workspace, no bind mounts — the historical behaviour.
            tmpfs["/workspace"] = (
                f"size={self.workspace_tmpfs_mb}m,uid=1000,gid=1000,mode=1777"
            )
            kwargs["command"] = ["sleep", "infinity"]
        else:
            # /workspace comes from a bind mount instead; the container's own
            # CMD (or an explicit runtime_command) starts the gRPC server.
            kwargs["command"] = self.runtime_command
            if self.binds:
                kwargs["volumes"] = {
                    b.host_path: {
                        "bind": b.container_path,
                        "mode": "ro" if b.read_only else "rw",
                    }
                    for b in self.binds
                }
            if self.env:
                kwargs["environment"] = dict(self.env)
            if self.publish_ports:
                kwargs["ports"] = {
                    port: (host_ip, None) for port, host_ip in self.publish_ports.items()
                }
            if self.network_name:
                kwargs["network"] = self.network_name

        # Networked modes ("egress-allowlist" for the filtering proxy, "bridge"
        # for the unfiltered escape hatch) both need the container to resolve the
        # host by name; the allowlist mode also forces all traffic through the
        # proxy.
        if self.network in ("bridge", "egress-allowlist"):
            kwargs["extra_hosts"] = {"host.docker.internal": "host-gateway"}
        if self.network == "egress-allowlist" and self.egress_proxy_endpoint:
            # host.docker.internal is excluded so the gRPC call-home to
            # HostBridge never traverses the HTTP proxy.
            no_proxy = "localhost,127.0.0.1,host.docker.internal"
            proxy_env = {
                "HTTP_PROXY": self.egress_proxy_endpoint,
                "HTTPS_PROXY": self.egress_proxy_endpoint,
                "http_proxy": self.egress_proxy_endpoint,
                "https_proxy": self.egress_proxy_endpoint,
                "NO_PROXY": no_proxy,
                "no_proxy": no_proxy,
            }
            kwargs["environment"] = {**kwargs.get("environment", {}), **proxy_env}

        kwargs["tmpfs"] = tmpfs
        return kwargs
