"""Tests for the sponsor application -> Account + Contact + CSponsorProfile."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from forms.sponsor.orchestrator import (
    ACCOUNT,
    CONTACT,
    SPONSOR_CONTACTS,
    SPONSOR_PROFILE,
    submit_sponsor,
)
from forms.sponsor.schemas import SponsorApplication


class CapturingClient:
    """Fake EspoApi that records calls and returns sequential ids."""

    def __init__(self, existing_contact=None, existing_account=None, enum_options=None, team_id=None):
        self.creates: list[tuple[str, dict]] = []
        self.updates: list[tuple[str, str, dict]] = []
        self.relates: list[tuple[str, str, str, str]] = []
        self._existing_contact = existing_contact
        self._existing_account = existing_account
        self._team_id = team_id  # id returned for a Team name lookup; None => not readable
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
        if entity == "Team" and self._team_id:
            return {"id": self._team_id}
        return None

    async def relate(self, entity, record_id, link, related_id):
        self.relates.append((entity, record_id, link, related_id))


def _application(**overrides) -> SponsorApplication:
    base = dict(
        company="Generous Corp",
        first_name="Sam",
        last_name="Sponsor",
        email="sam@generous.com",
        message="We'd love to sponsor a cohort this fall.",
        how_did_you_hear="CBM Email",
        terms_accepted=True,
        submission_token="tok-sponsor1",
    )
    base.update(overrides)
    return SponsorApplication(**base)


@pytest.mark.asyncio
async def test_creates_three_linked_records():
    client = CapturingClient()
    ids = await submit_sponsor(_application(), client)

    assert set(ids) == {"accountId", "contactId", "sponsorProfileId"}
    assert [e for e, _ in client.creates] == [ACCOUNT, CONTACT, SPONSOR_PROFILE]

    _, account = client.creates[0]
    assert account["name"] == "Generous Corp"
    assert account["cAccountType"] == ["Donor/Sponsor"]

    _, contact = client.creates[1]
    assert contact["cContactType"] == ["Sponsor"]
    assert contact["accountId"] == ids["accountId"]
    assert contact["cHowDidYouHear"] == "CBM Email"  # Pass A
    # Single consent checkbox -> all three Contact bools.
    assert contact["cTermsOfUseAccepted"] is True
    assert contact["cPrivacyPolicyAccepted"] is True
    assert contact["cCodeOfConductAccepted"] is True

    _, profile = client.creates[2]
    assert profile["sponsorCompanyId"] == ids["accountId"]
    assert profile["sponsorContactId"] == ids["contactId"]
    assert profile["description"] == "We'd love to sponsor a cohort this fall."

    assert client.relates == [
        (SPONSOR_PROFILE, ids["sponsorProfileId"], SPONSOR_CONTACTS, ids["contactId"])
    ]


@pytest.mark.asyncio
async def test_phone_normalized_and_website_prefixed():
    client = CapturingClient()
    await submit_sponsor(
        _application(phone="(216) 555-0199", business_website="generous.com"),
        client,
    )
    _, account = client.creates[0]
    assert account["website"] == "https://generous.com"
    _, contact = client.creates[1]
    assert contact["phoneNumber"] == "+12165550199"


@pytest.mark.asyncio
async def test_existing_account_and_contact_reused():
    client = CapturingClient(existing_contact="contact-50", existing_account="account-3")
    ids = await submit_sponsor(_application(), client)

    assert [e for e, _ in client.creates] == [SPONSOR_PROFILE]
    assert ids["accountId"] == "account-3"
    assert ids["contactId"] == "contact-50"
    _, profile = client.creates[0]
    assert profile["sponsorCompanyId"] == "account-3"
    assert profile["sponsorContactId"] == "contact-50"


@pytest.mark.asyncio
async def test_sponsor_profile_stamped_with_sponsor_team():
    """A new CSponsorProfile carries the sponsor team (Doug's ruling 2026-07-20,
    the partner-form pattern) so team-scoped roles can see every funder in
    /sponsorsessions."""
    client = CapturingClient(team_id="team-sm")
    await submit_sponsor(_application(), client)
    _, profile = client.creates[2]
    assert profile["teamsIds"] == ["team-sm"]
    # Only the profile gets the team — Account/Contact are untouched.
    assert "teamsIds" not in client.creates[0][1]
    assert "teamsIds" not in client.creates[1][1]


@pytest.mark.asyncio
async def test_team_unresolvable_never_blocks_the_sponsor():
    """The intake API role may lack Team read (lookup returns None) — the
    profile is still created, just without the team stamp (logged WARNING)."""
    client = CapturingClient()  # find_one(Team) -> None
    ids = await submit_sponsor(_application(), client)
    assert set(ids) == {"accountId", "contactId", "sponsorProfileId"}
    _, profile = client.creates[2]
    assert "teamsIds" not in profile


@pytest.mark.asyncio
async def test_team_lookup_failure_never_blocks_the_sponsor():
    from core.espo import EspoError

    class Failing(CapturingClient):
        async def find_one(self, entity, attribute, value, select="id"):
            if entity == "Team":
                raise EspoError("HTTP 403: forbidden")
            return await super().find_one(entity, attribute, value, select)

    client = Failing()
    ids = await submit_sponsor(_application(), client)
    assert set(ids) == {"accountId", "contactId", "sponsorProfileId"}
    _, profile = client.creates[2]
    assert "teamsIds" not in profile


def test_message_is_required():
    with pytest.raises(ValidationError):
        _application(message="")


def test_company_is_required():
    with pytest.raises(ValidationError):
        _application(company="")


def test_consent_required():
    with pytest.raises(ValidationError):
        _application(terms_accepted=False)


def test_schema_contract_covers_sponsor_contact_type():
    """P2 (reliability review 2026-07-17): the drift check must pre-warn if the
    CRM ever loses the "Sponsor" option this orchestrator writes."""
    from core.schema_contract import EXPECTED_ENUMS

    assert "Sponsor" in EXPECTED_ENUMS[("Contact", "cContactType")]
