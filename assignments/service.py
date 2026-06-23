"""Read Submitted engagements + eligible mentors, and perform an assignment.

Field/link names and enum values reconciled live against crm-test (2026-06-19):

  * ``CEngagement.engagementStatus`` enum includes ``Submitted`` and
    ``Pending Acceptance``.
  * ``CEngagement.assignedUser`` (FK ``assignedUserId``) — the assigned User.
  * ``CEngagement.mentorProfile`` (FK ``mentorProfileId``) — the assigned mentor.
  * Related records to re-assign: ``primaryEngagementContact`` +
    ``engagementContacts`` (hasMany) Contacts, ``engagementClient``
    (CClientProfile), ``clientOrganization`` (Account, often null). Each carries
    a standard ``assignedUser``.
  * Mentor source ``CMentorProfile``; eligible = ``acceptingNewClients=true`` AND
    ``mentorStatus="Active"`` AND ``assignedUser`` set. The mentor's login User is
    ``CMentorProfile.assignedUser``.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

log = logging.getLogger("cbm_intake.assignments.service")

# --- Entity names ---
ENGAGEMENT = "CEngagement"
MENTOR_PROFILE = "CMentorProfile"
CONTACT = "Contact"
ACCOUNT = "Account"
CLIENT_PROFILE = "CClientProfile"

# --- Values ---
STATUS_SUBMITTED = "Submitted"
STATUS_PENDING = "Pending Acceptance"
MENTOR_STATUS_ACTIVE = "Active"

# Full engagementStatus enum (crm-test metadata 2026-06-19) — the filter's option
# set. Kept here rather than fetched per-request; refresh if the CRM enum changes.
ENGAGEMENT_STATUSES = [
    "Submitted", "Declined", "Pending Acceptance", "Assigned",
    "Assignment Declined", "Assignment Dormant", "Active", "On-Hold",
    "Dormant", "Inactive", "Abandoned", "Completed",
]

# Link of CEngagement -> the hasMany of additional/secondary contacts.
ENGAGEMENT_CONTACTS = "engagementContacts"

# Assignment field differs by entity (verified live crm-test 2026-06-19):
# Contact/Account use the single `assignedUser`; CEngagement and CClientProfile
# have `assignedUser` DISABLED and use the multi-user `assignedUsers`
# (collaborators) field — writing `assignedUserId` to them is silently ignored.
# These two take `assignedUsersIds=[userId]` instead.
USES_ASSIGNED_USERS = {ENGAGEMENT, CLIENT_PROFILE}


def _assigned_user_payload(entity: str, user_id: str) -> dict[str, Any]:
    if entity in USES_ASSIGNED_USERS:
        return {"assignedUsersIds": [user_id]}
    return {"assignedUserId": user_id}


class AssignClient(Protocol):
    """The slice of ``EspoClient`` this module needs (eases test mocking)."""

    async def get(self, entity: str, record_id: str, select: str | None = ...) -> dict[str, Any]: ...
    async def list(self, entity: str, **kwargs: Any) -> dict[str, Any]: ...
    async def list_related(self, entity: str, record_id: str, link: str, **kwargs: Any) -> dict[str, Any]: ...
    async def update(self, entity: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class AssignError(Exception):
    """The chosen mentor is ineligible — a 400-level, user-facing condition."""


async def list_engagements(
    client: AssignClient, statuses: list[str]
) -> list[dict[str, Any]]:
    """Engagements in any of ``statuses``, newest first, with grid display fields."""
    data = await client.list(
        ENGAGEMENT,
        where=[{"type": "in", "attribute": "engagementStatus", "value": list(statuses)}],
        select="name,createdAt,engagementStatus,primaryEngagementContactName,engagementClientName",
        max_size=200,
        order_by="createdAt",
        order="desc",
    )
    return [
        {
            "id": r["id"],
            "name": r.get("name"),
            "createdAt": r.get("createdAt"),
            "status": r.get("engagementStatus"),
            "contactName": r.get("primaryEngagementContactName"),
            "clientName": r.get("engagementClientName"),
        }
        for r in data.get("list", [])
    ]


async def get_engagement_detail(
    client: AssignClient, engagement_id: str
) -> dict[str, Any]:
    """Engagement detail for the popup: primary contact info + mentoring needs.

    Two reads: the engagement, then its primary Contact (for email/phone/company).
    ``mentoringNeedsDescription`` is a wysiwyg field but intake stores plain text;
    the frontend renders it as text.
    """
    eng = await client.get(
        ENGAGEMENT,
        engagement_id,
        select=(
            "name,engagementStatus,createdAt,meetingCadence,mentoringFocusAreas,"
            "mentoringNeedsDescription,engagementNotes,primaryEngagementContactId,"
            "engagementClientName"
        ),
    )
    contact = None
    contact_id = eng.get("primaryEngagementContactId")
    if contact_id:
        c = await client.get(
            CONTACT, contact_id,
            select="name,emailAddress,phoneNumber,accountName,title",
        )
        contact = {
            "name": c.get("name"),
            "email": c.get("emailAddress"),
            "phone": c.get("phoneNumber"),
            "company": c.get("accountName"),
            "title": c.get("title"),
        }

    focus = eng.get("mentoringFocusAreas") or []
    if isinstance(focus, str):  # single-value enums can come back as a bare string
        focus = [focus]
    return {
        "id": engagement_id,
        "name": eng.get("name"),
        "status": eng.get("engagementStatus"),
        "createdAt": eng.get("createdAt"),
        "meetingCadence": eng.get("meetingCadence"),
        "clientName": eng.get("engagementClientName"),
        "contact": contact,
        "focusAreas": focus,
        # Rich-text (wysiwyg) HTML — sanitized + rendered by the frontend.
        "needs": eng.get("mentoringNeedsDescription") or "",
        "notes": eng.get("engagementNotes") or "",
    }


# Shared select for both the assign dropdown and the review list.
_MENTOR_SELECT = (
    "name,createdAt,assignedUserId,assignedUserName,availableCapacity,currentActiveClients,"
    "maximumClientCapacity,yearsOfExperience,mentorType,mentorStatus,recordStatus,"
    "acceptingNewClients,industrySector,mentoringFocusAreas,areaOfExpertise"
)


def _mentor_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r["id"],
        "name": r.get("name"),
        "createdAt": r.get("createdAt"),
        "userId": r.get("assignedUserId"),
        "userName": r.get("assignedUserName"),
        "availableCapacity": r.get("availableCapacity"),
        "assignedClients": r.get("currentActiveClients"),
        "maxCapacity": r.get("maximumClientCapacity"),
        "yearsOfExperience": r.get("yearsOfExperience"),
        "mentorType": r.get("mentorType"),
        "status": r.get("mentorStatus"),
        "acceptingNewClients": bool(r.get("acceptingNewClients")),
        "recordStatus": r.get("recordStatus"),
        "industrySector": r.get("industrySector"),
        "focusAreas": r.get("mentoringFocusAreas") or [],
        "expertise": r.get("areaOfExpertise") or [],
    }


async def list_eligible_mentors(client: AssignClient) -> list[dict[str, Any]]:
    """Mentors accepting new clients, Active, with a linked User (the dropdown)."""
    data = await client.list(
        MENTOR_PROFILE,
        where=[
            {"type": "isTrue", "attribute": "acceptingNewClients"},
            {"type": "equals", "attribute": "mentorStatus", "value": MENTOR_STATUS_ACTIVE},
            {"type": "isNotNull", "attribute": "assignedUserId"},
        ],
        select=_MENTOR_SELECT,
        max_size=200,
        order_by="name",
    )
    # Defensive: isNotNull should already exclude userless rows.
    return [_mentor_row(r) for r in data.get("list", []) if r.get("assignedUserId")]


async def list_all_mentors(client: AssignClient) -> list[dict[str, Any]]:
    """Every mentor profile (any status) for the review/compare list."""
    data = await client.list(
        MENTOR_PROFILE, select=_MENTOR_SELECT, max_size=200, order_by="name"
    )
    return [_mentor_row(r) for r in data.get("list", [])]


async def assign_engagement(
    client: AssignClient, engagement_id: str, mentor_profile_id: str
) -> dict[str, Any]:
    """Assign ``engagement_id`` to ``mentor_profile_id`` and re-home its records.

    Steps (each awaited in order; a later failure leaves earlier writes in place,
    matching the intake orchestrators' partial-progress contract):

      1. Resolve + re-validate the mentor -> their User.
      2. Engagement: set assignedUser + mentorProfile, status -> Pending Acceptance.
      3. Read the engagement's related contact/client/account ids.
      4. Set assignedUser on every contact, the CClientProfile, and the Account.
    """
    mentor = await client.get(
        MENTOR_PROFILE,
        mentor_profile_id,
        select="name,acceptingNewClients,mentorStatus,assignedUserId,assignedUserName",
    )
    user_id = mentor.get("assignedUserId")
    if not user_id:
        raise AssignError("The selected mentor has no linked user account.")
    if not mentor.get("acceptingNewClients") or mentor.get("mentorStatus") != MENTOR_STATUS_ACTIVE:
        raise AssignError(
            "The selected mentor is no longer eligible (not Active / not accepting "
            "new clients). Refresh and try again."
        )

    # 2. The engagement itself (assignedUsers, not assignedUser — see above).
    await client.update(
        ENGAGEMENT,
        engagement_id,
        {
            **_assigned_user_payload(ENGAGEMENT, user_id),
            "mentorProfileId": mentor_profile_id,
            "engagementStatus": STATUS_PENDING,
        },
    )

    # 3. Gather related records.
    eng = await client.get(
        ENGAGEMENT,
        engagement_id,
        select="primaryEngagementContactId,engagementClientId,clientOrganizationId",
    )
    contact_ids: set[str] = set()
    if eng.get("primaryEngagementContactId"):
        contact_ids.add(eng["primaryEngagementContactId"])
    related = await client.list_related(
        ENGAGEMENT, engagement_id, ENGAGEMENT_CONTACTS, select="id", max_size=200
    )
    for r in related.get("list", []):
        contact_ids.add(r["id"])

    # 4. Re-assign contacts, then the client profile + account. Each entity gets
    # whichever assignment field it actually uses (single vs. collaborators).
    for cid in sorted(contact_ids):
        await client.update(CONTACT, cid, _assigned_user_payload(CONTACT, user_id))

    client_profile_updated = False
    if eng.get("engagementClientId"):
        await client.update(
            CLIENT_PROFILE, eng["engagementClientId"],
            _assigned_user_payload(CLIENT_PROFILE, user_id),
        )
        client_profile_updated = True

    account_updated = False
    if eng.get("clientOrganizationId"):
        await client.update(
            ACCOUNT, eng["clientOrganizationId"],
            _assigned_user_payload(ACCOUNT, user_id),
        )
        account_updated = True

    log.info(
        "assigned engagement=%s -> mentor=%s user=%s contacts=%d client=%s account=%s",
        engagement_id, mentor_profile_id, user_id, len(contact_ids),
        client_profile_updated, account_updated,
    )
    return {
        "engagementId": engagement_id,
        "engagementStatus": STATUS_PENDING,
        "mentorProfileId": mentor_profile_id,
        "mentorName": mentor.get("name"),
        "assignedUserId": user_id,
        "assignedUserName": mentor.get("assignedUserName"),
        "contactsUpdated": len(contact_ids),
        "clientProfileUpdated": client_profile_updated,
        "accountUpdated": account_updated,
    }
