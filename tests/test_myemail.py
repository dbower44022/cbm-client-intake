"""My Email (the unified inbox) + the unread/awaiting-reply enrichment +
document email attachments (the /records/{id}/messages documentId shape)."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from comms import service as comms_service
from comms.store import MemoryCommsStore
from core.app import create_app
from core.config import get_settings
from forms import info_request
from tests.test_comms_sync import FakeEspo

_USER = {
    "userId": "u1",
    "userName": "matt.mentor",
    "name": "Matt Mentor",
    "isAdmin": False,
    "teams": ["Mentor Team"],
    "roles": [],
    "token": "t",
}


def _stamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _espo_with_inbox() -> FakeEspo:
    """One mentor profile → one active engagement → one conversation whose
    last message is INBOUND (awaiting a reply)."""
    espo = FakeEspo()
    espo.lists["CMentorProfile"] = [{"id": "mp1", "assignedUserId": "u1"}]
    espo.lists[("CMentorProfile", "mp1", "engagements1")] = [
        {"id": "E1", "name": "Agape Weight Loss", "engagementStatus": "Active"},
    ]
    espo.lists[("CMentorProfile", "mp1", "engagements")] = []
    espo.lists[("CEngagement", "E1", "conversations")] = [
        {
            "id": "CV1", "name": "Marketing question",
            "conversationStatus": "Open", "participants": "James Koran",
            "messageCount": 2, "firstMessageAt": _stamp(_now() - timedelta(days=2)),
            "lastMessageAt": _stamp(_now() - timedelta(hours=3)),
        },
    ]
    espo.lists["CCommunication"] = [
        {"id": "M2", "conversationId": "CV1", "direction": "Inbound",
         "sentAt": _stamp(_now() - timedelta(hours=3))},
        {"id": "M1", "conversationId": "CV1", "direction": "Outbound",
         "sentAt": _stamp(_now() - timedelta(days=2))},
    ]
    # Thread read + the "Open in record" links.
    espo.records[("CConversation", "CV1")] = {
        "name": "Marketing question", "conversationStatus": "Open",
    }
    espo.lists[("CConversation", "CV1", "engagements")] = [
        {"id": "E1", "name": "Agape Weight Loss"},
    ]
    espo.lists[("CConversation", "CV1", "partnerProfiles")] = []
    espo.lists[("CConversation", "CV1", "sponsorProfiles")] = []
    return espo


def _app(monkeypatch, espo, store, user=_USER, gmail_sync=True):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("GMAIL_SYNC", "true" if gmail_sync else "false")
    get_settings.cache_clear()
    monkeypatch.setattr("myemail.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("myemail.router.client_for", lambda settings, u: espo)
    monkeypatch.setattr(comms_service, "get_store", lambda settings: store)
    return create_app([info_request.SPEC])


def test_myemail_requires_auth(monkeypatch):
    espo, store = _espo_with_inbox(), MemoryCommsStore()
    app = _app(monkeypatch, espo, store, user=None)
    with TestClient(app) as c:
        assert c.get("/myemail/api/inbox").status_code == 401


def test_myemail_requires_a_management_team(monkeypatch):
    outsider = dict(_USER, teams=["Marketing Admin Team"])
    espo, store = _espo_with_inbox(), MemoryCommsStore()
    app = _app(monkeypatch, espo, store, user=outsider)
    with TestClient(app) as c:
        r = c.get("/myemail/api/inbox")
    assert r.status_code == 403


def test_inbox_assembles_rows_with_records_unread_and_awaiting(monkeypatch):
    espo, store = _espo_with_inbox(), MemoryCommsStore()
    with TestClient(_app(monkeypatch, espo, store)) as c:
        r = c.get("/myemail/api/inbox")
    assert r.status_code == 200
    data = r.json()
    assert data["profileFound"] is True
    assert len(data["conversations"]) == 1
    row = data["conversations"][0]
    assert row["id"] == "CV1"
    assert row["records"] == [
        {"entity": "CEngagement", "id": "E1", "name": "Agape Weight Loss",
         "slug": "mentorsessions"},
    ]
    # Last message is inbound + never opened + recent => both flags.
    assert row["awaitingReply"] is True
    assert row["unread"] is True


def test_opening_the_thread_marks_it_read(monkeypatch):
    espo, store = _espo_with_inbox(), MemoryCommsStore()
    with TestClient(_app(monkeypatch, espo, store)) as c:
        t = c.get("/myemail/api/conversations/CV1")
        assert t.status_code == 200
        assert t.json()["records"][0]["slug"] == "mentorsessions"
        r = c.get("/myemail/api/inbox")
    row = r.json()["conversations"][0]
    assert row["unread"] is False          # seen stamp is newer than the message
    assert row["awaitingReply"] is True    # still their ball — reading ≠ replying


def test_mark_all_read(monkeypatch):
    espo, store = _espo_with_inbox(), MemoryCommsStore()
    with TestClient(_app(monkeypatch, espo, store)) as c:
        r = c.post("/myemail/api/markallread", json={"conversationIds": ["CV1"]})
        assert r.status_code == 200 and r.json()["marked"] == 1
        row = c.get("/myemail/api/inbox").json()["conversations"][0]
    assert row["unread"] is False


def test_inbox_503_when_gmail_off(monkeypatch):
    espo, store = _espo_with_inbox(), MemoryCommsStore()
    with TestClient(_app(monkeypatch, espo, store, gmail_sync=False)) as c:
        assert c.get("/myemail/api/inbox").status_code == 503


# --- enrichment unit behavior -------------------------------------------------


async def test_enrichment_never_seen_old_mail_is_not_unread():
    espo = FakeEspo()
    espo.lists["CCommunication"] = [
        {"id": "M1", "conversationId": "CVOLD", "direction": "Outbound",
         "sentAt": _stamp(_now() - timedelta(days=90))},
    ]
    rows = [{"id": "CVOLD", "lastMessageAt": _stamp(_now() - timedelta(days=90))}]
    await comms_service.enrich_conversation_rows(espo, MemoryCommsStore(), "u", rows)
    # Older than the never-seen window => day one doesn't bold a year of history.
    assert rows[0]["unread"] is False
    assert rows[0]["awaitingReply"] is False  # last message was ours


async def test_enrichment_survives_a_failing_client():
    class Boom:
        async def list(self, *a, **k):
            raise RuntimeError("down")

    rows = [{"id": "X", "lastMessageAt": _stamp(_now())}]
    await comms_service.enrich_conversation_rows(Boom(), MemoryCommsStore(), "u", rows)
    assert rows[0]["awaitingReply"] is False  # decoration failed open
    assert rows[0]["unread"] is True          # seen-map path still ran


# --- document attachments on the record compose --------------------------------


def test_send_resolves_document_attachments(monkeypatch):
    """A {documentId} chip becomes the document's original bytes (base64,
    local-upload shape) before the send path runs."""
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("GMAIL_SYNC", "true")
    monkeypatch.setenv("GDRIVE_DOCS", "true")
    get_settings.cache_clear()
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: _USER)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, u: FakeEspo())
    monkeypatch.setattr(comms_service, "get_store", lambda settings: MemoryCommsStore())

    from sessions import router as sessions_router

    monkeypatch.setattr(
        sessions_router.docs_service, "get_store", lambda settings: object()
    )

    async def fake_drive(settings, client, user):
        return object()

    fetched = []

    async def fake_fetch(store, drive, entity, record_id, doc_id, original=False):
        fetched.append((entity, record_id, doc_id, original))
        return {
            "data": b"PDFBYTES", "mime_type": "application/pdf",
            "filename": "plan.pdf", "modified_time": None,
        }

    monkeypatch.setattr(sessions_router.docs_service, "drive_for_user", fake_drive)
    monkeypatch.setattr(sessions_router.docs_service, "fetch_document", fake_fetch)

    sent = {}

    async def fake_send(**kwargs):
        sent.update(kwargs)
        return {"gmailMessageId": "g1", "writeBack": {"ok": True}}

    monkeypatch.setattr(comms_service, "send_message", fake_send)

    async def fake_gmail(settings, client, user):
        return object()

    monkeypatch.setattr(comms_service, "gmail_for_user", fake_gmail)

    app = create_app([info_request.SPEC])
    with TestClient(app) as c:
        r = c.post(
            "/mentorsessions/api/records/E1/messages",
            json={
                "to": ["james@acme.test"], "subject": "Plan", "body": "<p>hi</p>",
                "attachments": [
                    {"documentId": "d9", "filename": "plan.pdf"},
                    {"filename": "note.txt", "contentType": "text/plain",
                     "dataBase64": base64.b64encode(b"n").decode()},
                ],
            },
        )
    assert r.status_code == 200, r.text
    assert fetched == [("CEngagement", "E1", "d9", True)]  # record-scoped, original bytes
    resolved = sent["attachments"]
    assert resolved[0]["filename"] == "plan.pdf"
    assert resolved[0]["contentType"] == "application/pdf"
    assert base64.b64decode(resolved[0]["dataBase64"]) == b"PDFBYTES"
    assert resolved[1]["filename"] == "note.txt"  # non-document chips untouched


def test_send_blocks_when_document_integration_off(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("GMAIL_SYNC", "true")
    monkeypatch.setenv("GDRIVE_DOCS", "false")
    get_settings.cache_clear()
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: _USER)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, u: FakeEspo())
    monkeypatch.setattr(comms_service, "get_store", lambda settings: MemoryCommsStore())

    app = create_app([info_request.SPEC])
    with TestClient(app) as c:
        r = c.post(
            "/mentorsessions/api/records/E1/messages",
            json={"to": ["a@b.c"], "body": "x",
                  "attachments": [{"documentId": "d9", "filename": "plan.pdf"}]},
        )
    assert r.status_code == 400
    assert "document" in r.json()["detail"].lower()
