"""V2 Phase 0: the durable-store wiring in the intake handler.

Uses a fake store (no database) to verify capture-first, durable idempotency,
and held-honeypot capture. The store-disabled path stays V1 and is covered by
the existing per-form tests.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.store import (
    STATUS_COMPLETED,
    STATUS_HELD,
    STATUS_PENDING,
    Captured,
    _connect_args,
    _normalize_url,
)
from forms import info_request


def test_normalize_url_strips_libpq_params():
    url = "postgresql://u:p@db.example.com:25060/cbm?sslmode=require&channel_binding=require"
    normalized = _normalize_url(url)
    assert normalized.startswith("postgresql+asyncpg://")
    assert "sslmode" not in normalized and "channel_binding" not in normalized
    # SSL is required for the managed URL, not for a plain local one.
    assert "ssl" in _connect_args(url)
    assert _connect_args("postgresql://u:p@localhost:5432/cbm") == {}


class FakeStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict] = {}
        self.captures: list[tuple[str, str, str, dict]] = []
        self.completed: list[tuple[str, dict]] = []
        self.failed: list[tuple[str, str, str]] = []
        self._n = 0

    async def create_all(self) -> None:
        pass

    async def dispose(self) -> None:
        pass

    async def capture(self, form_slug, submission_token, payload, *, status) -> Captured:
        key = (form_slug, submission_token)
        if key in self.rows:
            r = self.rows[key]
            return Captured(r["id"], False, r["status"], r["result"])
        self._n += 1
        rid = f"sub-{self._n}"
        self.rows[key] = {"id": rid, "status": status, "result": None}
        self.captures.append((form_slug, submission_token, status, payload))
        return Captured(rid, True, status, None)

    async def mark_completed(self, submission_id, result) -> None:
        for r in self.rows.values():
            if r["id"] == submission_id:
                r["status"] = STATUS_COMPLETED
                r["result"] = result
        self.completed.append((submission_id, result))

    async def mark_failed(self, submission_id, *, status, error) -> None:
        for r in self.rows.values():
            if r["id"] == submission_id:
                r["status"] = status
        self.failed.append((submission_id, status, error))


def _client(store) -> TestClient:
    return TestClient(create_app([info_request.SPEC], store=store))


def _body(**over):
    body = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "message": "Tell me more about mentoring.",
        "submission_token": "tok-store-1",
    }
    body.update(over)
    return body


def test_capture_first_then_complete():
    store = FakeStore()
    with _client(store) as c:
        r = c.post("/api/info-request/intake", json=_body())
    assert r.status_code == 200 and r.json()["status"] == "ok"
    # captured once as pending, before the (dry-run) CRM work, then completed.
    assert len(store.captures) == 1
    assert store.captures[0][2] == STATUS_PENDING
    assert store.captures[0][3]["company_url"] == ""  # honeypot never persisted
    assert len(store.completed) == 1
    _, result = store.completed[0]
    assert "contactId" in result


def test_durable_idempotent_replay():
    store = FakeStore()
    with _client(store) as c:
        first = c.post("/api/info-request/intake", json=_body()).json()
        second = c.post("/api/info-request/intake", json=_body()).json()
    assert second.get("idempotent") is True
    # despite two posts: one capture, one completion, and the same ids returned.
    assert len(store.captures) == 1
    assert len(store.completed) == 1
    assert second["contactId"] == first["contactId"]


def test_honeypot_captured_held_and_not_processed():
    store = FakeStore()
    with _client(store) as c:
        r = c.post(
            "/api/info-request/intake",
            json=_body(company_url="i-am-a-bot", submission_token="tok-honeypot-1"),
        )
    assert r.json()["status"] == "received"
    assert store.captures[0][2] == STATUS_HELD
    assert store.completed == []  # held submissions are never processed


def test_healthz_reports_durable_store():
    store = FakeStore()
    with _client(store) as c:
        assert c.get("/healthz").json()["durableStore"] is True
    # And false when there is no store.
    with TestClient(create_app([info_request.SPEC])) as c:
        assert c.get("/healthz").json()["durableStore"] is False


def test_async_delivery_defers_processing(monkeypatch):
    # With ASYNC_DELIVERY on, the accept endpoint captures and returns without
    # processing — the worker does the CRM work later.
    monkeypatch.setenv("ASYNC_DELIVERY", "true")
    get_settings.cache_clear()
    store = FakeStore()
    try:
        with TestClient(create_app([info_request.SPEC], store=store)) as c:
            r = c.post("/api/info-request/intake", json=_body(submission_token="tok-async-1")).json()
        assert r["status"] == "received"
        assert "reference" in r
        assert len(store.captures) == 1  # captured…
        assert store.completed == []     # …but not processed inline
    finally:
        get_settings.cache_clear()
