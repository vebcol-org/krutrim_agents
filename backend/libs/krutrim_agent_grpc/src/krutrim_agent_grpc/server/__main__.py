"""Entry point for the in-sandbox AgentRuntime server (the image's CMD).

    python -m krutrim_agent_grpc.server        # endpoints from run.json

`--health-check` dials the runtime on ``127.0.0.1:50051`` and calls `Health`,
exiting 0/1 — that's the image's HEALTHCHECK. It works before `run.json` exists.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import signal
import sys
import time
from pathlib import Path

DEFAULT_STAGING = "/run/krutrim_agent"
HEALTHCHECK_TARGET = "127.0.0.1:50051"
DEFAULT_BIND = "0.0.0.0:50051"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="krutrim_agent_grpc.server")
    p.add_argument("--staging-dir", default=DEFAULT_STAGING)
    p.add_argument("--health-check", action="store_true")
    p.add_argument("--config-wait-seconds", type=float, default=15.0)
    return p.parse_args(argv)


def _dial_health(target: str) -> bool:
    import grpc

    from krutrim_agent_grpc.proto import agent_runtime_pb2 as pb
    from krutrim_agent_grpc.proto import agent_runtime_pb2_grpc as pbg

    try:
        with grpc.insecure_channel(target) as channel:
            reply = pbg.AgentRuntimeStub(channel).Health(pb.HealthRequest(), timeout=4)
        return bool(reply.ready)
    except Exception:  # noqa: BLE001
        return False


def _health_check() -> int:
    if _dial_health(HEALTHCHECK_TARGET):
        return 0
    print("health check failed", file=sys.stderr)
    return 1


def _wait_for_config(staging_dir: Path, timeout: float):
    from krutrim_agent_grpc.run_config import RUN_CONFIG_NAME, RunConfig

    deadline = time.monotonic() + timeout
    path = staging_dir / RUN_CONFIG_NAME
    while time.monotonic() < deadline:
        if path.is_file():
            return RunConfig.read(staging_dir)
        time.sleep(0.25)
    raise FileNotFoundError(f"{path} not written within {timeout}s")


async def _serve(bind: str, cfg) -> None:
    import grpc

    from krutrim_agent_grpc.proto import agent_runtime_pb2_grpc as pbg
    from krutrim_agent_grpc.server.servicer import AgentRuntimeServicer

    stop_event = asyncio.Event()
    server = grpc.aio.server()
    pbg.add_AgentRuntimeServicer_to_server(
        AgentRuntimeServicer(cfg, stop_event), server
    )
    server.add_insecure_port(bind)
    await server.start()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()
    await server.stop(grace=5)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    staging_dir = Path(args.staging_dir)
    if args.health_check:
        return _health_check()

    cfg = _wait_for_config(staging_dir, args.config_wait_seconds)

    # Set env BEFORE any krutrim_agents_core / krutrim_agent_management import so
    # `settings` resolves the mounted paths, not the image's baked ones.
    os.environ.setdefault("KRUTRIM_AGENT_RUNTIME_IN_SANDBOX", "1")
    os.environ["KRUTRIM_AGENT_HARNESS_DIR"] = cfg.harness_dir
    os.environ["KRUTRIM_AGENT_STORAGE_ROOT"] = cfg.storage_root
    os.environ["KRUTRIM_AGENT_RUNS_DIR_OVERRIDE"] = cfg.runs_dir
    os.environ["KRUTRIM_AGENT_HOST_BRIDGE_ENDPOINT"] = cfg.host_bridge_dial
    os.environ["KRUTRIM_AGENT_GRAPH_RECURSION_LIMIT"] = str(cfg.recursion_limit)
    # The image rootfs is read-only; keep every default path AppSettings might
    # touch (log_dir's default_factory calls default_storage_root() directly,
    # which mkdirs ~/.krutrim_agent) inside the writable staging mount.
    os.environ["KRUTRIM_AGENT_LOG_DIR"] = f"{cfg.out_dir}/logs"
    Path(cfg.out_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.runs_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.out_dir, "logs").mkdir(parents=True, exist_ok=True)

    bind = cfg.runtime_bind or DEFAULT_BIND
    asyncio.run(_serve(bind, cfg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
