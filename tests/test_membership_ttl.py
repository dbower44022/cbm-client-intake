"""P1-12 (reliability review 2026-07-17): staff-gate membership TTL.

The signed cookie caches team membership at login; the TTL middleware re-reads
it from the CRM on staff API requests once the session stamp is older than
MEMBERSHIP_REFRESH_SECONDS — so a staffer removed from a team (or whose token
was revoked) loses app access within the window even if they bookmark an app
and never revisit the portal. /ops is the key case: it makes no CRM calls of
its own, so without this a dead token could keep listing/redriving forever.
"""

from __future__ import annotations

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from assignments import auth
from core.app import create_app
from core.config import get_settings
from forms import info_request

_USER = {
    "userId": "u1", "userName": "staffer", "name": "Staff Person", "token": "tok",
    "isAdmin": True, "teams": ["Marketing Admin Team"], "roles": [],
}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _app(monkeypatch, ttl="0"):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("MEMBERSHIP_REFRESH_SECONDS", ttl)
    # TestClient speaks http:// — a Secure cookie would never come back.
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])

    # A test-only login endpoint: establishes the shared staff session exactly
    # like the portal does (set_session stamps refreshedAt).
    async def login(request: Request):
        auth.set_session(request, _USER)
        return {"ok": True}

    app.add_api_route("/testonly/login", login, methods=["POST"])
    return app


def test_stale_membership_is_refreshed_from_the_crm(monkeypatch):
    calls = []

    async def fake_refresh(settings, sess):
        calls.append(sess["userName"])
        return dict(sess, teams=["New Team"])

    monkeypatch.setattr(auth, "refresh_membership", fake_refresh)
    with TestClient(_app(monkeypatch, ttl="0")) as c:  # ttl 0 = always stale
        c.post("/testonly/login")
        r = c.get("/ops/api/session")
    # The gate saw the refreshed session (admin passes regardless; the refresh ran).
    assert r.status_code == 200
    assert calls == ["staffer"]


def test_fresh_membership_is_not_rechecked(monkeypatch):
    calls = []

    async def fake_refresh(settings, sess):
        calls.append(1)
        return sess

    monkeypatch.setattr(auth, "refresh_membership", fake_refresh)
    with TestClient(_app(monkeypatch, ttl="900")) as c:  # login stamp is fresh
        c.post("/testonly/login")
        c.get("/ops/api/session")
        c.get("/ops/api/session")
    assert calls == []


def test_dead_token_clears_session_and_401s(monkeypatch):
    async def fake_refresh(settings, sess):
        raise auth.AuthError("Your session has expired — please sign in again.")

    monkeypatch.setattr(auth, "refresh_membership", fake_refresh)
    with TestClient(_app(monkeypatch, ttl="0")) as c:
        c.post("/testonly/login")
        r = c.get("/ops/api/session")
    assert r.status_code == 401


def test_portal_api_is_exempt(monkeypatch):
    """The portal's own session restore already refreshes — the middleware must
    not double-refresh /api/portal requests."""
    calls = []

    async def fake_refresh(settings, sess):
        calls.append(1)
        return sess

    monkeypatch.setattr(auth, "refresh_membership", fake_refresh)
    with TestClient(_app(monkeypatch, ttl="0")) as c:
        c.post("/testonly/login")
        c.post("/api/portal/logout")
    assert calls == []
