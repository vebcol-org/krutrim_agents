"""`RecordingFilesystemBackend` logs fs ops to the run transcript and stays a
pure (non-execute) filesystem backend."""

from __future__ import annotations

import json

from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.protocol import SandboxBackendProtocol
from krutrim_agents_core.harness.recording_backend import RecordingFilesystemBackend
from krutrim_agents_core.harness.runs import RunLogger


def _events(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def test_writes_and_reads_are_recorded_and_delegated(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    transcript = tmp_path / "run.jsonl"
    backend = RecordingFilesystemBackend(
        FilesystemBackend(root_dir=str(workspace), virtual_mode=True),
        RunLogger("research", "thread-1", path=transcript),
    )

    assert backend.write("/a.txt", "hello").error is None
    assert backend.read("/a.txt").file_data["content"] == "hello"
    assert (workspace / "a.txt").read_text() == "hello"

    ops = [(e["op"], e["path"], e["ok"]) for e in _events(transcript) if e["type"] == "fs_op"]
    assert ("write", "/a.txt", True) in ops
    assert ("read", "/a.txt", True) in ops
    assert all(e["source"] == "sandbox_fs" for e in _events(transcript))


def test_is_not_a_sandbox_backend(tmp_path):
    backend = RecordingFilesystemBackend(
        FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True),
        RunLogger("research", "t", path=tmp_path / "r.jsonl"),
    )
    # deepagents gates the `execute` tool on this check — a filesystem-only
    # sandbox must fail it.
    assert not isinstance(backend, SandboxBackendProtocol)


async def test_async_write_is_recorded(tmp_path):
    transcript = tmp_path / "run.jsonl"
    backend = RecordingFilesystemBackend(
        FilesystemBackend(root_dir=str(tmp_path), virtual_mode=True),
        RunLogger("research", "t", path=transcript),
    )

    await backend.awrite("/b.txt", "x")

    ops = [e for e in _events(transcript) if e["type"] == "fs_op" and e["op"] == "write"]
    assert ops and ops[0]["path"] == "/b.txt"
