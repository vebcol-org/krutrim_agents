"""Live status over SSE: sandbox container lifecycle transitions and
background job progress, both published by `krutrim_agent_celery` workers (and, for
container status, `krutrim_agent_backend`'s own `SandboxRegistry`) via Redis
pub/sub — see `krutrim_agent_sandbox/status_channel.py` for the publish side and
`SandboxRegistry`/`reap_idle_containers_once`/`precompute_embeddings` for
the call sites.

This is the illustrative minimum slice the migration plan calls out, not a
polished status UI: one channel per owner/job id, JSON messages passed
through verbatim as SSE `data:` lines. Uses `redis.asyncio` directly rather
than the `PubSubBackend` publish-side ABC — subscribing is a genuinely
long-lived async loop, a different shape of operation than a single
fire-and-forget `publish()` call (see `status_channel.py`'s own docstring).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from krutrim_agent_management.config import settings
from krutrim_agent_sandbox.status_channel import (
    CONTAINER_STATUS_CHANNEL,
    JOB_STATUS_CHANNEL,
)

router = APIRouter(prefix="/api/status", tags=["status"])


async def _sse_stream(channel: str) -> AsyncIterator[str]:
    import redis.asyncio as redis_asyncio

    client = redis_asyncio.Redis.from_url(settings.redis_url)
    pubsub = client.pubsub()
    await pubsub.subscribe(channel)
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            data = message["data"]
            text = (
                data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
            )
            yield f"data: {text}\n\n"
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await client.aclose()


@router.get("/containers/{owner_id}")
async def stream_container_status(owner_id: str) -> StreamingResponse:
    return StreamingResponse(
        _sse_stream(CONTAINER_STATUS_CHANNEL.format(owner_id=owner_id)),
        media_type="text/event-stream",
    )


@router.get("/jobs/{job_id}")
async def stream_job_progress(job_id: str) -> StreamingResponse:
    return StreamingResponse(
        _sse_stream(JOB_STATUS_CHANNEL.format(job_id=job_id)),
        media_type="text/event-stream",
    )
