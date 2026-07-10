"""Communications sync engine — scope building, ingest, dedup, curation."""

from __future__ import annotations

import itertools
from typing import Any, Optional

import pytest

from comms import crm, sync, triage
from comms.store import ACTION_EXCLUDE, MemoryCommsStore
from comms.sync import ingest_message, sync_mailbox
from core.gmail import ParsedGmailMessage


class FakeEspo:
    """Minimal EspoApi stand-in: in-memory records + relate log."""

    def __init__(self, lists: Optional[dict] = None):
        self.records: dict[tuple[str, str], dict] = {}
        self.relates: list[tuple[str, str, str, str]] = []
        self.lists = lists or {}  # (entity, link_or_None) -> list payloads
        self._ids = itertools.count(1)

    async def list(self, entity, *, where=None, select=None, max_size=50, **kw):
        # rfcMessageId / conversation searches walk the in-memory records.
        rows = []
        for (ent, rid), rec in self.records.items():
            if ent != entity:
                continue
            ok = True
            for clause in where or []:
                if clause["type"] == "equals" and rec.get(clause["attribute"]) != clause["value"]:
                    ok = False
                elif clause["type"] == "isNull" and rec.get(clause["attribute"]) is not None:
                    ok = False
            if ok:
                rows.append({"id": rid, **rec})
        if entity in self.lists:
            rows = self.lists[entity]
        return {"total": len(rows), "list": rows[:max_size]}

    async def list_related(self, entity, record_id, link, *, select=None, max_size=200):
        return {"list": self.lists.get((entity, record_id, link), [])}

    async def find_one(self, entity, attribute, value, select="id"):
        for (ent, rid), rec in self.records.items():
            if ent == entity and rec.get(attribute) == value:
                return {"id": rid, **rec}
        return None

    async def get(self, entity, record_id, select=None):
        return {"id": record_id, **self.records.get((entity, record_id), {})}

    async def create(self, entity, payload):
        rid = f"{entity[:4].lower()}{next(self._ids)}"
        self.records[(entity, rid)] = dict(payload)
        return {"id": rid, **payload}

    async def update(self, entity, record_id, payload):
        self.records.setdefault((entity, record_id), {}).update(payload)
        return {"id": record_id}

    async def relate(self, entity, record_id, link, related_id):
        self.relates.append((entity, record_id, link, related_id))


class FakeGmail:
    def __init__(self, mailbox, messages=None, history=None, profile_history="999"):
        self.mailbox = mailbox
        self.messages = messages or {}  # id -> raw message resource
        self.history = history          # None => HistoryExpiredError on list_history
        self.profile_history = profile_history

    async def profile(self):
        return {"emailAddress": self.mailbox, "historyId": self.profile_history}

    async def list_messages(self, query, page_token=None, max_results=100):
        return {"messages": [{"id": mid} for mid in self.messages]}

    async def list_history(self, start_history_id, page_token=None):
        if self.history is None:
            from core.gmail import HistoryExpiredError

            raise HistoryExpiredError("expired")
        return {"historyId": self.profile_history, "history": self.history}

    async def get_message(self, message_id):
        return self.messages[message_id]


def raw_message(
    mid="m1", thread="t1", frm="james@acme.test", to="bob.mentor@cbmentors.org",
    subject="Session", rfc_id=None, body="Hi Bob, Tuesday works.", refs="",
):
    headers = [
        {"name": "From", "value": f"James Koran <{frm}>"},
        {"name": "To", "value": to},
        {"name": "Subject", "value": subject},
        {"name": "Message-ID", "value": f"<{rfc_id or mid}@mail>"},
    ]
    if refs:
        headers.append({"name": "References", "value": refs})
    import base64

    return {
        "id": mid,
        "threadId": thread,
        "internalDate": "1780000000000",
        "snippet": body[:50],
        "payload": {
            "mimeType": "text/plain",
            "headers": headers,
            "body": {"data": base64.urlsafe_b64encode(body.encode()).decode()},
        },
    }


def scope(addresses={"james@acme.test"}, entity="CEngagement", rec_id="E1"):
    return crm.MailboxScope(
        mailbox="bob.mentor@cbmentors.org",
        manager_name="Bob Mentor",
        owner_user_id="u1",
        records=[
            crm.RecordRef(
                entity=entity, id=rec_id, name="Acme", contact_ids={"c1"},
                addresses=set(addresses),
            )
        ],
    )


class Cfg:
    gmail_backfill = "newer_than:365d"
    request_timeout_seconds = 20
    comms_engagement_statuses_list = ["Active", "Assigned"]
    comms_partner_excluded_statuses_list = ["Ended"]


# --- ingest ---------------------------------------------------------------


async def test_ingest_creates_conversation_and_message_and_links():
    espo, store = FakeEspo(), MemoryCommsStore()
    parsed = sync.parse_message(raw_message())
    conv_id = await ingest_message(espo, store, scope(), parsed)
    assert conv_id
    conv = espo.records[(crm.CONVERSATION, conv_id)]
    assert conv["conversationStatus"] == "Open"
    assert conv["messageCount"] == 1                      # aggregate bumped
    assert conv["summarizedAt"] is None                   # flagged for the AI pass
    comms = [r for (e, _), r in espo.records.items() if e == crm.COMMUNICATION]
    assert len(comms) == 1 and comms[0]["direction"] == "Inbound"
    assert (crm.CONVERSATION, conv_id, "engagements", "E1") in espo.relates
    assert (crm.CONVERSATION, conv_id, "contacts", "c1") in espo.relates
    # owner-stamped so read-own roles see it
    assert espo.records[(crm.CONVERSATION, conv_id)]["assignedUsersIds"] == ["u1"]


async def test_ingest_dedups_by_rfc_message_id_across_mailboxes():
    espo, store = FakeEspo(), MemoryCommsStore()
    parsed = sync.parse_message(raw_message(rfc_id="shared-id"))
    conv1 = await ingest_message(espo, store, scope(), parsed)
    # The co-mentor's mailbox sees the SAME email (same Message-ID).
    co = scope()
    co.mailbox = "carol.mentor@cbmentors.org"
    co.owner_user_id = "u2"
    conv2 = await ingest_message(espo, store, co, sync.parse_message(raw_message(rfc_id="shared-id", mid="m2")))
    assert conv1 == conv2
    comms = [r for (e, _), r in espo.records.items() if e == crm.COMMUNICATION]
    assert len(comms) == 1                                # ONE stored message
    assert set(espo.records[(crm.CONVERSATION, conv1)]["assignedUsersIds"]) == {"u1", "u2"}


async def test_ingest_joins_conversation_via_references():
    espo, store = FakeEspo(), MemoryCommsStore()
    first = sync.parse_message(raw_message(rfc_id="root-id"))
    conv1 = await ingest_message(espo, store, scope(), first)
    # A different Gmail thread (e.g. other mailbox) referencing the stored id.
    reply = sync.parse_message(
        raw_message(mid="m9", thread="OTHER", rfc_id="reply-id", refs="<root-id@mail>")
    )
    conv2 = await ingest_message(espo, store, scope(), reply)
    assert conv1 == conv2


async def test_exclusion_blocks_record_link():
    espo, store = FakeEspo(), MemoryCommsStore()
    first = sync.parse_message(raw_message())
    conv_id = await ingest_message(espo, store, scope(), first)
    await store.set_override("CEngagement", "E1", conv_id, ACTION_EXCLUDE)
    espo.relates.clear()
    reply = sync.parse_message(raw_message(mid="m2", rfc_id="r2"))
    await ingest_message(espo, store, scope(), reply)
    assert (crm.CONVERSATION, conv_id, "engagements", "E1") not in espo.relates


async def test_unmatched_and_junk_are_skipped():
    espo, store = FakeEspo(), MemoryCommsStore()
    stranger = sync.parse_message(raw_message(frm="other@else.test"))
    assert await ingest_message(espo, store, scope(), stranger) is None
    junk = sync.parse_message(raw_message(frm="no-reply@acme.test"))
    junk.from_address = "no-reply@acme.test"
    assert await ingest_message(espo, store, scope(), junk) is None
    assert not espo.records


# --- mailbox sync ------------------------------------------------------------


async def test_initial_sync_sets_cursor_and_known_addresses():
    espo, store = FakeEspo(), MemoryCommsStore()
    sc = scope()
    gmail = FakeGmail(sc.mailbox, messages={"m1": raw_message()}, profile_history="1234")
    stats = await sync_mailbox(gmail, espo, store, sc, Cfg())
    assert stats == {"fetched": 1, "stored": 1}
    state = await store.get_sync_state(sc.mailbox)
    assert state.initial_done and state.history_id == "1234"
    assert "james@acme.test" in state.known_addresses


async def test_incremental_sync_uses_history():
    espo, store = FakeEspo(), MemoryCommsStore()
    sc = scope()
    await store.save_sync_state(
        sc.mailbox, history_id="100", initial_done=True,
        known_addresses={"james@acme.test"},
    )
    gmail = FakeGmail(
        sc.mailbox,
        messages={"m5": raw_message(mid="m5")},
        history=[{"messagesAdded": [{"message": {"id": "m5"}}]}],
        profile_history="200",
    )
    stats = await sync_mailbox(gmail, espo, store, sc, Cfg())
    assert stats["stored"] == 1
    assert (await store.get_sync_state(sc.mailbox)).history_id == "200"


async def test_expired_cursor_falls_back_to_query():
    espo, store = FakeEspo(), MemoryCommsStore()
    sc = scope()
    await store.save_sync_state(
        sc.mailbox, history_id="1", initial_done=True,
        known_addresses={"james@acme.test"},
    )
    gmail = FakeGmail(sc.mailbox, messages={"m1": raw_message()}, history=None,
                      profile_history="500")
    stats = await sync_mailbox(gmail, espo, store, sc, Cfg())
    assert stats["stored"] == 1
    assert (await store.get_sync_state(sc.mailbox)).history_id == "500"


async def test_new_address_triggers_targeted_backfill():
    espo, store = FakeEspo(), MemoryCommsStore()
    sc = scope(addresses={"james@acme.test", "new@acme.test"})
    await store.save_sync_state(
        sc.mailbox, history_id="100", initial_done=True,
        known_addresses={"james@acme.test"},  # new@acme.test is new this cycle
    )
    gmail = FakeGmail(
        sc.mailbox, messages={"m7": raw_message(mid="m7", frm="new@acme.test")},
        history=[],
    )
    stats = await sync_mailbox(gmail, espo, store, sc, Cfg())
    assert stats["stored"] == 1
    assert "new@acme.test" in (await store.get_sync_state(sc.mailbox)).known_addresses


# --- scope building -----------------------------------------------------------


async def test_build_scopes_filters_statuses_and_requires_mailbox():
    lists = {
        "CMentorProfile": [
            {"id": "p1", "name": "Bob", "cbmEmail": "bob@cbmentors.org", "assignedUserId": "u1"},
            {"id": "p2", "name": "NoMail", "assignedUserId": "u2"},          # skipped
            {"id": "p3", "name": "NoUser", "cbmEmail": "x@cbmentors.org"},   # skipped
        ],
        ("CMentorProfile", "p1", "engagements1"): [
            {"id": "E1", "name": "Active One", "engagementStatus": "Active"},
            {"id": "E2", "name": "Closed One", "engagementStatus": "Completed"},  # filtered
        ],
        ("CMentorProfile", "p1", "managedPartners"): [
            {"id": "P1", "name": "Partner", "partnershipStatus": "Ended"},  # excluded
        ],
        ("CMentorProfile", "p1", "managedSponsors"): [],
        ("CEngagement", "E1", "engagementContacts"): [
            {"id": "c1", "name": "James", "emailAddress": "James@Acme.test"},
        ],
    }
    espo = FakeEspo(lists=lists)
    scopes = await crm.build_scopes(espo, Cfg())
    assert len(scopes) == 1
    sc = scopes[0]
    assert sc.mailbox == "bob@cbmentors.org"
    assert [r.id for r in sc.records] == ["E1"]
    assert sc.records[0].addresses == {"james@acme.test"}  # lowercased


# --- triage --------------------------------------------------------------------


def test_triage_patterns():
    def msg(frm="james@acme.test", subject="Hello", body="Real content"):
        return ParsedGmailMessage(
            gmail_id="x", thread_id="t", rfc_message_id="r", in_reply_to="",
            references="", subject=subject, from_address=frm, from_name="",
            body_text=body,
        )

    assert triage.is_junk(msg(frm="no-reply@stripe.com"))
    assert triage.is_junk(msg(subject="Automatic reply: Out of Office"))
    assert triage.is_junk(msg(body="Click here to unsubscribe from this list"))
    assert not triage.is_junk(msg())
