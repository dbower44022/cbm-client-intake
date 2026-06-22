"""Mentor Admin router + service: auth gating, list/detail/update, whitelist."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from forms import info_request
from mentoradmin import service

_USER = {"userId": "u1", "userName": "boss", "name": "Mentor Boss", "isAdmin": True, "token": "tok"}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- service-level fake client ---

class FakeClient:
    """Captures get/update calls and returns canned records."""

    def __init__(self, record=None, metadata=None):
        self.record = record or {"id": "m1", "name": "Jane Mentor", "mentorStatus": "Active"}
        self._metadata = metadata or {}
        self.updates = []
        self.gets = []

    async def get(self, entity, record_id, select=None):
        self.gets.append((entity, record_id, select))
        return dict(self.record, id=record_id)

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        self.record.update(payload)
        return dict(self.record, id=record_id)

    async def metadata(self, key):
        return self._metadata


# --- service tests ---

@pytest.mark.asyncio
async def test_update_mentor_whitelists_fields():
    client = FakeClient()
    await service.update_mentor(
        client, "m1",
        {"mentorStatus": "Inactive", "id": "hacked", "totalMentoringHours": 999, "name": "New Name"},
    )
    assert len(client.updates) == 1
    _, rid, payload = client.updates[0]
    assert rid == "m1"
    # only whitelisted editable fields survive
    assert payload == {"mentorStatus": "Inactive", "name": "New Name"}
    assert "id" not in payload and "totalMentoringHours" not in payload


@pytest.mark.asyncio
async def test_update_mentor_no_editable_changes_skips_update():
    client = FakeClient()
    await service.update_mentor(client, "m1", {"totalMentoringHours": 5, "id": "x"})
    assert client.updates == []  # nothing whitelisted -> no write
    assert client.gets  # still re-reads the record


@pytest.mark.asyncio
async def test_get_mentor_selects_contact_info_foreign_fields():
    """The read-only summary card needs the Contact-mirrored foreign fields."""
    client = FakeClient()
    await service.get_mentor(client, "m1")
    _, _, select = client.gets[0]
    cols = select.split(",")
    for f in ("personalEmail", "contactPhone", "contactStreet", "contactCity", "postalCode"):
        assert f in cols
    # these stay read-only — never in the editable whitelist
    assert not (service.EDITABLE_NAMES & {"personalEmail", "contactPhone", "postalCode"})


@pytest.mark.asyncio
async def test_field_options_reads_live_enums():
    meta = {
        "mentorStatus": {"type": "enum", "options": ["Active", "Inactive"]},
        "mentoringFocusAreas": {"type": "multiEnum", "options": ["Finance", "Marketing"]},
        "name": {"type": "varchar"},  # not an enum -> excluded
    }
    client = FakeClient(metadata=meta)
    opts = await service.field_options(client)
    assert opts["mentorStatus"] == ["Active", "Inactive"]
    assert opts["mentoringFocusAreas"] == ["Finance", "Marketing"]
    assert "name" not in opts


# --- router tests ---

def _app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")  # enables session + router
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


def _authed(monkeypatch):
    monkeypatch.setattr("mentoradmin.router.current_user", lambda request, key=None: _USER)
    monkeypatch.setattr("mentoradmin.router.client_for", lambda settings, user: object())


def test_requires_auth(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/mentoradmin/api/mentors").status_code == 401
        assert c.get("/mentoradmin/api/session").status_code == 401


def test_lists_mentors(monkeypatch):
    _authed(monkeypatch)

    async def fake_list(client):
        return [{"id": "m1", "name": "Jane", "status": "Active"}]

    monkeypatch.setattr("mentoradmin.router.assign_service.list_all_mentors", fake_list)
    with TestClient(_app(monkeypatch)) as c:
        data = c.get("/mentoradmin/api/mentors").json()
    assert data["mentors"][0]["name"] == "Jane"


def test_fields_endpoint_returns_spec_and_options(monkeypatch):
    _authed(monkeypatch)

    async def fake_opts(client):
        return {"mentorStatus": ["Active", "Inactive"]}

    monkeypatch.setattr("mentoradmin.router.service.field_options", fake_opts)
    with TestClient(_app(monkeypatch)) as c:
        data = c.get("/mentoradmin/api/fields").json()
    assert data["options"]["mentorStatus"] == ["Active", "Inactive"]
    assert any(f["name"] == "mentorStatus" for f in data["fields"])


def test_get_and_update_mentor(monkeypatch):
    _authed(monkeypatch)

    async def fake_get(client, mentor_id):
        return {"id": mentor_id, "name": "Jane", "mentorStatus": "Active"}

    async def fake_update(client, mentor_id, changes):
        return {"id": mentor_id, "name": "Jane", **changes}

    monkeypatch.setattr("mentoradmin.router.service.get_mentor", fake_get)
    monkeypatch.setattr("mentoradmin.router.service.update_mentor", fake_update)
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/mentoradmin/api/mentors/m1").json()["mentorStatus"] == "Active"
        r = c.put("/mentoradmin/api/mentors/m1", json={"changes": {"mentorStatus": "Inactive"}})
    assert r.json()["mentorStatus"] == "Inactive"


def test_expired_token_returns_401(monkeypatch):
    _authed(monkeypatch)

    async def boom(client):
        raise EspoError("list CMentorProfile failed: HTTP 401 Unauthorized")

    monkeypatch.setattr("mentoradmin.router.assign_service.list_all_mentors", boom)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentoradmin/api/mentors")
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


def test_other_crm_error_returns_502(monkeypatch):
    _authed(monkeypatch)

    async def boom(client):
        raise EspoError("list CMentorProfile failed: HTTP 500 Server Error")

    monkeypatch.setattr("mentoradmin.router.assign_service.list_all_mentors", boom)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentoradmin/api/mentors")
    assert r.status_code == 502


def test_login_gated_to_mentor_admin_team(monkeypatch):
    """Login passes the Mentor Administration Team as the allowed team."""
    captured = {}

    async def fake_auth(settings, username, password, *, allowed_teams=None, allowed_roles=None):
        captured["teams"] = allowed_teams
        captured["roles"] = allowed_roles
        return _USER

    monkeypatch.setattr("mentoradmin.router.authenticate", fake_auth)
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/mentoradmin/api/login", json={"username": "boss", "password": "pw"})
    assert r.status_code == 200
    assert captured["teams"] == ["Mentor Administration Team"]
    assert captured["roles"] == []
