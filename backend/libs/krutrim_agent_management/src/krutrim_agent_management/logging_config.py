"""Shared loguru configuration for every krutrim-agent process.

Both entrypoints call this with the SAME knobs (`AppSettings.log_*` /
`KRUTRIM_AGENT_LOG_*`) — only the sink location differs:

    configure_logging("server")  ->  <log_dir>/server/server.log   (FastAPI app)
    configure_logging("worker")  ->  <log_dir>/worker/worker.log   (Celery worker/beat)

`<log_dir>` defaults to `~/.krutrim_agent/logs`. Rotation is periodic by
default (`log_rotation="1 day"` — a new file every 24h), overridable to a
size (`"20 MB"`) or a wall-clock time (`"00:00"`). Old files are pruned
after `log_retention` (`"14 days"`).

`diagnose=False` on the file sink is deliberate: loguru's diagnose mode
dumps local variable values into the traceback, which would leak provider
API keys (they sit in locals in `providers/*.py`) straight into the log
file. `backtrace` (frame list, no values) stays on for the file sink.

Idempotent per component: calling `configure_logging("server")` twice is a
no-op, and a process that somehow runs both roles just gets both file
sinks added once each on top of the single shared console sink.
"""

from __future__ import annotations

import logging
import sys

from loguru import logger

from krutrim_agent_management.config import settings

_configured: set[str] = set()


class _InterceptHandler(logging.Handler):
    """Bridges stdlib `logging` (uvicorn, celery, httpx, faisslite, ...) into
    loguru so third-party log records share the same format and land in the
    same rotating files as our own `logger.*` calls."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def _install_std_intercept() -> None:
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for name in list(logging.root.manager.loggerDict):
        std_logger = logging.getLogger(name)
        std_logger.handlers = []
        std_logger.propagate = True


def configure_logging(component: str = "server") -> None:
    """Wire up loguru for `component` ("server" or "worker"). See module docstring."""
    if component in _configured:
        return
    first_call = not _configured
    _configured.add(component)

    dev = settings.dev_mode
    console_level = "DEBUG" if dev else settings.log_console_level
    file_level = "DEBUG" if dev else settings.log_level

    if first_call:
        logger.remove()
        logger.add(
            sys.stderr,
            level=console_level,
            backtrace=settings.log_backtrace or dev,
            diagnose=False,
        )

    log_dir = settings.log_dir / component
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / f"{component}.log",
        level=file_level,
        rotation=settings.log_rotation,
        retention=settings.log_retention,
        compression=settings.log_compression or None,
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )

    if first_call and settings.log_intercept_std:
        _install_std_intercept()

    logger.info(
        "logging configured — component={} dir={} console={} file={} rotation={} retention={} dev_mode={}",
        component,
        log_dir,
        console_level,
        file_level,
        settings.log_rotation,
        settings.log_retention,
        dev,
    )
