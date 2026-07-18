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
    gmail_dead_letter_passes = 5  # D6
    alert_webhook_url = ""


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


# --- participants ---------------------------------------------------------


def test_merge_participants_dedups_by_address_and_upgrades_entries():
    merged = crm.merge_participants(
        "", [("James Koran", "james@acme.test"), ("", "bob@cbmentors.org")]
    )
    assert merged == "James Koran <james@acme.test>, bob@cbmentors.org"
    # Same address again — any casing, with or without a name — never duplicates;
    # a bare-address entry is upgraded once the display name is learned.
    again = crm.merge_participants(
        merged, [("James Koran", "JAMES@acme.test"), ("Bob Mentor", "bob@cbmentors.org")]
    )
    assert again == "James Koran <james@acme.test>, Bob Mentor <bob@cbmentors.org>"
    # Legacy name-only entry (pre-v0.55.0 format) upgraded once its address arrives.
    legacy = crm.merge_participants("James Koran", [("James Koran", "james@acme.test")])
    assert legacy == "James Koran <james@acme.test>"
    # Commas in display names are sanitized so the flat list stays parseable.
    comma = crm.merge_participants("", [("Koran, James", "james@acme.test")])
    assert comma == "Koran James <james@acme.test>"


def test_merge_participants_drops_legacy_name_when_address_learned_bare_first():
    # Address arrives bare (a To recipient), the legacy senders-only entry
    # holds just the name — learning the name later must not leave both.
    state = crm.merge_participants("Mindy Bower", [("", "mindy@mindybower.com")])
    assert state == "Mindy Bower, mindy@mindybower.com"
    healed = crm.merge_participants(state, [("Mindy Bower", "mindy@mindybower.com")])
    assert healed == "Mindy Bower <mindy@mindybower.com>"
    # An already-duplicated stored list self-heals on the next merge too.
    dup = "doug@cbmentors.org, Mindy Bower, Mindy Bower <mindy@mindybower.com>"
    assert crm.merge_participants(dup, [("Mindy Bower", "mindy@mindybower.com")]) == (
        "doug@cbmentors.org, Mindy Bower <mindy@mindybower.com>"
    )


def test_merge_participants_clamps_to_whole_entries():
    adds = [(f"Person {i}", f"person{i}@example.test") for i in range(40)]
    merged = crm.merge_participants("", adds)
    assert len(merged) <= crm.PARTICIPANTS_MAX
    assert merged.endswith(">")  # never cut mid-entry


async def test_ingest_records_sender_and_recipients_as_participants():
    espo, store = FakeEspo(), MemoryCommsStore()
    raw = raw_message()
    raw["payload"]["headers"].append(
        {"name": "Cc", "value": "Carol Mentor <carol.mentor@cbmentors.org>"}
    )
    conv_id = await ingest_message(espo, store, scope(), sync.parse_message(raw))
    assert espo.records[(crm.CONVERSATION, conv_id)]["participants"] == (
        "James Koran <james@acme.test>, bob.mentor@cbmentors.org, "
        "Carol Mentor <carol.mentor@cbmentors.org>"
    )
    # A reply the other way adds nothing new — everyone is already listed.
    reply = raw_message(
        mid="m2", rfc_id="r2", frm="bob.mentor@cbmentors.org", to="james@acme.test"
    )
    reply["payload"]["headers"][0]["value"] = "Bob Mentor <bob.mentor@cbmentors.org>"
    await ingest_message(espo, store, scope(), sync.parse_message(reply))
    assert espo.records[(crm.CONVERSATION, conv_id)]["participants"] == (
        "James Koran <james@acme.test>, Bob Mentor <bob.mentor@cbmentors.org>, "
        "Carol Mentor <carol.mentor@cbmentors.org>"
    )


async def test_replaying_a_stored_message_backfills_participants():
    """The dedup path merges participants, so a GMAIL_RESYNC pass upgrades
    conversations stored before the recipients change (senders-only)."""
    espo, store = FakeEspo(), MemoryCommsStore()
    conv_id = await ingest_message(espo, store, scope(), sync.parse_message(raw_message()))
    # Simulate the pre-v0.55.0 state: senders-only, name without address.
    espo.records[(crm.CONVERSATION, conv_id)]["participants"] = "James Koran"
    # Same message replayed (same rfc id) — dedup path, no new CCommunication.
    await ingest_message(espo, store, scope(), sync.parse_message(raw_message()))
    conv = espo.records[(crm.CONVERSATION, conv_id)]
    assert conv["participants"] == (
        "James Koran <james@acme.test>, bob.mentor@cbmentors.org"
    )
    assert conv["messageCount"] == 1  # replay never bumps the counters
    comms = [r for (e, _), r in espo.records.items() if e == crm.COMMUNICATION]
    assert len(comms) == 1


# --- mailbox sync ------------------------------------------------------------


async def test_initial_sync_sets_cursor_and_known_addresses():
    espo, store = FakeEspo(), MemoryCommsStore()
    sc = scope()
    gmail = FakeGmail(sc.mailbox, messages={"m1": raw_message()}, profile_history="1234")
    stats = await sync_mailbox(gmail, espo, store, sc, Cfg())
    assert stats == {"fetched": 1, "stored": 1, "failed": 0, "deadLettered": 0}
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


async def test_reset_all_sync_state_forces_initial_resync():
    store = MemoryCommsStore()
    await store.save_sync_state("m@x", history_id="42", initial_done=True,
                                known_addresses={"a@b"})
    await store.reset_all_sync_state()
    st = await store.get_sync_state("m@x")
    assert st.initial_done is False and st.history_id is None
    assert st.known_addresses == set()


async def test_drafts_spam_trash_are_never_ingested():
    espo, store = FakeEspo(), MemoryCommsStore()
    for label in ("DRAFT", "SPAM", "TRASH"):
        raw = raw_message(mid=f"m-{label}", rfc_id=f"r-{label}")
        raw["labelIds"] = [label]
        assert await ingest_message(espo, store, scope(), sync.parse_message(raw)) is None
    assert not espo.records
    sent = raw_message(mid="m-ok", rfc_id="r-ok")
    sent["labelIds"] = ["SENT"]
    assert await ingest_message(espo, store, scope(), sync.parse_message(sent))


async def test_thread_following_ingests_reply_from_unknown_address():
    espo, store = FakeEspo(), MemoryCommsStore()
    # Establish a conversation normally (known contact).
    first = sync.parse_message(raw_message(rfc_id="root"))
    conv_id = await ingest_message(espo, store, scope(), first)
    # A reply on the SAME Gmail thread from an address on no contact record.
    reply = raw_message(mid="m2", thread="t1", frm="stranger@else.test", rfc_id="r2")
    got = await ingest_message(espo, store, scope(), sync.parse_message(reply))
    assert got == conv_id                                  # followed the thread
    comms = [r for (e, _), r in espo.records.items() if e == crm.COMMUNICATION]
    assert len(comms) == 2
    # …but an unrelated message from an unknown address is still skipped.
    other = raw_message(mid="m3", thread="OTHER", frm="stranger@else.test", rfc_id="r3")
    assert await ingest_message(espo, store, scope(), sync.parse_message(other)) is None


# --- P1-5 loss prevention (reliability review 2026-07-17, Phase 4) ------------


class FailingEspo(FakeEspo):
    """CCommunication creates fail (the robert.cohen incident class)."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fail_comm_create = True

    async def create(self, entity, payload):
        if self.fail_comm_create and entity == crm.COMMUNICATION:
            from core.espo import EspoError

            raise EspoError("create CCommunication failed: HTTP 400 maxLength")
        return await super().create(entity, payload)


_HIST_M1 = [{"id": "h1", "messagesAdded": [{"message": {"id": "m1"}}]}]


async def _seed_done(store, cursor="100"):
    sc = scope()
    await store.save_sync_state(
        sc.mailbox, history_id=cursor, initial_done=True,
        known_addresses=sc.all_addresses,
    )
    return sc


async def test_failed_ingest_holds_cursor_then_dead_letters_after_five():
    """The DoD simulation: a message whose CRM create keeps failing holds the
    cursor (nothing lost) and is dead-lettered on the 5th consecutive failing
    pass (D6), after which the cursor moves on and the id is skipped."""
    espo, store = FailingEspo(), MemoryCommsStore()
    sc = await _seed_done(store, cursor="100")

    for n in range(1, 5):
        gmail = FakeGmail(sc.mailbox, messages={"m1": raw_message()},
                          history=_HIST_M1, profile_history="200")
        stats = await sync_mailbox(gmail, espo, store, sc, Cfg())
        st = await store.get_sync_state(sc.mailbox)
        assert stats["failed"] == 1 and stats["stored"] == 0
        assert st.history_id == "100", f"cursor must hold on pass {n}"
        assert st.failed_ids == {"m1": n}
        assert st.dead_letter == []

    # Pass 5: dead-lettered; the cursor finally advances past it.
    gmail = FakeGmail(sc.mailbox, messages={"m1": raw_message()},
                      history=_HIST_M1, profile_history="200")
    stats = await sync_mailbox(gmail, espo, store, sc, Cfg())
    st = await store.get_sync_state(sc.mailbox)
    assert stats["deadLettered"] == 1
    assert st.dead_letter == ["m1"] and st.failed_ids == {}
    assert st.history_id == "200"

    # Pass 6: the dead-lettered id is skipped entirely (not even fetched).
    gmail = FakeGmail(sc.mailbox, messages={"m1": raw_message()},
                      history=_HIST_M1, profile_history="300")
    stats = await sync_mailbox(gmail, espo, store, sc, Cfg())
    assert stats["fetched"] == 0 and stats["failed"] == 0


async def test_recovered_message_clears_failure_count_and_advances():
    espo, store = FailingEspo(), MemoryCommsStore()
    sc = await _seed_done(store, cursor="100")
    gmail = FakeGmail(sc.mailbox, messages={"m1": raw_message()},
                      history=_HIST_M1, profile_history="200")
    await sync_mailbox(gmail, espo, store, sc, Cfg())
    assert (await store.get_sync_state(sc.mailbox)).failed_ids == {"m1": 1}

    espo.fail_comm_create = False  # the CRM recovered
    gmail = FakeGmail(sc.mailbox, messages={"m1": raw_message()},
                      history=_HIST_M1, profile_history="200")
    stats = await sync_mailbox(gmail, espo, store, sc, Cfg())
    st = await store.get_sync_state(sc.mailbox)
    assert stats["stored"] == 1
    assert st.failed_ids == {} and st.dead_letter == []
    assert st.history_id == "200"  # cursor advances once nothing is failing


async def test_last_synced_at_only_advances_on_success():
    """F2: last_synced_at is the expired-cursor backfill window source — a
    failed/partial pass must never bump it."""
    from datetime import datetime, timezone

    espo, store = FailingEspo(), MemoryCommsStore()
    sc = await _seed_done(store)
    t0 = datetime(2026, 6, 1, tzinfo=timezone.utc)
    store._state[sc.mailbox].last_synced_at = t0

    gmail = FakeGmail(sc.mailbox, messages={"m1": raw_message()},
                      history=_HIST_M1, profile_history="200")
    await sync_mailbox(gmail, espo, store, sc, Cfg())  # failing pass
    assert (await store.get_sync_state(sc.mailbox)).last_synced_at == t0

    espo.fail_comm_create = False
    gmail = FakeGmail(sc.mailbox, messages={"m1": raw_message()},
                      history=_HIST_M1, profile_history="200")
    await sync_mailbox(gmail, espo, store, sc, Cfg())  # clean pass
    assert (await store.get_sync_state(sc.mailbox)).last_synced_at != t0


async def test_expired_cursor_window_comes_from_last_success():
    """The DoD outage simulation: after a two-week outage the expired-cursor
    re-query window must start at the last SUCCESSFUL pass, not yesterday."""
    from datetime import datetime, timezone

    class QueryCapturingGmail(FakeGmail):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.queries = []

        async def list_messages(self, query, page_token=None, max_results=100):
            self.queries.append(query)
            return await super().list_messages(query, page_token, max_results)

    espo, store = FakeEspo(), MemoryCommsStore()
    sc = await _seed_done(store)
    store._state[sc.mailbox].last_synced_at = datetime(2026, 6, 1, tzinfo=timezone.utc)

    gmail = QueryCapturingGmail(sc.mailbox, messages={}, history=None)  # None => expired
    await sync_mailbox(gmail, espo, store, sc, Cfg())
    assert gmail.queries, "the expired cursor must trigger a re-query"
    assert all("after:2026/05/31" in q for q in gmail.queries)


async def test_truncated_history_resumes_from_last_processed_entry():
    """The DoD 21-page simulation: a history listing longer than the page cap
    must NOT save the tip cursor (that skipped the unfetched pages) — it saves
    the last processed entry's id and continues next pass."""
    from comms.sync import _collect_history_ids

    class EndlessHistoryGmail(FakeGmail):
        async def list_history(self, start_history_id, page_token=None):
            i = int(page_token or 0)
            return {
                "historyId": "tip-999",
                "history": [
                    {"id": f"h{i}", "messagesAdded": [{"message": {"id": f"m{i}"}}]}
                ],
                "nextPageToken": str(i + 1),  # never drains
            }

    gmail = EndlessHistoryGmail(scope().mailbox)
    ids, cursor = await _collect_history_ids(gmail, "100")
    assert len(ids) == 20  # one per page, capped
    assert cursor == "h19"  # the LAST PROCESSED entry — never "tip-999"


async def test_drained_history_still_saves_tip_cursor():
    from comms.sync import _collect_history_ids

    gmail = FakeGmail(scope().mailbox, history=_HIST_M1, profile_history="777")
    ids, cursor = await _collect_history_ids(gmail, "100")
    assert ids == ["m1"] and cursor == "777"


async def test_resync_clears_failure_state():
    """GMAIL_RESYNC still works: cursors AND failure tracking reset — a
    formerly dead-lettered message gets its five new chances."""
    store = MemoryCommsStore()
    sc = await _seed_done(store)
    await store.save_sync_state(
        sc.mailbox, history_id="100", initial_done=True,
        known_addresses=sc.all_addresses,
        failed_ids={"m9": 3}, dead_letter=["m1"],
    )
    await store.reset_all_sync_state()
    st = await store.get_sync_state(sc.mailbox)
    assert st.initial_done is False and st.history_id is None
    assert st.failed_ids == {} and st.dead_letter == []


async def test_shell_conversation_is_reused_not_duplicated():
    """F5: a conversation whose first message create failed is an empty shell;
    the retry must fill the SAME conversation (the five hand-deleted crm-test
    shells came from duplicating here)."""
    espo, store = FailingEspo(), MemoryCommsStore()
    sc = scope()
    parsed = sync.parse_message(raw_message())
    try:
        await ingest_message(espo, store, sc, parsed)
    except Exception:
        pass  # the message create failed; the shell + thread map remain
    shells = [rid for (ent, rid) in espo.records if ent == crm.CONVERSATION]
    assert len(shells) == 1

    espo.fail_comm_create = False
    conv = await ingest_message(espo, store, sc, parsed)
    assert conv == shells[0]  # reused, not duplicated
    convs = [rid for (ent, rid) in espo.records if ent == crm.CONVERSATION]
    assert len(convs) == 1


async def test_alerts_fire_on_persistent_failure_and_dead_letter():
    from comms.sync import _alert_on_persistent_failures

    sent = []

    async def collect(settings, text):
        sent.append(text)

    store = MemoryCommsStore()
    sc = await _seed_done(store)
    # count == 2 => "keeps failing" alert
    await store.save_sync_state(
        sc.mailbox, history_id="100", initial_done=True,
        known_addresses=sc.all_addresses, failed_ids={"m1": 2},
    )
    await _alert_on_persistent_failures(Cfg(), store, sc.mailbox, {"failed": 1}, collect)
    assert len(sent) == 1 and "keep failing" in sent[0]

    # dead-letter => its own alert
    await _alert_on_persistent_failures(
        Cfg(), store, sc.mailbox, {"failed": 1, "deadLettered": 2}, collect
    )
    assert len(sent) == 2 and "DEAD-LETTERED" in sent[1]

    # count == 1 (first failure) => no alert yet
    sent.clear()
    await store.save_sync_state(
        sc.mailbox, history_id="100", initial_done=True,
        known_addresses=sc.all_addresses, failed_ids={"m1": 1},
    )
    await _alert_on_persistent_failures(Cfg(), store, sc.mailbox, {"failed": 1}, collect)
    assert sent == []
