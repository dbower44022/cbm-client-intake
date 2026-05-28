"""Volunteer application -> Contact (Mentor) + linked CMentorProfile.

Reconciled against the deployed crm-test instance (2026-05-28). The mentor
model mirrors the client side: a native Contact carries identity plus
``cContactType = ["Mentor"]``, and the mentor-specific data lives on a
CMentorProfile record linked back to the Contact via ``contactRecord``
(FK ``contactRecordId``). The earlier flat-Contact mapping (per MR-Contact.yaml)
did not match the instance — only ``cContactType`` existed there.

Mapping decisions (confirmed with the product owner):
  * mentorStatus  -> "Candidate" (new applicant; enum has no "Submitted")
  * mentorType    -> "Mentor"
  * industry_experience is multi-select on the form but ``industrySector`` is a
    single enum on the instance, so only the FIRST value is stored for now
    (multi-store deferred until a multi-value field is deployed).
  * terms_accepted -> CMentorProfile.termsAccepted (a dedicated bool field).

NOT YET DEPLOYED / deferred:
  * Resume upload — no attachment field exists on Contact or CMentorProfile on
    the instance, so an uploaded resume is accepted by the form but not stored.
  * currently_employed / contact_preference / phone_type have no target field.
"""

from __future__ import annotations

import logging

from core.espo import EspoApi
from core.phone import to_e164

from .schemas import VolunteerApplication

log = logging.getLogger("cbm_intake.volunteer")

CONTACT = "Contact"  # native
MENTOR_PROFILE = "CMentorProfile"

# --- Contact attributes (reconciled against the deployed instance) ---
C_CONTACT_TYPE = "cContactType"       # multiEnum
C_LINKEDIN = "cLinkedInProfile"       # url
C_PREFERRED_NAME = "cPreferredName"   # varchar

# --- CMentorProfile attributes ---
P_CONTACT_LINK = "contactRecordId"    # belongsTo Contact (link FK)
P_STATUS = "mentorStatus"             # enum
P_TYPE = "mentorType"                 # enum
P_WHY = "mentoringWhyInterested"      # wysiwyg
P_BIO = "mentorProfessionalBio"       # wysiwyg
P_FOCUS_AREAS = "mentoringFocusAreas"  # multiEnum
P_LANGUAGES = "fluentLanguages"       # multiEnum
P_INDUSTRY = "industrySector"         # enum (single)
P_HOW_HEARD = "howDidYouHearAboutCBM"  # varchar
P_FELONY = "felonyConfiction"         # bool (note: CRM field name is misspelled)
P_TERMS = "termsAccepted"             # bool

# --- System-set values ---
CONTACT_TYPE_MENTOR = "Mentor"
MENTOR_STATUS_NEW = "Candidate"
MENTOR_TYPE_DEFAULT = "Mentor"


async def _find_or_create_mentor_contact(sub: VolunteerApplication, client: EspoApi) -> str:
    """Find-or-create the mentor's Contact by email and return its id.

    A matched Contact is reused without overwrite (the create-only API user
    cannot update it anyway); the mentor profile still links to it.
    """
    existing = await client.find_one(CONTACT, "emailAddress", str(sub.email))
    if existing:
        log.info("matched existing Contact %s for %s", existing["id"], sub.email)
        return existing["id"]

    payload: dict = {
        "firstName": sub.first_name,
        "lastName": sub.last_name,
        "emailAddress": str(sub.email),
        "phoneNumber": to_e164(sub.phone),
        "addressPostalCode": sub.zip_code,
        C_CONTACT_TYPE: [CONTACT_TYPE_MENTOR],
    }
    if sub.middle_initial:
        payload["middleName"] = sub.middle_initial
    if sub.preferred_name:
        payload[C_PREFERRED_NAME] = sub.preferred_name
    if sub.street:
        payload["addressStreet"] = sub.street
    if sub.linkedin_profile:
        payload[C_LINKEDIN] = sub.linkedin_profile

    created = await client.create(CONTACT, payload)
    return created["id"]


async def _create_mentor_profile(
    sub: VolunteerApplication, client: EspoApi, contact_id: str
) -> str:
    """Create the CMentorProfile holding the mentor-specific data."""
    payload: dict = {
        "name": f"{sub.first_name} {sub.last_name}",
        P_CONTACT_LINK: contact_id,
        P_STATUS: MENTOR_STATUS_NEW,
        P_TYPE: MENTOR_TYPE_DEFAULT,
        P_WHY: sub.why_volunteer,
        P_FOCUS_AREAS: sub.areas_of_expertise,
        P_FELONY: sub.felony_conviction,
        P_TERMS: sub.terms_accepted,
    }
    if sub.work_experience:
        payload[P_BIO] = sub.work_experience
    if sub.fluent_languages:
        payload[P_LANGUAGES] = sub.fluent_languages
    if sub.industry_experience:
        # Single-enum field — store only the first selection for now.
        payload[P_INDUSTRY] = sub.industry_experience[0]
    if sub.how_did_you_hear:
        payload[P_HOW_HEARD] = sub.how_did_you_hear

    created = await client.create(MENTOR_PROFILE, payload)
    return created["id"]


async def submit_application(sub: VolunteerApplication, client: EspoApi) -> dict[str, str]:
    """Create/reuse the mentor Contact, then create the linked CMentorProfile."""
    if sub.resume is not None:
        # No attachment field is deployed for the resume yet (see module docstring).
        log.warning(
            "resume received for %s but not stored — no deployed attachment field",
            sub.email,
        )

    contact_id = await _find_or_create_mentor_contact(sub, client)
    profile_id = await _create_mentor_profile(sub, client, contact_id)
    return {"contactId": contact_id, "mentorProfileId": profile_id}
