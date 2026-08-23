# `krutrim_agent_celery_core` (backend/libs/krutrim_agent_celery_core)

Package name: **`krutrim-agent-celery-core`** (`backend/libs/krutrim_agent_celery_core/pyproject.toml`). One function: the generic Celery app construction that used to be hardcoded inline in `krutrim_agent_celery/app.py`, extracted so a second Celery service (e.g. a separate deployment with its own additional tasks) can build its own app the same way without re-deriving broker/backend/timezone/beat-schedule wiring.

```
krutrim_agent_celery_core/
└── factory.py   build_celery_app(name, *, beat_schedule=None, timezone="UTC") -> Celery
```

## `factory.py`

```python
def build_celery_app(
    name: str, *, beat_schedule: dict | None = None, timezone: str = "UTC"
) -> Celery:
    app = Celery(name, broker=settings.redis_url, backend=settings.redis_url)
    app.conf.timezone = timezone
    if beat_schedule is not None:
        app.conf.beat_schedule = beat_schedule
    return app
```

Both broker and result-backend point at `krutrim_agent_management.config.settings.redis_url` — the same Redis instance every other package in this workspace shares, no service-specific settings needed here.

**Deliberately does not import task modules itself.** A Celery task module conventionally does `from <app module> import celery_app` to get the `@celery_app.task` decorator — that only resolves once the *calling* module has already bound `celery_app = build_celery_app(...)` in its own namespace. Importing task modules from inside `build_celery_app`, before that assignment completes, would be a circular import (`krutrim_agent_celery.app`'s `celery_app` attribute wouldn't exist yet on the partially-initialized module). So task-module importing (for its `@celery_app.task` registration side effect) stays the caller's job, done right after `build_celery_app(...)` returns:

```python
# krutrim_agent_celery/app.py
celery_app = build_celery_app("krutrim_agent_celery", beat_schedule={...})

from krutrim_agent_celery.tasks import reap_idle_containers as _reap_idle_containers
from krutrim_agent_celery.tasks import precompute_embeddings as _precompute_embeddings
```

A second Celery service copies this exact shape — its own `celery_app = build_celery_app("its_name", beat_schedule={...})` followed by its own task-module imports.

## Dependencies

[`pyproject.toml`](../../libs/krutrim_agent_celery_core/pyproject.toml) — package `krutrim-agent-celery-core`: `celery[redis]`, plus workspace `krutrim-agent-management` (for `settings.redis_url`). Notably **no** `deepagents`/`numpy`/`langchain-ollama` — those are `krutrim_agent_celery`'s own task-specific dependencies, not part of the generic engine.

See [`services/krutrim_agent_celery.md`](../services/krutrim_agent_celery.md#1-apppy) for how `krutrim_agent_celery` itself uses this.
