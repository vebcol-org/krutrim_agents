"""Tuning knobs specific to the Celery worker/beat process.

Kept separate from `krutrim_agent_management.config.AppSettings` (which owns
infra-wide config like `redis_url`, shared with the FastAPI process) since
these are meant to become `krutrim_agent_celery`'s own service config once it's
extracted into its own deployable package — see the pending migration
plan's "extract into the uv workspace" step. Different env prefix
(`KRUTRIM_AGENT_CELERY_`, not `KRUTRIM_AGENT_`) reflects that split now rather than
requiring a rename later.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class CelerySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KRUTRIM_AGENT_CELERY_", env_file=".env", extra="ignore"
    )

    idle_timeout_seconds: int = 600
    """Default staleness threshold for tearing down an unreferenced container.
    A project's own `sandbox_idle_timeout_seconds` (see storage/models.py),
    when set, overrides this default — see reap_idle_containers.py."""

    beat_interval_seconds: int = 60
    """How often the reaper task itself runs, via Celery beat — distinct from
    `idle_timeout_seconds`, which is the staleness threshold it checks for."""


celery_settings = CelerySettings()
