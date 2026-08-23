"""Startup self-check: proves the extension wiring is actually live, and
refuses to boot an extended deployment that's silently still running
community's no-op authenticator — fails CLOSED, not open.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from krutrim_agent_extensions.contracts import NoOpRequestAuthenticator
from krutrim_agent_extensions.registry import all_hooks, get_authenticator

if TYPE_CHECKING:
    from krutrim_agent_management.config import AppSettings


@dataclass(frozen=True)
class ExtensionStatus:
    edition: str
    hooks: dict[str, str]  # hook name -> implementation class name


def run_startup_selfcheck(settings: "AppSettings") -> ExtensionStatus:
    hooks = all_hooks()
    status = ExtensionStatus(
        edition=settings.edition,
        hooks={name: type(impl).__name__ for name, impl in hooks.items()},
    )
    logger.info("Extension status: edition={} hooks={}", status.edition, status.hooks)

    if settings.edition == "extended" and isinstance(
        get_authenticator(), NoOpRequestAuthenticator
    ):
        raise RuntimeError(
            "settings.edition == 'extended' but no RequestAuthenticator was registered — "
            "refusing to start with no real authentication in place. Add your authenticator "
            "module to settings.extension_sources."
        )
    return status
