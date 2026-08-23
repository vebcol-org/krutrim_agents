"""Write-to-temp-file-then-`Path.replace()` helpers.

A concurrent reader must never observe a partially-written value — writing
straight to the destination path risks exactly that. Every on-disk store in
this workspace needs this same pattern; it previously existed twice
(`krutrim_agent_management.blobstore.LocalBlobStore.write`,
`krutrim_agents_core.providers.store.ProviderStore._write`), independently
implemented. This is the one copy both now use.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_bytes(data)
    tmp_path.replace(path)


def atomic_write_json(
    path: Path, data: Any, *, indent: int = 2, sort_keys: bool = True
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, sort_keys=sort_keys)
    tmp_path.replace(path)
