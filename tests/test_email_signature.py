"""Email signature (EspoCRM Preferences.signature) — comms read helper, the
/mailbox surfacing, and the /mentorprofile editor endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from comms import service as comms_service
from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from forms import info_request
from tests.test_comms_sync import FakeEspo

_USER = {
    "userId": "u1", "userName": "bob.mentor", "name": "Bob Mentor",
    "isAdmin": True, "teams": [], "roles": [], "token": "t",
}


# --- comms_service.user_signature --------------------------------------------


async def test_user_signature_reads_and_sanitizes_preferences():
    espo = FakeEspo()
    espo.records[("Preferences", "u1")] = {
        "signature": "<p>Bob Mentor</p><script>x()</script><p onclick=\"x()\">CBM</p>",
    }
    sig = await comms_service.user_signature(espo, "u1")
    assert "Bob Mentor" in sig and "CBM" in sig
    assert "<script" not in sig and "onclick" not in sig


async def test_user_signature_empty_or_failing_is_blank():
    espo = FakeEspo()
    espo.records[("Preferences", "u1")] = {"signature": "   "}
    assert await comms_service.user_signature(espo, "u1") == ""

    class Broken:
        async def get(self, *a, **kw):
            raise EspoError("get Preferences/u1 failed: HTTP 403")

    assert await comms_service.user_signature(Broken(), "u1") == ""


# --- endpoints ----------------------------------------------------------------


def _app(monkeypatch, gmail_sync=True):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("GMAIL_SYNC", "true" if gmail_sync else "false")
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


def _as(monkeypatch, client):
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: _USER)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, user: client)
    monkeypatch.setattr("mentorprofile.router.current_user", lambda request, key=None: _USER)
    monkeypatch.setattr("mentorprofile.router.client_for", lambda settings, user: client)


def test_sessions_mailbox_carries_the_signature(monkeypatch):
    espo = FakeEspo()
    espo.records[("Preferences", "u1")] = {"signature": "<p>— Bob</p>"}
    _as(monkeypatch, espo)

    async def fake_resolve(client, user_id):
        return "bob.mentor@cbmentors.org"

    monkeypatch.setattr("sessions.service.resolve_user_mailbox", fake_resolve)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentorsessions/api/mailbox")
    assert r.status_code == 200
    assert r.json()["signature"] == "<p>— Bob</p>"


def test_mentorprofile_signature_roundtrip(monkeypatch):
    espo = FakeEspo()
    espo.records[("Preferences", "u1")] = {"signature": "<p>old</p>"}
    _as(monkeypatch, espo)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentorprofile/api/signature")
        assert r.status_code == 200 and r.json() == {"signature": "<p>old</p>"}
        r2 = c.put("/mentorprofile/api/signature", json={
            "signature": "<p>Bob Mentor</p><script>evil()</script>",
        })
        assert r2.status_code == 200
    # sanitized before the write, saved to the CALLER's own Preferences
    stored = espo.records[("Preferences", "u1")]["signature"]
    assert "Bob Mentor" in stored and "<script" not in stored


def test_mentorprofile_signature_clears_with_empty_string(monkeypatch):
    espo = FakeEspo()
    espo.records[("Preferences", "u1")] = {"signature": "<p>old</p>"}
    _as(monkeypatch, espo)
    with TestClient(_app(monkeypatch)) as c:
        r = c.put("/mentorprofile/api/signature", json={"signature": ""})
        assert r.status_code == 200
    assert espo.records[("Preferences", "u1")]["signature"] == ""
