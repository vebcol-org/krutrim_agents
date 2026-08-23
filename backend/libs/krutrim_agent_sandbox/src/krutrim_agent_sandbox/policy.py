"""Fixed, server-side sandbox policy.

This is constructed once from application config and handed to
`DockerSandboxBackend`. It is never built from model/tool-call input — the
`execute` tool the agent sees only ever takes a `command` string, so there is
no code path for the agent to loosen these limits.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SandboxPolicy(BaseModel):
    image: str = "krutrim_agent-sandbox:latest"

    timeout_seconds: int = 30
    """Hard wall-clock limit per `execute()` call, enforced via the `timeout` coreutil."""

    memory_mb: int = 512
    nano_cpus: int = 1_000_000_000
    """1e9 nano_cpus == 1 full CPU core."""

    pids_limit: int = 128

    network: Literal["none"] = "none"
    """Only "none" is implemented for v1 — no egress at all."""

    workspace_tmpfs_mb: int = 256
    """In-memory /workspace — no host bind mount, so the sandbox has zero host filesystem access."""

    tmp_tmpfs_mb: int = 64

    max_output_bytes: int = 200_000
    """Per-command output cap; excess is truncated, not silently dropped."""
