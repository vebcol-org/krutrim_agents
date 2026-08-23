"""Default `STORAGE_ROOT` location; kept separate from `local.py` so `config.py` can
import just this, without pulling in sqlite3/json machinery.
"""

from __future__ import annotations

from pathlib import Path


def default_storage_root() -> Path:
    path = Path.home() / ".krutrim_agent"
    path.mkdir(parents=True, exist_ok=True)
    return path
