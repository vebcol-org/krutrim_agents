"""Live-status pub/sub for sandbox containers and background jobs.

Redis is the only implementation today (`RedisPubSubBackend`) — publish call
sites (`SandboxRegistry`, the idle reaper, the embedding precompute task)
depend on the `PubSubBackend` ABC, not on `redis` directly, so a future
broker swap (RabbitMQ, per the pending migration plan) means writing one new
class — nothing else changes. Celery's own broker/result-backend config is
separate and already isolated from this module.

`publish()` is deliberately synchronous — a single fire-and-forget Redis
command, not a long-lived loop — consistent with this codebase's sandbox
module already calling the (sync-only) Docker SDK directly from async
methods (see `sandbox/registry.py`) rather than wrapping every quick I/O
call in a thread. The SSE *subscribing* side
(`krutrim_agent_backend/api/status_routes.py`) is a genuinely long-lived async loop
and uses `redis.asyncio` directly instead of this ABC — a different shape
of operation, not part of the publish contract.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

CONTAINER_STATUS_CHANNEL = "sandbox:container:{owner_id}"
JOB_STATUS_CHANNEL = "sandbox:job:{job_id}"


class PubSubBackend(ABC):
    @abstractmethod
    def publish(self, channel: str, message: str) -> None: ...


class RedisPubSubBackend(PubSubBackend):
    def __init__(self, redis_url: str) -> None:
        import redis

        self._client = redis.Redis.from_url(redis_url)

    def publish(self, channel: str, message: str) -> None:
        self._client.publish(channel, message)


def publish_container_status(
    pubsub: PubSubBackend, owner_id: str, status: str, **extra
) -> None:
    payload = json.dumps({"status": status, **extra})
    pubsub.publish(CONTAINER_STATUS_CHANNEL.format(owner_id=owner_id), payload)


def publish_job_progress(
    pubsub: PubSubBackend, job_id: str, processed: int, total: int
) -> None:
    payload = json.dumps({"processed": processed, "total": total})
    pubsub.publish(JOB_STATUS_CHANNEL.format(job_id=job_id), payload)


def publish_job_stage_progress(
    pubsub: PubSubBackend, job_id: str, stage: str, processed: int, total: int
) -> None:
    """Like `publish_job_progress`, plus a named `stage` — used by multi-stage
    jobs (e.g. `process_rag_document`'s extract/chunk/embed/index pipeline)
    where a bare processed/total count doesn't say what's actually happening.
    Publishes to the same `JOB_STATUS_CHANNEL`/job_id — the SSE route
    (`GET /api/status/jobs/{job_id}`) forwards whatever JSON shape is
    published verbatim, so no route change is needed to support this."""
    payload = json.dumps({"stage": stage, "processed": processed, "total": total})
    pubsub.publish(JOB_STATUS_CHANNEL.format(job_id=job_id), payload)


def publish_job_error(pubsub: PubSubBackend, job_id: str, error: str) -> None:
    """A job's terminal failure state — without this, a failed
    `process_rag_document` run is invisible to the SSE-only frontend (Celery's
    own result backend isn't subscribed to from the browser). `stage: "error"`
    lets `GET /api/status/jobs/{job_id}` subscribers distinguish this from an
    in-progress `publish_job_stage_progress` event."""
    payload = json.dumps({"stage": "error", "error": error})
    pubsub.publish(JOB_STATUS_CHANNEL.format(job_id=job_id), payload)
