"""Tests for `process_rag_document`'s Redis-lock serialization — a multi-file
upload's extraction/embedding must run one file at a time cluster-wide
(regardless of worker concurrency), so these verify the locking wrapper in
isolation from `process_rag_document_once`'s own ingestion logic (already
covered by `test_process_rag_document.py`)."""

from __future__ import annotations

import krutrim_agent_celery.tasks.process_rag_document as module
import redis


class FakeLock:
    def __init__(self, acquirable: bool) -> None:
        self._acquirable = acquirable
        self.acquire_calls = 0
        self.released = False

    def acquire(self, blocking: bool = True) -> bool:
        self.acquire_calls += 1
        assert blocking is False, "must not block a worker slot waiting for the lock"
        return self._acquirable

    def release(self) -> None:
        self.released = True


class FakeRedisClient:
    def __init__(self, lock: FakeLock) -> None:
        self._lock = lock

    def lock(self, name: str, timeout: int | None = None):
        return self._lock


class RetryCalled(Exception):
    def __init__(self, countdown) -> None:
        super().__init__(f"retry(countdown={countdown})")
        self.countdown = countdown


def test_retries_without_running_ingestion_when_lock_unavailable(monkeypatch):
    fake_lock = FakeLock(acquirable=False)
    monkeypatch.setattr(redis.Redis, "from_url", staticmethod(lambda url: FakeRedisClient(fake_lock)))

    def fake_retry(countdown=None, **kwargs):
        raise RetryCalled(countdown)

    monkeypatch.setattr(module.process_rag_document, "retry", fake_retry)

    called = False

    async def fake_once(*args, **kwargs):
        nonlocal called
        called = True
        return {"status": "ok"}

    monkeypatch.setattr(module, "process_rag_document_once", fake_once)

    try:
        module.process_rag_document("s1", "d1", "_rag_uploads/d1.pdf", "Title")
        raised = False
    except RetryCalled as exc:
        raised = True
        assert exc.countdown == module._RAG_INGESTION_RETRY_COUNTDOWN_SECONDS

    assert raised
    assert called is False  # never ran the heavy body — the whole point of retrying instead of blocking
    assert fake_lock.released is False  # never acquired, so nothing to release


def test_runs_ingestion_and_releases_lock_when_acquired(monkeypatch):
    fake_lock = FakeLock(acquirable=True)
    monkeypatch.setattr(redis.Redis, "from_url", staticmethod(lambda url: FakeRedisClient(fake_lock)))

    async def fake_once(*args, **kwargs):
        return {"status": "ok", "document_id": "d1", "title": "Title", "chunks_added": 3}

    monkeypatch.setattr(module, "process_rag_document_once", fake_once)

    result = module.process_rag_document("s1", "d1", "_rag_uploads/d1.pdf", "Title")

    assert result == {"status": "ok", "document_id": "d1", "title": "Title", "chunks_added": 3}
    assert fake_lock.acquire_calls == 1
    assert fake_lock.released is True


def test_releases_lock_even_when_ingestion_raises(monkeypatch):
    fake_lock = FakeLock(acquirable=True)
    monkeypatch.setattr(redis.Redis, "from_url", staticmethod(lambda url: FakeRedisClient(fake_lock)))

    async def fake_once(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "process_rag_document_once", fake_once)

    try:
        module.process_rag_document("s1", "d1", "_rag_uploads/d1.pdf", "Title")
        raised = False
    except RuntimeError:
        raised = True

    assert raised
    assert fake_lock.released is True
