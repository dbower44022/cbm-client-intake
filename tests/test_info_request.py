"""Tests for the info request -> Contact (Prospect) + optional Account."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from forms.info_request.orchestrator import ACCOUNT, CONTACT, PROSPECT, submit_request
from forms.info_request.schemas import InfoRequest


class CapturingClient:
    def __init__(self, existing_contact=None, existing_description=None):
        self.creates: list[tuple[str, dict]] = []
        self.updates: list[tuple[str, str, dict]] = []
        self._existing_contact = existing_contact
        self._existing_description = existing_description
        self._n = 0

    async def create(self, entity, payload):
        self._n += 1
        self.creates.append((entity, payload))
        return {"id": f"{entity}-{self._n}", **payload}

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        return {"id": record_id, **payload}

    async def find_one(self, entity, attribute, value, select="id"):
        if entity == CONTACT and self._existing_contact:
            return {
                "id": self._existing_contact,
                "description": self._existing_description,
            }
        return None


def _request(**overrides) -> InfoRequest:
    base = dict(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        message="I'd like to learn more about mentoring for my bakery.",
        submission_token="tok-inforeq1",
    )
    base.update(overrides)
    return InfoRequest(**base)


@pytest.mark.asyncio
async def test_new_contact_without_company_skips_account():
    client = CapturingClient()
    ids = await submit_request(_request(), client)

    assert [e for e, _ in client.creates] == [CONTACT]
    _, payload = client.creates[0]
    assert payload["cContactType"] == [PROSPECT]
    assert "accountId" not in payload
    assert "I'd like to learn more" in payload["description"]
    assert payload["description"].startswith("[Information request via website")
    assert ids.keys() == {"contactId"}


@pytest.mark.asyncio
async def test_new_contact_with_company_creates_prospect_account():
    client = CapturingClient()
    ids = await submit_request(
        _request(company="Ada's Bakery", phone="216-555-0100"), client
    )

    assert [e for e, _ in client.creates] == [ACCOUNT, CONTACT]
    _, account = client.creates[0]
    assert account["name"] == "Ada's Bakery"
    assert account["cAccountType"] == ["Client"]
    assert account["cClientStatus"] == PROSPECT
    _, contact = client.creates[1]
    assert contact["accountId"] == ids["accountId"]
    assert contact["phoneNumber"] == "+12165550100"


@pytest.mark.asyncio
async def test_existing_contact_appends_description():
    client = CapturingClient(
        existing_contact="contact-99", existing_description="Staff note: VIP."
    )
    ids = await submit_request(_request(company="Ada's Bakery"), client)

    assert client.creates == []  # no new Contact, and no Account either
    [(entity, record_id, payload)] = client.updates
    assert (entity, record_id) == (CONTACT, "contact-99")
    assert payload["description"].startswith("Staff note: VIP.\n\n[Information request")
    assert "Company: Ada's Bakery" in payload["description"]
    assert "cContactType" not in payload  # existing contact's type left untouched
    assert ids == {"contactId": "contact-99"}


@pytest.mark.asyncio
async def test_existing_contact_with_empty_description():
    client = CapturingClient(existing_contact="contact-7", existing_description=None)
    await submit_request(_request(), client)

    [(_, _, payload)] = client.updates
    assert payload["description"].startswith("[Information request via website")


@pytest.mark.asyncio
async def test_how_did_you_hear_lands_in_description():
    client = CapturingClient()
    await submit_request(_request(how_did_you_hear="Online search"), client)

    _, payload = client.creates[0]
    assert "How they heard about CBM: Online search" in payload["description"]


def test_message_is_required():
    with pytest.raises(ValidationError):
        _request(message="")
