"""Tests for the Account -> Contact -> CClientProfile -> CEngagement orchestration."""

from __future__ import annotations

import pytest

from forms.client_intake.orchestrator import (
    ACCOUNT,
    CLIENT_PROFILE,
    CONTACT,
    ENGAGEMENT,
    submit_intake,
)
from forms.client_intake.schemas import IntakeSubmission


class CapturingClient:
    """Fake EspoApi that records create calls and returns sequential ids."""

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
        # Matched records report only an id, so every other field reads as empty
        # (null) -> the orchestrator's null-fill path updates them.
        if entity == CONTACT and self._existing_contact:
            return {"id": self._existing_contact}
        if entity == ACCOUNT and self._existing_account:
            return {"id": self._existing_account}
        return None

    async def relate(self, entity, record_id, link, related_id):
        self.relates.append((entity, record_id, link, related_id))


def _submission(**overrides) -> IntakeSubmission:
    base = dict(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        confirm_email="ada@example.com",
        phone="216-555-0100",
        zip_code="44121",
        how_did_you_hear="Search Engine",
        mentoring_focus_areas=["Manufacturing", "Retail"],
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


async def test_drifted_enums_dropped_but_records_created():
    """Drifted business-stage / industry / focus-area values are dropped (not
    fatal); the four records are still created and the drops noted on the
    engagement, so the request + contact info are always captured."""
    client = CapturingClient(enum_options={
        (ACCOUNT, "cBusinessStage"): ["Startup", "Growth"],
        (ACCOUNT, "cIndustrySector"): ["Technology & Software"],
        (ENGAGEMENT, "mentoringFocusAreas"): ["Manufacturing", "Marketing & Branding"],
    })
    sub = _submission(
        business_stage="Startup",                       # valid -> kept
        industry_sector="Manufacturing",                # not in enum -> dropped
        mentoring_focus_areas=["Manufacturing", "Retail"],  # Retail dropped
    )
    ids = await submit_intake(sub, client)
    assert set(ids) == {"accountId", "contactId", "clientProfileId", "engagementId"}

    _, account_payload = client.creates[0]
    assert account_payload["cBusinessStage"] == "Startup"
    assert "cIndustrySector" not in account_payload      # dropped
    assert account_payload["cAccountType"] == ["Client"]  # discriminator untouched

    _, eng_payload = client.creates[3]
    assert eng_payload["mentoringFocusAreas"] == ["Manufacturing"]  # Retail filtered
    # The aggregated note (Account + Engagement drops) lands on the engagement.
    assert "cIndustrySector" in eng_payload["description"]
    assert "Manufacturing" in eng_payload["description"]  # the dropped industry value
    assert "Retail" in eng_payload["description"]


async def test_creates_four_linked_records():
    client = CapturingClient()
    ids = await submit_intake(_submission(), client)

    assert set(ids) == {"accountId", "contactId", "clientProfileId", "engagementId"}
    entities = [e for e, _ in client.creates]
    assert entities == [ACCOUNT, CONTACT, CLIENT_PROFILE, ENGAGEMENT]

    _, account_payload = client.creates[0]
    assert account_payload["cAccountType"] == ["Client"]   # required discriminator
    assert account_payload["cCompanyType"] == ["Client"]   # legacy, kept in sync

    _, contact_payload = client.creates[1]
    assert contact_payload["accountId"] == ids["accountId"]
    assert contact_payload["cContactType"] == ["Client"]

    _, profile_payload = client.creates[2]
    assert profile_payload["linkedCompanyId"] == ids["accountId"]
    assert profile_payload["clientcontactId"] == ids["contactId"]

    _, eng_payload = client.creates[3]
    assert eng_payload["engagementClientId"] == ids["clientProfileId"]
    assert eng_payload["primaryEngagementContactId"] == ids["contactId"]
    assert eng_payload["engagementStatus"] == "Submitted"

    # The applicant is also added to the Engagement Contacts (hasMany) link.
    assert (ENGAGEMENT, ids["engagementId"], "engagementContacts", ids["contactId"]) in (
        client.relates
    )
    # Fields not deployed on the instance must not be sent.
    assert "termsAccepted" not in eng_payload
    assert "meetingPreference" not in eng_payload


async def test_new_contact_and_client_profile_fields_written():
    """Pass A mappings: how-heard / marketing / terms land on the Contact, and
    year-formed (as a date) + employee count land on the CClientProfile."""
    client = CapturingClient()
    await submit_intake(
        _submission(how_did_you_hear="Online Search", year_formed=2024,
                    number_of_employees=3, marketing_consent=True, terms_accepted=True),
        client,
    )
    _, contact_payload = client.creates[1]
    assert contact_payload["cHowDidYouHear"] == "Online Search"
    assert contact_payload["cMarketingOptIn"] is True
    # The single consent checkbox sets all three Contact bools.
    assert contact_payload["cTermsOfUseAccepted"] is True
    assert contact_payload["cPrivacyPolicyAccepted"] is True
    assert contact_payload["cCodeOfConductAccepted"] is True

    _, profile_payload = client.creates[2]
    assert profile_payload["numberOfEmployees"] == 3
    assert profile_payload["formationDate"] == "2024-01-01"  # year -> Jan 1


async def test_repeat_contact_backfills_only_null_fields():
    """A matched Contact is reused (not re-created) and the null-fill update
    carries the new fields without a second Contact create."""
    client = CapturingClient(existing_contact="c-existing")
    await submit_intake(_submission(how_did_you_hear="Online Search"), client)
    # No Contact create — it was matched.
    assert CONTACT not in [e for e, _ in client.creates]
    # The fill-nulls update targets the matched Contact with the new fields.
    contact_updates = [u for u in client.updates if u[0] == CONTACT]
    assert contact_updates and contact_updates[0][1] == "c-existing"
    assert "cHowDidYouHear" in contact_updates[0][2]


async def test_matched_contact_is_reused_not_created():
    client = CapturingClient(existing_contact="existing-123")
    ids = await submit_intake(_submission(), client)

    assert ids["contactId"] == "existing-123"
    entities = [e for e, _ in client.creates]
    assert CONTACT not in entities  # contact reused, not created
    assert entities == [ACCOUNT, CLIENT_PROFILE, ENGAGEMENT]


async def test_matched_account_is_reused_not_created():
    client = CapturingClient(existing_account="acct-existing")
    ids = await submit_intake(_submission(), client)

    assert ids["accountId"] == "acct-existing"
    entities = [e for e, _ in client.creates]
    assert ACCOUNT not in entities  # account reused, not created
    assert entities == [CONTACT, CLIENT_PROFILE, ENGAGEMENT]

    _, contact_payload = client.creates[0]
    assert contact_payload["accountId"] == "acct-existing"
    _, profile_payload = client.creates[1]
    assert profile_payload["linkedCompanyId"] == "acct-existing"


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


@pytest.mark.parametrize(
    "entered,stored",
    [
        ("example.com", "https://example.com"),
        ("www.example.com", "https://www.example.com"),
        ("  example.com  ", "https://example.com"),
        ("http://example.com", "http://example.com"),
        ("https://example.com", "https://example.com"),
        ("sub.example.co.uk/path", "https://sub.example.co.uk/path"),
        ("", None),
        # Non-URL junk is dropped, not sent to EspoCRM's url field (would 400).
        ("n/a", None),
        ("none", None),
        ("N/A", None),
        ("acme .com", None),
        ("just some text", None),
        ("https://nodot", None),
    ],
)
def test_website_normalized_or_dropped(entered, stored):
    assert _submission(business_website=entered).business_website == stored
