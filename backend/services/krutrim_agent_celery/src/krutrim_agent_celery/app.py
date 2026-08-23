"""The Celery application instance — one process type, run as either a
worker (executes tasks) or with `--beat` (also schedules them; fine to run
both in one process for a single-node deployment).

Broker/backend/timezone wiring lives in `krutrim_agent_celery_core.factory.build_celery_app`
(shared with any other Celery service in this workspace); this module's own
job is supplying *this* app's name, beat schedule, and task list — the
community-specific part. `krutrim_agent_backend` dispatches `precompute_embeddings`
via a separate, minimal Celery *client* of its own
(`krutrim_agent_backend/celery_client.py`) using this task's registered name string,
not by importing this module — so the FastAPI process never pulls in
`numpy`/`langchain_ollama`/etc. just to enqueue a job.
"""

from __future__ import annotations

from krutrim_agent_celery_core.factory import build_celery_app

from krutrim_agent_celery.config import celery_settings

celery_app = build_celery_app(
    "krutrim_agent_celery",
    beat_schedule={
        "reap-idle-containers": {
            "task": "krutrim_agent_celery.reap_idle_containers",
            "schedule": celery_settings.beat_interval_seconds,
        },
    },
)

from krutrim_agent_management.config import settings as _app_settings
from krutrim_agent_utils import dev_cache

dev_cache.install(_app_settings.storage_root / "dev_api_cache")  # na-git

# Imported for its side effect (registering `@celery_app.task`-decorated
# functions against this app instance) — not referenced directly here. Must
# stay after `celery_app` is bound above: each task module does
# `from krutrim_agent_celery.app import celery_app`, which only resolves once this
# assignment has completed (see `krutrim_agent_celery_core.factory`'s docstring).
from krutrim_agent_celery.tasks import (
    precompute_embeddings as _precompute_embeddings,  # noqa: F401
)
from krutrim_agent_celery.tasks import (
    process_rag_document as _process_rag_document,  # noqa: F401
)
from krutrim_agent_celery.tasks import (
    reap_idle_containers as _reap_idle_containers,  # noqa: F401
)
