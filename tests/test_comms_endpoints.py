"""Communications endpoints on the sessions routers (flag-gated)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from comms import service as comms_service
from core.app import create_app
from core.config import get_settings
from forms import info_request

_USER = {
    "userId": "u1",
    "userName": "bob.mentor",
    "name": "Bob Mentor",
    "isAdmin": False,
    "teams": ["Mentor Team"],
    "roles": [],
    "token": "t",
}


def _app(monkeypatch, gmail_sync: bool):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("GMAIL_SYNC", "true" if gmail_sync else "false")
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


def _as(monkeypatch, user=_USER):
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, user: object())


def test_disabled_returns_503(monkeypatch):
    _as(monkeypatch)
    with TestClient(_app(monkeypatch, gmail_sync=False)) as c:
        r = c.get("/mentorsessions/api/records/E1/conversations")
    assert r.status_code == 503
    assert "isn't enabled" in r.json()["detail"]


def test_session_config_reports_comms_flag(monkeypatch):
    _as(monkeypatch)
    with TestClient(_app(monkeypatch, gmail_sync=False)) as c:
        r = c.get("/mentorsessions/api/session")
    assert r.status_code == 200
    assert r.json()["commsEnabled"] is False


def test_enabled_lists_conversations(monkeypatch):
    _as(monkeypatch)

    async def fake_list(client, parent_entity, parent_id):
        assert parent_entity == "CEngagement" and parent_id == "E1"
        return [{"id": "conv1", "subject": "Hello", "status": "Open"}]

    monkeypatch.setattr(comms_service, "list_conversations", fake_list)
    monkeypatch.setattr(comms_service, "get_store", lambda settings: object())
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        r = c.get("/mentorsessions/api/records/E1/conversations")
    assert r.status_code == 200
    assert r.json()["conversations"][0]["id"] == "conv1"


def test_enabled_without_database_503s(monkeypatch):
    _as(monkeypatch)
    monkeypatch.setattr(comms_service, "get_store", lambda settings: None)
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        r = c.get("/mentorsessions/api/records/E1/conversations")
    assert r.status_code == 503
    assert "database" in r.json()["detail"]


def test_send_requires_recipients(monkeypatch):
    _as(monkeypatch)
    monkeypatch.setattr(comms_service, "get_store", lambda settings: object())

    async def fake_gmail_for_user(settings, client, user):
        class G:
            mailbox = "bob.mentor@cbmentors.org"

        return G()

    async def fake_send(**kwargs):
        raise comms_service.CommsError("Add at least one recipient.")

    monkeypatch.setattr(comms_service, "gmail_for_user", fake_gmail_for_user)
    monkeypatch.setattr(comms_service, "send_message", fake_send)
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        r = c.post(
            "/mentorsessions/api/records/E1/messages",
            json={"to": [], "subject": "x", "body": "y"},
        )
    assert r.status_code == 400
    assert "recipient" in r.json()["detail"]


def test_mailbox_returns_own_send_address(monkeypatch):
    _as(monkeypatch)

    async def fake_resolve(client, user_id):
        assert user_id == "u1"
        return "bob.mentor@cbmentors.org"

    monkeypatch.setattr("sessions.service.resolve_user_mailbox", fake_resolve)
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        r = c.get("/mentorsessions/api/mailbox")
    assert r.status_code == 200
    assert r.json()["mailbox"] == "bob.mentor@cbmentors.org"


def test_mailbox_null_when_no_cbm_email(monkeypatch):
    _as(monkeypatch)

    async def fake_resolve(client, user_id):
        return None

    monkeypatch.setattr("sessions.service.resolve_user_mailbox", fake_resolve)
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        r = c.get("/mentorsessions/api/mailbox")
    assert r.status_code == 200
    assert r.json()["mailbox"] is None


def test_unauthenticated_401_before_comms_checks(monkeypatch):
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: None)
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        assert c.get("/mentorsessions/api/records/E1/conversations").status_code == 401


# --- exclude_conversation (P2 + D5, reliability review 2026-07-17) ------------


class _ExcludeStore:
    def __init__(self, fail=False):
        self.overrides = []
        self._fail = fail

    async def set_override(self, parent_entity, parent_id, conversation_id, action, username):
        if self._fail:
            raise RuntimeError("db down")
        self.overrides.append((parent_entity, parent_id, conversation_id, action, username))


class _UnlinkClient:
    def __init__(self, fail=False):
        self.unrelates = []
        self._fail = fail

    async def unrelate(self, entity, record_id, link, related_id):
        if self._fail:
            from core.espo import EspoError
            raise EspoError("unrelate CConversation failed: HTTP 403 denied")
        self.unrelates.append((entity, record_id, link, related_id))


async def test_exclude_unlinks_then_records_override():
    client, store = _UnlinkClient(), _ExcludeStore()
    await comms_service.exclude_conversation(
        client, store, "CEngagement", "E1", "conv1", "jdoe"
    )
    assert client.unrelates == [("CConversation", "conv1", "engagements", "E1")]
    assert store.overrides == [("CEngagement", "E1", "conv1", "exclude", "jdoe")]


async def test_exclude_failed_unlink_records_nothing():
    """A failed unlink raises (readable 403 at the router) with NO override
    recorded — 'hidden in the app, still linked in the CRM' can't happen."""
    from core.espo import EspoError

    client, store = _UnlinkClient(fail=True), _ExcludeStore()
    import pytest
    with pytest.raises(EspoError):
        await comms_service.exclude_conversation(
            client, store, "CEngagement", "E1", "conv1", "jdoe"
        )
    assert store.overrides == []


async def test_exclude_store_failure_after_unlink_raises_comms_error():
    import pytest

    client, store = _UnlinkClient(), _ExcludeStore(fail=True)
    with pytest.raises(comms_service.CommsError, match="Hide it again"):
        await comms_service.exclude_conversation(
            client, store, "CEngagement", "E1", "conv1", "jdoe"
        )
    assert client.unrelates  # the unlink did happen first
