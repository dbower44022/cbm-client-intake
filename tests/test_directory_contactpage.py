"""View Contact page (directory): the record route, the contact-scoped
Communications endpoints (only-my-conversations filter, exclude/include/send
keyed to the Contact), and the comms-layer Contact parameterization."""

from __future__ import annotations

from fastapi.testclient import TestClient

import pytest

# comms.service first: importing comms.crm directly first trips the documented
# latent circular import (see CHANGELOG 0.127.0 — full-suite collection is fine).
from comms import service as comms_service
from comms import crm as comms_crm
from comms.store import ACTION_EXCLUDE, ACTION_INCLUDE, MemoryCommsStore
from core.app import create_app
from core.config import get_settings
from directory import service as dir_service
from directory.config import MENTORS
from forms import info_request
from tests.test_comms_send import FakeGmailSend
from tests.test_comms_sync import FakeEspo
from tests.test_directory import FakeClient

_USER = {
    "userId": "u1",
    "userName": "bob.mentor",
    "name": "Bob Mentor",
    "isAdmin": False,
    "teams": ["Mentor Team"],
    "roles": [],
    "token": "t",
}

MAILBOX = "bob.mentor@cbmentors.org"


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _app(monkeypatch, gmail_sync: bool = True):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("GMAIL_SYNC", "true" if gmail_sync else "false")
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


def _as(monkeypatch, user=_USER):
    monkeypatch.setattr("directory.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("directory.router.client_for", lambda settings, user: object())
    monkeypatch.setattr("directory.comms_router.client_for", lambda settings, user: object())


def _mailbox(monkeypatch, value=MAILBOX):
    async def fake_resolve(client, user_id):
        return value

    monkeypatch.setattr("sessions.service.resolve_user_mailbox", fake_resolve)


# --- participants_contain (the only-mine filter primitive) --------------------

def test_participants_contain_matches_named_and_bare_entries():
    s = "Jane Client <jane@acme.test>, bob.mentor@cbmentors.org"
    assert comms_crm.participants_contain(s, "jane@acme.test")
    assert comms_crm.participants_contain(s, "BOB.MENTOR@CBMENTORS.ORG")
    assert not comms_crm.participants_contain(s, "carol@cbmentors.org")


def test_participants_contain_legacy_name_only_never_matches():
    # Pre-v0.55.0 senders-only entries have no address to match.
    assert not comms_crm.participants_contain("Jane Client", "jane@acme.test")
    assert not comms_crm.participants_contain("", "jane@acme.test")
    assert not comms_crm.participants_contain("Jane <jane@acme.test>", "")


# --- comms layer: Contact refs ------------------------------------------------

async def test_contact_ref_builds_allowlist_from_the_contact():
    espo = FakeEspo()
    espo.records[("Contact", "c1")] = {
        "name": "Jane Client", "emailAddress": "jane@acme.test",
        "emailAddressData": [
            {"emailAddress": "jane@acme.test"},
            {"emailAddress": "jane.alt@acme.test"},
        ],
    }
    ref = await comms_service.contact_ref(espo, "c1")
    assert ref.entity == "Contact" and ref.id == "c1"
    assert ref.contact_ids == {"c1"}
    assert "jane@acme.test" in ref.addresses
    assert ref.contact_by_address["jane@acme.test"] == "c1"


async def test_link_records_contact_ref_relates_only_the_contacts_link():
    espo = FakeEspo()
    ref = comms_crm.RecordRef(entity="Contact", id="c1", name="Jane")
    ref.contact_ids = {"c1"}
    await comms_crm.link_records(espo, "conv1", [ref], excludes=set())
    assert espo.relates == [("CConversation", "conv1", "contacts", "c1")]


async def test_link_records_honors_contact_level_excludes():
    # A contact-page "Remove" must hold even when the sync re-matches the
    # contact through an engagement scope.
    espo = FakeEspo()
    eng = comms_crm.RecordRef(entity="CEngagement", id="E1", name="Eng")
    eng.contact_ids = {"c1", "c2"}
    await comms_crm.link_records(
        espo, "conv1", [eng], excludes={("Contact", "c1", "conv1")}
    )
    links = [r for r in espo.relates if r[2] == "contacts"]
    assert ("CConversation", "conv1", "contacts", "c2") in links
    assert all(r[3] != "c1" for r in links)
    # The engagement link itself still lands.
    assert ("CConversation", "conv1", "engagements", "E1") in espo.relates


async def test_exclude_conversation_contact_scope_unrelates_contacts_link():
    class U:
        def __init__(self):
            self.unrelated = []

        async def unrelate(self, entity, record_id, link, related_id):
            self.unrelated.append((entity, record_id, link, related_id))

    user_client = U()
    store = MemoryCommsStore()
    await comms_service.exclude_conversation(
        user_client, store, "Contact", "c1", "conv1", "bob.mentor"
    )
    assert user_client.unrelated == [("CConversation", "conv1", "contacts", "c1")]
    overrides = await store.overrides_for_parent("Contact", "c1")
    assert overrides.get("conv1") == ACTION_EXCLUDE


async def test_send_with_contact_ref_links_contact_and_no_parent():
    espo = FakeEspo()
    espo.records[("Contact", "c1")] = {
        "name": "Jane Client", "emailAddress": "jane@acme.test",
    }
    store = MemoryCommsStore()
    ref = await comms_service.contact_ref(espo, "c1")
    result = await comms_service.send_message(
        settings=None, api_client=espo, store=store,
        gmail=FakeGmailSend(), user=USER_SEND, ref=ref,
        to=["outsider@else.test"], subject="One-off", body_html="hello",
        allow_unknown_recipients=True,
    )
    conv_id = result["conversationId"]
    assert conv_id
    # The include override keys off the CONTACT, not a parent record.
    overrides = await store.overrides_for_parent("Contact", "c1")
    assert overrides.get(conv_id) == ACTION_INCLUDE
    # The conversation relates to the contact and to NO parent link.
    contact_links = [r for r in espo.relates if r[2] == "contacts"]
    assert ("CConversation", conv_id, "contacts", "c1") in contact_links
    parent_links = set(comms_crm.PARENT_LINKS.values())
    assert all(r[2] not in parent_links for r in espo.relates)


async def test_send_with_contact_ref_known_recipient_needs_no_confirm():
    espo = FakeEspo()
    espo.records[("Contact", "c1")] = {
        "name": "Jane Client", "emailAddress": "jane@acme.test",
    }
    ref = await comms_service.contact_ref(espo, "c1")
    result = await comms_service.send_message(
        settings=None, api_client=espo, store=MemoryCommsStore(),
        gmail=FakeGmailSend(), user=USER_SEND, ref=ref,
        to=["jane@acme.test"], subject="x", body_html="hello",
    )
    assert result["gmailMessageId"] == "gsent1"


USER_SEND = {"userId": "u1", "userName": "bob.mentor", "name": "Bob Mentor"}


# --- directory service: mentors rows carry contactId --------------------------

@pytest.mark.asyncio
async def test_mentor_rows_carry_contact_id():
    client = FakeClient(
        layouts={("CMentorProfile", "list"): [{"name": "name", "link": True}]},
        i18n={"CMentorProfile": {"fields": {}}},
        fields={"CMentorProfile": {"name": {"type": "varchar"}}},
        records={"CMentorProfile": [
            {"id": "m1", "name": "Pat Mentor", "contactRecordId": "c7"},
            {"id": "m2", "name": "Lee Mentor"},
        ]},
    )
    page = await dir_service.list_records(client, MENTORS)
    rows = {r["id"]: r for r in page["rows"]}
    assert rows["m1"]["contactId"] == "c7"
    assert rows["m2"]["contactId"] is None


# --- the record-page route ----------------------------------------------------

def test_contact_record_page_served_with_base_and_no_store(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/directory/contacts/record/c123")
    assert r.status_code == 200
    assert '<base href="/directory/contacts/">' in r.text
    assert r.headers["cache-control"] == "no-store"
    assert "record.js" in r.text


def test_only_the_contact_page_kind_gets_the_record_route(monkeypatch):
    app = _app(monkeypatch)
    paths = {r.path for r in app.routes if isinstance(getattr(r, "path", None), str)}
    assert "/directory/contacts/record/{record_id}" in paths
    assert "/directory/mentors/record/{record_id}" not in paths
    # The contact-scoped comms endpoints register only on the contacts kind.
    assert "/directory/contacts/api/records/{contact_id}/conversations" in paths
    assert "/directory/mentors/api/records/{contact_id}/conversations" not in paths


def test_session_reports_contact_page_and_comms_flags(monkeypatch):
    _as(monkeypatch)

    async def fake_filters(client, cfg):
        return []

    monkeypatch.setattr("directory.service.filters", fake_filters)
    with TestClient(_app(monkeypatch, gmail_sync=False)) as c:
        r = c.get("/directory/contacts/api/session")
        assert r.status_code == 200
        assert r.json()["contactPage"] is True
        assert r.json()["commsEnabled"] is False
        r2 = c.get("/directory/mentors/api/session")
        assert r2.json()["contactPage"] is False


# --- contact-scoped comms endpoints -------------------------------------------

def test_conversations_disabled_503(monkeypatch):
    _as(monkeypatch)
    with TestClient(_app(monkeypatch, gmail_sync=False)) as c:
        r = c.get("/directory/contacts/api/records/c1/conversations")
    assert r.status_code == 503


def test_conversations_filtered_to_my_mailbox(monkeypatch):
    _as(monkeypatch)
    _mailbox(monkeypatch)
    monkeypatch.setattr(comms_service, "get_store", lambda settings: object())

    async def fake_list(client, contact_id):
        assert contact_id == "c1"
        return [
            {"id": "mine", "participants": "Jane <jane@acme.test>, Bob Mentor <bob.mentor@cbmentors.org>"},
            {"id": "theirs", "participants": "Jane <jane@acme.test>, Carol <carol.mentor@cbmentors.org>"},
        ]

    async def fake_enrich(client, store, username, rows):
        for r in rows:
            r["unread"] = False

    monkeypatch.setattr(comms_service, "list_contact_conversations", fake_list)
    monkeypatch.setattr(comms_service, "enrich_conversation_rows", fake_enrich)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/directory/contacts/api/records/c1/conversations")
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()["conversations"]]
    assert ids == ["mine"]
    assert r.json()["mailbox"] == MAILBOX


def test_conversations_without_mailbox_returns_notice(monkeypatch):
    _as(monkeypatch)
    _mailbox(monkeypatch, value=None)
    monkeypatch.setattr(comms_service, "get_store", lambda settings: object())
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/directory/contacts/api/records/c1/conversations")
    assert r.status_code == 200
    assert r.json()["conversations"] == []
    assert "mailbox" in r.json()["notice"].lower()


def test_thread_open_requires_participation(monkeypatch):
    _as(monkeypatch)
    _mailbox(monkeypatch)

    class Store:
        async def mark_seen(self, username, conversation_id):
            raise AssertionError("must not stamp a refused thread")

    monkeypatch.setattr(comms_service, "get_store", lambda settings: Store())

    class Client:
        async def get(self, entity, record_id, select=None):
            assert entity == "CConversation"
            return {"participants": "Jane <jane@acme.test>, Carol <carol@cbmentors.org>"}

    monkeypatch.setattr("directory.comms_router.client_for", lambda settings, user: Client())
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/directory/contacts/api/conversations/conv9")
    assert r.status_code == 404
    assert "yours" in r.json()["detail"]


def test_thread_open_stamps_seen_for_participant(monkeypatch):
    _as(monkeypatch)
    _mailbox(monkeypatch)
    seen = []

    class Store:
        async def mark_seen(self, username, conversation_id):
            seen.append((username, conversation_id))

    monkeypatch.setattr(comms_service, "get_store", lambda settings: Store())

    class Client:
        async def get(self, entity, record_id, select=None):
            return {"participants": "Bob Mentor <bob.mentor@cbmentors.org>"}

    monkeypatch.setattr("directory.comms_router.client_for", lambda settings, user: Client())

    async def fake_get_conversation(client, conversation_id, **kwargs):
        return {"id": conversation_id, "subject": "Hi", "messages": []}

    monkeypatch.setattr(comms_service, "get_conversation", fake_get_conversation)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/directory/contacts/api/conversations/conv1")
    assert r.status_code == 200
    assert seen == [("bob.mentor", "conv1")]


def test_exclude_endpoint_uses_contact_scope(monkeypatch):
    _as(monkeypatch)
    calls = []

    async def fake_exclude(user_client, store, parent_entity, parent_id,
                           conversation_id, username):
        calls.append((parent_entity, parent_id, conversation_id, username))

    monkeypatch.setattr(comms_service, "get_store", lambda settings: object())
    monkeypatch.setattr(comms_service, "exclude_conversation", fake_exclude)
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/directory/contacts/api/records/c1/conversations/conv1/exclude")
    assert r.status_code == 200
    assert calls == [("Contact", "c1", "conv1", "bob.mentor")]


def test_include_endpoint_passes_contact_ref(monkeypatch):
    _as(monkeypatch)
    monkeypatch.setattr(comms_service, "get_store", lambda settings: object())

    async def fake_contact_ref(client, contact_id):
        return comms_crm.RecordRef(entity="Contact", id=contact_id, name="Jane")

    async def fake_gmail(settings, client, user):
        return object()

    captured = {}

    async def fake_include(**kwargs):
        captured.update(kwargs)
        return "conv5"

    monkeypatch.setattr(comms_service, "contact_ref", fake_contact_ref)
    monkeypatch.setattr(comms_service, "gmail_for_user", fake_gmail)
    monkeypatch.setattr(comms_service, "include_thread", fake_include)
    with TestClient(_app(monkeypatch)) as c:
        r = c.post(
            "/directory/contacts/api/records/c1/conversations/include",
            json={"gmailThreadId": "t1"},
        )
    assert r.status_code == 200
    assert r.json()["conversationId"] == "conv5"
    assert captured["ref"].entity == "Contact" and captured["ref"].id == "c1"


def test_send_endpoint_passes_contact_ref_and_rejects_doc_chips(monkeypatch):
    _as(monkeypatch)
    monkeypatch.setattr(comms_service, "get_store", lambda settings: object())

    async def fake_contact_ref(client, contact_id):
        return comms_crm.RecordRef(entity="Contact", id=contact_id, name="Jane")

    async def fake_gmail(settings, client, user):
        return object()

    captured = {}

    async def fake_send(**kwargs):
        captured.update(kwargs)
        return {"gmailMessageId": "g1", "conversationId": "conv1",
                "writeBack": {"ok": True, "emailId": "e1"}, "ingestWarning": ""}

    monkeypatch.setattr(comms_service, "contact_ref", fake_contact_ref)
    monkeypatch.setattr(comms_service, "gmail_for_user", fake_gmail)
    monkeypatch.setattr(comms_service, "send_message", fake_send)
    with TestClient(_app(monkeypatch)) as c:
        # Document chips are a record-page feature — refused here readably.
        r = c.post(
            "/directory/contacts/api/records/c1/messages",
            json={"to": ["jane@acme.test"], "subject": "x", "body": "y",
                  "attachments": [{"documentId": "d1"}]},
        )
        assert r.status_code == 400
        assert "record" in r.json()["detail"].lower()
        # A clean send routes through the contact ref.
        r2 = c.post(
            "/directory/contacts/api/records/c1/messages",
            json={"to": ["jane@acme.test"], "subject": "x", "body": "y"},
        )
    assert r2.status_code == 200
    assert captured["ref"].entity == "Contact" and captured["ref"].id == "c1"
    assert "cfg" not in captured or captured.get("cfg") is None
