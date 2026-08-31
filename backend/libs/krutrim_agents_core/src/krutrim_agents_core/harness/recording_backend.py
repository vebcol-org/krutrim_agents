"""`RecordingFilesystemBackend` — the backend-level half of the per-run eval trace.

`RunLoggingMiddleware` (`krutrim_agents_core.harness.run_logging`) records every
model call and every *tool* call. This wrapper records filesystem activity one
layer lower — at the backend boundary — so the transcript also covers reads and
writes issued by sub-agents or other middleware that never surface as a named
tool call, and gives eval a clean `fs_op` event stream keyed by real path.

It is a plain `BackendProtocol` delegate (deliberately **not** a
`SandboxBackendProtocol`), so deepagents never offers an `execute` tool for it —
matching the filesystem-only sandbox this project ships today. Wrap the backend
handed out by `SandboxRegistry.get_or_create` before passing it to `build_agent`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from deepagents.backends.protocol import (
    BackendProtocol,
    DeleteResult,
    EditResult,
    FileDownloadResponse,
    FileUploadResponse,
    GlobResult,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)

if TYPE_CHECKING:
    from krutrim_agents_core.harness.runs import RunLogger


class RecordingFilesystemBackend(BackendProtocol):
    def __init__(self, inner: BackendProtocol, run_logger: RunLogger) -> None:
        self._inner = inner
        self._log = run_logger

    # -- eval trace -------------------------------------------------------

    def _record(self, op: str, path: str, *, ok: bool, **extra: object) -> None:
        try:
            self._log.log(
                "fs_op",
                {"source": "sandbox_fs", "op": op, "path": path, "ok": ok, **extra},
            )
        except Exception:  # noqa: BLE001, S110 - the transcript is best-effort
            pass

    # -- mutating / reading ops (logged) --------------------------------

    def write(self, file_path: str, content: str) -> WriteResult:
        result = self._inner.write(file_path, content)
        self._record(
            "write", file_path, ok=result.error is None, bytes=len(content)
        )
        return result

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        result = await self._inner.awrite(file_path, content)
        self._record(
            "write", file_path, ok=result.error is None, bytes=len(content)
        )
        return result

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        result = self._inner.edit(file_path, old_string, new_string, replace_all)
        self._record("edit", file_path, ok=result.error is None)
        return result

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        result = await self._inner.aedit(
            file_path, old_string, new_string, replace_all
        )
        self._record("edit", file_path, ok=result.error is None)
        return result

    def delete(self, file_path: str) -> DeleteResult:
        result = self._inner.delete(file_path)
        self._record("delete", file_path, ok=result.error is None)
        return result

    async def adelete(self, file_path: str) -> DeleteResult:
        result = await self._inner.adelete(file_path)
        self._record("delete", file_path, ok=result.error is None)
        return result

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        result = self._inner.read(file_path, offset, limit)
        self._record("read", file_path, ok=result.error is None)
        return result

    async def aread(
        self, file_path: str, offset: int = 0, limit: int = 2000
    ) -> ReadResult:
        result = await self._inner.aread(file_path, offset, limit)
        self._record("read", file_path, ok=result.error is None)
        return result

    def upload_files(
        self, files: list[tuple[str, bytes]]
    ) -> list[FileUploadResponse]:
        result = self._inner.upload_files(files)
        for (path, content), resp in zip(files, result, strict=False):
            self._record(
                "upload", path, ok=resp.error is None, bytes=len(content)
            )
        return result

    async def aupload_files(
        self, files: list[tuple[str, bytes]]
    ) -> list[FileUploadResponse]:
        result = await self._inner.aupload_files(files)
        for (path, content), resp in zip(files, result, strict=False):
            self._record(
                "upload", path, ok=resp.error is None, bytes=len(content)
            )
        return result

    # -- pure reads / listings (delegated, not logged) -----------------

    def ls(self, path: str) -> LsResult:
        return self._inner.ls(path)

    async def als(self, path: str) -> LsResult:
        return await self._inner.als(path)

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        return self._inner.grep(pattern, path, glob, max_count=max_count)

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        return await self._inner.agrep(pattern, path, glob, max_count=max_count)

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        return self._inner.glob(pattern, path)

    async def aglob(self, pattern: str, path: str | None = None) -> GlobResult:
        return await self._inner.aglob(pattern, path)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return self._inner.download_files(paths)

    async def adownload_files(
        self, paths: list[str]
    ) -> list[FileDownloadResponse]:
        return await self._inner.adownload_files(paths)
