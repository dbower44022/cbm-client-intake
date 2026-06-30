"""Tests for the partner application -> Account + Contact + CPartnerProfile."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from forms.partner.orchestrator import (
    ACCOUNT,
    CONTACT,
    PARTNER_CONTACTS,
    PARTNER_PROFILE,
    submit_partner,
)
from forms.partner.schemas import PartnerApplication


class CapturingClient:
    """Fake EspoApi that records calls and returns sequential ids."""

    def __init__(self, existing_contact=None, existing_account=None, enum_options=None):
        self.creates: list[tuple[str, dict]] = []
        self.updates: list[tuple[str, str, dict]] = []
        self.relates: list[tuple[str, str, str, str]] = []
        self._existing_contact = existing_contact
        self._existing_account = existing_account
        # {(entity, field): [valid options]}; absent => None ("keep all").
        self._enum_options = enum_options or {}
        self._n = 0

    async def create(self, entity, payload):
        self._n += 1
        self.creates.append((entity, payload))
        return {"id": f"{entity}-{self._n}", **payload}

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        return {"id": record_id, **payload}

    async def metadata_enum_options(self, entity, field):
        return self._enum_options.get((entity, field))

    async def find_one(self, entity, attribute, value, select="id"):
        if entity == ACCOUNT and self._existing_account:
            return {"id": self._existing_account}
        if entity == CONTACT and self._existing_contact:
            return {"id": self._existing_contact}
        return None

    async def relate(self, entity, record_id, link, related_id):
        self.relates.append((entity, record_id, link, related_id))


def _application(**overrides) -> PartnerApplication:
    base = dict(
        company="Acme Partners LLC",
        first_name="Pat",
        last_name="Partner",
        email="pat@acmepartners.com",
        partnership_type="Referral Partner",
        partnership_value=["Co-Hosted Events", "Link on Website"],
        how_did_you_hear="Partner Referral",
        terms_accepted=True,
        submission_token="tok-partner1",
    )
    base.update(overrides)
    return PartnerApplication(**base)


@pytest.mark.asyncio
async def test_drifted_enums_dropped_but_records_created():
    """A drifted partnershipType/Value is dropped (not fatal); the records are
    still created and the drops noted on the profile description."""
    client = CapturingClient(enum_options={
        (PARTNER_PROFILE, "partnershipType"): ["Sponsor", "Vendor"],   # not Referral Partner
        (PARTNER_PROFILE, "partnershipValue"): ["Co-Hosted Events"],   # not Link on Website
    })
    sub = _application(
        partnership_type="Referral Partner",                # dropped
        partnership_value=["Co-Hosted Events", "Link on Website"],  # 2nd dropped
    )
    ids = await submit_partner(sub, client)
    assert set(ids) == {"accountId", "contactId", "partnerProfileId"}
    _, profile = client.creates[2]
    assert "partnershipType" not in profile                  # dropped
    assert profile["partnershipValue"] == ["Co-Hosted Events"]  # filtered
    assert profile["partnershipStatus"] == "Candidate"       # system value untouched
    assert "partnershipType" in profile["description"]
    assert "Referral Partner" in profile["description"]
    assert "Link on Website" in profile["description"]


@pytest.mark.asyncio
async def test_creates_three_linked_records():
    client = CapturingClient()
    ids = await submit_partner(_application(), client)

    assert set(ids) == {"accountId", "contactId", "partnerProfileId"}
    assert [e for e, _ in client.creates] == [ACCOUNT, CONTACT, PARTNER_PROFILE]

    _, account = client.creates[0]
    assert account["name"] == "Acme Partners LLC"
    assert account["cAccountType"] == ["Partner"]

    _, contact = client.creates[1]
    assert contact["cContactType"] == ["Partner"]
    assert contact["accountId"] == ids["accountId"]
    assert contact["cHowDidYouHear"] == "Partner Referral"  # Pass A
    # Single consent checkbox -> all three Contact bools.
    assert contact["cTermsOfUseAccepted"] is True
    assert contact["cPrivacyPolicyAccepted"] is True
    assert contact["cCodeOfConductAccepted"] is True

    _, profile = client.creates[2]
    assert profile["partnerCompanyId"] == ids["accountId"]
    assert profile["primaryPartnercontactId"] == ids["contactId"]
    assert profile["partnershipStatus"] == "Candidate"
    assert profile["partnershipType"] == "Referral Partner"
    assert profile["partnershipValue"] == ["Co-Hosted Events", "Link on Website"]

    # Applicant added to the profile's Contacts hasMany link.
    assert client.relates == [
        (PARTNER_PROFILE, ids["partnerProfileId"], PARTNER_CONTACTS, ids["contactId"])
    ]


@pytest.mark.asyncio
async def test_phone_normalized_and_website_prefixed():
    client = CapturingClient()
    await submit_partner(
        _application(phone="216-555-0100", business_website="acmepartners.com"),
        client,
    )
    _, account = client.creates[0]
    assert account["website"] == "https://acmepartners.com"
    _, contact = client.creates[1]
    assert contact["phoneNumber"] == "+12165550100"


@pytest.mark.asyncio
async def test_optional_partnership_fields_omitted_when_empty():
    client = CapturingClient()
    await submit_partner(
        _application(partnership_type=None, partnership_value=[]), client
    )
    _, profile = client.creates[2]
    assert "partnershipType" not in profile
    assert "partnershipValue" not in profile
    # phone/website omitted too
    _, account = client.creates[0]
    assert "website" not in account
    _, contact = client.creates[1]
    assert "phoneNumber" not in contact


@pytest.mark.asyncio
async def test_existing_account_and_contact_reused():
    client = CapturingClient(existing_contact="contact-99", existing_account="account-7")
    ids = await submit_partner(_application(), client)

    # Only the profile is created; Account + Contact are matched.
    assert [e for e, _ in client.creates] == [PARTNER_PROFILE]
    assert ids["accountId"] == "account-7"
    assert ids["contactId"] == "contact-99"
    _, profile = client.creates[0]
    assert profile["partnerCompanyId"] == "account-7"
    assert profile["primaryPartnercontactId"] == "contact-99"


def test_company_is_required():
    with pytest.raises(ValidationError):
        _application(company="")


def test_invalid_partnership_type_rejected():
    with pytest.raises(ValidationError):
        _application(partnership_type="Not A Real Type")


def test_consent_required():
    with pytest.raises(ValidationError):
        _application(terms_accepted=False)
