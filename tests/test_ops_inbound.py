"""The inbound info@ mailbox poller + the info-email submission kind
(v0.110.0): new inbound threads become held submissions in the /ops queue;
approval delivers them through the info-request CRM mapping."""

from __future__ import annotations

import base64

import pytest

from core.config import Settings
from core.store import STATUS_HELD_REVIEW
from forms.info_email.orchestrator import submit_email
from forms.info_email.schemas import InfoEmail
from ops.inbound import _split_name, run_inbound_cycle, thread_token

MAILBOX = "info@cbmentors.org"


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _raw(msg_id, thread_id, frm, *, subject="Hello CBM", body="I need a mentor.",
         labels=("INBOX",), internal="1753000000000"):
    return {
        "id": msg_id, "threadId": thread_id, "labelIds": list(labels),
        "internalDate": internal, "snippet": body[:100],
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": frm},
                {"name": "To", "value": MAILBOX},
                {"name": "Subject", "value": subject},
                {"name": "Message-ID", "value": f"<{msg_id}@mail.example>"},
            ],
            "body": {"data": _b64(body)},
        },
    }


class FakeGmail:
    def __init__(self, listing=None, threads=None):
        self.mailbox = MAILBOX
        self._listing = listing or []
        self._threads = threads or {}
        self.closed = False

    async def list_messages(self, query, page_token=None, max_results=100):
        return {"messages": self._listing}

    async def get_thread(self, thread_id, *, headers_only=False):
        return self._threads[thread_id]

    async def aclose(self):
        self.closed = True


class FakeInboundStore:
    def __init__(self):
        self.rows: dict[str, dict] = {}
        self._by_key: dict[tuple[str, str], str] = {}
        self._n = 0

    async def capture(self, form_slug, submission_token, payload, *, status):
        key = (form_slug, submission_token)
        if key in self._by_key:
            row = self.rows[self._by_key[key]]
            from core.store import Captured
            return Captured(id=row["id"], is_new=False, status=row["status"], result=None)
        self._n += 1
        sid = f"sub-{self._n}"
        self.rows[sid] = {
            "id": sid, "form_slug": form_slug, "submission_token": submission_token,
            "payload": payload, "status": status, "thread_ids": None,
        }
        self._by_key[key] = sid
        from core.store import Captured
        return Captured(id=sid, is_new=True, status=status, result=None)

    async def add_thread_id(self, submission_id, thread_id):
        row = self.rows.get(submission_id)
        if row is None:
            return False
        threads = list(row["thread_ids"] or [])
        if thread_id not in threads:
            threads.append(thread_id)
        row["thread_ids"] = threads
        return True

    async def existing_tokens(self, form_slug, tokens):
        return {t for (f, t) in self._by_key if f == form_slug and t in set(tokens)}

    async def known_gmail_threads(self, thread_ids):
        wanted = set(thread_ids)
        known = set()
        for row in self.rows.values():
            known.update(t for t in (row["thread_ids"] or []) if t in wanted)
        return known


def _settings(**overrides) -> Settings:
    base = dict(gmail_sync=True, ops_mailbox=MAILBOX)
    base.update(overrides)
    return Settings(**base)


def _patch_gmail(monkeypatch, gmail):
    async def fake(settings, mailbox):
        assert mailbox == MAILBOX
        return gmail

    monkeypatch.setattr("comms.service.gmail_for_shared_mailbox", fake)


@pytest.mark.asyncio
async def test_new_inbound_thread_captured_held(monkeypatch):
    """A brand-new inbound thread becomes a held info-email submission with the
    email facts in the payload and the origin thread anchored."""
    gmail = FakeGmail(
        listing=[{"id": "m1", "threadId": "t1"}],
        threads={"t1": {"messages": [_raw("m1", "t1", "Jane Q Doe <jane@example.com>")]}},
    )
    _patch_gmail(monkeypatch, gmail)
    store = FakeInboundStore()

    stats = await run_inbound_cycle(_settings(), store)

    assert stats["captured"] == 1 and stats["errors"] == 0
    row = list(store.rows.values())[0]
    assert row["status"] == STATUS_HELD_REVIEW
    assert row["form_slug"] == "info-email"
    assert row["submission_token"] == thread_token("t1")
    p = row["payload"]
    assert p["email"] == "jane@example.com"
    assert (p["first_name"], p["last_name"]) == ("Jane", "Q Doe")
    assert p["subject"] == "Hello CBM"
    assert "I need a mentor." in p["message"]
    assert p["gmail_thread_id"] == "t1" and p["mailbox"] == MAILBOX
    # Origin thread mirrored into the anchor column (the conversation source).
    assert row["thread_ids"] == ["t1"]
    # The captured payload validates as an InfoEmail — approval can deliver it.
    InfoEmail.model_validate(p)
    assert gmail.closed


@pytest.mark.asyncio
async def test_second_pass_is_idempotent(monkeypatch):
    gmail = FakeGmail(
        listing=[{"id": "m1", "threadId": "t1"}],
        threads={"t1": {"messages": [_raw("m1", "t1", "Jane <jane@example.com>")]}},
    )
    _patch_gmail(monkeypatch, gmail)
    store = FakeInboundStore()
    await run_inbound_cycle(_settings(), store)
    stats = await run_inbound_cycle(_settings(), store)
    assert stats["captured"] == 0
    assert stats["skippedKnown"] == 1
    assert len(store.rows) == 1


@pytest.mark.asyncio
async def test_reply_on_anchored_form_thread_not_recaptured(monkeypatch):
    """A submitter replying to a conversation staff started from a FORM
    submission lands in the inbox on the anchored thread — it must join that
    conversation, never become a second submission."""
    gmail = FakeGmail(listing=[{"id": "m9", "threadId": "t-form"}], threads={})
    _patch_gmail(monkeypatch, gmail)
    store = FakeInboundStore()
    # A form submission whose /ops send anchored thread t-form.
    cap = await store.capture("info-request", "tok-1", {"email": "x@example.com"}, status="completed")
    await store.add_thread_id(cap.id, "t-form")

    stats = await run_inbound_cycle(_settings(), store)
    assert stats["captured"] == 0
    assert stats["skippedKnown"] == 1
    assert len(store.rows) == 1  # still only the form submission


@pytest.mark.asyncio
async def test_outbound_initiated_and_bounces_skipped(monkeypatch):
    gmail = FakeGmail(
        listing=[{"id": "a", "threadId": "t-out"}, {"id": "b", "threadId": "t-bounce"}],
        threads={
            # Staff mailed out directly from Gmail — first message is ours.
            "t-out": {"messages": [_raw("a", "t-out", f"CBM Info <{MAILBOX}>")]},
            "t-bounce": {"messages": [_raw("b", "t-bounce", "Mail Delivery <mailer-daemon@google.com>")]},
        },
    )
    _patch_gmail(monkeypatch, gmail)
    store = FakeInboundStore()
    stats = await run_inbound_cycle(_settings(), store)
    assert stats["captured"] == 0 and stats["errors"] == 0
    assert store.rows == {}


@pytest.mark.asyncio
async def test_noop_when_not_configured(monkeypatch):
    def boom(*a, **k):  # must not even resolve a client
        raise AssertionError("should not be called")

    monkeypatch.setattr("comms.service.gmail_for_shared_mailbox", boom)
    store = FakeInboundStore()
    off = await run_inbound_cycle(_settings(gmail_sync=False), store)
    no_mailbox = await run_inbound_cycle(_settings(ops_mailbox=""), store)
    assert off["captured"] == 0 and no_mailbox["captured"] == 0
    assert store.rows == {}


def test_split_name_variants():
    assert _split_name("Jane Doe", "jane@example.com") == ("Jane", "Doe")
    assert _split_name("Doe, Jane", "jane@example.com") == ("Doe", "Jane")
    assert _split_name("acme", "sales@example.com") == ("acme", "(unknown)")
    assert _split_name("", "sales@example.com") == ("sales", "(unknown)")


# --- delivery: the info-email orchestrator ---------------------------------


class CapturingClient:
    def __init__(self):
        self.creates: list[tuple[str, dict]] = []
        self._n = 0

    async def create(self, entity, payload):
        self._n += 1
        self.creates.append((entity, payload))
        return {"id": f"{entity}-{self._n}", **payload}

    async def update(self, entity, record_id, payload):
        return {"id": record_id, **payload}

    async def find_one(self, entity, attribute, value, select="id"):
        return None


def _email_submission(**overrides) -> InfoEmail:
    base = dict(
        first_name="Jane", last_name="Doe", email="jane@example.com",
        subject="Question about mentoring",
        message="Do you help retail startups?",
        gmail_thread_id="t1", gmail_message_id="m1", mailbox=MAILBOX,
        submission_token=thread_token("t1"),
    )
    base.update(overrides)
    return InfoEmail(**base)


@pytest.mark.asyncio
async def test_orchestrator_reuses_info_request_mapping_with_email_wording():
    client = CapturingClient()
    ids = await submit_email(_email_submission(), client)

    entities = [e for e, _ in client.creates]
    assert entities == ["Contact", "CInformationRequest"]
    contact = client.creates[0][1]
    assert contact["description"].startswith("[Information request via email")
    req = client.creates[1][1]
    assert req["form"] == "info-email"
    assert req["source"] == "Email"
    assert req["message"].startswith("Subject: Question about mentoring")
    assert "Do you help retail startups?" in req["message"]
    assert f"via email to {MAILBOX}" in req["description"]
    assert ids.keys() == {"contactId", "informationRequestId"}


@pytest.mark.asyncio
async def test_orchestrator_without_subject_keeps_plain_message():
    client = CapturingClient()
    await submit_email(_email_submission(subject=None), client)
    req = client.creates[1][1]
    assert req["message"] == "Do you help retail startups?"
