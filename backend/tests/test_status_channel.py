"""Tests for `krutrim_agent_sandbox/status_channel.py`'s publish-side helpers —
plain formatting/channel-naming logic, checked against a fake `PubSubBackend`
(no real Redis needed)."""

from __future__ import annotations

import json

from krutrim_agent_sandbox.status_channel import (
    CONTAINER_STATUS_CHANNEL,
    JOB_STATUS_CHANNEL,
    PubSubBackend,
    publish_container_status,
    publish_job_progress,
)


class FakePubSub(PubSubBackend):
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    def publish(self, channel: str, message: str) -> None:
        self.published.append((channel, message))


def test_publish_container_status_formats_channel_and_payload():
    pubsub = FakePubSub()

    publish_container_status(pubsub, "sess-1", "running", ref_count=2)

    assert len(pubsub.published) == 1
    channel, message = pubsub.published[0]
    assert channel == "sandbox:container:sess-1"
    assert json.loads(message) == {"status": "running", "ref_count": 2}


def test_publish_container_status_without_extra_fields():
    pubsub = FakePubSub()

    publish_container_status(pubsub, "sess-2", "stopped")

    channel, message = pubsub.published[0]
    assert channel == CONTAINER_STATUS_CHANNEL.format(owner_id="sess-2")
    assert json.loads(message) == {"status": "stopped"}


def test_publish_job_progress_formats_channel_and_payload():
    pubsub = FakePubSub()

    publish_job_progress(pubsub, "proj:sess:embed", 3, 10)

    channel, message = pubsub.published[0]
    assert channel == JOB_STATUS_CHANNEL.format(job_id="proj:sess:embed")
    assert json.loads(message) == {"processed": 3, "total": 10}
