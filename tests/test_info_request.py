"""Tests for the info request -> Contact (Prospect) + optional Account."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.espo import EspoError
from forms.info_request.orchestrator import (
    ACCOUNT,
    CONTACT,
    INFO_REQUEST,
    PROSPECT,
    submit_request,
)
from forms.info_request.schemas import InfoRequest


class CapturingClient:
    def __init__(self, existing_contact=None, existing_description=None, fail_entities=()):
        self.creates: list[tuple[str, dict]] = []
        self.updates: list[tuple[str, str, dict]] = []
        self._existing_contact = existing_contact
        self._existing_description = existing_description
        self._fail = set(fail_entities)
        self._n = 0

    async def create(self, entity, payload):
        self._n += 1
        self.creates.append((entity, payload))
        if entity in self._fail:
            raise EspoError(f"simulated failure creating {entity}")
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

    assert [e for e, _ in client.creates] == [CONTACT, INFO_REQUEST]
    _, payload = client.creates[0]
    assert payload["cContactType"] == [PROSPECT]
    assert "accountId" not in payload
    assert "I'd like to learn more" in payload["description"]
    assert payload["description"].startswith("[Information request via website")
    assert ids.keys() == {"contactId", "informationRequestId"}


@pytest.mark.asyncio
async def test_new_contact_with_company_creates_prospect_account():
    client = CapturingClient()
    ids = await submit_request(
        _request(company="Ada's Bakery", phone="216-555-0100"), client
    )

    assert [e for e, _ in client.creates] == [ACCOUNT, CONTACT, INFO_REQUEST]
    _, account = client.creates[0]
    assert account["name"] == "Ada's Bakery"
    assert account["cAccountType"] == ["Client"]
    assert account["cClientStatus"] == PROSPECT
    _, contact = client.creates[1]
    assert contact["accountId"] == ids["accountId"]
    assert contact["phoneNumber"] == "+12165550100"
    # The Information Request links to the Contact and the Account
    # (via infoRequestCompany, not the standard `account` link).
    _, info = client.creates[2]
    assert info["contactId"] == ids["contactId"]
    assert info["infoRequestCompanyId"] == ids["accountId"]
    assert info["company"] == "Ada's Bakery"
    assert info["phone"] == "+12165550100"


@pytest.mark.asyncio
async def test_existing_contact_appends_description():
    client = CapturingClient(
        existing_contact="contact-99", existing_description="Staff note: VIP."
    )
    ids = await submit_request(_request(company="Ada's Bakery"), client)

    # No new Contact and no Account — but an Information Request IS created.
    assert [e for e, _ in client.creates] == [INFO_REQUEST]
    [(entity, record_id, payload)] = client.updates
    assert (entity, record_id) == (CONTACT, "contact-99")
    assert payload["description"].startswith("Staff note: VIP.\n\n[Information request")
    assert "Company: Ada's Bakery" in payload["description"]
    assert "cContactType" not in payload  # existing contact's type left untouched
    assert ids == {"contactId": "contact-99", "informationRequestId": f"{INFO_REQUEST}-1"}
    # The request record links to the existing contact (account left untouched).
    _, info = client.creates[0]
    assert info["contactId"] == "contact-99"
    assert "infoRequestCompanyId" not in info


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


@pytest.mark.asyncio
async def test_information_request_fields():
    client = CapturingClient()
    await submit_request(_request(how_did_you_hear="Online search"), client)

    info_creates = [p for e, p in client.creates if e == INFO_REQUEST]
    assert len(info_creates) == 1
    info = info_creates[0]
    assert info["firstName"] == "Ada"
    assert info["lastName"] == "Lovelace"
    assert info["email"] == "ada@example.com"
    assert info["message"].startswith("I'd like to learn more")
    assert info["requestStatus"] == "New"
    assert info["source"] == "Online search"
    assert info["name"].startswith("Ada Lovelace — ")
    assert info["contactId"]  # linked to the produced Contact
    # Mirror-the-submission fields:
    assert info["form"] == "info-request"
    assert info["submitterEmail"] == "ada@example.com"
    assert "submission payload" in info["description"]
    assert '"message"' in info["description"]  # raw JSON included
    assert '"company_url": ""' in info["description"]  # honeypot cleared


@pytest.mark.asyncio
async def test_information_request_failure_does_not_break_submission():
    # The CInformationRequest entity may not exist / be granted yet — best-effort.
    client = CapturingClient(fail_entities={INFO_REQUEST})
    ids = await submit_request(_request(), client)

    # Contact still created; no informationRequestId, but the submission succeeds.
    assert ids.keys() == {"contactId"}
    assert "informationRequestId" not in ids


def test_message_is_required():
    with pytest.raises(ValidationError):
        _request(message="")


@pytest.mark.asyncio
async def test_description_append_not_repeated_on_resumable_retry():
    """pipeline-M1 (reliability review 2026-07-17): the description APPEND
    accumulates, so a delivery retry (worker or /ops redrive) must not re-run
    it — a partial failure after the append used to duplicate the block in
    staff-visible data. The named progress step guards it."""
    from core.resumable import ResumableClient

    saved: dict = {}

    async def save(progress):
        saved.clear()
        saved.update(progress)

    inner = CapturingClient(
        existing_contact="contact-99", existing_description="Staff note.",
    )
    # First delivery completes; the append step lands in the saved progress.
    await submit_request(_request(), ResumableClient(inner, None, save))
    assert len(inner.updates) == 1
    assert any(k.startswith("step:append-description:") for k in saved)

    # Re-delivery of the SAME row (a worker killed between delivering and
    # mark_completed is reclaimed after the lease; /ops redrive replays too):
    # the append is skipped, and the recorded create is not repeated either.
    await submit_request(_request(), ResumableClient(inner, dict(saved), save))
    assert len(inner.updates) == 1  # STILL one append — never duplicated
    assert len([e for e, _ in inner.creates if e == INFO_REQUEST]) == 1


@pytest.mark.asyncio
async def test_plain_client_append_runs_unguarded():
    """V1 storeless mode has no retries — the append just runs."""
    client = CapturingClient(existing_contact="c1", existing_description=None)
    await submit_request(_request(), client)
    assert len(client.updates) == 1
