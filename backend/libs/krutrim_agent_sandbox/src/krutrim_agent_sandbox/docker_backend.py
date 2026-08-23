"""Docker-isolated `SandboxBackendProtocol` implementation for deepagents.

Subclassing `deepagents.backends.sandbox.BaseSandbox` means we only need to
implement `execute`, `upload_files`, `download_files`, and `id` — `ls`,
`read_file`, `write_file`, `edit_file`, `grep`, and `glob` are all derived by
`BaseSandbox` from `execute()`/`upload_files()`, so every filesystem
operation the agent performs happens inside the container, never on the host.

One container is started lazily per backend instance and kept running for the
process lifetime (not per-call) so files written in one turn are still there
in the next. Each instance is keyed by an `owner_id` — resolved per session/
project by `krutrim_agent_sandbox.registry.SandboxRegistry`, not a fixed
agent-profile key — so a given owner's scratch workspace never leaks into
another's. `owner_id` is usually a session id (the default, isolated case, or
the target of an explicit "attach to another session's container" action);
it is never influenced by cross-agent messaging sharing policy, which grants a
communication channel between two separate containers rather than merging them.
"""

from __future__ import annotations

import base64
import shlex
import threading
import time
import uuid
from typing import TYPE_CHECKING

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox
from docker.errors import NotFound

import docker
from krutrim_agent_sandbox.exceptions import SandboxStartError
from krutrim_agent_sandbox.factory import register_sandbox_runtime
from krutrim_agent_sandbox.policy import SandboxPolicy

if TYPE_CHECKING:
    from docker.models.containers import Container


class DockerSandboxBackend(BaseSandbox):
    def __init__(
        self,
        policy: SandboxPolicy | None = None,
        owner_id: str | None = None,
        client: docker.DockerClient | None = None,
    ) -> None:
        self._policy = policy or SandboxPolicy()
        self._owner_id = owner_id or uuid.uuid4().hex[:12]
        self._client = client or docker.from_env()
        self._container: Container | None = None
        self._lock = threading.Lock()
        self._last_active_at = time.monotonic()

    @property
    def id(self) -> str:
        return f"docker-{self._owner_id}"

    @property
    def owner_id(self) -> str:
        return self._owner_id

    @property
    def last_active_at(self) -> float:
        """`time.monotonic()` timestamp of the last successful `execute()` call
        (which `upload_files`/`download_files` also go through) — what
        `SandboxRegistry`/the idle-container reaper reads to decide staleness."""
        return self._last_active_at

    def touch(self) -> None:
        self._last_active_at = time.monotonic()

    def hydrate(self, files: list[tuple[str, bytes]]) -> None:
        """Ensures a container is running (starting one if needed, via the
        existing lazy `_ensure_container` path) then re-uploads a previously
        persisted workspace. Idempotent — safe to call against an
        already-warm container, since uploads just overwrite same-named
        files. Used by `SandboxRegistry` to resume a session whose container
        was torn down by the idle reaper."""
        self._ensure_container()
        if files:
            self.upload_files(files)

    def _reattach_or_remove_stale(self, name: str) -> Container | None:
        """Looks for a container already named `name` from a *different*
        `DockerSandboxBackend` instance — another process (a Celery reaper
        task reading this container's workspace before tearing it down), or
        this same process after `SandboxRegistry` lost track of it (e.g. a
        restart) — before assuming none exists.

        Returns the existing container if it's still running (the caller
        should use it as-is, not start a new one). Otherwise removes
        whatever's there by that name (a stale leftover from a crashed prior
        run that never called `close()`) so `containers.run()` can claim the
        name cleanly, and returns None.
        """
        try:
            existing = self._client.containers.get(name)
        except NotFound:
            return None
        except Exception:  # noqa: BLE001 - best-effort, a real start failure surfaces from containers.run() itself
            return None
        try:
            existing.reload()
            if existing.status == "running":
                return existing
        except NotFound:
            return None
        try:
            existing.remove(force=True)
        except Exception:  # noqa: BLE001 - best-effort, a real start failure surfaces from containers.run() itself
            pass
        return None

    def _ensure_container(self) -> Container:
        with self._lock:
            if self._container is not None:
                try:
                    self._container.reload()
                    if self._container.status == "running":
                        return self._container
                except NotFound:
                    pass
                self._container = None

            policy = self._policy
            container_name = f"krutrim_agent-sandbox-{self._owner_id}"
            reattached = self._reattach_or_remove_stale(container_name)
            if reattached is not None:
                self._container = reattached
                return self._container
            try:
                container = self._client.containers.run(
                    policy.image,
                    command=["sleep", "infinity"],
                    detach=True,
                    name=container_name,
                    network_disabled=(policy.network == "none"),
                    mem_limit=f"{policy.memory_mb}m",
                    nano_cpus=policy.nano_cpus,
                    pids_limit=policy.pids_limit,
                    read_only=True,
                    tmpfs={
                        "/tmp": f"size={policy.tmp_tmpfs_mb}m,uid=1000,gid=1000,mode=1777",
                        "/workspace": f"size={policy.workspace_tmpfs_mb}m,uid=1000,gid=1000,mode=1777",
                    },
                    working_dir="/workspace",
                    user="sandbox",
                    cap_drop=["ALL"],
                    security_opt=["no-new-privileges"],
                    auto_remove=False,
                )
            except Exception as exc:
                raise SandboxStartError(
                    f"Failed to start sandbox container from image {policy.image!r}: {exc}"
                ) from exc
            self._container = container
            return container

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        container = self._ensure_container()
        effective_timeout = (
            timeout if timeout is not None else self._policy.timeout_seconds
        )
        # `timeout` is coreutils, present in the sandbox image; -k sends SIGKILL
        # shortly after SIGTERM for commands that ignore the first signal.
        wrapped = f"timeout -k 2 {int(effective_timeout)} sh -c {shlex.quote(command)}"
        try:
            exit_code, output = container.exec_run(
                ["/bin/sh", "-lc", wrapped], workdir="/workspace"
            )
        except Exception as exc:  # noqa: BLE001 - return as a tool-visible error, don't crash the graph
            return ExecuteResponse(
                output=f"Error executing command in sandbox: {exc}",
                exit_code=1,
                truncated=False,
            )

        self.touch()  # reached the container successfully — resets the reaper's idle clock,
        # regardless of the command's own exit code (a timeout is still "activity").
        text = (
            output.decode("utf-8", errors="replace")
            if isinstance(output, (bytes, bytearray))
            else str(output)
        )
        truncated = False
        encoded = text.encode("utf-8")
        if len(encoded) > self._policy.max_output_bytes:
            text = encoded[: self._policy.max_output_bytes].decode(
                "utf-8", errors="ignore"
            )
            text += "\n\n[Output truncated by sandbox policy.]"
            truncated = True
        if exit_code == 124:
            text = f"Error: command timed out after {effective_timeout}s.\n{text}"
        return ExecuteResponse(output=text, exit_code=exit_code, truncated=truncated)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        # The container's rootfs is read-only, and Docker's archive-copy API
        # (what `put_archive` uses) refuses to write to a read-only container
        # even when the target path is a writable tmpfs mount. Transferring
        # through `execute()` (base64 over a shell pipe) sidesteps that and
        # keeps the container's rootfs genuinely immutable.
        responses: list[FileUploadResponse] = []
        for path, content in files:
            try:
                # A bare filename with no "/" at all (e.g. "result.txt" — the
                # common case for workspace-mirror-relative paths, see
                # sandbox/registry.py) has no parent to mkdir; rsplit's
                # no-separator behavior returns the whole string as [0], not
                # "", so it can't be told apart from a real parent by `or`
                # alone — check for "/" explicitly instead.
                if "/" in path:
                    parent = path.rsplit("/", 1)[0] or "/"
                else:
                    parent = "."
                b64 = base64.b64encode(content).decode("ascii")
                cmd = f"mkdir -p {shlex.quote(parent)} && printf '%s' {shlex.quote(b64)} | base64 -d > {shlex.quote(path)}"
                result = self.execute(cmd)
                if result.exit_code != 0:
                    responses.append(
                        FileUploadResponse(
                            path=path, error=result.output.strip() or "upload failed"
                        )
                    )
                else:
                    responses.append(FileUploadResponse(path=path))
            except Exception as exc:  # noqa: BLE001 - partial-success contract, see BackendProtocol.upload_files
                responses.append(FileUploadResponse(path=path, error=str(exc)))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            try:
                result = self.execute(f"base64 {shlex.quote(path)}")
                if result.exit_code != 0:
                    responses.append(
                        FileDownloadResponse(path=path, error="file_not_found")
                    )
                    continue
                content = base64.b64decode(result.output.strip() or "")
                responses.append(FileDownloadResponse(path=path, content=content))
            except Exception as exc:  # noqa: BLE001 - partial-success contract, see BackendProtocol.download_files
                responses.append(FileDownloadResponse(path=path, error=str(exc)))
        return responses

    def close(self) -> None:
        """Stop and remove the sandbox container. Call on app/session shutdown."""
        with self._lock:
            if self._container is not None:
                try:
                    self._container.remove(force=True)
                except Exception:  # noqa: BLE001 - best-effort cleanup
                    pass
                self._container = None


def _create_docker_backend(
    owner_id: str, policy: SandboxPolicy | None
) -> DockerSandboxBackend:
    return DockerSandboxBackend(policy=policy, owner_id=owner_id)


register_sandbox_runtime("docker", _create_docker_backend)
