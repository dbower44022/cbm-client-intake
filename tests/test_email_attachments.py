"""Email-quality Phase 1 — inbound attachment auto-filing, View original,
bounce flags on record threads (plan: prds/email-quality-improvement-plan.md §3)."""

from __future__ import annotations

import base64
import hashlib
import itertools
from typing import Any, Optional

import pytest

import comms.service as comms_service  # noqa: F401 — resolves the sync import cycle
from comms import attachments as att
from comms import crm
from comms.store import (
    ATTACHMENT_DUPLICATE,
    ATTACHMENT_FAILED,
    ATTACHMENT_FILED,
    ATTACHMENT_TOO_LARGE,
    MemoryCommsStore,
)
from core.email_clean import sanitize_original_html
from core.gmail import parse_message
from docs.store import MemoryDocumentStore


# --- fixtures ----------------------------------------------------------------


class Cfg:
    gmail_sync = True
    gdrive_docs = True
    database_url = "postgresql://x"
    gdrive_shared_drive_id = "drv"
    gdrive_identity = "service"
    gdrive_max_file_mb = 1
    gdrive_doc_types_list = ["Other"]
    gdrive_entity_labels_map = {"CPartnerProfile": "Partners"}
    request_timeout_seconds = 20
    espo_dry_run = True
    espo_api_key = ""


class FakeEspo:
    def __init__(self, lists: Optional[dict] = None):
        self.lists = lists or {}
        self.records: dict[tuple[str, str], dict] = {}

    async def get(self, entity, record_id, select=None):
        return {"id": record_id, **self.records.get((entity, record_id), {})}

    async def list_related(self, entity, record_id, link, *, select=None, max_size=200):
        return {"list": self.lists.get((entity, record_id, link), [])}


class FakeDrive:
    drive_id = "drv"
    mailbox = "bob.mentor@cbmentors.org"

    def __init__(self):
        self.uploads: list[tuple[str, str, int]] = []
        self._ids = itertools.count(1)
        self.fail = False

    async def find_child_folder(self, parent, name):
        return None

    async def create_folder(self, parent, name):
        return f"f-{name}"

    async def generate_file_id(self):
        return f"gen{next(self._ids)}"

    async def upload_file(self, folder_id, filename, mime, data, file_id=None):
        if self.fail:
            from core.gdrive import DriveError

            raise DriveError("drive down")
        fid = file_id or f"file{next(self._ids)}"
        self.uploads.append((folder_id, filename, len(data)))
        return {
            "id": fid,
            "webViewLink": "https://drive.example/x",
            "modifiedTime": "2026-07-21T00:00:00Z",
            "md5Checksum": "md5",
        }

    async def delete_file(self, fid):
        pass

    async def get_file(self, fid, fields=""):
        return {"id": fid}


class FakeGmail:
    def __init__(self, mailbox="bob.mentor@cbmentors.org", parts=None, messages=None):
        self.mailbox = mailbox
        self.parts = parts or {}  # attachment_id -> bytes
        self.messages = messages or {}

    async def get_attachment(self, message_id, attachment_id):
        return self.parts[attachment_id]

    async def get_message(self, message_id):
        return self.messages[message_id]

    async def aclose(self):
        pass


PDF_BYTES = b"%PDF-1.4 fake plan document"


def raw_with_attachments(
    mid="m1", thread="t1", frm="james@acme.test", subject="Plan attached",
    extra_parts=None,
):
    text = base64.urlsafe_b64encode(b"See the attached plan.").decode()
    parts = [
        {"mimeType": "text/plain", "body": {"data": text}},
        {
            "mimeType": "application/pdf",
            "filename": "plan.pdf",
            "headers": [
                {"name": "Content-Disposition", "value": 'attachment; filename="plan.pdf"'},
            ],
            "body": {"attachmentId": "att-pdf", "size": len(PDF_BYTES)},
        },
        {
            "mimeType": "image/png",
            "filename": "logo.png",
            "headers": [
                {"name": "Content-Disposition", "value": 'inline; filename="logo.png"'},
                {"name": "Content-ID", "value": "<logo@cid>"},
            ],
            "body": {"attachmentId": "att-logo", "size": 10},
        },
    ] + (extra_parts or [])
    return {
        "id": mid,
        "threadId": thread,
        "internalDate": "1780000000000",
        "snippet": "See the attached plan.",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "From", "value": f"James Koran <{frm}>"},
                {"name": "To", "value": "bob.mentor@cbmentors.org"},
                {"name": "Subject", "value": subject},
                {"name": "Message-ID", "value": f"<{mid}@mail>"},
            ],
            "parts": parts,
        },
    }


@pytest.fixture()
def doc_store(monkeypatch):
    store = MemoryDocumentStore()
    monkeypatch.setattr("docs.service.get_store", lambda settings: store)
    return store


@pytest.fixture()
def drive(monkeypatch):
    d = FakeDrive()

    async def _drive(settings, attribution):
        return d

    monkeypatch.setattr(att, "_service_drive", _drive)
    return d


# --- parsing -----------------------------------------------------------------


def test_parse_collects_real_and_inline_attachments():
    parsed = parse_message(raw_with_attachments())
    assert len(parsed.attachments) == 2
    real = parsed.real_attachments
    assert [a.filename for a in real] == ["plan.pdf"]
    assert real[0].attachment_id == "att-pdf"
    logo = [a for a in parsed.attachments if a.filename == "logo.png"][0]
    assert not logo.is_attachment           # inline never qualifies (the ruling)
    assert logo.content_id == "logo@cid"
    assert logo.is_inline_image


def test_parse_named_part_without_disposition_counts_as_attachment():
    raw = raw_with_attachments(extra_parts=[{
        "mimeType": "application/vnd.ms-excel",
        "filename": "numbers.xls",
        "body": {"attachmentId": "att-xls", "size": 5},
    }])
    parsed = parse_message(raw)
    names = [a.filename for a in parsed.real_attachments]
    assert "numbers.xls" in names


# --- filing engine -----------------------------------------------------------


async def test_files_real_attachment_and_ledgers_it(doc_store, drive):
    store = MemoryCommsStore()
    gmail = FakeGmail(parts={"att-pdf": PDF_BYTES})
    parsed = parse_message(raw_with_attachments())
    await att.file_message_attachments(
        Cfg(), FakeEspo(), store, gmail, parsed,
        [("CPartnerProfile", "P1", "Acme Partners")],
    )
    # Only the real attachment was filed — never the inline logo.
    assert len(drive.uploads) == 1
    docs = await doc_store.list_documents("CPartnerProfile", "P1")
    assert len(docs) == 1
    assert docs[0]["filename"] == "plan.pdf"
    assert docs[0]["docType"] == "Email attachment"
    assert docs[0]["contentSha256"] == hashlib.sha256(PDF_BYTES).hexdigest()
    assert docs[0]["uploadedBy"] == "bob.mentor@cbmentors.org"
    state = await store.attachment_state("m1@mail", 2, "CPartnerProfile", "P1")
    assert state["status"] == ATTACHMENT_FILED
    assert state["documentId"] == docs[0]["id"]


async def test_same_bytes_dedup_per_record(doc_store, drive):
    store = MemoryCommsStore()
    gmail = FakeGmail(parts={"att-pdf": PDF_BYTES})
    rec = [("CPartnerProfile", "P1", "Acme Partners")]
    await att.file_message_attachments(
        Cfg(), FakeEspo(), store, gmail, parse_message(raw_with_attachments()), rec
    )
    # A reply re-attaching the SAME pdf: one stored document, second row = duplicate.
    reply = parse_message(raw_with_attachments(mid="m2"))
    await att.file_message_attachments(Cfg(), FakeEspo(), store, gmail, reply, rec)
    assert len(await doc_store.list_documents("CPartnerProfile", "P1")) == 1
    state = await store.attachment_state("m2@mail", 2, "CPartnerProfile", "P1")
    assert state["status"] == ATTACHMENT_DUPLICATE
    assert state["documentId"]
    # A DIFFERENT record still gets its own copy (per-record dedup by design).
    await att.file_message_attachments(
        Cfg(), FakeEspo(), store, gmail, reply,
        [("CPartnerProfile", "P2", "Other Partners")],
    )
    assert len(await doc_store.list_documents("CPartnerProfile", "P2")) == 1


async def test_oversize_marked_too_large_without_fetch(doc_store, drive):
    store = MemoryCommsStore()
    raw = raw_with_attachments()
    raw["payload"]["parts"][1]["body"]["size"] = 5 * 1024 * 1024  # over the 1 MB cap
    gmail = FakeGmail(parts={})  # a fetch would KeyError — must not be attempted
    await att.file_message_attachments(
        Cfg(), FakeEspo(), store, gmail, parse_message(raw),
        [("CPartnerProfile", "P1", "Acme")],
    )
    state = await store.attachment_state("m1@mail", 2, "CPartnerProfile", "P1")
    assert state["status"] == ATTACHMENT_TOO_LARGE
    assert not drive.uploads


async def test_drive_failure_ledgers_failed_and_retry_heals(doc_store, drive):
    store = MemoryCommsStore()
    gmail = FakeGmail(parts={"att-pdf": PDF_BYTES})
    parsed = parse_message(raw_with_attachments())
    rec = [("CPartnerProfile", "P1", "Acme")]
    drive.fail = True
    await att.file_message_attachments(Cfg(), FakeEspo(), store, gmail, parsed, rec)
    state = await store.attachment_state("m1@mail", 2, "CPartnerProfile", "P1")
    assert state["status"] == ATTACHMENT_FAILED
    assert state["attempts"] == 1
    assert "drive down" in (state["lastError"] or "")
    # Next pass: Drive is back — the failed row is re-attempted and files.
    drive.fail = False
    await att.file_message_attachments(Cfg(), FakeEspo(), store, gmail, parsed, rec)
    state = await store.attachment_state("m1@mail", 2, "CPartnerProfile", "P1")
    assert state["status"] == ATTACHMENT_FILED
    # Idempotent: a third pass changes nothing.
    await att.file_message_attachments(Cfg(), FakeEspo(), store, gmail, parsed, rec)
    assert len(await doc_store.list_documents("CPartnerProfile", "P1")) == 1


async def test_retry_sweep_refetches_from_source_mailbox(doc_store, drive, monkeypatch):
    store = MemoryCommsStore()
    raw = raw_with_attachments()
    await store.upsert_attachment({
        "rfc_message_id": "m1@mail", "part_index": 2,
        "entity_type": "CPartnerProfile", "record_id": "P1",
        "filename": "plan.pdf", "mime_type": "application/pdf", "size": 10,
        "status": ATTACHMENT_FAILED, "attempts": 1,
        "gmail_message_id": "m1", "source_mailbox": "bob.mentor@cbmentors.org",
    })
    fake = FakeGmail(parts={"att-pdf": PDF_BYTES}, messages={"m1": raw})
    monkeypatch.setattr(
        att, "GmailClient", lambda info, mailbox, timeout: fake
    )
    espo = FakeEspo()
    espo.records[("CPartnerProfile", "P1")] = {"name": "Acme"}
    n = await att.retry_failed_attachments(Cfg(), espo, store, {"sa": True})
    assert n == 1
    state = await store.attachment_state("m1@mail", 2, "CPartnerProfile", "P1")
    assert state["status"] == ATTACHMENT_FILED


async def test_file_for_ingest_gates(doc_store, drive):
    store = MemoryCommsStore()
    gmail = FakeGmail(parts={"att-pdf": PDF_BYTES})
    parsed = parse_message(raw_with_attachments(frm="bob.mentor@cbmentors.org"))
    scope = crm.MailboxScope(
        mailbox="bob.mentor@cbmentors.org", manager_name="Bob", owner_user_id="u1",
        records=[],
    )
    # Outbound — never auto-filed (the plan files INBOUND attachments only).
    await att.file_for_ingest(
        Cfg(), FakeEspo(), store, gmail, scope, parsed, "conv1", [], set()
    )
    assert not drive.uploads
    # Disabled pipeline — no-op even for inbound.
    inbound = parse_message(raw_with_attachments())
    off = Cfg(); off.gdrive_docs = False
    await att.file_for_ingest(
        off, FakeEspo(), store, gmail, scope, inbound, "conv1",
        [crm.RecordRef(entity="CPartnerProfile", id="P1", name="Acme")], set(),
    )
    assert not drive.uploads


async def test_thread_following_files_to_conversation_records(doc_store, drive):
    store = MemoryCommsStore()
    gmail = FakeGmail(parts={"att-pdf": PDF_BYTES})
    parsed = parse_message(raw_with_attachments())
    scope = crm.MailboxScope(
        mailbox="bob.mentor@cbmentors.org", manager_name="Bob", owner_user_id="u1",
        records=[],
    )
    espo = FakeEspo(lists={
        ("CConversation", "conv1", "partnerProfiles"): [{"id": "P9", "name": "Linked"}],
    })
    await att.file_for_ingest(
        Cfg(), espo, store, gmail, scope, parsed, "conv1", [], set()
    )
    assert len(await doc_store.list_documents("CPartnerProfile", "P9")) == 1


# --- bounce + chips on the thread payload -------------------------------------


class ThreadEspo:
    """user_client stand-in for get_conversation / enrich."""

    def __init__(self, messages):
        self.messages = messages

    async def get(self, entity, record_id, select=None):
        return {"id": record_id, "name": "Subject line"}

    async def list(self, entity, *, where=None, select=None, max_size=50, **kw):
        return {"list": self.messages, "total": len(self.messages)}


async def test_get_conversation_flags_bounces_and_attaches_chips():
    store = MemoryCommsStore()
    await store.upsert_attachment({
        "rfc_message_id": "r1", "part_index": 2,
        "entity_type": "CEngagement", "record_id": "E1",
        "filename": "plan.pdf", "mime_type": "application/pdf", "size": 10,
        "status": ATTACHMENT_FILED, "document_id": "doc-1", "attempts": 1,
    })
    client = ThreadEspo([
        {"id": "c1", "direction": "Inbound", "fromAddress": "james@acme.test",
         "name": "Re: plan", "rfcMessageId": "r1", "bodyCleaned": "<p>hi</p>"},
        {"id": "c2", "direction": "Inbound",
         "fromAddress": "mailer-daemon@googlemail.com",
         "name": "Delivery Status Notification (Failure)", "rfcMessageId": "r2"},
    ])
    thread = await comms_service.get_conversation(
        client, "conv1", store=store, parent_entity="CEngagement", parent_id="E1"
    )
    m1, m2 = thread["messages"]
    assert m1["bounce"] is False
    assert m1["attachments"][0]["documentId"] == "doc-1"
    assert m1["attachments"][0]["status"] == ATTACHMENT_FILED
    assert m2["bounce"] is True
    assert "attachments" not in m2


async def test_enrich_marks_bounced_not_awaiting():
    store = MemoryCommsStore()
    client = ThreadEspo([
        # newest first (the enrich query orders desc)
        {"conversationId": "conv1", "direction": "Inbound",
         "fromAddress": "mailer-daemon@googlemail.com",
         "name": "Delivery Status Notification (Failure)", "sentAt": "2026-07-21 10:00:00"},
        {"conversationId": "conv2", "direction": "Inbound",
         "fromAddress": "james@acme.test", "name": "Re: plan",
         "sentAt": "2026-07-21 09:00:00"},
    ])
    rows = [{"id": "conv1"}, {"id": "conv2"}]
    await comms_service.enrich_conversation_rows(client, store, "staff", rows)
    assert rows[0]["bounced"] is True
    assert rows[0]["awaitingReply"] is False
    assert rows[1]["bounced"] is False
    assert rows[1]["awaitingReply"] is True


# --- View original ------------------------------------------------------------


def test_sanitize_original_strips_active_content_keeps_formatting():
    html = (
        "<div style='color:red'><script>evil()</script>"
        "<p onclick='x()'>Hello <b>there</b></p>"
        "<a href='javascript:alert(1)'>bad</a>"
        "<img src='cid:logo@cid'>"
        "<img src='https://example.test/pic.png'></div>"
    )
    out = sanitize_original_html(html, cid_base="/mentorsessions/api/communications/c1/original/cid")
    assert "script" not in out
    assert "onclick" not in out
    assert "javascript:" not in out
    assert 'style="color:red"' in out
    assert "<b>there</b>" in out
    assert "/mentorsessions/api/communications/c1/original/cid/logo%40cid" in out
    assert "https://example.test/pic.png" in out  # remote formatting kept


class OriginalEspo:
    async def get(self, entity, record_id, select=None):
        return {
            "id": record_id, "name": "Plan attached",
            "sourceMailbox": "bob.mentor@cbmentors.org", "gmailMessageId": "m1",
        }


async def test_get_original_fetches_and_sanitizes(monkeypatch):
    raw = raw_with_attachments()
    html = base64.urlsafe_b64encode(
        b"<p>Hello <b>bold</b></p><img src='cid:logo@cid'><script>x()</script>"
    ).decode()
    raw["payload"]["parts"].insert(1, {"mimeType": "text/html", "body": {"data": html}})
    fake = FakeGmail(messages={"m1": raw})

    async def _shared(settings, mailbox):
        assert mailbox == "bob.mentor@cbmentors.org"
        return fake

    monkeypatch.setattr(comms_service, "gmail_for_shared_mailbox", _shared)
    o = await comms_service.get_original(
        Cfg(), OriginalEspo(), "comm1", cid_base="/x/cid", acting_user="staff"
    )
    assert o["subject"] == "Plan attached"
    assert "<b>bold</b>" in o["bodyHtml"]
    assert "script" not in o["bodyHtml"]
    assert "/x/cid/logo%40cid" in o["bodyHtml"]
    real = [a for a in o["attachments"] if not a["inline"]]
    assert [a["filename"] for a in real] == ["plan.pdf"]


async def test_get_original_part_serves_cid_bytes(monkeypatch):
    fake = FakeGmail(
        messages={"m1": raw_with_attachments()},
        parts={"att-logo": b"PNGBYTES"},
    )

    async def _shared(settings, mailbox):
        return fake

    monkeypatch.setattr(comms_service, "gmail_for_shared_mailbox", _shared)
    part = await comms_service.get_original_part(
        Cfg(), OriginalEspo(), "comm1", "logo@cid"
    )
    assert part["data"] == b"PNGBYTES"
    assert part["mime_type"] == "image/png"


async def test_get_original_gone_message(monkeypatch):
    class GoneGmail(FakeGmail):
        async def get_message(self, message_id):
            from core.gmail import MessageGoneError

            raise MessageGoneError("gone")

    async def _shared(settings, mailbox):
        return GoneGmail()

    monkeypatch.setattr(comms_service, "gmail_for_shared_mailbox", _shared)
    with pytest.raises(comms_service.OriginalGoneError):
        await comms_service.get_original(
            Cfg(), OriginalEspo(), "comm1", cid_base="/x"
        )


# --- bounce ingest exemption (§3.4 — found in live-verification prep) ---------


def _bounce_raw(mid="dsn1", thread="t1"):
    import base64 as b64

    body = b64.urlsafe_b64encode(b"Address not found: casey@typo.test").decode()
    return {
        "id": mid, "threadId": thread, "internalDate": "1780000100000",
        "snippet": "Address not found",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "Mail Delivery Subsystem <mailer-daemon@googlemail.com>"},
                {"name": "To", "value": "bob.mentor@cbmentors.org"},
                {"name": "Subject", "value": "Delivery Status Notification (Failure)"},
                {"name": "Message-ID", "value": f"<{mid}@mail>"},
            ],
            "body": {"data": body},
        },
    }


async def test_bounce_on_stored_thread_is_ingested_not_junked():
    """Triage junks mailer-daemon mail — but a bounce replying on a STORED
    conversation is the fate of our own send and must reach the thread."""
    from comms.sync import ingest_message
    from tests.test_comms_sync import FakeEspo as SyncEspo, raw_message, scope

    espo, store = SyncEspo(), MemoryCommsStore()
    # An outbound conversation exists on thread t1.
    first = parse_message(raw_message())
    conv = await ingest_message(espo, store, scope(), first)
    assert conv
    # The bounce arrives on the same thread from mailer-daemon: stored.
    bounce = parse_message(_bounce_raw(thread="t1"))
    got = await ingest_message(espo, store, scope(), bounce)
    assert got == conv
    stored = [r for (e, _), r in espo.records.items() if e == "CCommunication"]
    assert any("Delivery Status" in (r.get("name") or "") for r in stored)


async def test_bounce_without_stored_thread_stays_junk():
    from comms.sync import ingest_message
    from tests.test_comms_sync import FakeEspo as SyncEspo, scope

    espo, store = SyncEspo(), MemoryCommsStore()
    bounce = parse_message(_bounce_raw(thread="t-unknown"))
    assert await ingest_message(espo, store, scope(), bounce) is None
    assert not any(e == "CCommunication" for (e, _) in espo.records)


async def test_enrich_pages_within_espo_200_cap():
    """EspoCRM hard-caps list pages at 200 (a larger maxSize is a 403 that
    silently killed the whole enrichment — found live 2026-07-22): the query
    must page, never ask for more than 200."""
    calls = []

    class PagedEspo(ThreadEspo):
        async def list(self, entity, *, where=None, select=None, max_size=50,
                       offset=0, **kw):
            calls.append((max_size, offset))
            assert max_size <= 200
            if offset == 0:
                # 200 messages, all for conv1 — conv2's newest is on page 2.
                return {"list": [
                    {"conversationId": "conv1", "direction": "Outbound",
                     "fromAddress": "b@cbmentors.org", "name": "x",
                     "sentAt": f"2026-07-21 10:{i:02d}:00"}
                    for i in range(200)
                ]}
            return {"list": [
                {"conversationId": "conv2", "direction": "Inbound",
                 "fromAddress": "james@acme.test", "name": "Re: plan",
                 "sentAt": "2026-07-20 09:00:00"},
            ]}

    rows = [{"id": "conv1"}, {"id": "conv2"}]
    await comms_service.enrich_conversation_rows(
        PagedEspo([]), MemoryCommsStore(), "staff", rows
    )
    assert calls[0] == (200, 0) and calls[1] == (200, 200)
    assert rows[0]["awaitingReply"] is False   # last message outbound
    assert rows[1]["awaitingReply"] is True    # found on page 2
