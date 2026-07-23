"""V2 Phase 1: the delivery worker — success, retry/backoff, needs_attention."""

from __future__ import annotations

import worker
from core.config import Settings
from core.espo import EspoError, EspoTransportError
from core.store import Claimed


class FakeWorkerStore:
    def __init__(self) -> None:
        self.completed: list = []
        self.retried: list = []
        self.failed: list = []
        self.progress: dict = {}
        self.claim_calls = 0
        self.to_claim: list = []

    async def create_all(self):
        pass

    async def dispose(self):
        pass

    async def claim_batch(self, limit, *, lease_seconds=900):
        self.claim_calls += 1
        items, self.to_claim = self.to_claim, []
        return items

    async def save_progress(self, submission_id, progress):
        self.progress[submission_id] = dict(progress)

    async def mark_completed(self, submission_id, result, *, auto_close_reason=None):
        self.completed.append((submission_id, result))
        self.autoclosed = getattr(self, "autoclosed", [])
        if auto_close_reason:
            self.autoclosed.append((submission_id, auto_close_reason))

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


# --- 2026-07-17 reliability hardening (Phase 1) --------------------------------


async def test_worker_poison_payload_needs_attention_not_crash():
    """P0-1: a payload the current schema rejects must route to needs_attention
    (with a diagnosable traceback), never escape process_one and kill the loop."""
    store = FakeWorkerStore()
    poisoned = Claimed(
        id="sub-poison",
        form_slug="info-request",
        submission_token="tok-poison",
        payload={"first_name": "Ada", "submission_token": "tok-poison"},  # missing required fields
        progress=None,
        attempt_count=0,
    )
    await worker.process_one(store, _settings(), poisoned)
    assert store.retried == [] and store.completed == []
    assert len(store.failed) == 1
    sid, status, error = store.failed[0]
    assert (sid, status) == ("sub-poison", "needs_attention")
    assert "--- traceback (tail) ---" in error
    assert "ValidationError" in error or "validation error" in error


async def test_worker_needs_attention_stores_traceback_tail(monkeypatch):
    monkeypatch.setattr(worker, "_client", lambda s: _Boom(EspoError("create X failed: HTTP 400 bad enum")))
    store = FakeWorkerStore()
    await worker.process_one(store, _settings(), _claimed())
    assert store.failed
    error = store.failed[0][2]
    assert "create X failed: HTTP 400 bad enum" in error
    assert "--- traceback (tail) ---" in error


async def test_worker_transport_error_is_transient(monkeypatch):
    """P0-3: EspoClient now wraps transport failures as EspoTransportError —
    the worker must keep classifying them as retryable."""
    monkeypatch.setattr(worker, "_client", lambda s: _Boom(
        EspoTransportError("create Contact failed: could not reach the CRM (crm-test.example): ConnectError: boom")
    ))
    store = FakeWorkerStore()
    await worker.process_one(store, _settings(), _claimed(attempt_count=0))
    assert store.failed == []
    assert len(store.retried) == 1


async def test_run_cycle_sync_mode_never_claims():
    """P0-2: with ASYNC_DELIVERY off (the documented rollback), the web tier
    delivers synchronously — the worker must not also claim pending rows."""
    store = FakeWorkerStore()
    store.to_claim = [_claimed()]
    claimed = await worker.run_cycle(store, _settings(async_delivery=False))
    assert claimed == 0
    assert store.claim_calls == 0
    assert store.completed == [] and store.retried == [] and store.failed == []


async def test_run_cycle_claims_when_async_delivery_on():
    store = FakeWorkerStore()
    store.to_claim = [_claimed()]
    claimed = await worker.run_cycle(store, _settings(async_delivery=True))
    assert claimed == 1
    assert store.claim_calls == 1
    assert len(store.completed) == 1


async def test_run_cycle_survives_store_errors():
    """P0-1 loop guard: a store/claim failure logs and reports an empty batch —
    it must never propagate and kill the worker process."""

    class ExplodingStore(FakeWorkerStore):
        async def claim_batch(self, limit, *, lease_seconds=900):
            raise RuntimeError("db went away")

    claimed = await worker.run_cycle(ExplodingStore(), _settings(async_delivery=True))
    assert claimed == 0


async def test_sigterm_stops_mid_batch_after_current_item():
    """Phase 6 graceful shutdown: stop set mid-batch finishes the CURRENT item
    and skips the rest (their leases expire and the next worker reclaims)."""
    import asyncio

    store = FakeWorkerStore()
    stop = asyncio.Event()
    stop.set()  # SIGTERM arrived while the batch was being claimed
    store.to_claim = [
        _claimed(), 
        Claimed(id="sub-2", form_slug="info-request", submission_token="tok-2",
                payload={"first_name": "B", "last_name": "C", "email": "b@c.d",
                         "message": "hi", "submission_token": "tok-2"},
                progress=None, attempt_count=0),
    ]
    claimed = await worker.run_once(store, _settings(), stop)
    assert claimed == 2  # both were claimed…
    assert len(store.completed) == 1  # …but only the in-flight item delivered


# --- auto-close of record-creating submissions (Doug's ruling 2026-07-22) ----


def test_autoclose_reason_helper():
    from core.store import autoclose_reason
    assert autoclose_reason("info-request") is None   # needs an admin reply
    assert autoclose_reason("info-email") is None
    for slug in ("client-intake", "volunteer", "partner", "sponsor"):
        assert autoclose_reason(slug) == "Process completed"


async def test_info_request_is_not_autoclosed():
    """An info-request delivers but stays OPEN — it needs a human response."""
    store = FakeWorkerStore()
    await worker.process_one(store, _settings(), _claimed(slug="info-request"))
    assert len(store.completed) == 1
    assert getattr(store, "autoclosed", []) == []


def _volunteer_claimed():
    return Claimed(
        id="vol-1", form_slug="volunteer", submission_token="tok-vol-1",
        payload={
            "first_name": "Ada", "last_name": "Lovelace", "email": "ada@example.com",
            "confirm_email": "ada@example.com", "zip_code": "44114",
            "phone": "2165550100", "why_volunteer": "Help founders.",
            "areas_of_expertise": ["Marketing"], "terms_accepted": True,
            "submission_token": "tok-vol-1",
        },
        progress=None, attempt_count=0,
    )


async def test_record_creating_form_autocloses_on_delivery():
    """A volunteer submission delivers its CRM records and is auto-closed with
    'Process completed' — nothing for the Submission Admin team to do."""
    store = FakeWorkerStore()
    await worker.process_one(store, _settings(), _volunteer_claimed())
    assert len(store.completed) == 1
    assert store.autoclosed == [("vol-1", "Process completed")]
