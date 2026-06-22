"""V2 Phase 1: the delivery worker — success, retry/backoff, needs_attention."""

from __future__ import annotations

import worker
from core.config import Settings
from core.espo import EspoError
from core.store import Claimed


class FakeWorkerStore:
    def __init__(self) -> None:
        self.completed: list = []
        self.retried: list = []
        self.failed: list = []
        self.progress: dict = {}

    async def create_all(self):
        pass

    async def dispose(self):
        pass

    async def save_progress(self, submission_id, progress):
        self.progress[submission_id] = dict(progress)

    async def mark_completed(self, submission_id, result):
        self.completed.append((submission_id, result))

    async def mark_retry(self, submission_id, *, attempt_count, next_attempt_at, error):
        self.retried.append((submission_id, attempt_count, error))

    async def mark_failed(self, submission_id, *, status, error):
        self.failed.append((submission_id, status, error))


def _settings(**over):
    base = dict(espo_dry_run=True, max_delivery_attempts=3)
    base.update(over)
    return Settings(**base)


def _claimed(attempt_count=0, slug="info-request"):
    return Claimed(
        id="sub-1",
        form_slug=slug,
        submission_token="tok-worker-1",
        payload={
            "first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com",
            "message": "Tell me more.", "submission_token": "tok-worker-1",
        },
        progress=None,
        attempt_count=attempt_count,
    )


class _Boom:
    def __init__(self, exc):
        self._exc = exc

    async def create(self, *a, **k):
        raise self._exc

    async def find_one(self, *a, **k):
        return None

    async def update(self, *a, **k):
        return {}

    async def relate(self, *a, **k):
        return None

    async def upload_attachment(self, **k):
        return "att"


async def test_worker_delivers_via_dry_run():
    store = FakeWorkerStore()
    await worker.process_one(store, _settings(), _claimed())
    assert len(store.completed) == 1
    sid, result = store.completed[0]
    assert sid == "sub-1"
    assert "contactId" in result
    assert store.retried == [] and store.failed == []


async def test_worker_retries_transient(monkeypatch):
    monkeypatch.setattr(worker, "_client", lambda s: _Boom(EspoError("create X failed: HTTP 503 busy")))
    store = FakeWorkerStore()
    await worker.process_one(store, _settings(), _claimed(attempt_count=0))
    assert store.completed == []
    assert len(store.retried) == 1
    sid, attempt, _ = store.retried[0]
    assert (sid, attempt) == ("sub-1", 1)


async def test_worker_permanent_failure_needs_attention(monkeypatch):
    monkeypatch.setattr(worker, "_client", lambda s: _Boom(EspoError("create X failed: HTTP 400 bad enum")))
    store = FakeWorkerStore()
    await worker.process_one(store, _settings(), _claimed())
    assert store.retried == []
    assert len(store.failed) == 1
    sid, status, _ = store.failed[0]
    assert (sid, status) == ("sub-1", "needs_attention")


async def test_worker_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr(worker, "_client", lambda s: _Boom(EspoError("HTTP 503 busy")))
    store = FakeWorkerStore()
    # attempt_count=2, max=3 → this is attempt 3 → no more retries.
    await worker.process_one(store, _settings(max_delivery_attempts=3), _claimed(attempt_count=2))
    assert store.retried == []
    assert store.failed and store.failed[0][1] == "needs_attention"


async def test_worker_unknown_form_needs_attention():
    store = FakeWorkerStore()
    await worker.process_one(store, _settings(), _claimed(slug="not-a-form"))
    assert store.failed and store.failed[0][1] == "needs_attention"
