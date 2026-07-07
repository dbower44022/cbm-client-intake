"""Portal: the authenticated home page + single sign-on session (/api/portal)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from forms import info_request, volunteer


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _app(monkeypatch, **env):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ASSIGN_ALLOWED_TEAMS", "Client Administration Team")
    # TestClient talks plain HTTP; a Secure cookie would never be replayed.
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "false")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    return create_app([info_request.SPEC, volunteer.SPEC])


def _fake_login(monkeypatch, user):
    async def fake_auth(settings, username, password, *, gate=True, **kwargs):
        assert gate is False  # the portal must sign in ungated
        return user

    monkeypatch.setattr("portal.router.authenticate", fake_auth)


def _user(**overrides):
    base = {"userId": "u1", "userName": "jdoe", "name": "Jane Doe", "token": "tok",
            "isAdmin": False, "teams": [], "roles": []}
    base.update(overrides)
    return base


# --- the root page swap ------------------------------------------------------

def test_root_serves_portal_when_staff_stack_on(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/")
    assert r.status_code == 200
    assert "Sign in" in r.text
    assert "portal/app.js" in r.text
    assert r.headers["cache-control"] == "no-store"
    # The public form list is NOT on the page (login only).
    assert "/volunteer/" not in r.text


def test_root_serves_public_index_without_session_secret(monkeypatch):
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    get_settings.cache_clear()
    with TestClient(create_app([info_request.SPEC, volunteer.SPEC])) as c:
        r = c.get("/")
    assert "CBM Intake Forms" in r.text
    assert "/volunteer/" in r.text  # dev app keeps the public index


# --- login + session ---------------------------------------------------------

def test_login_returns_entitlements_and_sets_session(monkeypatch):
    _fake_login(monkeypatch, _user(teams=["Client Administration Team"]))
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/api/portal/login", json={"username": "jdoe", "password": "pw"})
        assert r.status_code == 200
        data = r.json()
        # the session now works without re-login
        s = c.get("/api/portal/session")
        assert s.status_code == 200 and s.json() == data
    assert data["user"] == {"userName": "jdoe", "name": "Jane Doe", "isAdmin": False}
    assert data["apps"] == [{"title": "Client Administration", "url": "/assignments/"}]
    assert data["crmUrl"] is None  # not on the Mentor Team
    assert {f["url"] for f in data["forms"]} == {"/info-request/", "/volunteer/"}


def test_session_requires_login(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/api/portal/session").status_code == 401


def test_logout_clears_session(monkeypatch):
    _fake_login(monkeypatch, _user(isAdmin=True))
    with TestClient(_app(monkeypatch)) as c:
        c.post("/api/portal/login", json={"username": "a", "password": "b"})
        assert c.get("/api/portal/session").status_code == 200
        c.post("/api/portal/logout")
        assert c.get("/api/portal/session").status_code == 401


# --- entitlements ------------------------------------------------------------

def _login_payload(monkeypatch, user):
    _fake_login(monkeypatch, user)
    with TestClient(_app(monkeypatch)) as c:
        return c.post("/api/portal/login", json={"username": "x", "password": "y"}).json()


def test_mentor_team_sees_crm_and_forms_only(monkeypatch):
    data = _login_payload(monkeypatch, _user(teams=["Mentor Team"]))
    assert data["apps"] == []
    assert data["crmUrl"]  # the deploy's CRM base URL
    assert len(data["forms"]) == 2


def test_no_team_user_sees_only_public_forms(monkeypatch):
    data = _login_payload(monkeypatch, _user())
    assert data["apps"] == [] and data["crmUrl"] is None
    assert len(data["forms"]) == 2


def test_each_admin_team_maps_to_its_app(monkeypatch):
    data = _login_payload(monkeypatch, _user(teams=["Mentor Administration Team"]))
    assert data["apps"] == [{"title": "Mentor Administration", "url": "/mentoradmin/"}]
    data = _login_payload(monkeypatch, _user(teams=["Marketing Admin Team"]))
    assert data["apps"] == [{"title": "Submission Admin", "url": "/ops/"}]


def test_admin_sees_everything(monkeypatch):
    data = _login_payload(monkeypatch, _user(isAdmin=True))
    assert [a["url"] for a in data["apps"]] == ["/assignments/", "/mentoradmin/", "/ops/"]
    assert data["crmUrl"]


def test_multiple_teams_union(monkeypatch):
    data = _login_payload(
        monkeypatch,
        _user(teams=["Client Administration Team", "Marketing Admin Team", "Mentor Team"]),
    )
    assert [a["url"] for a in data["apps"]] == ["/assignments/", "/ops/"]
    assert data["crmUrl"]


# --- SSO: one portal login works in the staff apps ---------------------------

def test_portal_login_carries_into_staff_apps(monkeypatch):
    """The single portal sign-in is THE staff session: a Mentor-Admin-team user
    can call /mentoradmin/api directly, and gets a 403 (not a login prompt)
    from an app their teams don't include."""
    _fake_login(monkeypatch, _user(teams=["Mentor Administration Team"]))

    async def fake_list(client):
        return {"mentors": [], "metricsAvailable": True}

    monkeypatch.setattr("mentoradmin.router.assign_service.list_all_mentors", fake_list)
    monkeypatch.setattr("mentoradmin.router.client_for", lambda settings, user: object())
    with TestClient(_app(monkeypatch)) as c:
        c.post("/api/portal/login", json={"username": "x", "password": "y"})
        assert c.get("/mentoradmin/api/mentors").status_code == 200
        r = c.get("/assignments/api/engagements")
        assert r.status_code == 403
        assert "Client Administration Team" in r.json()["detail"]
