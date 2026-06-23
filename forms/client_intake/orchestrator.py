"""The four-record create-and-link sequence (Technical Design §3.3).

A submission yields, in dependency order:

  1. Account          — the client organization
  2. Contact          — the applicant (find-or-create by email), linked to Account
  3. CClientProfile   — the client-relationship hub, linked to Account + Contact
  4. CEngagement      — the mentoring request, linked to CClientProfile + Contact

INSTANCE MAPPING — reconciled against crm-test.clevelandbusinessmentors.org
(2026-05-28) by reading the deployed EspoCRM metadata:

  * The deployed model has a CClientProfile hub; CEngagement.engagementClient is
    a belongsTo CClientProfile (NOT Account). This differs from the original
    three-record assumption — see Requirements Specification §3.
  * Discriminators are multiEnums taking ["Client"]: Account.cAccountType
    (REQUIRED, added crm-test 2026-06) and Contact.cContactType. The legacy
    Account.cCompanyType is still present (now optional) and kept in sync.
  * Link FKs: Contact.accountId (belongsTo Account); CClientProfile.clientcontactId
    (belongsTo Contact) + linkedCompanyId (hasOne Account); CEngagement
    .engagementClientId (belongsTo CClientProfile) + primaryEngagementContactId.
    The applicant is additionally added to CEngagement.engagementContacts, a
    hasMany Contact link, via a relationship POST after the engagement create.
  * Engagement status field is `engagementStatus` (value "Submitted").

NOT DEPLOYED on this instance (Requirements Specification §11.1 pending
carry-forward) — therefore omitted from the payloads until they exist:
  - Account: year formed, number of employees, industry subsector (placeholder
    options only)
  - Contact: marketing consent, how-did-you-hear, applicant-since timestamp
  - CEngagement: meeting preference, notification preference, terms accepted
The form still collects these; they are simply not written until the fields land.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from core.enum_filter import EnumSanitizer
from core.espo import EspoApi
from core.phone import to_e164

from .schemas import IntakeSubmission

log = logging.getLogger("cbm_intake.orchestrator")

# --- Entity names ---
ACCOUNT = "Account"
CONTACT = "Contact"
CLIENT_PROFILE = "CClientProfile"
ENGAGEMENT = "CEngagement"

# --- Attribute names (reconciled against the deployed instance) ---
A_ACCOUNT_TYPE = "cAccountType"      # multiEnum on Account — REQUIRED (added crm-test 2026-06)
A_COMPANY_TYPE = "cCompanyType"      # multiEnum on Account (legacy, now optional)
A_BUSINESS_STAGE = "cBusinessStage"  # enum
A_INDUSTRY_SECTOR = "cIndustrySector"  # enum
C_CONTACT_TYPE = "cContactType"      # multiEnum on Contact
ENGAGEMENT_STATUS = "engagementStatus"

# --- Link names ---
ENGAGEMENT_CONTACTS = "engagementContacts"  # CEngagement hasMany Contact

# --- System-set values (Requirements Specification §5.4) ---
CLIENT = "Client"
STATUS_SUBMITTED = "Submitted"


async def _find_or_create_account(
    sub: IntakeSubmission, client: EspoApi, san: EnumSanitizer
) -> str:
    """Find-or-create the client Account by name and return its id.

    Reusing a same-named Account dedupes repeat submitters and avoids EspoCRM's
    duplicate-detection 409, which would otherwise fail the whole submission.
    Name matching is deliberately simple (exact, case-insensitive via the DB
    collation), aligning with EspoCRM's own name-based duplicate check; distinct
    businesses sharing a name collapse to one Account — acceptable for intake
    capture, split by admins downstream if ever needed.

    Pre-Startup submissions collect no business profile; the Account is created
    with a placeholder name (Account creation precedence ladder — OPEN, TD §7).
    """
    if sub.business_stage == "Pre-Startup":
        name = f"{sub.first_name} {sub.last_name} (Pre-Startup)"
    else:
        name = sub.business_name or f"{sub.first_name} {sub.last_name}"

    existing = await client.find_one(ACCOUNT, "name", name)
    if existing:
        log.info("matched existing Account %s for %r", existing["id"], name)
        return existing["id"]

    payload: dict = {
        "name": name,
        A_ACCOUNT_TYPE: [CLIENT],   # required discriminator — never sanitized
        A_COMPANY_TYPE: [CLIENT],   # legacy discriminator, kept in sync
    }
    # User-supplied enums: drop a drifted value rather than 400 the create.
    business_stage = await san.enum(ACCOUNT, A_BUSINESS_STAGE, sub.business_stage)
    if business_stage:
        payload[A_BUSINESS_STAGE] = business_stage
    if sub.business_stage != "Pre-Startup":
        if sub.business_website:
            payload["website"] = sub.business_website
        if sub.industry_sector:
            industry = await san.enum(ACCOUNT, A_INDUSTRY_SECTOR, sub.industry_sector)
            if industry:
                payload[A_INDUSTRY_SECTOR] = industry
    created = await client.create(ACCOUNT, payload)
    return created["id"]


async def _find_or_create_contact(
    sub: IntakeSubmission, client: EspoApi, account_id: str
) -> str:
    """Find-or-create the Contact by email (Technical Design §4.2)."""
    existing = await client.find_one(CONTACT, "emailAddress", str(sub.email))
    if existing:
        log.info("matched existing Contact %s for %s", existing["id"], sub.email)
        return existing["id"]

    payload = {
        "firstName": sub.first_name,
        "lastName": sub.last_name,
        "emailAddress": str(sub.email),
        "phoneNumber": to_e164(sub.phone),
        "addressPostalCode": sub.zip_code,
        "accountId": account_id,
        C_CONTACT_TYPE: [CLIENT],
    }
    created = await client.create(CONTACT, payload)
    return created["id"]


async def _create_client_profile(
    sub: IntakeSubmission, client: EspoApi, account_id: str, contact_id: str
) -> str:
    """Create the CClientProfile hub linked to the Account and Contact."""
    name = sub.business_name or f"{sub.first_name} {sub.last_name}"
    payload = {
        "name": name,
        "clientcontactId": contact_id,   # belongsTo Contact
        "linkedCompanyId": account_id,   # hasOne Account
    }
    created = await client.create(CLIENT_PROFILE, payload)
    return created["id"]


async def _create_engagement(
    sub: IntakeSubmission, client: EspoApi, client_profile_id: str, contact_id: str,
    san: EnumSanitizer,
) -> str:
    """Create the Engagement linked to the CClientProfile and the Contact.

    Drops any drifted ``mentoringFocusAreas`` value and records everything dropped
    across the whole chain (Account + Engagement) on ``description`` for follow-up,
    so a stale enum option never blocks capturing the request + contact info.
    """
    focus_areas = await san.multi(ENGAGEMENT, "mentoringFocusAreas", sub.mentoring_focus_areas)
    payload = {
        "name": f"{sub.first_name} {sub.last_name} — Intake {datetime.now(timezone.utc):%Y-%m-%d}",
        ENGAGEMENT_STATUS: STATUS_SUBMITTED,
        "mentoringFocusAreas": focus_areas,
        "mentoringNeedsDescription": sub.mentoring_needs_description,
        "engagementClientId": client_profile_id,      # belongsTo CClientProfile
        "primaryEngagementContactId": contact_id,     # belongsTo Contact
    }
    note = san.note()
    if note:
        payload["description"] = note
    created = await client.create(ENGAGEMENT, payload)
    return created["id"]


async def submit_intake(sub: IntakeSubmission, client: EspoApi) -> dict[str, str]:
    """Run the full Account -> Contact -> CClientProfile -> CEngagement sequence.

    Each id is captured as its step succeeds. On a later-step failure the caller
    routes to the failed-submission store (Technical Design §4.3); already-created
    records are valid canonical data and are not deleted.
    """
    san = EnumSanitizer(client)
    account_id = await _find_or_create_account(sub, client, san)
    contact_id = await _find_or_create_contact(sub, client, account_id)
    client_profile_id = await _create_client_profile(sub, client, account_id, contact_id)
    engagement_id = await _create_engagement(sub, client, client_profile_id, contact_id, san)
    # Also add the applicant to the Engagement Contacts (hasMany) link, alongside
    # the primaryEngagementContact set on the engagement itself.
    await client.relate(ENGAGEMENT, engagement_id, ENGAGEMENT_CONTACTS, contact_id)
    return {
        "accountId": account_id,
        "contactId": contact_id,
        "clientProfileId": client_profile_id,
        "engagementId": engagement_id,
    }
