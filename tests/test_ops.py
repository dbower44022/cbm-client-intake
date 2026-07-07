"""V2 Phase 2: the ops console router — auth gating, list, re-drive."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from forms import info_request

_USER = {"userName": "staffer", "name": "Staff Person", "isAdmin": True}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeOpsStore:
    def __init__(self):
        self.rows = {
            "abc12345": {
                "id": "abc12345", "form_slug": "info-request", "status": "needs_attention",
                "attempt_count": 2, "last_error": "boom", "email": "a@b.com",
                "payload": {"first_name": "Ada"}, "progress": None, "result": None,
            }
        }
        self.redriven = []

    async def list_submissions(self, *, status=None, form=None, limit=200):
        rows = list(self.rows.values())
        if status:
            rows = [r for r in rows if r["status"] == status]
        if form:
            rows = [r for r in rows if r["form_slug"] == form]
        return rows

    async def get_submission(self, submission_id):
        return self.rows.get(submission_id)

    async def counts_by_status(self):
        return {"needs_attention": 1}

    async def redrive(self, submission_id):
        if submission_id in self.rows:
            self.redriven.append(submission_id)
            return True
        return False

    async def discard(self, submission_id):
        row = self.rows.get(submission_id)
        if row is None or row["status"] == "completed":
            return False
        row["status"] = "discarded"
        return True

    async def metrics(self):
        return {"counts": {"needs_attention": 1}, "needsAttention": 1,
                "backlog": 0, "oldestPendingAgeSeconds": None, "avgLatencySeconds": None}


def _app(monkeypatch, store):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")  # enables session + ops router
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])
    app.state.submission_store = store
    return app


def _authed(monkeypatch):
    monkeypatch.setattr("ops.router.current_user", lambda request: _USER)


def test_requires_auth(monkeypatch):
    with TestClient(_app(monkeypatch, FakeOpsStore())) as c:
        assert c.get("/ops/api/submissions").status_code == 401


def test_gated_to_marketing_admin_team(monkeypatch):
    """/ops has its own request-time gate (Marketing Admin Team by default) —
    membership in the other staff teams is not enough."""
    outsider = {"userName": "cc", "name": "C", "isAdmin": False,
                "teams": ["Client Administration Team"], "roles": []}
    monkeypatch.setattr("ops.router.current_user", lambda request: outsider)
    with TestClient(_app(monkeypatch, FakeOpsStore())) as c:
        r = c.get("/ops/api/submissions")
    assert r.status_code == 403
    assert "Marketing Admin Team" in r.json()["detail"]

    member = dict(outsider, teams=["Marketing Admin Team"])
    monkeypatch.setattr("ops.router.current_user", lambda request: member)
    with TestClient(_app(monkeypatch, FakeOpsStore())) as c:
        assert c.get("/ops/api/submissions").status_code == 200


def test_lists_submissions_and_counts(monkeypatch):
    store = FakeOpsStore()
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        data = c.get("/ops/api/submissions").json()
    assert data["counts"] == {"needs_attention": 1}
    assert [r["id"] for r in data["submissions"]] == ["abc12345"]


def test_503_when_store_not_configured(monkeypatch):
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, None)) as c:
        assert c.get("/ops/api/submissions").status_code == 503


def test_redrive(monkeypatch):
    store = FakeOpsStore()
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        ok = c.post("/ops/api/submissions/abc12345/redrive")
        missing = c.post("/ops/api/submissions/nope/redrive")
    assert ok.status_code == 200 and ok.json()["status"] == "requeued"
    assert store.redriven == ["abc12345"]
    assert missing.status_code == 404


def test_discard(monkeypatch):
    store = FakeOpsStore()
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, store)) as c:
        ok = c.post("/ops/api/submissions/abc12345/discard")
        missing = c.post("/ops/api/submissions/nope/discard")
    assert ok.status_code == 200 and ok.json()["status"] == "discarded"
    assert store.rows["abc12345"]["status"] == "discarded"
    assert missing.status_code == 404


def test_detail(monkeypatch):
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, FakeOpsStore())) as c:
        d = c.get("/ops/api/submissions/abc12345").json()
    assert d["payload"]["first_name"] == "Ada"
    assert d["status"] == "needs_attention"


def test_metrics(monkeypatch):
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch, FakeOpsStore())) as c:
        m = c.get("/ops/api/metrics").json()
    assert m["needsAttention"] == 1 and "backlog" in m
