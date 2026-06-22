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


# Editable fields, grouped for the form. type drives the input + how the value
# is sent. Order is the display order.
EDITABLE_FIELDS: list[dict[str, str]] = [
    {"name": "name", "label": "Name", "type": "varchar", "group": "Profile"},
    {"name": "mentorStatus", "label": "Status", "type": "enum", "group": "Status"},
    {"name": "mentorType", "label": "Type", "type": "enum", "group": "Status"},
    {"name": "acceptingNewClients", "label": "Accepting new clients", "type": "bool", "group": "Status"},
    {"name": "mentorStatusNotes", "label": "Status notes", "type": "text", "group": "Status"},
    {"name": "maximumClientCapacity", "label": "Maximum client capacity", "type": "int", "group": "Capacity"},
    {"name": "yearsOfExperience", "label": "Years of experience", "type": "int", "group": "Capacity"},
    {"name": "industrySector", "label": "Industry sector", "type": "enum", "group": "Expertise"},
    {"name": "mentoringFocusAreas", "label": "Mentoring focus areas", "type": "multiEnum", "group": "Expertise"},
    {"name": "areaOfExpertise", "label": "Areas of expertise", "type": "multiEnum", "group": "Expertise"},
    {"name": "fluentLanguages", "label": "Fluent languages", "type": "multiEnum", "group": "Expertise"},
    {"name": "backgroundCheckCompleted", "label": "Background check completed", "type": "bool", "group": "Compliance"},
    {"name": "backgroundCheckDate", "label": "Background check date", "type": "date", "group": "Compliance"},
    {"name": "ethicsAgreementAccepted", "label": "Ethics agreement accepted", "type": "bool", "group": "Compliance"},
    {"name": "trainingCompleted", "label": "Training completed", "type": "bool", "group": "Compliance"},
    {"name": "trainingCompletionDate", "label": "Training completion date", "type": "date", "group": "Compliance"},
    {"name": "termsAccepted", "label": "Terms accepted", "type": "bool", "group": "Compliance"},
    {"name": "felonyConfiction", "label": "Felony conviction", "type": "bool", "group": "Compliance"},
    {"name": "duesStatus", "label": "Dues status", "type": "enum", "group": "Compliance"},
    {"name": "duesPaymentDate", "label": "Dues payment date", "type": "date", "group": "Compliance"},
    {"name": "duesRenewalDate", "label": "Dues renewal date", "type": "date", "group": "Compliance"},
    {"name": "mentorStartDate", "label": "Mentor start date", "type": "date", "group": "Dates"},
    {"name": "departureDate", "label": "Departure date", "type": "date", "group": "Dates"},
    {"name": "departureReason", "label": "Departure reason", "type": "enum", "group": "Dates"},
    {"name": "cbmEmail", "label": "CBM email", "type": "varchar", "group": "Profile"},
    {"name": "boardPosition", "label": "Board position", "type": "varchar", "group": "Profile"},
    {"name": "howDidYouHearAboutCBM", "label": "How they heard about CBM", "type": "varchar", "group": "Profile"},
    {"name": "description", "label": "Description / notes", "type": "text", "group": "Profile"},
    {"name": "aboutMentor", "label": "About the mentor", "type": "wysiwyg", "group": "Bio"},
    {"name": "mentorProfessionalBio", "label": "Professional bio", "type": "wysiwyg", "group": "Bio"},
    {"name": "mentoringSkills", "label": "Mentoring skills", "type": "wysiwyg", "group": "Bio"},
    {"name": "mentoringWhyInterested", "label": "Why interested in mentoring", "type": "wysiwyg", "group": "Bio"},
]

EDITABLE_NAMES = {f["name"] for f in EDITABLE_FIELDS}
_ENUM_FIELDS = [f["name"] for f in EDITABLE_FIELDS if f["type"] in ("enum", "multiEnum")]

# Read-only context shown above the form.
READ_ONLY_FIELDS = [
    "availableCapacity", "currentActiveClients", "maximumClientCapacity",
    "totalLifetimeSessions", "totalSessionsLast30Days", "totalMentoringHours",
    "contactRecordName", "assignedUserName", "createdAt", "modifiedAt",
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
