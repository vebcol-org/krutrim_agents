"""Central loguru setup: console output plus a rotating file under
`default_storage_root()/logs`, shared by every module via `from loguru import logger`.

`diagnose=False` on the file sink is deliberate: loguru's diagnose mode dumps
local variable values into the traceback, which would leak provider API keys
(they sit in local variables in `providers/*.py`) straight into the log file.
"""

from __future__ import annotations

import sys

from krutrim_agent_management.paths import default_storage_root
from loguru import logger

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    log_dir = default_storage_root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()
    logger.add(sys.stderr, level="INFO")
    logger.add(
        log_dir / "app.log",
        level="DEBUG",
        rotation="10 MB",
        retention="14 days",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )
