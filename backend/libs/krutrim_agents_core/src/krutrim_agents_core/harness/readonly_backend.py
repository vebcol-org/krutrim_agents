"""A `FilesystemBackend` that refuses every mutation.

Used to mount `harness/skills/` and `harness/memory/` into the agent's
`CompositeBackend` as read-only routes. deepagents' `permissions` rules can't
be combined with a sandbox-execute backend (the `execute` tool bypasses
tool-level permission checks entirely), so read-only enforcement has to live
here, at the backend itself, where it can't be bypassed by any tool.
"""

from __future__ import annotations

from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.protocol import DeleteResult, EditResult, WriteResult

_DENIED = "Permission denied: this path is a read-only harness directory."


class ReadOnlyFilesystemBackend(FilesystemBackend):
    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error=_DENIED)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return EditResult(error=_DENIED)

    def delete(self, file_path: str) -> DeleteResult:
        return DeleteResult(error=_DENIED)
