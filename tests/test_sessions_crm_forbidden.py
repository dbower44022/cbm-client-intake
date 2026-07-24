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
    # noAccessToForeignRecord = the denial is on the record BEING LINKED (the
    # contact), not the engagement — the hint must say so (2026-07-20 fix).
    assert "record being linked" in r.json()["detail"]


def test_crm_5xx_still_maps_to_502(monkeypatch):
    _as(monkeypatch, _USER)

    async def broken(cfg, client, parent_id, contact_id):
        raise EspoError("relate CEngagement/E1/engagementContacts failed: HTTP 500 ")

    monkeypatch.setattr("sessions.details.link_contact", broken)
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/mentorsessions/api/records/E1/contacts", json={"contactId": "C9"})
    assert r.status_code == 502
    # A CRM 5xx is EspoCRM's own failure — the detail must be readable advice,
    # not the raw "HTTP 500" echo (which reached a user as an unexplained 504
    # on 2026-07-24 when oversized session notes tripped the database).
    assert "internal error" in r.json()["detail"]
    assert "Nothing you typed has been lost" in r.json()["detail"]


def test_crm_500_on_session_save_returns_readable_502(monkeypatch):
    # The exact live failure 2026-07-24: EspoCRM 500'd on a session update
    # (MySQL "Data too long for column 'session_notes'" — a pasted base64
    # image) and the user saw a bare 504. The mapped 502 must explain itself.
    _as(monkeypatch, _USER)

    async def broken_update(cfg, client, session_id, changes, attendees, **kw):
        raise EspoError("update CSession/s1 failed: HTTP 500 ")

    monkeypatch.setattr("sessions.service.update_session", broken_update)
    with TestClient(_app(monkeypatch)) as c:
        r = c.put("/mentorsessions/api/sessions/s1",
                  json={"changes": {"sessionNotes": "<p>x</p>"}})
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert detail.startswith("Could not save session")
    assert "Nothing you typed has been lost" in detail


def test_inline_image_upload_and_fetch_endpoints(monkeypatch):
    _as(monkeypatch, _USER)

    async def fake_upload(client, *, filename, content_type, data_base64, field):
        assert field == "sessionNotes"
        return {"id": "a77"}

    async def fake_fetch(client, attachment_id):
        assert attachment_id == "a77"
        return b"png-bytes", "image/png"

    monkeypatch.setattr("sessions.service.upload_inline_image", fake_upload)
    monkeypatch.setattr("sessions.service.fetch_inline_image", fake_fetch)
    with TestClient(_app(monkeypatch)) as c:
        up = c.post("/mentorsessions/api/inlineimages",
                    json={"contentType": "image/png", "dataBase64": "aGk="})
        assert up.status_code == 200 and up.json()["id"] == "a77"
        got = c.get("/mentorsessions/api/attachments/a77")
        assert got.status_code == 200
        assert got.content == b"png-bytes"
        assert got.headers["content-type"].startswith("image/png")
        assert "immutable" in got.headers["cache-control"]


def test_inline_image_upload_validation_is_a_readable_400(monkeypatch):
    _as(monkeypatch, _USER)
    from sessions import service as sessions_service

    async def rejected(client, **kw):
        raise sessions_service.SessionError("The pasted image is too large (limit 5 MB).")

    monkeypatch.setattr("sessions.service.upload_inline_image", rejected)
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/mentorsessions/api/inlineimages",
                   json={"contentType": "image/png", "dataBase64": "aGk="})
    assert r.status_code == 400
    assert "too large" in r.json()["detail"]


def test_session_error_on_save_returns_readable_400(monkeypatch):
    # A SessionError raised by the save path (e.g. the oversized-content guard)
    # is the caller's data, not a server fault — a readable 400.
    _as(monkeypatch, _USER)
    from sessions import service as sessions_service

    async def too_big(cfg, client, session_id, changes, attendees, **kw):
        raise sessions_service.SessionError("The Session notes content is too large to store.")

    monkeypatch.setattr("sessions.service.update_session", too_big)
    with TestClient(_app(monkeypatch)) as c:
        r = c.put("/mentorsessions/api/sessions/s1",
                  json={"changes": {"sessionNotes": "<p>x</p>"}})
    assert r.status_code == 400
    assert "too large" in r.json()["detail"]
