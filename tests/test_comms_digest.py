"""Daily email digest (comms/digest.py) + the record_unread_map aggregation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from comms import digest
from comms import service as comms_service
from comms.store import MemoryCommsStore
from core.config import get_settings
from tests.test_comms_sync import FakeEspo


def _stamp(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _now():
    return datetime.now(timezone.utc)


def _espo_two_records():
    """One profile → two engagements; E1 has an unread inbound conversation,
    E2 has an all-read one."""
    espo = FakeEspo()
    espo.lists["CMentorProfile"] = [
        {"id": "mp1", "name": "Bob Mentor", "cbmEmail": "bob@cbmentors.org",
         "assignedUserId": "u1"},
    ]
    espo.records[("User", "u1")] = {"userName": "bob.mentor", "isActive": True}
    espo.lists[("CMentorProfile", "mp1", "engagements1")] = [
        {"id": "E1", "name": "Agape", "engagementStatus": "Active"},
        {"id": "E2", "name": "Beacon", "engagementStatus": "Active"},
    ]
    espo.lists[("CMentorProfile", "mp1", "engagements")] = []
    espo.lists[("CEngagement", "E1", "conversations")] = [
        {"id": "CV1", "name": "Question", "lastMessageAt": _stamp(_now() - timedelta(hours=2))},
    ]
    espo.lists[("CEngagement", "E2", "conversations")] = [
        {"id": "CV2", "name": "Old", "lastMessageAt": _stamp(_now() - timedelta(hours=5))},
    ]
    # last-message directions (the enrich batch query reads CCommunication)
    espo.lists["CCommunication"] = [
        {"id": "m1", "conversationId": "CV1", "direction": "Inbound",
         "sentAt": _stamp(_now() - timedelta(hours=2)), "fromAddress": "x@y.z", "name": "Question"},
        {"id": "m2", "conversationId": "CV2", "direction": "Outbound",
         "sentAt": _stamp(_now() - timedelta(hours=5)), "fromAddress": "bob@cbmentors.org", "name": "Old"},
    ]
    return espo


async def test_record_unread_map_counts_per_record():
    espo = _espo_two_records()
    store = MemoryCommsStore()
    m = await comms_service.record_unread_map(
        espo, store, "bob.mentor", [("CEngagement", "E1"), ("CEngagement", "E2")]
    )
    assert m["E1"]["unread"] == 1 and m["E1"]["awaiting"] is True
    # CV2 is read once bob has seen it:
    await store.mark_seen("bob.mentor", "CV2")
    m2 = await comms_service.record_unread_map(espo, store, "bob.mentor", [("CEngagement", "E2")])
    assert m2["E2"]["unread"] == 0 and m2["E2"]["awaiting"] is False


async def test_digest_sends_only_records_with_pending_mail(monkeypatch):
    monkeypatch.setenv("GMAIL_SYNC", "true")
    monkeypatch.setenv("COMMS_DIGEST", "true")
    monkeypatch.setenv("OPS_MAILBOX", "info@cbmentors.org")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    monkeypatch.setenv("APP_BASE_URL", "https://apps.example.org")
    get_settings.cache_clear()
    settings = get_settings()

    sent = []

    class FakeShared:
        mailbox = "info@cbmentors.org"

        async def aclose(self):
            pass

    async def fake_shared(s, mailbox):
        return FakeShared()

    async def fake_send(**kwargs):
        sent.append(kwargs)
        return {"gmailMessageId": "g1"}

    monkeypatch.setattr(comms_service, "gmail_for_shared_mailbox", fake_shared)
    monkeypatch.setattr(comms_service, "send_quick_message", fake_send)

    espo = _espo_two_records()
    store = MemoryCommsStore()
    # E2's conversation is already read (its last message is ours anyway), so
    # only E1 — with a fresh inbound — has pending mail.
    await store.mark_seen("bob.mentor", "CV2")
    n = await digest.run_digest_cycle(settings, espo, store)
    assert n == 1
    msg = sent[0]
    assert msg["to"] == ["bob@cbmentors.org"]
    assert msg["sender_name"] == "Cleveland Business Mentors"
    # Only the record WITH pending mail is listed, with a real deep link.
    assert "Agape" in msg["body_html"]
    assert "https://apps.example.org/mentorsessions/record/E1" in msg["body_html"]
    assert "Beacon" not in msg["body_html"]
    assert "user_client" not in msg or msg.get("user_client") is None  # no CRM write-back


async def test_digest_no_email_when_nothing_pending(monkeypatch):
    monkeypatch.setenv("GMAIL_SYNC", "true")
    monkeypatch.setenv("COMMS_DIGEST", "true")
    monkeypatch.setenv("OPS_MAILBOX", "info@cbmentors.org")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    get_settings.cache_clear()
    settings = get_settings()

    sent = []
    monkeypatch.setattr(comms_service, "send_quick_message",
                        lambda **k: sent.append(k))

    espo = _espo_two_records()
    store = MemoryCommsStore()
    # Mark the one unread conversation as seen -> nothing pending -> no email.
    await store.mark_seen("bob.mentor", "CV1")
    n = await digest.run_digest_cycle(settings, espo, store)
    assert n == 0 and sent == []


async def test_digest_disabled_without_ops_mailbox(monkeypatch):
    monkeypatch.setenv("GMAIL_SYNC", "true")
    monkeypatch.setenv("COMMS_DIGEST", "true")
    monkeypatch.delenv("OPS_MAILBOX", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    get_settings.cache_clear()
    assert digest.digest_enabled(get_settings()) is False
