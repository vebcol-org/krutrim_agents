"""`SandboxRegistry` in-sandbox orchestration against real Docker + the real
sandbox image: staging-dir build, container start, gRPC health over the
resolved endpoint, and `release` -> `import_scope`.

Complements `test_in_sandbox_runtime.py` (servicer unit tests, no Docker) and
`test_hot_reload.py` (tool-backend registry + Docker). Skips under the same
`requires_sandbox` condition.
"""

from __future__ import annotations

import asyncio
import json
import shutil

import grpc
from krutrim_agent_grpc.proto import agent_runtime_pb2 as pb
from krutrim_agent_grpc.proto import agent_runtime_pb2_grpc as pbg
from krutrim_agent_management import LocalStorage
from krutrim_agent_sandbox.registry import SandboxRegistry
from krutrim_agents_core.providers.store import ProviderStore
from test_sandbox import requires_sandbox


async def _health_ok(endpoint: str) -> bool:
    async with grpc.aio.insecure_channel(endpoint) as ch:
        for _ in range(60):
            try:
                r = await pbg.AgentRuntimeStub(ch).Health(pb.HealthRequest(), timeout=3)
                if r.ready:
                    return True
            except grpc.aio.AioRpcError:
                pass
            await asyncio.sleep(0.5)
    return False


@requires_sandbox
async def test_get_or_create_builds_staging_and_starts_grpc_runtime(tmp_path):
    storage = LocalStorage(tmp_path / "store")
    provider_store = ProviderStore(tmp_path / "providers.json")
    project = await storage.create_project("E2E")
    agent = await storage.create_agent(project.project_id, "research", "E2E agent")
    session = await storage.create_session("agent", agent.agent_id)

    registry = SandboxRegistry(
        store=storage,
        provider_store=provider_store,
        enable_in_sandbox=True,
    )

    handle = None
    try:
        handle = await registry.get_or_create(session.session_id)

        # staging dir: scoped store + this profile's harness + run.json
        staging = registry._staging_dir(handle.owner_id)
        assert (staging / "store" / "project.db").is_file()
        assert (staging / "harness" / "skills" / "research").is_dir()
        assert (staging / "provider_settings.json").is_file()
        run_cfg = json.loads((staging / "run.json").read_text())
        assert "transport" not in run_cfg
        assert run_cfg["session_id"] == session.session_id

        # a real gRPC runtime, reachable over the resolved TCP endpoint
        assert handle.runtime is not None
        assert handle.runtime.run_endpoint.startswith("127.0.0.1:")
        assert await _health_ok(handle.runtime.run_endpoint)

        record = await storage.get_container(handle.owner_id)
        assert record is not None and record.status == "running"
        assert record.policy_snapshot["run_mode"] == "in-sandbox"

        await registry.release(handle.owner_id)
        record = await storage.get_container(handle.owner_id)
        assert record.status == "idle"
    finally:
        if handle is not None:
            backend = registry.local_backend(handle.owner_id)
            if backend is not None and hasattr(backend, "close"):
                backend.close()
            shutil.rmtree(
                registry._staging_dir(handle.owner_id), ignore_errors=True
            )
