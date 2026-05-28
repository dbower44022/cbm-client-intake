"""The three-record create-and-link sequence (Technical Design §3.3).

A submission yields one Account, one Contact (find-or-create by email), and one
Engagement, created in dependency order so each link target exists before it is
referenced.

INSTANCE MAPPING — CONFIRM BEFORE GOING LIVE
--------------------------------------------
The entity and attribute names below are the single place to reconcile against
the deployed EspoCRM metadata (Technical Design §3.4 and the §7 open issue):

  * Custom fields added to the NATIVE Account and Contact entities are stored
    under ``c``-prefixed attribute names; the guesses below assume that.
  * Engagement is a CUSTOM entity, so EspoCRM names it ``CEngagement`` and its
    own fields use natural names.
  * The §11.1 "pending carry-forward" fields must be deployed on the instance
    before they are populated; until then, omit them from the payload.

In ESPO_DRY_RUN mode the exact names are immaterial (nothing is sent), so the
form is fully testable while these remain provisional.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .espo import EspoApi
from .schemas import IntakeSubmission

log = logging.getLogger("cbm_intake.orchestrator")

# --- Entity names ---
ACCOUNT = "Account"        # native
CONTACT = "Contact"        # native
ENGAGEMENT = "CEngagement"  # custom entity -> C-prefixed; CONFIRM

# --- Attribute names (CONFIRM; see module docstring) ---
A_TYPE = "cAccountType"            # custom on native Account
A_BUSINESS_STAGE = "cBusinessStage"
A_INDUSTRY_SECTOR = "cIndustrySector"
A_INDUSTRY_SUBSECTOR = "cIndustrySubsector"
A_YEAR_FORMED = "cYearFormed"
A_NUMBER_OF_EMPLOYEES = "cNumberOfEmployees"

C_TYPE = "cContactType"            # custom on native Contact
C_HOW_HEARD = "cHowDidYouHearAboutCbm"
C_MARKETING_CONSENT = "cMarketingConsent"
C_APPLICANT_SINCE = "cApplicantSinceTimestamp"

# --- System-set values (Requirements Specification §5.4) ---
CLIENT = "Client"
ENGAGEMENT_STATUS_SUBMITTED = "Submitted"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def _resolve_account(sub: IntakeSubmission, client: EspoApi) -> str:
    """Create (or resolve) the client Account and return its id.

    Pre-Startup submissions collect no business profile. How they map to the
    required Account is governed by the Account creation precedence ladder
    (Master PRD v2.5) and is an OPEN issue (Technical Design §7). The scaffold
    creates a clearly-labelled placeholder Account so the sequence completes;
    revisit when the ladder is specified.
    """
    payload: dict = {A_TYPE: CLIENT}
    if sub.business_stage == "Pre-Startup":
        payload["name"] = f"{sub.first_name} {sub.last_name} (Pre-Startup)"  # TODO: precedence ladder
        payload[A_BUSINESS_STAGE] = sub.business_stage
    else:
        payload["name"] = sub.business_name or f"{sub.first_name} {sub.last_name}"
        payload[A_BUSINESS_STAGE] = sub.business_stage
        if sub.business_website:
            payload["website"] = sub.business_website
        if sub.industry_sector:
            payload[A_INDUSTRY_SECTOR] = sub.industry_sector
        if sub.industry_subsector:
            payload[A_INDUSTRY_SUBSECTOR] = sub.industry_subsector
        if sub.year_formed is not None:
            payload[A_YEAR_FORMED] = sub.year_formed
        if sub.number_of_employees is not None:
            payload[A_NUMBER_OF_EMPLOYEES] = sub.number_of_employees

    created = await client.create(ACCOUNT, payload)
    return created["id"]


async def _find_or_create_contact(
    sub: IntakeSubmission, client: EspoApi, account_id: str
) -> str:
    """Find-or-create the Contact by email (Technical Design §4.2).

    A matched Contact is reused rather than duplicated. The merge policy for
    updating a matched Contact's fields is an OPEN issue (Technical Design §7),
    so the scaffold reuses the existing record without overwriting it.
    """
    existing = await client.find_one(CONTACT, "emailAddress", str(sub.email))
    if existing:
        log.info("matched existing Contact %s for %s", existing["id"], sub.email)
        return existing["id"]

    payload = {
        "firstName": sub.first_name,
        "lastName": sub.last_name,
        "emailAddress": str(sub.email),
        "phoneNumber": sub.phone,
        "addressPostalCode": sub.zip_code,
        "accountId": account_id,
        C_TYPE: CLIENT,
        C_MARKETING_CONSENT: sub.marketing_consent,
        C_APPLICANT_SINCE: _now_iso(),
    }
    if sub.how_did_you_hear:
        payload[C_HOW_HEARD] = sub.how_did_you_hear

    created = await client.create(CONTACT, payload)
    return created["id"]


async def _create_engagement(
    sub: IntakeSubmission, client: EspoApi, account_id: str, contact_id: str
) -> str:
    """Create the Engagement linked to the Account and the Contact."""
    payload = {
        # Auto-named at the business level (DAT-020); set a sensible value in
        # case the instance does not compute one via formula.
        "name": f"{sub.first_name} {sub.last_name} — Intake {datetime.now(timezone.utc):%Y-%m-%d}",
        "status": ENGAGEMENT_STATUS_SUBMITTED,
        "mentoringFocusAreas": sub.mentoring_focus_areas,
        "mentoringNeedsDescription": sub.mentoring_needs_description,
        "termsAccepted": sub.terms_accepted,
        "accountId": account_id,
        # Primary-engagement-contact relationship (DAT-025). Link name to be
        # confirmed against the Engagement Entity PRD / deployed metadata.
        "contactsIds": [contact_id],
    }
    if sub.meeting_preference:
        payload["meetingPreference"] = sub.meeting_preference
    if sub.notification_preference:
        payload["notificationPreference"] = sub.notification_preference

    created = await client.create(ENGAGEMENT, payload)
    return created["id"]


async def submit_intake(sub: IntakeSubmission, client: EspoApi) -> dict[str, str]:
    """Run the full Account -> Contact -> Engagement sequence.

    Each id is captured as its step succeeds. On a later-step failure the
    caller is responsible for routing to the failed-submission store
    (Technical Design §4.3); this function does not delete already-created
    records, which are valid canonical data.
    """
    account_id = await _resolve_account(sub, client)
    contact_id = await _find_or_create_contact(sub, client, account_id)
    engagement_id = await _create_engagement(sub, client, account_id, contact_id)
    return {
        "accountId": account_id,
        "contactId": contact_id,
        "engagementId": engagement_id,
    }
