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
  * industry_experience (multi-select) -> ``industryExperience`` (multiEnum) — all
    selections stored (the field was made a multiEnum with the canonical 28-value
    list on both CRMs 2026-06-30).
  * terms_accepted -> CMentorProfile.termsAccepted (a dedicated bool field).

Resume upload is stored on ``CMentorProfile.resumeUpload`` (a file field): the
file is created as an EspoCRM Attachment bound to that field, and its id is set
on the profile at create time.

NOT YET DEPLOYED / deferred:
  * currently_employed / contact_preference / phone_type have no target field.
"""

from __future__ import annotations

import logging

from core.crm_upsert import find_create_or_fill
from core.enum_filter import EnumSanitizer
from core.espo import EspoApi
from core.phone import e164_or_none

from .schemas import VolunteerApplication

log = logging.getLogger("cbm_intake.volunteer")

CONTACT = "Contact"  # native
MENTOR_PROFILE = "CMentorProfile"

# --- Contact attributes (reconciled against the deployed instance) ---
C_CONTACT_TYPE = "cContactType"       # multiEnum
C_LINKEDIN = "cLinkedInProfile"       # url
C_PREFERRED_NAME = "cPreferredName"   # varchar
C_CONTACT_METHOD = "cPreferredContactMethod"  # enum
C_EMPLOYMENT = "cEmploymentStatus"    # enum
# The single consent checkbox sets all three Contact bools.
C_TERMS_ACCEPTED = "cTermsOfUseAccepted"       # bool on Contact
C_PRIVACY_ACCEPTED = "cPrivacyPolicyAccepted"  # bool on Contact
C_CODE_OF_CONDUCT = "cCodeOfConductAccepted"   # bool on Contact

# Contact fields eligible for null-fill on a repeat submission (the match key,
# any FK, and the cContactType discriminator are excluded so they are never
# back-written over a curated record).
_CONTACT_FILL_KEYS = (
    "firstName", "lastName", "middleName", C_PREFERRED_NAME, "addressStreet",
    "addressPostalCode", "phoneNumber", C_LINKEDIN, C_CONTACT_METHOD, C_EMPLOYMENT,
    C_TERMS_ACCEPTED, C_PRIVACY_ACCEPTED, C_CODE_OF_CONDUCT,
)

# --- CMentorProfile attributes ---
P_CONTACT_LINK = "contactRecordId"    # belongsTo Contact (link FK)
P_STATUS = "mentorStatus"             # enum
P_TYPE = "mentorType"                 # enum
P_WHY = "mentoringWhyInterested"      # wysiwyg
P_BIO = "mentorProfessionalBio"       # wysiwyg
P_AREA_OF_EXPERTISE = "areaOfExpertise"  # multiEnum (the mentor's skill areas)
P_LANGUAGES = "fluentLanguages"       # multiEnum
P_INDUSTRY_EXP = "industryExperience"  # multiEnum (all selections)
P_HOW_HEARD = "howDidYouHearAboutCBM"  # varchar
P_FELONY = "felonyConfiction"         # bool (note: CRM field name is misspelled)
P_TERMS = "termsAccepted"             # bool
P_MENTOR_CODE = "mentorCodeAccepted"  # bool — the mentor-specific code-of-conduct
P_DESCRIPTION = "description"          # text — used to note any dropped values
P_RESUME_ID = "resumeUploadId"        # file field FK (-> Attachment)
RESUME_FIELD = "resumeUpload"         # the file field the attachment binds to

# --- System-set values ---
CONTACT_TYPE_MENTOR = "Mentor"
MENTOR_STATUS_NEW = "Candidate"
MENTOR_TYPE_DEFAULT = "Mentor"


async def _find_or_create_mentor_contact(
    sub: VolunteerApplication, client: EspoApi, san: EnumSanitizer
) -> str:
    """Find-or-create the mentor's Contact by email and return its id.

    On a repeat email the matched Contact is reused and any *empty* field is
    backfilled — never overwriting curated data (see ``find_create_or_fill``).
    """
    payload: dict = {
        "firstName": sub.first_name,
        "lastName": sub.last_name,
        "emailAddress": str(sub.email),
        "addressPostalCode": sub.zip_code,
        C_CONTACT_TYPE: [CONTACT_TYPE_MENTOR],
        C_TERMS_ACCEPTED: bool(sub.terms_accepted),
        C_PRIVACY_ACCEPTED: bool(sub.terms_accepted),
        C_CODE_OF_CONDUCT: bool(sub.terms_accepted),
    }
    phone = e164_or_none(sub.phone)  # omit an implausible phone rather than 400
    if phone:
        payload["phoneNumber"] = phone
    if sub.middle_initial:
        payload["middleName"] = sub.middle_initial
    if sub.preferred_name:
        payload[C_PREFERRED_NAME] = sub.preferred_name
    if sub.street:
        payload["addressStreet"] = sub.street
    if sub.linkedin_profile:
        payload[C_LINKEDIN] = sub.linkedin_profile
    if sub.contact_preference:
        method = await san.enum(CONTACT, C_CONTACT_METHOD, sub.contact_preference)
        if method:
            payload[C_CONTACT_METHOD] = method
    if sub.currently_employed:
        employment = await san.enum(CONTACT, C_EMPLOYMENT, sub.currently_employed)
        if employment:
            payload[C_EMPLOYMENT] = employment

    contact_id, action = await find_create_or_fill(
        client, CONTACT,
        match_attr="emailAddress", match_value=str(sub.email),
        create_payload=payload, fill_keys=_CONTACT_FILL_KEYS,
    )
    log.info("Contact %s (%s) for %s", contact_id, action, sub.email)
    return contact_id


async def _create_mentor_profile(
    sub: VolunteerApplication, client: EspoApi, contact_id: str, san: EnumSanitizer
) -> str:
    """Create the CMentorProfile holding the mentor-specific data.

    Enum-backed fields are sanitized against the live CRM options first: an
    unrecognized value (e.g. a drifted industry/language option) is dropped rather
    than failing the whole create, so the mentor record — and the applicant's
    contact details — are always captured. Anything dropped is noted on the record
    (``description``) for staff follow-up. The shared ``san`` spans the whole
    delivery (Contact + profile) so all dropped values aggregate into one note.
    """
    expertise = await san.multi(MENTOR_PROFILE, P_AREA_OF_EXPERTISE, sub.areas_of_expertise)

    payload: dict = {
        "name": f"{sub.first_name} {sub.last_name}",
        P_CONTACT_LINK: contact_id,
        P_STATUS: MENTOR_STATUS_NEW,
        P_TYPE: MENTOR_TYPE_DEFAULT,
        P_WHY: sub.why_volunteer,
        P_AREA_OF_EXPERTISE: expertise,
        P_FELONY: sub.felony_conviction,
        P_TERMS: sub.terms_accepted,
        P_MENTOR_CODE: bool(sub.terms_accepted),
    }
    if sub.work_experience:
        payload[P_BIO] = sub.work_experience
    if sub.fluent_languages:
        languages = await san.multi(MENTOR_PROFILE, P_LANGUAGES, sub.fluent_languages)
        if languages:
            payload[P_LANGUAGES] = languages
    if sub.industry_experience:
        industries = await san.multi(MENTOR_PROFILE, P_INDUSTRY_EXP, sub.industry_experience)
        if industries:
            payload[P_INDUSTRY_EXP] = industries
    if sub.how_did_you_hear:
        # Sanitized: the form list tracks Contact.cHowDidYouHear, whose options may
        # differ from this profile enum — drop a mismatch rather than 400 the create.
        how_heard = await san.enum(MENTOR_PROFILE, P_HOW_HEARD, sub.how_did_you_hear)
        if how_heard:
            payload[P_HOW_HEARD] = how_heard
    note = san.note()
    if note:
        payload[P_DESCRIPTION] = note
    if sub.resume is not None:
        # Upload the file as an Attachment bound to CMentorProfile.resumeUpload,
        # then set its id so it links when the profile is created.
        attachment_id = await client.upload_attachment(
            filename=sub.resume.filename,
            content_type=sub.resume.content_type,
            data_base64=sub.resume.data_base64,
            related_type=MENTOR_PROFILE,
            field=RESUME_FIELD,
        )
        payload[P_RESUME_ID] = attachment_id

    created = await client.create(MENTOR_PROFILE, payload)
    return created["id"]


async def submit_application(sub: VolunteerApplication, client: EspoApi) -> dict[str, str]:
    """Create/reuse the mentor Contact, then create the linked CMentorProfile.

    A resume, if provided, is uploaded as an Attachment and linked on the
    profile's ``resumeUpload`` file field (see ``_create_mentor_profile``).
    """
    san = EnumSanitizer(client)
    contact_id = await _find_or_create_mentor_contact(sub, client, san)
    profile_id = await _create_mentor_profile(sub, client, contact_id, san)
    return {"contactId": contact_id, "mentorProfileId": profile_id}
