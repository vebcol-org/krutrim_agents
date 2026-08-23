"""A minimal Celery client for dispatching tasks `krutrim_agent_celery` owns, without
depending on that package's code (docker, deepagents, numpy, langchain_ollama,
...) — just the shared Redis broker URL and a task's registered name string.
`Celery.send_task()` is designed for exactly this: enqueuing a task by name
across process/package boundaries, with no import of the task function
itself required.
"""

from __future__ import annotations

from celery import Celery
from krutrim_agent_management.config import settings

celery_client = Celery(
    "krutrim_agent_backend", broker=settings.redis_url, backend=settings.redis_url
)
