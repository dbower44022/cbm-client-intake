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


# --- View original + attachment-scoped thread reads (email-quality Phase 1) ---


def test_conversation_detail_passes_record_scope(monkeypatch):
    _as(monkeypatch)
    seen = {}

    async def fake_get_conversation(client, conversation_id, *, store=None,
                                    parent_entity=None, parent_id=None):
        seen.update(parent_entity=parent_entity, parent_id=parent_id)
        return {"id": conversation_id, "messages": []}

    class _Store:
        async def mark_seen(self, username, conversation_id):
            pass

    monkeypatch.setattr(comms_service, "get_conversation", fake_get_conversation)
    monkeypatch.setattr(comms_service, "get_store", lambda settings: _Store())
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        r = c.get("/mentorsessions/api/conversations/conv1?parentId=E1")
    assert r.status_code == 200
    assert seen == {"parent_entity": "CEngagement", "parent_id": "E1"}


def test_original_endpoint_serves_and_maps_gone_to_404(monkeypatch):
    _as(monkeypatch)
    monkeypatch.setattr(comms_service, "get_store", lambda settings: object())
    calls = {}

    async def fake_get_original(settings, client, communication_id, *, cid_base,
                                acting_user=""):
        calls["cid_base"] = cid_base
        if communication_id == "gone":
            raise comms_service.OriginalGoneError("The original no longer exists.")
        return {"id": communication_id, "subject": "S", "bodyHtml": "<p>x</p>"}

    monkeypatch.setattr(comms_service, "get_original", fake_get_original)
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        ok = c.get("/mentorsessions/api/communications/comm1/original")
        assert calls["cid_base"] == "/mentorsessions/api/communications/comm1/original/cid"
        gone = c.get("/mentorsessions/api/communications/gone/original")
    assert ok.status_code == 200 and ok.json()["subject"] == "S"
    assert gone.status_code == 404
    assert "no longer exists" in gone.json()["detail"]


def test_original_cid_endpoint_streams_bytes(monkeypatch):
    _as(monkeypatch)
    monkeypatch.setattr(comms_service, "get_store", lambda settings: object())

    async def fake_part(settings, client, communication_id, content_id, *,
                        acting_user=""):
        assert content_id == "logo@cid"
        return {"data": b"PNG", "mime_type": "image/png"}

    monkeypatch.setattr(comms_service, "get_original_part", fake_part)
    with TestClient(_app(monkeypatch, gmail_sync=True)) as c:
        r = c.get("/mentorsessions/api/communications/comm1/original/cid/logo%40cid")
    assert r.status_code == 200
    assert r.content == b"PNG"
    assert r.headers["content-type"].startswith("image/png")
    assert "private" in r.headers["cache-control"]


def test_original_endpoint_503_when_comms_off(monkeypatch):
    _as(monkeypatch)
    with TestClient(_app(monkeypatch, gmail_sync=False)) as c:
        r = c.get("/mentorsessions/api/communications/comm1/original")
    assert r.status_code == 503
