"""A CRM 403 (missing ACL grant) surfaces as a readable HTTP 403, never a raw
502/504 — found live 2026-07-15: a mentor whose role lacks the Contact create
grant hit "+ Add → Create new contact" and got a blank edge 504."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from forms import info_request

_USER = {"userId": "u1", "userName": "boss", "name": "The Boss", "isAdmin": True, "token": "tok"}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


def _as(monkeypatch, user):
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, user: object())


def test_crm_403_on_contact_create_returns_readable_403(monkeypatch):
    _as(monkeypatch, _USER)

    async def forbidden_create(cfg, client, parent_id, changes):
        raise EspoError("create Contact failed: HTTP 403 ")

    monkeypatch.setattr("sessions.details.create_contact", forbidden_create)
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/mentorsessions/api/records/E1/contacts",
                   json={"changes": {"firstName": "Zed", "lastName": "Test"}})
    assert r.status_code == 403
    # The message names the exact missing grant (Doug's ask 2026-07-16),
    # so the CRM admin knows what to add without reading server logs.
    assert "create access to Contact records" in r.json()["detail"]


def test_crm_403_on_contact_link_returns_readable_403(monkeypatch):
    # EspoCRM's relate requires edit on the FOREIGN record; without it the
    # relate 403s (noAccessToForeignRecord) — must also read as a permission
    # problem, not a server fault.
    _as(monkeypatch, _USER)

    async def forbidden_link(cfg, client, parent_id, contact_id):
        raise EspoError(
            'relate CEngagement/E1/engagementContacts failed: HTTP 403 '
            '{"messageTranslation":{"label":"noAccessToForeignRecord"}}'
        )

    monkeypatch.setattr("sessions.details.link_contact", forbidden_link)
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/mentorsessions/api/records/E1/contacts", json={"contactId": "C9"})
    assert r.status_code == 403
    assert "edit access to CEngagement records" in r.json()["detail"]


def test_crm_5xx_still_maps_to_502(monkeypatch):
    _as(monkeypatch, _USER)

    async def broken(cfg, client, parent_id, contact_id):
        raise EspoError("relate CEngagement/E1/engagementContacts failed: HTTP 500 ")

    monkeypatch.setattr("sessions.details.link_contact", broken)
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/mentorsessions/api/records/E1/contacts", json={"contactId": "C9"})
    assert r.status_code == 502
