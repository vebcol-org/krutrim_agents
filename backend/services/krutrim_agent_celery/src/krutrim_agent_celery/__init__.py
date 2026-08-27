"""Background/scheduled work for the sandbox lifecycle — today, just the
idle-container reaper (`tasks/reap_idle_containers.py`). Its own deployable
package within the `backend/` uv workspace (see `services/krutrim_agent_celery/pyproject.toml`),
depending on `krutrim_agent_management`/`krutrim_agent_sandbox` as libraries. Run a worker
with:

    uv run krutrim-agent-worker
    # or, equivalently:
    uv run celery -A krutrim_agent_celery.app worker --beat --loglevel=info
"""

from __future__ import annotations


def main() -> None:
    """`uv run krutrim-agent-worker` — starts the Celery worker with in-process
    beat (fine for a single-node deployment; see `krutrim_agent_celery/app.py`).

    Any extra CLI args pass straight through to `celery worker`, e.g.
    `uv run krutrim-agent-worker --concurrency=4 --loglevel=debug --queues=rag`.
    """
    import sys

    from krutrim_agent_celery.app import celery_app

    celery_app.worker_main(argv=["worker", "--beat", *sys.argv[1:]])
