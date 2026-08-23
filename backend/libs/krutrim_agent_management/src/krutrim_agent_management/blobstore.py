"""File-shaped storage seam `LocalStorage` depends on instead of touching the filesystem
directly. `LocalBlobStore` is the only implementation today.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from krutrim_agent_utils.atomic_write import atomic_write_bytes


class BlobStore(ABC):
    @abstractmethod
    def read(self, key: str) -> bytes | None:
        """Returns None if `key` doesn't exist."""

    @abstractmethod
    def write(self, key: str, data: bytes) -> None:
        """Creates or overwrites `key`. Implementations must write atomically —
        a concurrent reader must never observe a partially-written value."""

    @abstractmethod
    def list(self, prefix: str) -> list[str]:
        """Returns paths relative to `prefix` for every blob stored under it
        (posix-style, `/`-separated). Empty list if `prefix` has no blobs."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """No-op (not an error) if `key` doesn't exist."""


class LocalBlobStore(BlobStore):
    def __init__(self, root: Path) -> None:
        self._root = root

    def _abs(self, key: str) -> Path:
        return self._root / key

    def read(self, key: str) -> bytes | None:
        path = self._abs(key)
        return path.read_bytes() if path.exists() else None

    def write(self, key: str, data: bytes) -> None:
        atomic_write_bytes(self._abs(key), data)

    def list(self, prefix: str) -> list[str]:
        base = self._abs(prefix)
        if not base.is_dir():
            return []
        return sorted(
            p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()
        )

    def delete(self, key: str) -> None:
        self._abs(key).unlink(missing_ok=True)
