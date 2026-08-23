"""Background/scheduled work for the sandbox lifecycle — today, just the
idle-container reaper (`tasks/reap_idle_containers.py`). Its own deployable
package within the `backend/` uv workspace (see `services/krutrim_agent_celery/pyproject.toml`),
depending on `krutrim_agent_management`/`krutrim_agent_sandbox` as libraries. Run a worker
with:

    uv run celery -A krutrim_agent_celery.app worker --beat --loglevel=info
"""
