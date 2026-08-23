"""Reusable Celery app construction: broker/backend/timezone/beat-schedule
wiring, extracted from what `krutrim_agent_celery/app.py` used to hardcode inline.

Deliberately does **not** import task modules itself: a Celery task module
conventionally does `from <app module> import celery_app` to get the
`@celery_app.task` decorator, which only works once the calling module has
already bound `celery_app = build_celery_app(...)` in its own namespace —
importing tasks from inside this function, before that assignment
completes, would be a circular import. So task-module importing (for its
`@celery_app.task` registration side effect) stays the caller's job, done
right after `build_celery_app(...)` returns — see `krutrim_agent_celery/app.py` for
the exact shape a second Celery service (e.g. a separate one, with its
own extra tasks) should copy.
"""

from __future__ import annotations

from celery import Celery
from krutrim_agent_management.config import settings


def build_celery_app(
    name: str, *, beat_schedule: dict | None = None, timezone: str = "UTC"
) -> Celery:
    app = Celery(name, broker=settings.redis_url, backend=settings.redis_url)
    app.conf.timezone = timezone
    if beat_schedule is not None:
        app.conf.beat_schedule = beat_schedule
    return app
