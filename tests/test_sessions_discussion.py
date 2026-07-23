"""Discussion pane (partner + sponsor): the staff-internal record comment
stream on the Overview. Router gating + store wiring, with a fake store and a
fake CRM client (the real Postgres round-trip lives in test_store_pg.py)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from forms import info_request
from sessions.config import MENTOR, PARTNER, SPONSOR

_USER = {"userId": "u1", "userName": "boss", "name": "The Boss", "isAdmin": True, "token": "tok"}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- fakes -----------------------------------------------------------------

class FakeClient:
    """Just enough CRM: an async get() that the ACL-gate read uses. A missing
    record raises EspoError (a 403/404 from the CRM)."""

    def __init__(self, readable=("P1",)):
        self._readable = set(readable)

    async def get(self, entity, record_id, select=None):
        if record_id not in self._readable:
            raise EspoError("Record not found or forbidden")
        return {"id": record_id}


class FakeStore:
    """In-memory record_comment behavior (mirrors PostgresStore's methods)."""

    def __init__(self):
        self.rows: list[dict] = []
        self._seq = 0

    async def add_record_comment(self, parent_type, parent_id, *, author, author_name, body):
        self._seq += 1
        row = {
            "id": f"c{self._seq}", "parent_type": parent_type, "parent_id": parent_id,
            "author": author, "author_name": author_name, "body": body,
            "created_at": "2026-07-23T12:00:00+00:00",
        }
        self.rows.append(row)
        return {k: row[k] for k in ("id", "author", "author_name", "body", "created_at")}

    async def list_record_comments(self, parent_type, parent_id):
        return [
            {k: r[k] for k in ("id", "author", "author_name", "body", "created_at")}
            for r in self.rows
            if r["parent_type"] == parent_type and r["parent_id"] == parent_id
        ]


def _app(monkeypatch, store=None):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()
    return create_app([info_request.SPEC], store=store)


def _as(monkeypatch, user, client=None):
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr(
        "sessions.router.client_for", lambda settings, u: client or FakeClient()
    )


# --- config ----------------------------------------------------------------

def test_discussion_flag_partner_sponsor_only():
    assert PARTNER.discussion_enabled is True
    assert SPONSOR.discussion_enabled is True
    assert MENTOR.discussion_enabled is False


def test_session_config_reports_discussion_enabled(monkeypatch):
    _as(monkeypatch, _USER)
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/partnersessions/api/session").json()["discussionEnabled"] is True
        assert c.get("/sponsorsessions/api/session").json()["discussionEnabled"] is True
        assert c.get("/mentorsessions/api/session").json()["discussionEnabled"] is False


# --- endpoints -------------------------------------------------------------

def test_mentor_domain_has_no_comment_endpoints(monkeypatch):
    _as(monkeypatch, _USER)
    with TestClient(_app(monkeypatch, store=FakeStore())) as c:
        # No comments route on the mentor domain: the request falls through to
        # the static mount (GET => 404 file-not-found, POST => 405). Either way
        # it is NOT a handled endpoint.
        assert c.get("/mentorsessions/api/records/E1/comments").status_code in (404, 405)
        assert c.post(
            "/mentorsessions/api/records/E1/comments", json={"body": "hi"}
        ).status_code in (404, 405)


def test_add_and_list_comment(monkeypatch):
    _as(monkeypatch, _USER)
    store = FakeStore()
    with TestClient(_app(monkeypatch, store=store)) as c:
        r = c.post("/partnersessions/api/records/P1/comments", json={"body": "  hello team  "})
        assert r.status_code == 200
        comment = r.json()["comment"]
        assert comment["body"] == "hello team"       # trimmed
        assert comment["author"] == "boss"           # userName
        assert comment["author_name"] == "The Boss"  # display name -> avatar
        # stored keyed by (CPartnerProfile, P1)
        assert store.rows[0]["parent_type"] == "CPartnerProfile"

        got = c.get("/partnersessions/api/records/P1/comments").json()["comments"]
        assert [x["body"] for x in got] == ["hello team"]


def test_empty_comment_rejected(monkeypatch):
    _as(monkeypatch, _USER)
    with TestClient(_app(monkeypatch, store=FakeStore())) as c:
        assert c.post(
            "/partnersessions/api/records/P1/comments", json={"body": "   "}
        ).status_code == 422


def test_comment_gated_on_record_read(monkeypatch):
    # A record the caller can't read (CRM 403/404 on the gate get) never resolves.
    _as(monkeypatch, _USER, client=FakeClient(readable=()))
    with TestClient(_app(monkeypatch, store=FakeStore())) as c:
        r = c.post("/partnersessions/api/records/NOPE/comments", json={"body": "x"})
        assert r.status_code in (403, 404, 502)


def test_no_store_503(monkeypatch):
    _as(monkeypatch, _USER)
    with TestClient(_app(monkeypatch, store=None)) as c:
        assert c.get("/partnersessions/api/records/P1/comments").status_code == 503
        assert c.post(
            "/partnersessions/api/records/P1/comments", json={"body": "x"}
        ).status_code == 503


def test_detail_merges_comments(monkeypatch):
    _as(monkeypatch, _USER)
    store = FakeStore()

    async def fake_detail(cfg, client, parent_id):
        return {"id": parent_id, "name": "Acme", "overview": []}

    monkeypatch.setattr("sessions.service.get_detail", fake_detail)
    with TestClient(_app(monkeypatch, store=store)) as c:
        c.post("/partnersessions/api/records/P1/comments", json={"body": "note one"})
        detail = c.get("/partnersessions/api/records/P1").json()
        assert [x["body"] for x in detail["comments"]] == ["note one"]


def test_detail_omits_comments_without_store(monkeypatch):
    # No store => the detail carries no `comments` key => the frontend hides the pane.
    _as(monkeypatch, _USER)

    async def fake_detail(cfg, client, parent_id):
        return {"id": parent_id, "name": "Acme", "overview": []}

    monkeypatch.setattr("sessions.service.get_detail", fake_detail)
    with TestClient(_app(monkeypatch, store=None)) as c:
        detail = c.get("/partnersessions/api/records/P1").json()
        assert "comments" not in detail
