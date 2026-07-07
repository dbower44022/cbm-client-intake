"""Session-expired handling: an expired EspoCRM token on a per-user call returns
401 (and clears the shared staff session) instead of a confusing 502."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from assignments.auth import session_expired
from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from forms import info_request

# A non-admin who IS entitled to the app (on the gate team) — the point of these
# tests is what happens when an entitled user's CRM token has expired.
_USER = {"userId": "u", "userName": "x", "name": "X", "isAdmin": False, "token": "tok",
         "teams": ["Client Administration Team"], "roles": []}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_session_expired_detects_401_only():
    assert session_expired(EspoError("list CEngagement failed: HTTP 401 Unauthorized"))
    assert not session_expired(EspoError("create failed: HTTP 500 Server Error"))
    assert not session_expired(EspoError("create failed: HTTP 403 Forbidden"))


def test_session_expired_ignores_status_text_in_body():
    # The real status code is the FIRST "HTTP <code>" in the message; an echoed
    # response body that merely mentions "HTTP 401" must not be misread as expiry.
    assert not session_expired(
        EspoError("update failed: HTTP 502 Bad Gateway — upstream said HTTP 401")
    )
    assert session_expired(EspoError("HTTP 401 token expired"))


def _app(monkeypatch, raises: EspoError):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")  # enables the assignments router
    monkeypatch.setenv("ASSIGN_ALLOWED_TEAMS", "Client Administration Team")
    get_settings.cache_clear()
    monkeypatch.setattr("assignments.auth.current_user", lambda request: _USER)
    monkeypatch.setattr("assignments.router.client_for", lambda settings, user: object())

    async def boom(*args, **kwargs):
        raise raises

    monkeypatch.setattr("assignments.service.list_engagements", boom)
    return create_app([info_request.SPEC])


def test_expired_token_returns_401(monkeypatch):
    app = _app(monkeypatch, EspoError("list CEngagement failed: HTTP 401 Unauthorized"))
    with TestClient(app) as c:
        r = c.get("/assignments/api/engagements")
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


def test_other_crm_error_still_502(monkeypatch):
    app = _app(monkeypatch, EspoError("list CEngagement failed: HTTP 500 Server Error"))
    with TestClient(app) as c:
        r = c.get("/assignments/api/engagements")
    assert r.status_code == 502
