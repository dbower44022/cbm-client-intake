"""Mentor Admin — read the full mentor record and update editable fields.

The editable-field set is declared here (the single source for the form layout
and the update whitelist); enum/multi-enum *options* are pulled live from
EspoCRM metadata so the CRM stays the source of truth. Computed totals
(availableCapacity, currentActiveClients, totals) are read-only.
"""

from __future__ import annotations

import re
from typing import Any, Optional, Protocol

MENTOR_PROFILE = "CMentorProfile"

# When a mentor is set to this status, a login User is provisioned for them.
STATUS_APPROVED = "Approved"
# CBM-issued email/login domain: userName = firstname.lastname@cbmentors.org.
CBM_EMAIL_DOMAIN = "cbmentors.org"
DEFAULT_MENTOR_TEAM = "Mentor Team"
USER_TYPE = "regular"


class MentorAdminError(Exception):
    """A mentor-admin operation could not be completed (e.g. team not found)."""


class MentorClient(Protocol):
    async def get(self, entity: str, record_id: str, select: str | None = ...) -> dict[str, Any]: ...
    async def update(self, entity: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def create(self, entity: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def find_one(self, entity: str, attribute: str, value: str, select: str = ...) -> Optional[dict[str, Any]]: ...
    async def list(self, entity: str, **kwargs: Any) -> dict[str, Any]: ...
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
    client: MentorClient,
    mentor_id: str,
    changes: dict[str, Any],
    *,
    team_name: Optional[str] = None,
    admin_client: Optional[MentorClient] = None,
) -> dict[str, Any]:
    """Update whitelisted editable fields; ignore anything else.

    Side effect: when ``mentorStatus`` transitions to ``Approved`` (and the
    mentor has no login user yet) AND an ``admin_client`` is supplied, provision
    an EspoCRM User for them, link it to the profile, and place it in the mentor
    team. **User creation/team lookup run under ``admin_client``** (a privileged
    backend credential), never the staff ``client`` — so Mentor Admin staff need
    no user-create permission. Without ``admin_client`` (the default), no
    provisioning is attempted. It runs *after* the status write and is
    best-effort: a failure is captured in the returned ``provision`` summary
    rather than failing the save, since the status change already took effect.
    """
    payload = {k: v for k, v in changes.items() if k in EDITABLE_NAMES}
    if not payload:
        return await get_mentor(client, mentor_id)

    # Only the transition into Approved (not re-saving an already-approved
    # mentor) triggers provisioning, and only if no user is linked yet.
    becoming_approved = payload.get("mentorStatus") == STATUS_APPROVED
    before = None
    if becoming_approved and admin_client is not None:
        before = await client.get(
            MENTOR_PROFILE, mentor_id, select="mentorStatus,assignedUserId"
        )

    await client.update(MENTOR_PROFILE, mentor_id, payload)

    provision: Optional[dict[str, Any]] = None
    if (
        admin_client is not None
        and before is not None
        and before.get("mentorStatus") != STATUS_APPROVED
        and not before.get("assignedUserId")
    ):
        try:
            summary = await provision_mentor_user(
                admin_client, client, mentor_id, team_name=team_name or DEFAULT_MENTOR_TEAM
            )
            provision = {"ok": True, **summary}
        except MentorAdminError as exc:
            provision = {"ok": False, "error": str(exc)}
        except Exception as exc:  # EspoError etc. — never break the saved status
            provision = {"ok": False, "error": str(exc)}

    result = await get_mentor(client, mentor_id)
    if provision is not None:
        result["provision"] = provision
    return result


def cbm_email_for(first: str, last: str) -> str:
    """Build firstname.lastname@cbmentors.org from a contact's name."""
    f = re.sub(r"[^a-z0-9]", "", (first or "").lower())
    last_clean = re.sub(r"[^a-z0-9]", "", (last or "").lower())
    local = ".".join(p for p in (f, last_clean) if p) or "mentor"
    return f"{local}@{CBM_EMAIL_DOMAIN}"


def _split_name(name: Optional[str]) -> tuple[str, str]:
    parts = (name or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


async def _unique_user_name(client: MentorClient, email: str) -> str:
    """The CBM email, or firstname.lastname2@… etc. if that login already exists."""
    local, _, domain = email.partition("@")
    for i in range(0, 100):
        candidate = email if i == 0 else f"{local}{i + 1}@{domain}"
        if not await client.find_one("User", "userName", candidate, select="id"):
            return candidate
    return email  # give up after 100; let the CRM enforce uniqueness


async def _find_team_id(client: MentorClient, team_name: str) -> str:
    team = await client.find_one("Team", "name", team_name, select="id,name")
    if team:
        return team["id"]
    available = await client.list("Team", select="name", max_size=200)
    names = sorted(t.get("name") for t in available.get("list", []) if t.get("name"))
    raise MentorAdminError(
        f"Team '{team_name}' not found in EspoCRM. Available teams: {names}"
    )


async def provision_mentor_user(
    admin_client: MentorClient,
    edit_client: MentorClient,
    mentor_id: str,
    *,
    team_name: str,
) -> dict[str, Any]:
    """Create a login User for an approved mentor, link it, and team it.

    Privilege split: ``admin_client`` (a backend service credential) does the
    User read/create + Team lookup — the operations staff users aren't allowed to
    do. ``edit_client`` (the logged-in staff user) reads the profile/contact and
    writes the ``assignedUser`` link, which staff already can. So the elevated
    permission lives only in the backend credential.

    userName/email = ``firstname.lastname@cbmentors.org`` (the CBM email; reuses
    the profile's ``cbmEmail`` if already set). The User is active, in
    ``team_name``, and EspoCRM is asked to email access info (``sendAccessInfo``)
    so the mentor sets their own password. The new User becomes the profile's
    ``assignedUser`` (the same link the assignment tool reads), and the CBM email
    is written back to the profile when it was blank.
    """
    profile = await edit_client.get(
        MENTOR_PROFILE, mentor_id, select="name,cbmEmail,contactRecordId"
    )
    first, last = "", ""
    contact_id = profile.get("contactRecordId")
    if contact_id:
        contact = await edit_client.get(
            "Contact", contact_id, select="firstName,lastName"
        )
        first = (contact.get("firstName") or "").strip()
        last = (contact.get("lastName") or "").strip()
    if not (first or last):
        first, last = _split_name(profile.get("name"))

    existing_cbm = (profile.get("cbmEmail") or "").strip()
    cbm = existing_cbm or cbm_email_for(first, last)
    user_name = await _unique_user_name(admin_client, cbm)
    team_id = await _find_team_id(admin_client, team_name)

    user_payload: dict[str, Any] = {
        "userName": user_name,
        "lastName": last or "Mentor",
        "emailAddress": cbm,
        "type": USER_TYPE,
        "isActive": True,
        "teamsIds": [team_id],
        "defaultTeamId": team_id,
        "sendAccessInfo": True,  # welcome email; ignored by CRM if unsupported
    }
    if first:
        user_payload["firstName"] = first
    user = await admin_client.create("User", user_payload)
    user_id = user.get("id")

    link_payload: dict[str, Any] = {"assignedUserId": user_id}
    if not existing_cbm:
        link_payload["cbmEmail"] = cbm
    await edit_client.update(MENTOR_PROFILE, mentor_id, link_payload)

    return {"userId": user_id, "userName": user_name, "email": cbm, "team": team_name}


async def field_options(client: MentorClient) -> dict[str, list[str]]:
    """Live option lists for the editable enum/multi-enum fields (CRM = truth)."""
    fields = await client.metadata(f"entityDefs.{MENTOR_PROFILE}.fields")
    options: dict[str, list[str]] = {}
    for name in _ENUM_FIELDS:
        opts = (fields.get(name) or {}).get("options")
        if isinstance(opts, list):
            options[name] = opts
    return options
