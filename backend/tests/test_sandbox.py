from __future__ import annotations

import shutil
import time
import uuid

import pytest
from krutrim_agent_sandbox.docker_backend import DockerSandboxBackend
from krutrim_agent_sandbox.policy import SandboxPolicy

import docker


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        docker.from_env().ping()
    except Exception:  # noqa: BLE001
        return False
    return True


def _image_available() -> bool:
    try:
        docker.from_env().images.get(SandboxPolicy().image)
    except Exception:  # noqa: BLE001
        return False
    return True


requires_sandbox = pytest.mark.skipif(
    not _docker_available() or not _image_available(),
    reason="Docker daemon or krutrim_agent-sandbox:latest image not available "
    "(build it with: docker build -f docker/sandbox.Dockerfile -t krutrim_agent-sandbox:latest backend)",
)


@pytest.fixture
def sandbox():
    backend = DockerSandboxBackend(policy=SandboxPolicy(timeout_seconds=5))
    yield backend
    backend.close()


@requires_sandbox
def test_execute_basic(sandbox):
    result = sandbox.execute("echo hello world")
    assert result.exit_code == 0
    assert "hello world" in result.output


@requires_sandbox
def test_execute_runs_as_non_root(sandbox):
    result = sandbox.execute("id -un")
    assert result.exit_code == 0
    assert result.output.strip() == "sandbox"


@requires_sandbox
def test_execute_enforces_timeout(sandbox):
    result = sandbox.execute("sleep 10", timeout=2)
    assert result.exit_code == 124


@requires_sandbox
def test_execute_has_no_network(sandbox):
    result = sandbox.execute(
        "python3 -c \"import urllib.request; urllib.request.urlopen('http://example.com', timeout=3)\""
    )
    assert result.exit_code != 0


@requires_sandbox
def test_rootfs_is_read_only_outside_tmpfs(sandbox):
    result = sandbox.execute("touch /etc/should-fail.txt")
    assert result.exit_code != 0


@requires_sandbox
def test_write_read_edit_roundtrip(sandbox):
    write_result = sandbox.write("/workspace/note.txt", "line1\nline2\n")
    assert write_result.error is None

    read_result = sandbox.read("/workspace/note.txt")
    assert read_result.file_data is not None
    assert read_result.file_data["content"] == "line1\nline2"

    edit_result = sandbox.edit("/workspace/note.txt", "line1", "LINE_ONE")
    assert edit_result.error is None

    reread = sandbox.read("/workspace/note.txt")
    assert "LINE_ONE" in reread.file_data["content"]


@requires_sandbox
def test_ls_and_grep(sandbox):
    sandbox.write("/workspace/a.txt", "needle here")
    sandbox.write("/workspace/b.txt", "nothing")

    ls_result = sandbox.ls("/workspace")
    paths = {entry["path"] for entry in ls_result.entries}
    assert "/workspace/a.txt" in paths
    assert "/workspace/b.txt" in paths

    grep_result = sandbox.grep("needle", "/workspace")
    assert grep_result.matches
    assert grep_result.matches[0]["path"] == "/workspace/a.txt"


@requires_sandbox
def test_output_truncation():
    policy = SandboxPolicy(timeout_seconds=5, max_output_bytes=100)
    backend = DockerSandboxBackend(policy=policy)
    try:
        result = backend.execute("python3 -c \"print('x' * 1000)\"")
        assert result.truncated is True
        assert len(result.output.encode("utf-8")) <= 200  # cap plus truncation message
    finally:
        backend.close()


@requires_sandbox
def test_close_removes_container(sandbox):
    sandbox.execute("echo warm-up")
    container_name = f"krutrim_agent-sandbox-{sandbox._owner_id}"
    client = docker.from_env()
    assert client.containers.get(container_name) is not None
    sandbox.close()
    with pytest.raises(docker.errors.NotFound):
        client.containers.get(container_name)


@requires_sandbox
def test_touch_updates_last_active_at(sandbox):
    before = sandbox.last_active_at
    time.sleep(0.01)
    sandbox.execute("echo hi")
    assert sandbox.last_active_at > before


@requires_sandbox
def test_hydrate_restores_files_after_teardown():
    owner_id = f"hydrate-test-{uuid.uuid4().hex[:8]}"
    backend = DockerSandboxBackend(
        policy=SandboxPolicy(timeout_seconds=5), owner_id=owner_id
    )
    rehydrated: DockerSandboxBackend | None = None
    try:
        write_result = backend.write(
            "/workspace/note.txt", "hello from before teardown"
        )
        assert write_result.error is None
        downloaded = backend.download_files(["/workspace/note.txt"])
        assert downloaded[0].error is None
        backend.close()

        rehydrated = DockerSandboxBackend(
            policy=SandboxPolicy(timeout_seconds=5), owner_id=owner_id
        )
        rehydrated.hydrate([(f.path, f.content) for f in downloaded])
        read_result = rehydrated.read("/workspace/note.txt")
        assert read_result.file_data is not None
        assert "hello from before teardown" in read_result.file_data["content"]
    finally:
        backend.close()
        if rehydrated is not None:
            rehydrated.close()


@requires_sandbox
def test_upload_files_bare_top_level_filename(sandbox):
    # Regression test: a bare relative filename with no "/" at all (e.g. the
    # workspace-mirror-relative paths SandboxRegistry/the reaper pass to
    # hydrate()/upload_files()) used to compute the wrong "parent" directory
    # (`path.rsplit("/", 1)[0]` returns the whole filename itself when there's
    # no separator, not ""), so `mkdir -p <that filename>` created a
    # directory that then shadowed the file it was supposed to hold.
    responses = sandbox.upload_files([("bare.txt", b"top-level, no directory prefix")])
    assert responses[0].error is None

    read_result = sandbox.read("/workspace/bare.txt")
    assert read_result.file_data is not None
    assert "top-level, no directory prefix" in read_result.file_data["content"]


@requires_sandbox
def test_new_instance_reattaches_to_existing_running_container():
    owner_id = f"reattach-test-{uuid.uuid4().hex[:8]}"
    first = DockerSandboxBackend(
        policy=SandboxPolicy(timeout_seconds=5), owner_id=owner_id
    )
    second: DockerSandboxBackend | None = None
    try:
        write_result = first.write(
            "/workspace/marker.txt", "written by the first instance"
        )
        assert write_result.error is None

        # A brand-new instance, same owner_id, first's container never closed —
        # simulates a different process (or a SandboxRegistry cache miss)
        # reattaching to an already-running container instead of clobbering it.
        second = DockerSandboxBackend(
            policy=SandboxPolicy(timeout_seconds=5), owner_id=owner_id
        )
        read_result = second.read("/workspace/marker.txt")
        assert read_result.file_data is not None
        assert "written by the first instance" in read_result.file_data["content"]
    finally:
        first.close()
        if second is not None:
            second.close()


@requires_sandbox
def test_hydrate_is_idempotent_on_warm_container(sandbox):
    sandbox.execute("echo warm-up")
    sandbox.hydrate([("/workspace/again.txt", b"still here")])
    read_result = sandbox.read("/workspace/again.txt")
    assert read_result.file_data is not None
    assert "still here" in read_result.file_data["content"]
