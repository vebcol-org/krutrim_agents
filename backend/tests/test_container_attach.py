"""Real-Docker end-to-end test for explicit container reuse: two sessions
attach to one container via `attached_to_session_id`, concurrent `execute()`
calls from both succeed, and the idle reaper only tears the container down
once *both* sessions have released it (combined ref_count).

Complements `test_sandbox_registry.py::test_get_or_create_combines_ref_count_across_attached_sessions`
(same assertions, fake backend/store) by proving it against a real container
and real concurrent Docker exec calls, not just the bookkeeping logic.
"""

from __future__ import annotations

import asyncio

from krutrim_agent_celery.tasks.reap_idle_containers import reap_idle_containers_once
from krutrim_agent_management import LocalStorage
from krutrim_agent_sandbox.registry import SandboxRegistry
from test_sandbox import requires_sandbox


@requires_sandbox
async def test_two_sessions_share_one_container_via_attach(tmp_path):
    storage = LocalStorage(tmp_path)
    registry = SandboxRegistry(store=storage)
    project = await storage.create_project("Attach Test")
    agent = await storage.create_agent(project.project_id, "research", "Test Agent")
    session_a = await storage.create_session("agent", agent.agent_id)
    session_b = await storage.create_session("agent", agent.agent_id)
    await storage.update_session_sandbox_policy(
        session_b.session_id, attached_to_session_id=session_a.session_id
    )

    handle_a = None
    try:
        handle_a = await registry.get_or_create(session_a.session_id)
        handle_b = await registry.get_or_create(session_b.session_id)

        assert handle_a.owner_id == handle_b.owner_id == session_a.session_id
        assert handle_a.backend is handle_b.backend  # literally the same container

        record = await storage.get_container(session_a.session_id)
        assert record.ref_count == 2

        # Concurrent execute() calls from "both sessions" — since it's the
        # same backend object, this exercises Docker's own exec_run
        # concurrency (see .architecture/sandbox-design.md's reasoning,
        # confirmed for real here rather than just reasoned about).
        result_a, result_b = await asyncio.gather(
            asyncio.to_thread(handle_a.backend.execute, "echo from-a"),
            asyncio.to_thread(handle_b.backend.execute, "echo from-b"),
        )
        assert result_a.exit_code == 0
        assert "from-a" in result_a.output
        assert result_b.exit_code == 0
        assert "from-b" in result_b.output

        # Releasing only one side must not make it reap-eligible.
        await registry.release(handle_a.owner_id)
        reap_result = await reap_idle_containers_once(storage, idle_timeout_seconds=0)
        assert reap_result["reaped"] == []
        assert await storage.get_container(session_a.session_id) is not None

        # Releasing the second side brings ref_count to 0 — now it's eligible.
        await registry.release(handle_b.owner_id)
        reap_result = await reap_idle_containers_once(storage, idle_timeout_seconds=0)
        assert reap_result["reaped"] == [session_a.session_id]
        assert await storage.get_container(session_a.session_id) is None
    finally:
        if handle_a is not None:
            handle_a.backend.close()  # no-op if the reaper already removed it
