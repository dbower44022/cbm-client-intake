"""comms.service.send_message — recipient guard, durable include, write-through."""

from types import SimpleNamespace

import pytest

from comms import service as comms_service
from comms.store import ACTION_INCLUDE, MemoryCommsStore
from tests.test_comms_sync import FakeEspo, raw_message


class FakeGmailSend:
    mailbox = "bob.mentor@cbmentors.org"

    def __init__(self):
        self.sent = []

    async def send(self, mime, thread_id=None):
        self.sent.append((mime, thread_id))
        return {"id": "gsent1"}

    async def get_message(self, message_id):
        return raw_message(
            mid=message_id, frm=self.mailbox, to="outsider@else.test",
            subject="One-off", rfc_id="sent-rfc",
        )


CFG = SimpleNamespace(parent_entity="CEngagement", parent_contacts_link="engagementContacts")
USER = {"userId": "u1", "userName": "bob.mentor", "name": "Bob Mentor"}


def espo_with_contacts():
    return FakeEspo(lists={
        ("CEngagement", "E1", "engagementContacts"): [
            {"id": "c1", "name": "James", "emailAddress": "james@acme.test"},
        ],
    })


async def test_unknown_recipient_refused_without_confirm():
    with pytest.raises(comms_service.CommsError) as exc:
        await comms_service.send_message(
            settings=None, api_client=espo_with_contacts(), store=MemoryCommsStore(),
            gmail=FakeGmailSend(), cfg=CFG, parent_id="E1", user=USER,
            to=["outsider@else.test"], subject="x", body_html="hello",
        )
    assert "outsider@else.test" in str(exc.value)


async def test_internal_recipient_is_never_unknown():
    result = await comms_service.send_message(
        settings=None, api_client=espo_with_contacts(), store=MemoryCommsStore(),
        gmail=FakeGmailSend(), cfg=CFG, parent_id="E1", user=USER,
        to=["carol.mentor@cbmentors.org"], subject="x", body_html="hello",
    )
    assert result["gmailMessageId"] == "gsent1"


async def test_confirmed_unknown_send_writes_durable_include():
    store = MemoryCommsStore()
    result = await comms_service.send_message(
        settings=None, api_client=espo_with_contacts(), store=store,
        gmail=FakeGmailSend(), cfg=CFG, parent_id="E1", user=USER,
        to=["outsider@else.test"], subject="One-off", body_html="hello",
        allow_unknown_recipients=True,
    )
    conv_id = result["conversationId"]
    assert conv_id
    overrides = await store.overrides_for_parent("CEngagement", "E1")
    assert overrides.get(conv_id) == ACTION_INCLUDE


async def test_lookup_contact_by_email_found_and_cbm_flag():
    espo = FakeEspo()
    espo.records[("Contact", "c9")] = {
        "name": "Jane Chen", "emailAddress": "jane@chenco.test",
        "accountName": "Chen Co", "cContactType": ["Prospect"],
    }
    espo.records[("Contact", "c10")] = {
        "name": "Matt Mentor", "emailAddress": "matt.mentor@cbmentors.org",
        "cContactType": ["Mentor"],
    }
    res = await comms_service.lookup_contact_by_email(espo, "Jane@ChenCo.test")
    assert res["found"] and res["contact"]["name"] == "Jane Chen"
    assert res["contact"]["company"] == "Chen Co"
    assert res["contact"]["isCbmMember"] is False
    res2 = await comms_service.lookup_contact_by_email(espo, "matt.mentor@cbmentors.org")
    assert res2["contact"]["isCbmMember"] is True
    assert (await comms_service.lookup_contact_by_email(espo, "nobody@x.test"))["found"] is False


async def test_resolve_company_reuses_or_creates():
    user_client = FakeEspo()
    user_client.records[("Account", "a1")] = {"name": "Acme Inc"}
    api_client = FakeEspo()
    # existing (read as the user) => reused, nothing created via the API client
    got = await comms_service.resolve_company(user_client, api_client, "Acme Inc")
    assert got == "a1" and not api_client.records
    # new => created via the API client
    got2 = await comms_service.resolve_company(user_client, api_client, "Fresh LLC")
    assert ("Account", got2) in api_client.records
    assert (await comms_service.resolve_company(user_client, api_client, "")) is None


async def test_lookup_matches_mentor_profile_by_cbm_email():
    espo = FakeEspo()
    espo.records[("CMentorProfile", "p1")] = {
        "name": "Carol Mentor", "cbmEmail": "carol.mentor@cbmentors.org",
        "contactRecordId": "c77",
    }
    res = await comms_service.lookup_contact_by_email(espo, "Carol.Mentor@cbmentors.org")
    assert res["found"] is True
    c = res["contact"]
    assert c["isCbmMember"] is True and c["mentorProfileId"] == "p1" and c["id"] == "c77"


async def test_lookup_resolves_profile_via_contact_for_personal_address():
    # The "added as Other Contacts" bug: a member reached via the personal
    # address on their Mentor-typed Contact must still carry mentorProfileId.
    espo = FakeEspo()
    espo.records[("Contact", "c77")] = {
        "name": "Douglas Bower", "emailAddress": "doug@dougbower.com",
        "cContactType": ["Mentor"],
    }
    espo.records[("CMentorProfile", "p9")] = {
        "name": "Douglas Bower", "contactRecordId": "c77",
    }
    res = await comms_service.lookup_contact_by_email(espo, "doug@dougbower.com")
    assert res["contact"]["isCbmMember"] is True
    assert res["contact"]["mentorProfileId"] == "p9"
