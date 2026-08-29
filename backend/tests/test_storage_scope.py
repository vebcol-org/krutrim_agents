"""`LocalStorage.export_scope` / `import_scope` — the per-run snapshot the
in-sandbox agent runtime bind-mounts. The load-bearing property is that the
export contains *only* the target project/agent/session and nothing else."""

from __future__ import annotations

import json
import sqlite3

import pytest
from krutrim_agent_management import LocalStorage


async def _seed(storage: LocalStorage):
    """Two projects, each with an agent + session, so leak checks have something
    to leak."""
    p1 = await storage.create_project("Target project")
    a1 = await storage.create_agent(p1.project_id, "research", "Target agent")
    s1 = await storage.create_session("agent", a1.agent_id)

    p2 = await storage.create_project("Other project")
    a2 = await storage.create_agent(p2.project_id, "research", "Other agent")
    s2 = await storage.create_session("agent", a2.agent_id)

    await storage.write_memory(p1.project_id, "target memory")
    await storage.write_memory(p2.project_id, "SECRET other-project memory")
    await storage.sync_workspace_from_container(
        s1.session_id, [("notes.md", b"# target notes")]
    )
    await storage.sync_workspace_from_container(
        s2.session_id, [("notes.md", b"other notes")]
    )
    return p1, a1, s1, p2, a2, s2


async def test_export_scope_contains_only_the_target(tmp_path):
    storage = LocalStorage(tmp_path / "store")
    p1, a1, s1, p2, a2, s2 = await _seed(storage)

    staging = tmp_path / "staging"
    await storage.export_scope(p1.project_id, a1.agent_id, s1.session_id, staging)

    store = staging / "store"
    projects = sqlite3.connect(store / "project.db").execute(
        "SELECT project_id FROM projects"
    ).fetchall()
    agents = sqlite3.connect(store / "agents.db").execute(
        "SELECT agent_id FROM agents"
    ).fetchall()
    sessions = sqlite3.connect(store / "sessions.db").execute(
        "SELECT session_id FROM sessions"
    ).fetchall()

    assert projects == [(p1.project_id,)]
    assert agents == [(a1.agent_id,)]
    assert sessions == [(s1.session_id,)]

    # workspace mirror is exposed as a plain dir, scoped to the target session
    assert (staging / "workspace" / "notes.md").read_bytes() == b"# target notes"
    # the other project's memory must be nowhere in the export
    dumped = list(staging.rglob("*"))
    for path in dumped:
        if path.is_file():
            assert b"SECRET other-project memory" not in path.read_bytes()

    assert (staging / "out").is_dir()


async def test_export_scope_reopenable_as_storage(tmp_path):
    storage = LocalStorage(tmp_path / "store")
    p1, a1, s1, *_ = await _seed(storage)

    staging = tmp_path / "staging"
    await storage.export_scope(p1.project_id, a1.agent_id, s1.session_id, staging)

    reopened = LocalStorage(staging / "store")
    assert (await reopened.get_project(p1.project_id)).project_title == "Target project"
    assert (await reopened.get_agent(a1.agent_id)).display_name == "Target agent"
    assert (await reopened.get_session(s1.session_id)).session_id == s1.session_id
    assert await reopened.read_memory(p1.project_id) == "target memory"


async def test_export_scope_rejects_mismatched_chain(tmp_path):
    storage = LocalStorage(tmp_path / "store")
    p1, a1, s1, p2, a2, s2 = await _seed(storage)
    with pytest.raises(KeyError):
        await storage.export_scope(p1.project_id, a1.agent_id, s2.session_id, tmp_path / "x")
    with pytest.raises(KeyError):
        await storage.export_scope(p2.project_id, a1.agent_id, s1.session_id, tmp_path / "y")


async def test_import_scope_round_trips_out_dir(tmp_path):
    storage = LocalStorage(tmp_path / "store")
    p1, a1, s1, *_ = await _seed(storage)

    staging = tmp_path / "staging"
    await storage.export_scope(p1.project_id, a1.agent_id, s1.session_id, staging)

    # simulate the container's writes
    (staging / "workspace" / "report.md").write_bytes(b"# final report")
    out = staging / "out"
    (out / "usage.json").write_text('{"input_tokens": 10}')
    (out / "runs").mkdir()
    (out / "runs" / f"{s1.session_id}.jsonl").write_text('{"type": "model_call"}\n')

    await storage.import_scope(s1.session_id, staging)

    files = set(await storage.read_workspace_files(s1.session_id))
    assert {"notes.md", "report.md"} <= files
    assert await storage.read_usage(s1.session_id) == {"input_tokens": 10}
    run_log = storage.session_dir(s1.session_id) / "runs" / f"{s1.session_id}.jsonl"
    assert run_log.is_file()


async def test_import_scope_merges_run_log_with_host_side_lines(tmp_path):
    """The host's HostBridge writes its own lines into `sessions/<id>/runs/<id>.jsonl`
    during the run; import_scope must append the container's lines, not clobber them."""
    storage = LocalStorage(tmp_path / "store")
    p1, a1, s1, *_ = await _seed(storage)

    # host-side transcript already on disk (HostBridge wrote it mid-run)
    host_runs = storage.session_dir(s1.session_id) / "runs"
    host_runs.mkdir(parents=True, exist_ok=True)
    (host_runs / f"{s1.session_id}.jsonl").write_text(
        '{"source": "host_bridge", "type": "chat_request"}\n'
        '{"source": "host_bridge", "type": "chat_response"}\n'
    )

    staging = tmp_path / "staging"
    await storage.export_scope(p1.project_id, a1.agent_id, s1.session_id, staging)
    (staging / "out" / "runs").mkdir(parents=True)
    (staging / "out" / "runs" / f"{s1.session_id}.jsonl").write_text(
        '{"source": "agent_runtime", "type": "RUN_STARTED"}\n'
        '{"source": "agent_graph", "type": "model_request"}\n'
    )

    await storage.import_scope(s1.session_id, staging)

    lines = (
        (host_runs / f"{s1.session_id}.jsonl").read_text().strip().splitlines()
    )
    sources = {json.loads(ln)["source"] for ln in lines}
    assert sources == {"host_bridge", "agent_runtime", "agent_graph"}
    assert len(lines) == 4
