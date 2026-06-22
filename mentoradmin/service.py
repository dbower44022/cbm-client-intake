"""Mentor Admin — read the full mentor record and update editable fields.

The editable-field set is declared here (the single source for the form layout
and the update whitelist); enum/multi-enum *options* are pulled live from
EspoCRM metadata so the CRM stays the source of truth. Computed totals
(availableCapacity, currentActiveClients, totals) are read-only.
"""

from __future__ import annotations

from typing import Any, Protocol

MENTOR_PROFILE = "CMentorProfile"


class MentorClient(Protocol):
    async def get(self, entity: str, record_id: str, select: str | None = ...) -> dict[str, Any]: ...
    async def update(self, entity: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def metadata(self, key: str) -> Any: ...


# "How did you hear about CBM" is a free-text CRM field, but the mentor intake
# (volunteer) form offers a fixed list — mirror it here so admins pick the same
# values. Kept in sync with forms/volunteer/frontend/options.js (howDidYouHear).
HOW_HEARD_OPTIONS = [
    "Friend or relative", "Newspaper", "Online search", "Radio", "SBA",
    "CBM client or volunteer", "Social media", "TV", "Workshop/Event", "Other",
]

# Editable fields, grouped for the form (one tab per group). ``type`` drives the
# input + how the value is sent; ``row`` (optional) sub-groups fields within a
# tab; ``options`` (optional) supplies a static dropdown list for a field whose
# CRM type is free-text. Order is the display order.
EDITABLE_FIELDS: list[dict[str, Any]] = [
    {"name": "name", "label": "Name", "type": "varchar", "group": "Profile"},
    {"name": "mentorStatus", "label": "Status", "type": "enum", "group": "Status"},
    {"name": "mentorType", "label": "Type", "type": "enum", "group": "Status"},
    {"name": "acceptingNewClients", "label": "Accepting new clients", "type": "bool", "group": "Status"},
    {"name": "mentorStartDate", "label": "Mentor start date", "type": "date", "group": "Status"},
    {"name": "mentorStatusNotes", "label": "Status notes", "type": "text", "group": "Status"},
    {"name": "maximumClientCapacity", "label": "Maximum client capacity", "type": "int", "group": "Capacity"},
    {"name": "yearsOfExperience", "label": "Years of experience", "type": "int", "group": "Capacity"},
    {"name": "industrySector", "label": "Industry sector", "type": "enum", "group": "Expertise"},
    {"name": "mentoringFocusAreas", "label": "Mentoring focus areas", "type": "multiEnum", "group": "Expertise"},
    {"name": "areaOfExpertise", "label": "Areas of expertise", "type": "multiEnum", "group": "Expertise"},
    {"name": "fluentLanguages", "label": "Fluent languages", "type": "multiEnum", "group": "Expertise"},
    # Compliance: checkboxes on the top row, dates (and dues status) below.
    {"name": "backgroundCheckCompleted", "label": "Background check completed", "type": "bool", "group": "Compliance", "row": "checks"},
    {"name": "ethicsAgreementAccepted", "label": "Ethics agreement accepted", "type": "bool", "group": "Compliance", "row": "checks"},
    {"name": "trainingCompleted", "label": "Training completed", "type": "bool", "group": "Compliance", "row": "checks"},
    {"name": "termsAccepted", "label": "Terms accepted", "type": "bool", "group": "Compliance", "row": "checks"},
    {"name": "felonyConfiction", "label": "Felony conviction", "type": "bool", "group": "Compliance", "row": "checks"},
    {"name": "duesStatus", "label": "Dues status", "type": "enum", "group": "Compliance", "row": "dates"},
    {"name": "backgroundCheckDate", "label": "Background check date", "type": "date", "group": "Compliance", "row": "dates"},
    {"name": "trainingCompletionDate", "label": "Training completion date", "type": "date", "group": "Compliance", "row": "dates"},
    {"name": "duesPaymentDate", "label": "Dues payment date", "type": "date", "group": "Compliance", "row": "dates"},
    {"name": "duesRenewalDate", "label": "Dues renewal date", "type": "date", "group": "Compliance", "row": "dates"},
    {"name": "departureDate", "label": "Departure date", "type": "date", "group": "Departure"},
    {"name": "departureReason", "label": "Departure reason", "type": "enum", "group": "Departure"},
    {"name": "cbmEmail", "label": "CBM email", "type": "varchar", "group": "Profile"},
    {"name": "boardPosition", "label": "Board position", "type": "varchar", "group": "Profile"},
    {"name": "howDidYouHearAboutCBM", "label": "How they heard about CBM", "type": "enum", "group": "Profile", "options": HOW_HEARD_OPTIONS},
    {"name": "description", "label": "Description / notes", "type": "text", "group": "Profile"},
    {"name": "aboutMentor", "label": "About the mentor", "type": "wysiwyg", "group": "Bio"},
    {"name": "mentorProfessionalBio", "label": "Professional bio", "type": "wysiwyg", "group": "Bio"},
    {"name": "mentoringSkills", "label": "Mentoring skills", "type": "wysiwyg", "group": "Bio"},
    {"name": "mentoringWhyInterested", "label": "Why interested in mentoring", "type": "wysiwyg", "group": "Bio"},
]

EDITABLE_NAMES = {f["name"] for f in EDITABLE_FIELDS}
_ENUM_FIELDS = [f["name"] for f in EDITABLE_FIELDS if f["type"] in ("enum", "multiEnum")]

# Read-only context shown above the form. Includes the contact-info "foreign"
# fields CMentorProfile mirrors from the linked Contact (personalEmail/
# contactPhone/contactStreet/contactCity/postalCode) — not editable here (they
# live on the Contact), shown read-only in the summary card.
READ_ONLY_FIELDS = [
    "availableCapacity", "currentActiveClients", "maximumClientCapacity",
    "totalLifetimeSessions", "totalSessionsLast30Days", "totalMentoringHours",
    "contactRecordName", "assignedUserName", "createdAt", "modifiedAt",
    "personalEmail", "contactPhone", "contactStreet", "contactCity", "postalCode",
]

_DETAIL_SELECT = ",".join(["id"] + sorted(EDITABLE_NAMES) + READ_ONLY_FIELDS)


async def get_mentor(client: MentorClient, mentor_id: str) -> dict[str, Any]:
    """The full mentor record: every editable field + read-only context."""
    return await client.get(MENTOR_PROFILE, mentor_id, select=_DETAIL_SELECT)


async def update_mentor(
    client: MentorClient, mentor_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    """Update only whitelisted editable fields; ignore anything else."""
    payload = {k: v for k, v in changes.items() if k in EDITABLE_NAMES}
    if not payload:
        return await get_mentor(client, mentor_id)
    await client.update(MENTOR_PROFILE, mentor_id, payload)
    return await get_mentor(client, mentor_id)


async def field_options(client: MentorClient) -> dict[str, list[str]]:
    """Live option lists for the editable enum/multi-enum fields (CRM = truth)."""
    fields = await client.metadata(f"entityDefs.{MENTOR_PROFILE}.fields")
    options: dict[str, list[str]] = {}
    for name in _ENUM_FIELDS:
        opts = (fields.get(name) or {}).get("options")
        if isinstance(opts, list):
            options[name] = opts
    return options
