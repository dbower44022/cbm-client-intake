"""Volunteer application -> a single Contact (contactType = "Mentor").

Unlike client intake (three linked records), MR-APPLY creates one Contact with
mentorStatus = "Submitted". No Account, no Engagement.

INSTANCE MAPPING — CONFIRM BEFORE GOING LIVE (same caveats as the client-intake
orchestrator): custom fields on the native Contact entity are ``c``-prefixed on
the deployed instance; the value lists (industry / expertise / languages /
how-heard) are owned upstream and pending reconciliation (mapping doc §4).
File upload (resume) is a documented follow-on (mapping doc §5) and is not
handled here yet.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from core.espo import EspoApi
from core.phone import to_e164

from .schemas import VolunteerApplication

log = logging.getLogger("cbm_intake.volunteer")

CONTACT = "Contact"  # native

# Attribute names (CONFIRM against deployed metadata) ---
C_TYPE = "cContactType"
C_MENTOR_STATUS = "cMentorStatus"
C_WHY = "whyInterestedInMentoring"  # custom; confirm prefix
C_BIO = "professionalBio"
C_CURRENTLY_EMPLOYED = "currentlyEmployed"
C_INDUSTRY = "industrySectors"
C_FOCUS_AREAS = "mentoringFocusAreas"
C_LANGUAGES = "fluentLanguages"
C_LINKEDIN = "linkedInProfile"
C_HOW_HEARD = "cHowDidYouHearAboutCbm"
C_FELONY = "felonyConvictionDisclosure"
C_TERMS = "termsAndConditionsAccepted"
C_APPLICANT_SINCE = "cApplicantSinceTimestamp"
# Attachment-multiple field that holds the resume on the Contact (CONFIRM).
C_RESUME_FIELD = "cResume"

MENTOR = "Mentor"
MENTOR_STATUS_SUBMITTED = "Submitted"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def submit_application(sub: VolunteerApplication, client: EspoApi) -> dict[str, str]:
    """Find-or-create the mentor Contact and return its id."""
    existing = await client.find_one(CONTACT, "emailAddress", str(sub.email))
    if existing:
        # Merge policy for a matched Contact is an open issue; reuse without overwrite.
        log.info("matched existing Contact %s for %s", existing["id"], sub.email)
        return {"contactId": existing["id"]}

    payload: dict = {
        "firstName": sub.first_name,
        "lastName": sub.last_name,
        "emailAddress": str(sub.email),
        "phoneNumber": to_e164(sub.phone),
        "addressPostalCode": sub.zip_code,
        C_TYPE: MENTOR,
        C_MENTOR_STATUS: MENTOR_STATUS_SUBMITTED,
        C_WHY: sub.why_volunteer,
        C_TERMS: sub.terms_accepted,
        C_FELONY: sub.felony_conviction,
        C_APPLICANT_SINCE: _now_iso(),
    }
    if sub.middle_initial:
        payload["middleName"] = sub.middle_initial
    if sub.street:
        payload["addressStreet"] = sub.street
    if sub.work_experience:
        payload[C_BIO] = sub.work_experience
    if sub.currently_employed is not None:
        payload[C_CURRENTLY_EMPLOYED] = sub.currently_employed != "No"
    if sub.linkedin_profile:
        payload[C_LINKEDIN] = sub.linkedin_profile
    if sub.industry_experience:
        payload[C_INDUSTRY] = sub.industry_experience
    if sub.areas_of_expertise:
        payload[C_FOCUS_AREAS] = sub.areas_of_expertise
    if sub.fluent_languages:
        payload[C_LANGUAGES] = sub.fluent_languages
    if sub.how_did_you_hear:
        payload[C_HOW_HEARD] = sub.how_did_you_hear

    # Resume: upload as an Attachment bound to the Contact's resume field, then
    # reference it by id on the create (attachment-multiple -> "<field>Ids").
    if sub.resume is not None:
        attachment_id = await client.upload_attachment(
            filename=sub.resume.filename,
            content_type=sub.resume.content_type,
            data_base64=sub.resume.data_base64,
            related_type=CONTACT,
            field=C_RESUME_FIELD,
        )
        payload[f"{C_RESUME_FIELD}Ids"] = [attachment_id]

    created = await client.create(CONTACT, payload)
    return {"contactId": created["id"]}
