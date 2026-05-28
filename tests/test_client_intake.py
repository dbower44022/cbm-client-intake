"""Tests for the Account -> Contact -> Engagement orchestration."""

from __future__ import annotations

import pytest

from forms.client_intake.orchestrator import ACCOUNT, CONTACT, ENGAGEMENT, submit_intake
from forms.client_intake.schemas import IntakeSubmission


class CapturingClient:
    """Fake EspoApi that records create calls and returns sequential ids."""

    def __init__(self, existing_contact=None):
        self.creates: list[tuple[str, dict]] = []
        self._existing_contact = existing_contact
        self._n = 0

    async def create(self, entity, payload):
        self._n += 1
        self.creates.append((entity, payload))
        return {"id": f"{entity}-{self._n}", **payload}

    async def find_one(self, entity, attribute, value):
        if entity == CONTACT and self._existing_contact:
            return {"id": self._existing_contact}
        return None


def _submission(**overrides) -> IntakeSubmission:
    base = dict(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        confirm_email="ada@example.com",
        phone="216-555-0100",
        zip_code="44121",
        how_did_you_hear="Search Engine",
        mentoring_focus_areas=["Marketing", "Retail"],
        mentoring_needs_description="Need help with go-to-market.",
        meeting_preference="Video",
        notification_preference="Email",
        business_stage="Startup",
        business_name="Difference Engine LLC",
        business_website="https://example.com",
        industry_sector="Manufacturing",
        industry_subsector="Machinery Manufacturing",
        year_formed=2024,
        number_of_employees=3,
        marketing_consent=True,
        terms_accepted=True,
        submission_token="tok-abcdefgh",
    )
    base.update(overrides)
    return IntakeSubmission(**base)


async def test_creates_three_linked_records():
    client = CapturingClient()
    ids = await submit_intake(_submission(), client)

    assert set(ids) == {"accountId", "contactId", "engagementId"}
    entities = [e for e, _ in client.creates]
    assert entities == [ACCOUNT, CONTACT, ENGAGEMENT]

    _, contact_payload = client.creates[1]
    assert contact_payload["accountId"] == ids["accountId"]

    _, eng_payload = client.creates[2]
    assert eng_payload["accountId"] == ids["accountId"]
    assert eng_payload["contactsIds"] == [ids["contactId"]]
    assert eng_payload["status"] == "Submitted"


async def test_matched_contact_is_reused_not_created():
    client = CapturingClient(existing_contact="existing-123")
    ids = await submit_intake(_submission(), client)

    assert ids["contactId"] == "existing-123"
    entities = [e for e, _ in client.creates]
    assert CONTACT not in entities  # contact reused, not created
    assert entities == [ACCOUNT, ENGAGEMENT]


async def test_pre_startup_creates_placeholder_account_without_profile():
    client = CapturingClient()
    sub = _submission(
        business_stage="Pre-Startup",
        business_name=None,
        business_website=None,
        industry_sector=None,
        industry_subsector=None,
        year_formed=None,
        number_of_employees=None,
    )
    await submit_intake(sub, client)

    _, account_payload = client.creates[0]
    assert "Pre-Startup" in account_payload["name"]
    assert "website" not in account_payload


async def test_email_mismatch_rejected():
    with pytest.raises(ValueError):
        _submission(confirm_email="typo@example.com")
