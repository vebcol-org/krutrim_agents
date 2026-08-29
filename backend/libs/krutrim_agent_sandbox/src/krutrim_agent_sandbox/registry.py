"""Owner-scoped sandbox container registry.

Replaces `krutrim_agent_backend.main`'s old `{profile_key: DockerSandboxBackend}`
dict — containers are keyed by `owner_id` (resolved per session's sharing
policy via `resolve_owner_id`), not by agent profile. This module is the one
entry point `krutrim_agent_backend` request handlers call before any action that
needs a sandbox; nothing else in the app should construct a sandbox backend
directly.

Container-lifecycle *decisions* (idle teardown, hot-reload rehydration) are
made here and in the Celery reaper task, both reading/writing the same
`ContainerRecord` rows via `Storage` — this in-process `_backends` cache is
just a per-process shortcut to avoid reattaching to an already-known-warm
container on every call; the source of truth for whether a container exists
is always the `ContainerRecord`, never this cache alone.

Takes a bare `session_id` (not a `project_id`/`session_id` pair) — sessions
are keyed globally (see `krutrim_agent_management.base.Storage`), so a session_id
alone is enough to look one up regardless of whether its owner is an `Agent`
or a project-less `Chat`.
"""

from __future__ import annotations

import shutil
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from deepagents.backends.sandbox import BaseSandbox
from krutrim_agent_management.models import ContainerRecord

from krutrim_agent_sandbox.factory import create_sandbox_backend
from krutrim_agent_sandbox.policy import BindMount, SandboxPolicy
from krutrim_agent_sandbox.status_channel import PubSubBackend, publish_container_status

if TYPE_CHECKING:
    from krutrim_agent_management.base import Storage
    from krutrim_agents_core.providers.store import ProviderStore

_STAGING_MOUNT = "/run/krutrim_agent"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class InSandboxRuntime:
    """Present on the `AttachHandle` when the owning agent's profile runs the
    whole graph inside the container (`SandboxPolicy.run_mode == "in-sandbox"`).
    `agent_run.py` serves `HostBridge` on `host_bridge_bind` and drives the turn
    over `AgentRuntimeClient(run_endpoint)`. Both are TCP gRPC targets
    (``host:port``)."""

    staging_dir: Path
    run_endpoint: str
    host_bridge_bind: str
    session_id: str
    agent_key: str
    egress_proxy_bind: str
    """``<bind_host>:<port>`` for the host's allowlist egress proxy. Always set:
    the in-sandbox container always runs behind the proxy (the allowlist may be
    empty — deny-all — but the proxy still runs). `agent_run.py` starts an
    `AllowlistEgressProxy` here for the life of a turn."""
    egress_allowlist: list[str] = field(default_factory=list)


@dataclass
class AttachHandle:
    backend: BaseSandbox
    owner_id: str
    runtime: InSandboxRuntime | None = None


@dataclass
class _InSandboxPlan:
    policy: SandboxPolicy
    agent_key: str
    host_bridge_bind: str
    """TCP gRPC target (``<bind_host>:<port>``) the host's HostBridge binds."""
    egress_proxy_bind: str
    egress_allowlist: list[str] = field(default_factory=list)


_TCP_CONTAINER_PORT = "50051/tcp"


def _free_localhost_port(host: str = "127.0.0.1") -> int:
    import socket as _socket

    s = _socket.socket()
    try:
        s.bind((host, 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _existing_hb_port(staging: Path) -> int | None:
    """The HostBridge port a previously written `run.json` records, so a warm
    reattach keeps binding the address the already-running sandbox dials rather
    than allocating a fresh port the sandbox never learns about."""
    try:
        from krutrim_agent_grpc.run_config import RunConfig

        cfg = RunConfig.read(staging)
    except Exception:  # noqa: BLE001 - no/*unreadable* run.json → allocate fresh
        return None
    if ":" not in cfg.host_bridge_dial:
        return None
    port = cfg.host_bridge_dial.rsplit(":", 1)[1]
    return int(port) if port.isdigit() else None


class SandboxRegistry:
    def __init__(
        self,
        store: Storage,
        policy_factory: Callable[[str], SandboxPolicy] | None = None,
        backend_factory: Callable[[str, SandboxPolicy], BaseSandbox] | None = None,
        pubsub: PubSubBackend | None = None,
        provider_store: ProviderStore | None = None,
        enable_in_sandbox: bool = False,
        runtime_connect: Callable[[str], object] | None = None,
    ) -> None:
        self._store = store
        self._policy_factory = policy_factory or (lambda owner_id: SandboxPolicy())
        # Used only to filter keyless per-role model settings into an
        # in-sandbox staging dir; None → the container falls back to profile
        # defaults. Never carries API keys (see ProviderStore docstring).
        self._provider_store = provider_store
        # Off by default so every existing caller/test keeps the historical
        # tool-backend path untouched. `bootstrap.build_app_state` turns it on;
        # a profile in `settings.in_sandbox_agent_profiles` then runs the whole
        # graph inside its container over gRPC.
        self._enable_in_sandbox = enable_in_sandbox
        # Injectable readiness probe for tests (default: real gRPC Health poll).
        self._runtime_connect = runtime_connect
        # Injectable for tests (avoid touching real Docker); defaults to the
        # real runtime-selecting factory in production.
        self._backend_factory = backend_factory or create_sandbox_backend
        self._backends: dict[str, BaseSandbox] = {}
        self._lock = threading.Lock()
        # None (the default) means "no live-status publishing" — every
        # publish call site below checks for this, so the registry works
        # exactly as before if the caller doesn't wire a pub/sub backend in.
        self._pubsub = pubsub

    def _publish(self, owner_id: str, status: str, **extra) -> None:
        if self._pubsub is None:
            return
        try:
            publish_container_status(self._pubsub, owner_id, status, **extra)
        except Exception:  # noqa: BLE001 - live status is best-effort, must never break a real sandbox operation
            pass

    async def resolve_owner_id(self, session_id: str) -> tuple[str, str]:
        """(1) An explicit `attached_to_session_id` wins — the session's sandbox
        actions resolve to that other session's container. (2) Otherwise the
        session is its own owner (isolated by default).

        `sandbox_sharing` never affects container identity — "session-shared"/
        "project-shared" only gate the separate cross-agent messaging tool (a
        communication channel between two still-separate containers), not a
        merge of them. `owner_kind` is always "session" through this path;
        "project" is reserved and unused, "channel" (future bot integrations)
        is addressed directly by channel id, never resolved from a session.
        """
        session = await self._store.get_session(session_id)
        if session.attached_to_session_id:
            return session.attached_to_session_id, "session"
        return session_id, "session"

    async def get_or_create(self, session_id: str) -> AttachHandle:
        owner_id, owner_kind = await self.resolve_owner_id(session_id)
        record = await self._store.get_container(owner_id)

        # `run_mode="in-sandbox"` profiles (settings.in_sandbox_agent_profiles)
        # build a per-owner staging dir + policy here; everything else keeps
        # the historical tool-backend path unchanged. The scoped export only
        # runs on a cold start — rewriting the staging store/ under a live
        # container would race its own writes.
        is_cold = record is None or record.status == "stopped"
        in_sandbox = await self._in_sandbox_plan(
            session_id, refresh_staging=is_cold
        )

        if record is not None and record.status != "stopped":
            policy = (
                in_sandbox.policy if in_sandbox else self._policy_factory(owner_id)
            )
            backend = self._backends.get(owner_id)
            if backend is None:
                # Process restarted (or this is a different process entirely)
                # but the container itself may still be running — reattach
                # rather than assuming it's gone.
                backend = self._backend_factory(owner_id, policy)
                self._backends[owner_id] = backend
            record.ref_count += 1
            record.status = "running"
            record.last_active_at = _now_iso()
            await self._store.upsert_container(record)
            self._publish(owner_id, "running", ref_count=record.ref_count)
            runtime = await self._connect_runtime(owner_id, in_sandbox)
            return AttachHandle(backend=backend, owner_id=owner_id, runtime=runtime)

        # Missing or stopped record: hot-reload from the persisted workspace mirror.
        self._publish(owner_id, "starting")
        if in_sandbox:
            policy = in_sandbox.policy
            # The staging dir already carries the session's workspace + checkpoint
            # (via export_scope); the container bind-mounts them, so there's no
            # base64 hydrate step.
            backend = self._backend_factory(owner_id, policy)
            backend.hydrate([])
        else:
            policy = self._policy_factory(owner_id)
            backend = self._backend_factory(owner_id, policy)
            saved_paths = await self._store.read_workspace_files(owner_id)
            files: list[tuple[str, bytes]] = []
            for path in saved_paths:
                content = await self._store.read_workspace_file(owner_id, path)
                if content is not None:
                    files.append((path, content))
            backend.hydrate(files)
        self._backends[owner_id] = backend

        now = _now_iso()
        owner_session = await self._store.get_session(owner_id)
        new_record = ContainerRecord(
            owner_id=owner_id,
            owner_kind=owner_kind,
            project_id=owner_session.project_id,
            container_name=f"krutrim_agent-sandbox-{owner_id}",
            status="running",
            ref_count=1,
            created_at=record.created_at if record is not None else now,
            last_active_at=now,
            policy_snapshot=policy.model_dump(),
        )
        await self._store.upsert_container(new_record)
        self._publish(owner_id, "running", ref_count=1)
        runtime = await self._connect_runtime(owner_id, in_sandbox)
        return AttachHandle(backend=backend, owner_id=owner_id, runtime=runtime)

    async def release(self, owner_id: str) -> None:
        record = await self._store.get_container(owner_id)
        if record is None:
            return
        record.ref_count = max(0, record.ref_count - 1)
        if record.ref_count == 0:
            record.status = "idle"
        await self._store.upsert_container(record)
        self._publish(owner_id, record.status, ref_count=record.ref_count)
        await self._import_in_sandbox_scope(owner_id)

    # -- in-sandbox (run_mode="in-sandbox") staging ----------------------

    def _staging_dir(self, owner_id: str) -> Path:
        from krutrim_agent_management.config import settings

        return Path(settings.storage_root) / "sandboxes" / owner_id

    async def _in_sandbox_plan(
        self, session_id: str, *, refresh_staging: bool
    ) -> _InSandboxPlan | None:
        """The container-run plan if the session's owning agent runs in-sandbox,
        else None. When `refresh_staging` is True (cold start) it (re)builds the
        per-owner staging dir; otherwise it only re-assembles the plan."""
        if not self._enable_in_sandbox:
            return None
        from krutrim_agent_management.config import settings

        session = await self._store.get_session(session_id)
        if session.owner_type != "agent":
            return None
        agent = await self._store.get_agent(session.owner_id)
        if agent.agent_key not in settings.in_sandbox_agent_profiles:
            return None

        owner_id, _ = await self.resolve_owner_id(session_id)
        staging = self._staging_dir(owner_id)
        bind_host = settings.sandbox_bind_host
        callback_host = settings.sandbox_callback_host
        network_name = settings.sandbox_network

        # gRPC is always TCP: publish the container's AgentRuntime on `bind_host`
        # (or reach it by container name on a shared Docker network) and let the
        # container dial the host's HostBridge back via `callback_host`. On a
        # warm reattach reuse the port the sandbox already recorded — a fresh one
        # would only be written into run.json on a cold start.
        hb_port = (
            None if refresh_staging else _existing_hb_port(staging)
        ) or _free_localhost_port(bind_host)
        host_bridge_bind = f"{bind_host}:{hb_port}"
        host_bridge_dial = f"{callback_host}:{hb_port}"
        runtime_bind = "0.0.0.0:50051"

        if refresh_staging:
            await self._store.export_scope(
                agent.project_id, agent.agent_id, session.session_id, staging
            )
            self._stage_harness(
                Path(settings.harness_dir), staging / "harness", agent.agent_key
            )
            self._write_provider_settings(staging, agent.agent_key)
            self._write_run_config(
                staging,
                agent,
                session,
                runtime_bind=runtime_bind,
                host_bridge_dial=host_bridge_dial,
            )
        else:
            (staging / "workspace").mkdir(parents=True, exist_ok=True)

        base = self._policy_factory(owner_id)
        env: dict[str, str] = {}
        binds = [
            BindMount(host_path=str(staging), container_path=_STAGING_MOUNT),
            BindMount(
                host_path=str(staging / "workspace"), container_path="/workspace"
            ),
        ]
        if settings.sandbox_agent_source_dir:
            src = Path(settings.sandbox_agent_source_dir)
            binds.append(
                BindMount(
                    host_path=str(src),
                    container_path="/opt/krutrim_agent/src",
                    read_only=True,
                )
            )
            pkg_srcs = sorted(str(p) for p in src.glob("*/src"))
            container_srcs = [
                f"/opt/krutrim_agent/src/{Path(p).parent.name}/src" for p in pkg_srcs
            ]
            if container_srcs:
                env["PYTHONPATH"] = ":".join(container_srcs)

        update: dict = {"run_mode": "in-sandbox", "binds": binds, "env": env}

        # TCP gRPC means the container needs a network interface, so it can't run
        # `network_disabled`. Default posture: it runs behind the host's
        # AllowlistEgressProxy (HTTP(S)_PROXY), which forwards only
        # `sandbox_egress_allowlist` hosts and denies everything else — often an
        # empty allowlist (deny-all), leaving the audited HostBridge call-home as
        # the only unfiltered path off-box. The proxy port is pinned here (baked
        # into the container env) and the proxy is (re)bound to it per turn by
        # agent_run.py, mirroring host_bridge_bind.
        egress_allowlist = list(settings.sandbox_egress_allowlist or [])
        egress_port = _free_localhost_port(bind_host)
        egress_proxy_bind = f"{bind_host}:{egress_port}"
        update["network"] = "egress-allowlist"
        update["egress_allowlist"] = egress_allowlist
        update["egress_proxy_endpoint"] = f"http://{callback_host}:{egress_port}"
        if network_name:
            # Backend and sandbox share a user network and reach each other by
            # container name — no host port publishing needed.
            update["network_name"] = network_name
        else:
            update["publish_ports"] = {_TCP_CONTAINER_PORT: bind_host}

        policy = base.model_copy(update=update)
        return _InSandboxPlan(
            policy=policy,
            agent_key=agent.agent_key,
            host_bridge_bind=host_bridge_bind,
            egress_proxy_bind=egress_proxy_bind,
            egress_allowlist=egress_allowlist,
        )

    @staticmethod
    def _stage_harness(harness_dir: Path, dest: Path, agent_key: str) -> None:
        """Copy only this profile's harness content (skills/common + skills/<key>
        + prompts + memory/<key>) into the bind-mounted, read-only-at-runtime
        `harness/` — never another profile's memory or skills."""
        dest.mkdir(parents=True, exist_ok=True)
        wanted = [
            ("skills/common", harness_dir / "skills" / "common"),
            (f"skills/{agent_key}", harness_dir / "skills" / agent_key),
            ("prompts", harness_dir / "prompts"),
            (f"memory/{agent_key}", harness_dir / "memory" / agent_key),
        ]
        for rel, src in wanted:
            if src.is_dir():
                target = dest / rel
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(src, target)

    def _write_provider_settings(self, staging: Path, agent_key: str) -> None:
        import json

        if self._provider_store is None:
            return
        try:
            roles = {
                role: ms.model_dump()
                for role, ms in self._provider_store.get_all(agent_key).items()
            }
        except Exception:  # noqa: BLE001 - fall back to profile defaults in-container
            return
        (staging / "provider_settings.json").write_text(
            json.dumps({agent_key: roles}, indent=2)
        )

    def _write_run_config(
        self,
        staging: Path,
        agent,
        session,
        *,
        runtime_bind: str,
        host_bridge_dial: str,
    ) -> None:
        from krutrim_agent_grpc.run_config import RunConfig

        RunConfig(
            agent_key=agent.agent_key,
            agent_id=agent.agent_id,
            project_id=agent.project_id,
            session_id=session.session_id,
            runtime_bind=runtime_bind,
            host_bridge_dial=host_bridge_dial,
        ).write(staging)

    def _resolve_run_endpoint(self, owner_id: str) -> str:
        """TCP gRPC target the host uses to dial the container's AgentRuntime.
        `sandbox_network` set → the container name on that shared network
        (`<name>:50051`, no publish); otherwise `sandbox_dial_host` + the host
        port Docker published for 50051/tcp."""
        from krutrim_agent_management.config import settings

        name = f"krutrim_agent-sandbox-{owner_id}"
        if settings.sandbox_network:
            return f"{name}:50051"
        import docker

        container = docker.from_env().containers.get(name)
        bindings = (
            container.attrs.get("NetworkSettings", {}).get("Ports") or {}
        ).get(_TCP_CONTAINER_PORT) or []
        if not bindings:
            raise RuntimeError(
                f"container {name} has no published {_TCP_CONTAINER_PORT} — "
                "cannot reach its AgentRuntime over TCP"
            )
        return f"{settings.sandbox_dial_host}:{bindings[0]['HostPort']}"

    async def _connect_runtime(
        self, owner_id: str, plan: _InSandboxPlan | None
    ) -> InSandboxRuntime | None:
        if plan is None:
            return None
        from krutrim_agent_management.config import settings

        staging = self._staging_dir(owner_id)
        run_endpoint = self._resolve_run_endpoint(owner_id)

        try:
            if self._runtime_connect is not None:
                await self._runtime_connect(run_endpoint)
            else:
                from krutrim_agent_grpc import AgentRuntimeClient

                async with AgentRuntimeClient(run_endpoint) as client:
                    await client.wait_healthy(
                        timeout=settings.sandbox_runtime_health_timeout
                    )
        except Exception as exc:
            self._publish(owner_id, "error", detail=str(exc))
            raise

        return InSandboxRuntime(
            staging_dir=staging,
            run_endpoint=run_endpoint,
            host_bridge_bind=plan.host_bridge_bind,
            session_id=owner_id,
            agent_key=plan.agent_key,
            egress_proxy_bind=plan.egress_proxy_bind,
            egress_allowlist=plan.egress_allowlist,
        )

    async def _import_in_sandbox_scope(self, owner_id: str) -> None:
        staging = self._staging_dir(owner_id)
        if not (staging / "out").exists():
            return
        try:
            await self._store.import_scope(owner_id, staging)
        except Exception:  # noqa: BLE001 - best-effort sync; a reap will retry
            pass

    async def interrupt(self, session_id: str) -> bool:
        """Cancel the in-flight turn of an in-sandbox agent. Returns True if a
        turn was actually running. No-op (False) for tool-backend sessions or
        when the runtime isn't reachable."""
        owner_id, _ = await self.resolve_owner_id(session_id)
        if not (self._staging_dir(owner_id) / "run.json").exists():
            return False
        from krutrim_agent_grpc import AgentRuntimeClient

        try:
            endpoint = self._resolve_run_endpoint(owner_id)
            async with AgentRuntimeClient(endpoint) as client:
                return await client.interrupt(session_id)
        except Exception:  # noqa: BLE001 - interrupt is best-effort
            return False

    def local_backend(self, owner_id: str) -> BaseSandbox | None:
        return self._backends.get(owner_id)

    def close_all(self) -> None:
        """Best-effort teardown of every backend this process started —
        called on app shutdown. Not part of the idle-reaper's job (that's a
        separate, time-based policy in a Celery task); this is just
        "the process is exiting, don't leak running containers behind it"."""
        for backend in self._backends.values():
            close = getattr(backend, "close", None)
            if callable(close):
                close()
        self._backends.clear()
