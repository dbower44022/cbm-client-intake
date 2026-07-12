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
