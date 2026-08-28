"""Backend logging entrypoint.

The actual loguru wiring now lives in
`krutrim_agent_management.logging_config` so the Celery worker
(`krutrim_agent_celery.app`) shares the exact same configuration and knobs
(`KRUTRIM_AGENT_LOG_*`). This module just pins the component name to
`"server"` — logs land in `<KRUTRIM_AGENT_LOG_DIR>/server/server.log`.
"""

from __future__ import annotations

from krutrim_agent_management.logging_config import (
    configure_logging as _configure_logging,
)


def configure_logging() -> None:
    _configure_logging("server")
