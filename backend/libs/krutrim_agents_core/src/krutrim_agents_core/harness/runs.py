"""Append-only JSONL run transcripts, one file per conversation thread.

Separate from deepagents' own checkpointing: this is for observability (what
did this run actually do) and for feeding `harness/evals/`, not for resuming
graph execution.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from typing import Any

from krutrim_agent_management.config import settings


class RunLogger:
    def __init__(self, agent_key: str, thread_id: str) -> None:
        self._agent_key = agent_key
        self._thread_id = thread_id
        self._lock = threading.Lock()
        run_dir = settings.runs_dir / agent_key
        run_dir.mkdir(parents=True, exist_ok=True)
        self._path = run_dir / f"{thread_id}.jsonl"

    def log(self, event_type: str, payload: dict[str, Any]) -> None:
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "agent": self._agent_key,
            "thread_id": self._thread_id,
            "type": event_type,
            **payload,
        }
        line = json.dumps(record, default=str, ensure_ascii=False)
        with self._lock, self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
