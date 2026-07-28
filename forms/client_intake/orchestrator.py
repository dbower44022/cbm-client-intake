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
  * Discriminators are multiEnums taking ["Client"]: Account.cCompanyType and
    Contact.cContactType. (The Account entity is presented as "Company" in the
    CRM; its type field is cCompanyType. The former cAccountType was removed
    from BOTH instances — verified 2026-07-28 — so writing it stored nothing.)
  * Link FKs: Contact.accountId (belongsTo Account); CClientProfile.clientcontactId
    (belongsTo Contact) + linkedCompanyId (hasOne Account); CEngagement
    .engagementClientId (belongsTo CClientProfile) + primaryEngagementContactId
    + clientOrganizationId (belongsTo Account — the company link the session
    tools display; engagements created before v0.38.1 lack it, the tools fall
    back through the client profile's linkedCompany).
    The applicant is additionally added to CEngagement.engagementContacts, a
    hasMany Contact link, via a relationship POST after the engagement create.
  * Engagement status field is `engagementStatus` (value "Submitted").

Field coverage (updated 2026-06-30, v0.13.0–0.21.0). Most of the fields that were
deferred under Requirements Specification §11.1 are now written to their intended
CRM field:
  - CClientProfile: year formed -> formationDate, number of employees ->
    numberOfEmployees
  - Contact: marketing consent -> cMarketingOptIn, how-did-you-hear ->
    cHowDidYouHear, meeting preference -> cMeetingPreference, notification
    preference -> cNotificationPreference, and the single consent checkbox ->
    cTermsOfUseAccepted + cPrivacyPolicyAccepted + cCodeOfConductAccepted
STILL not written (no target field yet): the Account industry subsector
(placeholder options only) and a Contact "applicant-since" timestamp. The form
collects these; they are simply not written until the fields land.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from core.crm_upsert import find_create_or_fill
from core.enum_filter import EnumSanitizer
from core.espo import EspoApi
from core.phone import e164_or_none

from .schemas import IntakeSubmission

log = logging.getLogger("cbm_intake.orchestrator")

# --- Entity names ---
ACCOUNT = "Account"
CONTACT = "Contact"
CLIENT_PROFILE = "CClientProfile"
ENGAGEMENT = "CEngagement"
MENTOR_PROFILE = "CMentorProfile"

# --- Attribute names (reconciled against the deployed instance) ---
A_COMPANY_TYPE = "cCompanyType"      # multiEnum on Account/Company — the type discriminator
A_BUSINESS_STAGE = "cBusinessStage"  # enum
A_INDUSTRY_SECTOR = "cIndustrySector"  # enum
C_CONTACT_TYPE = "cContactType"      # multiEnum on Contact
C_HOW_HEARD = "cHowDidYouHear"       # enum on Contact
C_MEETING_PREF = "cMeetingPreference"  # enum on Contact
C_NOTIFICATION_PREF = "cNotificationPreference"  # enum on Contact
C_MARKETING_OPT_IN = "cMarketingOptIn"     # bool on Contact
# The single consent checkbox ("...agree to the Code of Conduct, Terms of Use, and
# Privacy Policy") sets all three Contact bools.
C_TERMS_ACCEPTED = "cTermsOfUseAccepted"      # bool on Contact
C_PRIVACY_ACCEPTED = "cPrivacyPolicyAccepted"  # bool on Contact
C_CODE_OF_CONDUCT = "cCodeOfConductAccepted"   # bool on Contact
ENGAGEMENT_STATUS = "engagementStatus"

# Contact fields eligible for null-fill on a repeat submission (the match key
# emailAddress, the accountId FK, and the cContactType discriminator are excluded
# so they are never back-written over a curated record).
_CONTACT_FILL_KEYS = (
    "firstName", "lastName", "addressPostalCode", "phoneNumber",
    C_HOW_HEARD, C_MEETING_PREF, C_NOTIFICATION_PREF, C_MARKETING_OPT_IN,
    C_TERMS_ACCEPTED, C_PRIVACY_ACCEPTED, C_CODE_OF_CONDUCT,
)

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
        A_COMPANY_TYPE: [CLIENT],   # type discriminator — never sanitized
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
    sub: IntakeSubmission, client: EspoApi, account_id: str, san: EnumSanitizer
) -> str:
    """Find-or-create the Contact by email (Technical Design §4.2).

    On a repeat email the matched Contact is reused and any *empty* field is
    backfilled — never overwriting curated data (see ``find_create_or_fill``).
    """
    payload = {
        "firstName": sub.first_name,
        "lastName": sub.last_name,
        "emailAddress": str(sub.email),
        "addressPostalCode": sub.zip_code,
        "accountId": account_id,
        C_CONTACT_TYPE: [CLIENT],
        C_MARKETING_OPT_IN: bool(sub.marketing_consent),
        C_TERMS_ACCEPTED: bool(sub.terms_accepted),
        C_PRIVACY_ACCEPTED: bool(sub.terms_accepted),
        C_CODE_OF_CONDUCT: bool(sub.terms_accepted),
    }
    phone = e164_or_none(sub.phone)  # omit an implausible phone rather than 400
    if phone:
        payload["phoneNumber"] = phone
    if sub.how_did_you_hear:
        how_heard = await san.enum(CONTACT, C_HOW_HEARD, sub.how_did_you_hear)
        if how_heard:
            payload[C_HOW_HEARD] = how_heard
    if sub.meeting_preference:
        meeting = await san.enum(CONTACT, C_MEETING_PREF, sub.meeting_preference)
        if meeting:
            payload[C_MEETING_PREF] = meeting
    if sub.notification_preference:
        notif = await san.enum(CONTACT, C_NOTIFICATION_PREF, sub.notification_preference)
        if notif:
            payload[C_NOTIFICATION_PREF] = notif
    contact_id, action = await find_create_or_fill(
        client, CONTACT,
        match_attr="emailAddress", match_value=str(sub.email),
        create_payload=payload, fill_keys=_CONTACT_FILL_KEYS,
    )
    log.info("Contact %s (%s) for %s", contact_id, action, sub.email)
    return contact_id


async def _find_or_create_client_profile(
    sub: IntakeSubmission, client: EspoApi, account_id: str, contact_id: str
) -> str:
    """Find-or-create the CClientProfile hub linked to the Account and Contact.

    ONE client = one profile hub, so an existing profile for this Account is
    reused (and its empty fields backfilled) rather than duplicated. A second
    profile is not merely redundant: ``linkedCompany`` is a **hasOne** link, so
    creating one silently MOVES the Account (and contact) off the existing
    profile, orphaning it. That happened twice in production — 2026-07-17 and
    2026-07-27 — each time leaving a live engagement pointing at a hub with no
    company and no contact.

    Matching is by ``linkedCompanyId``: the Account is itself find-or-create by
    name, so it is the stable identity for "this client". A returning client
    correctly gets a NEW engagement on their EXISTING profile.
    """
    name = sub.business_name or f"{sub.first_name} {sub.last_name}"
    payload = {
        "name": name,
        "clientcontactId": contact_id,   # belongsTo Contact
        "linkedCompanyId": account_id,   # hasOne Account — see docstring
    }
    if sub.number_of_employees is not None:
        payload["numberOfEmployees"] = sub.number_of_employees
    if sub.year_formed is not None:
        # formationDate is a date; the form collects a year -> Jan 1 of that year.
        payload["formationDate"] = f"{sub.year_formed:04d}-01-01"
    profile_id, action = await find_create_or_fill(
        client, CLIENT_PROFILE,
        match_attr="linkedCompanyId", match_value=account_id,
        create_payload=payload,
        # Backfill only what an earlier submission may have left empty; never
        # rewrite the name or re-point the links of a curated profile.
        fill_keys=("numberOfEmployees", "formationDate", "clientcontactId"),
    )
    log.info("CClientProfile %s (%s) for Account %s", profile_id, action, account_id)
    return profile_id


async def _create_engagement(
    sub: IntakeSubmission, client: EspoApi, client_profile_id: str, contact_id: str,
    account_id: str, san: EnumSanitizer,
) -> str:
    """Create the Engagement linked to the CClientProfile, Contact, and Account.

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
        "clientOrganizationId": account_id,           # belongsTo Account — the
        # session tools' grid/Overview/Details read the company off this link
    }
    # The applicant's optional mentor request (2026-07-27). Verified against the
    # live roster before writing: the id arrives from a public form, and an
    # unknown/stale one would make EspoCRM reject the WHOLE engagement create
    # ("Can't relate with non-existing record"). A failed check drops the
    # request rather than the submission — the same never-block-on-an-optional-
    # field rule the enum sanitizer follows.
    requested = await _valid_requested_mentor(client, sub.requested_mentor_id)
    if requested:
        payload["requestedMentorId"] = requested

    note = san.note()
    if note:
        payload["description"] = note
    created = await client.create(ENGAGEMENT, payload)
    return created["id"]


async def _valid_requested_mentor(client: EspoApi, mentor_id: Optional[str]) -> Optional[str]:
    """Return ``mentor_id`` if it names a real CMentorProfile, else None."""
    if not mentor_id:
        return None
    try:
        found = await client.get(MENTOR_PROFILE, mentor_id, select="id")
    except Exception as exc:  # noqa: BLE001 — an optional request never blocks
        log.warning("requested mentor %r not usable (%s) — dropped", mentor_id, exc)
        return None
    return found.get("id") if found else None


async def submit_intake(sub: IntakeSubmission, client: EspoApi) -> dict[str, str]:
    """Run the full Account -> Contact -> CClientProfile -> CEngagement sequence.

    Each id is captured as its step succeeds. On a later-step failure the caller
    routes to the failed-submission store (Technical Design §4.3); already-created
    records are valid canonical data and are not deleted.
    """
    san = EnumSanitizer(client)
    account_id = await _find_or_create_account(sub, client, san)
    contact_id = await _find_or_create_contact(sub, client, account_id, san)
    client_profile_id = await _find_or_create_client_profile(
        sub, client, account_id, contact_id
    )
    engagement_id = await _create_engagement(
        sub, client, client_profile_id, contact_id, account_id, san
    )
    # Also add the applicant to the Engagement Contacts (hasMany) link, alongside
    # the primaryEngagementContact set on the engagement itself.
    await client.relate(ENGAGEMENT, engagement_id, ENGAGEMENT_CONTACTS, contact_id)
    return {
        "accountId": account_id,
        "contactId": contact_id,
        "clientProfileId": client_profile_id,
        "engagementId": engagement_id,
    }
