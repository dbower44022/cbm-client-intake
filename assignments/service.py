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
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol
from zoneinfo import ZoneInfo

from core.espo import EspoError
from core.stream import post_stream_note

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

# Engagement statuses that count toward a mentor's Active Clients (and, when
# engagementAssignedDate is within 30 days, the Assigned-last-30-days count).
ACTIVE_CLIENT_STATUSES = {"Active", "Assigned", STATUS_PENDING}

# Full engagementStatus enum (crm-test metadata 2026-06-19) — the filter's option
# set. Kept here rather than fetched per-request; refresh if the CRM enum changes.
ENGAGEMENT_STATUSES = [
    "Submitted", "Declined", "Pending Acceptance", "Assigned",
    "Assignment Declined", "Assignment Dormant", "Active", "On-Hold",
    "Dormant", "Inactive", "Abandoned", "Completed",
]

# Link of CEngagement -> the hasMany of additional/secondary contacts.
ENGAGEMENT_CONTACTS = "engagementContacts"

# Link of CEngagement -> its CSession records (same link the session tools use:
# sessions/service._ENGAGEMENT_SESSIONS_LINK — duplicated here because sessions
# imports FROM this module, so importing back would be circular).
SESSION = "CSession"
ENGAGEMENT_SESSIONS_LINK = "engagementSessions"

# Assignment field differs by entity AND by instance. Some entities use the single
# `assignedUser`; others have it DISABLED and use the multi-user `assignedUsers`
# (collaborators) field. The split also differs across instances (crm-test vs
# prod). For entities that use `assignedUsers` anywhere we write BOTH attributes —
# EspoCRM silently ignores the one the entity doesn't have, so the assignment
# sticks on either config without per-instance branching.
# Prod field audit (2026-06-26, verified live): `assignedUser` is DISABLED on
# CEngagement, CClientProfile, CMentorProfile **and Account** (all use
# `assignedUsers`). A plain `assignedUserId` PUT to a disabled-field entity
# returns 200 but stores nothing (the bug that left provisioned mentors
# userless / Accounts un-rehomed). See [[crm-test-assignment-acl-fields]].
# 2026-07-16/17: **Contact** was deliberately switched to Multiple Assigned
# Users on BOTH CRMs (co-mentors need to be assigned to client contacts), so
# its single `assignedUser` is now disabled too — every entity we assign gets
# the dual write.
USES_ASSIGNED_USERS = {ENGAGEMENT, CLIENT_PROFILE, MENTOR_PROFILE, ACCOUNT, CONTACT}


def _assigned_user_payload(entity: str, user_id: str) -> dict[str, Any]:
    if entity in USES_ASSIGNED_USERS:
        return {"assignedUsersIds": [user_id], "assignedUserId": user_id}
    return {"assignedUserId": user_id}


# Public alias for other staff-tool packages (e.g. mentoradmin) that write the
# mentor's User link.
assigned_user_payload = _assigned_user_payload


def assigned_user_id(rec: dict[str, Any]) -> Optional[str]:
    """The assigned User id from a record that may use the single ``assignedUser``
    OR the multi-user ``assignedUsers`` (collaborators) field — whichever holds it.
    Read the mentor's User through this, never ``rec['assignedUserId']`` directly,
    so it works on both crm-test (single) and prod (collaborators)."""
    return rec.get("assignedUserId") or next(iter(rec.get("assignedUsersIds") or []), None)


def assigned_user_name(rec: dict[str, Any]) -> Optional[str]:
    """The assigned User's display name, from either field shape (see
    :func:`assigned_user_id`)."""
    if rec.get("assignedUserName"):
        return rec["assignedUserName"]
    ids = rec.get("assignedUsersIds") or []
    names = rec.get("assignedUsersNames") or {}
    if ids and isinstance(names, dict):
        return names.get(ids[0])
    return None


class AssignClient(Protocol):
    """The slice of ``EspoClient`` this module needs (eases test mocking)."""

    async def get(self, entity: str, record_id: str, select: str | None = ...) -> dict[str, Any]: ...
    async def list(self, entity: str, **kwargs: Any) -> dict[str, Any]: ...
    async def list_related(self, entity: str, record_id: str, link: str, **kwargs: Any) -> dict[str, Any]: ...
    async def update(self, entity: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def create(self, entity: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class AssignError(Exception):
    """The chosen mentor is ineligible — a 400-level, user-facing condition."""


async def list_engagements(
    client: AssignClient, statuses: list[str]
) -> list[dict[str, Any]]:
    """Engagements in any of ``statuses``, newest first, with grid display fields."""
    data = await client.list(
        ENGAGEMENT,
        where=[{"type": "in", "attribute": "engagementStatus", "value": list(statuses)}],
        select=(
            "name,createdAt,engagementStatus,primaryEngagementContactName,"
            "engagementClientName,mentorProfileId,mentorProfileName,"
            "engagementAssignedDate,description"
        ),
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
            # The assigned mentor (CEngagement.mentorProfile). Present => the row
            # shows the mentor name instead of the Select-a-Mentor picker + button.
            "mentorId": r.get("mentorProfileId"),
            "mentorName": r.get("mentorProfileName"),
            # When the mentor was assigned (stamped by assign_engagement; null on
            # pre-0.27.0 assignments and unassigned rows).
            "assignedDate": r.get("engagementAssignedDate"),
            # Internal process notes (the grid's click-to-edit Notes column) —
            # see update_engagement_notes.
            "notes": r.get("description") or "",
        }
        for r in data.get("list", [])
    ]


async def update_engagement_notes(
    client: AssignClient, engagement_id: str, notes: str
) -> dict[str, Any]:
    """Save the grid's internal process notes to ``CEngagement.description``.

    ``description`` is deliberately surfaced ONLY here (the session tools'
    Details tab excludes it — see ``sessions/details.py:_ENTITY_EXCLUDED``), so
    these are staff-internal notes about the assignment, never shown to mentors.
    The intake orchestrator also drops its enum-drift follow-up note into this
    field on create — editing the cell replaces it, which is fine: that note is
    exactly the kind of triage material this column exists for.
    """
    await client.update(ENGAGEMENT, engagement_id, {"description": notes})
    return {"engagementId": engagement_id, "notes": notes}


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
            "engagementClientName,requestedMentorId,requestedMentorName,description"
        ),
    )

    # Requested mentor (DAT-026): a belongsTo → CMentorProfile the client/staff
    # asked for. The `*Name` accessor isn't a defined field, so fall back to a
    # CMentorProfile read; a deleted target (orphaned FK) resolves to no name.
    requested_mentor = None
    requested_id = eng.get("requestedMentorId")
    if requested_id:
        name = eng.get("requestedMentorName")
        if not name:
            try:
                prof = await client.get(MENTOR_PROFILE, requested_id, select="name")
                name = prof.get("name")
            except EspoError:
                name = None
        requested_mentor = {"id": requested_id, "name": name}

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
        "requestedMentor": requested_mentor,
        "contact": contact,
        "focusAreas": focus,
        # Rich-text (wysiwyg) HTML — sanitized + rendered by the frontend.
        "needs": eng.get("mentoringNeedsDescription") or "",
        "notes": eng.get("engagementNotes") or "",
        # The grid's internal process notes (CEngagement.description) — plain
        # text, staff-only (this tool is the field's only UI).
        "internalNotes": eng.get("description") or "",
    }


# Shared select for both the assign dropdown and the review list. The CRM's own
# computed availableCapacity/currentActiveClients are deliberately NOT read —
# crm-test's formula is known-buggy (computes 1 for every mentor), so the client
# counts are derived from CEngagement instead (mentor_engagement_metrics).
_MENTOR_SELECT = (
    "name,createdAt,assignedUserId,assignedUserName,assignedUsersIds,assignedUsersNames,"
    "maximumClientCapacity,yearsOfExperience,mentorType,mentorStatus,recordStatus,"
    "acceptingNewClients,cbmEmail,industrySector,industryExperience,"
    "mentoringFocusAreas,areaOfExpertise"
)

_METRICS_PAGE = 200
_EMPTY_METRICS = {"activeClients": 0, "assignedLast30": 0, "lifetimeClients": 0}


def _parse_espo_datetime(value: Any) -> Optional[datetime]:
    """EspoCRM datetimes are UTC ``YYYY-MM-DD HH:MM:SS`` (dates ``YYYY-MM-DD``)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace(" ", "T"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def espo_now() -> str:
    """Current UTC time in EspoCRM's datetime format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def mentor_engagement_metrics(client: AssignClient) -> dict[str, dict[str, int]]:
    """Per-mentor client counts, from one paginated sweep over CEngagement.

    Grouped by ``mentorProfileId`` in Python — no ``where`` clause, both because
    every engagement contributes to lifetime counts and because prod's field ACL
    rejects filtering on link attributes (the assignedUserId lesson above).

      * ``activeClients``   — status in :data:`ACTIVE_CLIENT_STATUSES`
      * ``assignedLast30``  — active-set AND assigned within the last 30 days
      * ``lifetimeClients`` — every engagement ever linked to the mentor
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    metrics: dict[str, dict[str, int]] = {}
    offset = 0
    while True:
        data = await client.list(
            ENGAGEMENT,
            select="mentorProfileId,engagementStatus,engagementAssignedDate",
            max_size=_METRICS_PAGE,
            offset=offset,
            order_by="createdAt",
            order="asc",
        )
        rows = data.get("list", [])
        for r in rows:
            mentor_id = r.get("mentorProfileId")
            if not mentor_id:
                continue
            m = metrics.setdefault(mentor_id, dict(_EMPTY_METRICS))
            m["lifetimeClients"] += 1
            if r.get("engagementStatus") in ACTIVE_CLIENT_STATUSES:
                m["activeClients"] += 1
                assigned = _parse_espo_datetime(r.get("engagementAssignedDate"))
                if assigned and assigned >= cutoff:
                    m["assignedLast30"] += 1
        if len(rows) < _METRICS_PAGE:
            break
        offset += _METRICS_PAGE
    return metrics


async def _mentor_type_options(client: AssignClient) -> list[str]:
    """The live ``mentorType`` enum options (CRM = source of truth), so the grid
    filters offer every type — not just the ones present in the current roster.
    Best-effort: no metadata access (or a client without the method, e.g. test
    fakes) → [] and the frontend falls back to the values found in the rows."""
    fetch = getattr(client, "metadata_enum_options", None)
    if fetch is None:
        return []
    try:
        options = await fetch(MENTOR_PROFILE, "mentorType")
    except EspoError as exc:
        log.warning("mentorType options unavailable: %s", exc)
        return []
    return [o for o in options or [] if o and o.strip()]


async def _metrics_or_none(client: AssignClient) -> Optional[dict[str, dict[str, int]]]:
    """Metrics, or None when CEngagement can't be read (e.g. a Mentor Admin user
    whose EspoCRM role lacks the grant) — the roster still loads, metrics blank."""
    try:
        return await mentor_engagement_metrics(client)
    except EspoError as exc:
        log.warning("mentor engagement metrics unavailable (CEngagement read failed): %s", exc)
        return None


def client_counts_for(
    metrics: Optional[dict[str, dict[str, int]]],
    mentor_id: str,
    max_cap: Optional[int],
) -> dict[str, Any]:
    """The five client-count fields for one mentor, from a metrics sweep.

    Shared by the grid rows AND the /mentoradmin detail card so both views
    always agree. ``metrics=None`` (sweep unavailable) → all-None counts.
    """
    m = metrics.get(mentor_id, _EMPTY_METRICS) if metrics is not None else None
    if m is None:
        return {
            "activeClients": None, "assignedLast30": None, "lifetimeClients": None,
            "availableCapacity": None, "maxCapacity": max_cap,
        }
    if max_cap is None:
        available: Optional[int] = None
    elif max_cap == -1:  # CRM convention: -1 = unlimited capacity
        available = -1
    else:
        available = max_cap - m["activeClients"]
    return {
        "activeClients": m["activeClients"],
        "assignedLast30": m["assignedLast30"],
        "lifetimeClients": m["lifetimeClients"],
        "availableCapacity": available,
        "maxCapacity": max_cap,
    }


def _mentor_row(
    r: dict[str, Any], metrics: Optional[dict[str, dict[str, int]]]
) -> dict[str, Any]:
    return {
        "id": r["id"],
        "name": r.get("name"),
        "createdAt": r.get("createdAt"),
        "userId": assigned_user_id(r),
        "userName": assigned_user_name(r),
        **client_counts_for(metrics, r["id"], r.get("maximumClientCapacity")),
        "yearsOfExperience": r.get("yearsOfExperience"),
        "mentorType": r.get("mentorType"),
        "status": r.get("mentorStatus"),
        "acceptingNewClients": bool(r.get("acceptingNewClients")),
        "recordStatus": r.get("recordStatus"),
        "cbmEmail": r.get("cbmEmail"),
        "industrySector": r.get("industrySector"),
        "industryExperience": r.get("industryExperience") or [],
        "focusAreas": r.get("mentoringFocusAreas") or [],
        "expertise": r.get("areaOfExpertise") or [],
    }


async def list_eligible_mentors(client: AssignClient) -> dict[str, Any]:
    """Mentors accepting new clients, Active, with a linked User (the dropdown).

    Returns ``{"mentors": [...], "metricsAvailable": bool}`` — the same envelope
    as :func:`list_all_mentors`, ready to serve as the endpoint response.
    """
    data = await client.list(
        MENTOR_PROFILE,
        where=[
            {"type": "isTrue", "attribute": "acceptingNewClients"},
            {"type": "equals", "attribute": "mentorStatus", "value": MENTOR_STATUS_ACTIVE},
        ],
        select=_MENTOR_SELECT,
        max_size=200,
        order_by="name",
    )
    metrics = await _metrics_or_none(client)
    # Filter userless rows in Python rather than the query: prod EspoCRM's ACL
    # forbids *filtering* CMentorProfile by assignedUserId in a `where` clause
    # ("Forbidden attribute 'assignedUserId' in where" → 400), even though it's
    # readable in `select`. crm-test allows it; prod (stock, tighter field ACL)
    # does not. Dropping the clause keeps the dropdown working on both. The
    # has-user test reads either assignedUser/assignedUsers (prod uses the latter).
    rows = [_mentor_row(r, metrics) for r in data.get("list", []) if assigned_user_id(r)]
    return {"mentors": rows, "metricsAvailable": metrics is not None}


async def list_all_mentors(client: AssignClient) -> dict[str, Any]:
    """Every mentor profile (any status) for the review/roster lists."""
    data = await client.list(
        MENTOR_PROFILE, select=_MENTOR_SELECT, max_size=200, order_by="name"
    )
    metrics = await _metrics_or_none(client)
    rows = [_mentor_row(r, metrics) for r in data.get("list", [])]
    return {
        "mentors": rows,
        "metricsAvailable": metrics is not None,
        "mentorTypeOptions": await _mentor_type_options(client),
    }


async def _merged_assignment_payload(
    client: AssignClient, entity: str, record_id: str,
    user_id: str, all_user_ids: list[str],
) -> dict[str, Any]:
    """Assignment payload for a client-side record that MERGES ``all_user_ids``
    (the new mentor + the engagement's co-mentors) into the record's existing
    ``assignedUsers`` instead of overwriting the list. An overwrite silently
    revoked the co-mentor access the session tools stamp onto the client
    profile / company (``sessions.service.add_comentor`` — the 2026-07-17
    review finding). The single ``assignedUserId`` still moves to the new
    mentor; entities on the single field get exactly the old payload.
    """
    payload = _assigned_user_payload(entity, user_id)
    if entity not in USES_ASSIGNED_USERS:
        return payload
    rec = await client.get(entity, record_id, select="assignedUsersIds")
    merged = list(rec.get("assignedUsersIds") or [])
    merged += [uid for uid in all_user_ids if uid not in merged]
    payload["assignedUsersIds"] = merged
    return payload


async def assign_engagement(
    client: AssignClient, engagement_id: str, mentor_profile_id: str
) -> dict[str, Any]:
    """Assign ``engagement_id`` to ``mentor_profile_id`` and re-home its records.

    Steps (each awaited in order; a later failure leaves earlier writes in place,
    matching the intake orchestrators' partial-progress contract):

      0. Re-read the engagement and verify it is still assignable (Submitted,
         no mentor) — a stale grid in another browser/tab must not overwrite an
         assignment already saved by someone else.
      1. Resolve + re-validate the mentor -> their User.
      2. Engagement: set assignedUser + mentorProfile, status -> Pending Acceptance.
      3. Read the engagement's related contact/client/account ids.
      4. Set assignedUser on every contact, the CClientProfile, and the Account —
         merging into (never overwriting) each record's ``assignedUsers`` so
         co-mentor access stamps survive.
    """
    current = await client.get(
        ENGAGEMENT,
        engagement_id,
        select="name,engagementStatus,mentorProfileId,mentorProfileName",
    )
    if current.get("mentorProfileId"):
        raise AssignError(
            "This engagement has already been assigned to "
            + (current.get("mentorProfileName") or "another mentor")
            + " — likely from another window or an out-of-date list. Nothing was "
            "changed; refresh the list to see its current state."
        )
    if current.get("engagementStatus") != STATUS_SUBMITTED:
        raise AssignError(
            "This engagement is no longer awaiting assignment (its status is now "
            f"“{current.get('engagementStatus') or 'unknown'}”). Nothing was "
            "changed; refresh the list to see its current state."
        )

    mentor = await client.get(
        MENTOR_PROFILE,
        mentor_profile_id,
        select="name,acceptingNewClients,mentorStatus,"
        "assignedUserId,assignedUserName,assignedUsersIds,assignedUsersNames",
    )
    user_id = assigned_user_id(mentor)
    if not user_id:
        raise AssignError("The selected mentor has no linked user account.")
    if not mentor.get("acceptingNewClients") or mentor.get("mentorStatus") != MENTOR_STATUS_ACTIVE:
        raise AssignError(
            "The selected mentor is no longer eligible (not Active / not accepting "
            "new clients). Refresh and try again."
        )

    # 2. The engagement itself (assignedUsers, not assignedUser — see above).
    # engagementAssignedDate is stamped here — nothing CRM-side fills it, and the
    # Assigned-last-30-days metric depends on it.
    # Co-mentors (additionalMentors) see the engagement only through their
    # membership in assignedUsers (Mentor Role reads CEngagement at "own"), so a
    # reassignment must MERGE their users into the write, not overwrite the list
    # with just the new mentor. Best-effort: an unreadable link just assigns the
    # new mentor alone.
    assigned_ids = [user_id]
    try:
        co = await client.list_related(
            ENGAGEMENT, engagement_id, "additionalMentors",
            select="assignedUserId,assignedUsersIds", max_size=50,
        )
        for r in co.get("list", []):
            uid = assigned_user_id(r)
            if uid and uid not in assigned_ids:
                assigned_ids.append(uid)
    except EspoError as exc:
        # P1-10: this read feeds the assignedUsers merge below — when it fails,
        # the write proceeds with just the new mentor, silently revoking every
        # co-mentor's engagement access (the defect class Doug already reported
        # once). The failure must be visible in the logs.
        log.warning(
            "co-mentor list unreadable on CEngagement/%s; the assignedUsers "
            "write may drop co-mentors: %s", engagement_id, exc,
        )
    await client.update(
        ENGAGEMENT,
        engagement_id,
        {
            **_assigned_user_payload(ENGAGEMENT, user_id),
            "assignedUsersIds": assigned_ids,
            "mentorProfileId": mentor_profile_id,
            "engagementStatus": STATUS_PENDING,
            "engagementAssignedDate": espo_now(),
        },
    )

    # The core assignment (steps 1-2) is done. The downstream re-homing below is
    # best-effort and per-target: a CRM failure on one record is recorded in
    # ``reassignmentErrors`` and reported to the staffer, rather than raising and
    # leaving them unsure whether the engagement itself was assigned (it was).
    reassignment_errors: list[dict[str, str]] = []

    # 3. Gather related records.
    contact_ids: set[str] = set()
    client_id = None
    account_id = None
    try:
        eng = await client.get(
            ENGAGEMENT,
            engagement_id,
            select="primaryEngagementContactId,engagementClientId,clientOrganizationId",
        )
        if eng.get("primaryEngagementContactId"):
            contact_ids.add(eng["primaryEngagementContactId"])
        related = await client.list_related(
            ENGAGEMENT, engagement_id, ENGAGEMENT_CONTACTS, select="id", max_size=200
        )
        for r in related.get("list", []):
            contact_ids.add(r["id"])
        client_id = eng.get("engagementClientId")
        account_id = eng.get("clientOrganizationId")
    except EspoError as exc:
        reassignment_errors.append({"entity": ENGAGEMENT, "id": engagement_id, "error": str(exc)})

    # 4. Re-assign contacts, then the client profile + account. Each entity gets
    # whichever assignment field it actually uses (single vs. collaborators);
    # collaborators-field entities are MERGED, not overwritten — co-mentors
    # stamped onto these records by the session tools must keep their access.
    contacts_updated = 0
    for cid in sorted(contact_ids):
        try:
            await client.update(
                CONTACT, cid,
                await _merged_assignment_payload(client, CONTACT, cid, user_id, assigned_ids),
            )
            contacts_updated += 1
        except EspoError as exc:
            reassignment_errors.append({"entity": CONTACT, "id": cid, "error": str(exc)})

    client_profile_updated = False
    if client_id:
        try:
            await client.update(
                CLIENT_PROFILE, client_id,
                await _merged_assignment_payload(
                    client, CLIENT_PROFILE, client_id, user_id, assigned_ids
                ),
            )
            client_profile_updated = True
        except EspoError as exc:
            reassignment_errors.append({"entity": CLIENT_PROFILE, "id": client_id, "error": str(exc)})

    account_updated = False
    if account_id:
        try:
            await client.update(
                ACCOUNT, account_id,
                await _merged_assignment_payload(
                    client, ACCOUNT, account_id, user_id, assigned_ids
                ),
            )
            account_updated = True
        except EspoError as exc:
            reassignment_errors.append({"entity": ACCOUNT, "id": account_id, "error": str(exc)})

    # Durable audit trail: a stream note on the engagement marks this as an
    # app-side assignment (a plain field update by the same user is otherwise
    # indistinguishable in Espo history from a hand edit in the CRM UI) and
    # records the re-homing outcome. Best-effort — never fails the assignment.
    def _rehomed(label: str, present: Any, updated: bool) -> str:
        if not present:
            return f"{label}: no link"
        return label if updated else f"{label}: FAILED"

    note = (
        f"Assigned to {mentor.get('name') or 'the selected mentor'} via the Client "
        f"Administration app — status set to {STATUS_PENDING}; re-homed to the "
        f"mentor's user: {contacts_updated}/{len(contact_ids)} contact(s), "
        f"{_rehomed('client profile', client_id, client_profile_updated)}, "
        f"{_rehomed('company', account_id, account_updated)}."
    )
    if reassignment_errors:
        note += (
            f" {len(reassignment_errors)} related record(s) could not be re-homed —"
            " reassign them in the CRM."
        )
    await post_stream_note(client, ENGAGEMENT, engagement_id, note)

    log.info(
        "assigned engagement=%s -> mentor=%s user=%s contacts=%d/%d client=%s account=%s errors=%d",
        engagement_id, mentor_profile_id, user_id, contacts_updated, len(contact_ids),
        client_profile_updated, account_updated, len(reassignment_errors),
    )
    if reassignment_errors:
        log.warning("assign engagement=%s partial re-homing: %s", engagement_id, reassignment_errors)
    return {
        "engagementId": engagement_id,
        "engagementStatus": STATUS_PENDING,
        "mentorProfileId": mentor_profile_id,
        "mentorName": mentor.get("name"),
        "assignedUserId": user_id,
        "assignedUserName": mentor.get("assignedUserName"),
        "contactsUpdated": contacts_updated,
        "contactsTotal": len(contact_ids),
        "clientProfileUpdated": client_profile_updated,
        "accountUpdated": account_updated,
        "reassignmentErrors": reassignment_errors,
    }


async def reassign_engagement(
    client: AssignClient,
    engagement_id: str,
    mentor_profile_id: str,
    actor: Optional[str] = None,
) -> dict[str, Any]:
    """Replace the engagement's PRIMARY mentor with ``mentor_profile_id``.

    The counterpart to :func:`assign_engagement` for an engagement that already
    has a mentor. Steps (core write first, everything downstream best-effort
    and per-target, the assign contract):

      0. Re-read: the engagement must currently HAVE a mentor (else use Assign)
         and the new mentor must differ.
      1. The new mentor clears the same bar as an initial assignment
         (Active + accepting new clients + linked User).
      2. Resolve the OLD mentor's User for un-stamping. Co-mentors' Users are
         PROTECTED — never removed, and merged into every multi-user write
         (the v0.76.1 merge rule).
      3. Engagement: ``mentorProfile`` -> new mentor; ``assignedUsers`` swaps
         old User for new (old kept when a co-mentor shares it);
         ``engagementAssignedDate`` re-stamped (Days Assigned counts the
         CURRENT mentor's tenure). ``engagementStatus`` is deliberately NOT
         changed — a replacement doesn't restart the acceptance flow.
      4. Client records re-homed so the new mentor can edit everything:
         every related Contact (single ``assignedUser`` -> new User), the
         CClientProfile and the Account (swap-merge on ``assignedUsers``).
      5. The engagement's CSession records: new User stamped onto every
         session; old User removed except from sessions they personally own
         (their ``assignedUser``) — the remove_comentor convention.
      6. History: a stream note on the engagement —
         "Mentor X was replaced with Mentor Y on MM/DD/YYYY by user NAME."
         (Doug's required wording), plus the re-homing outcome.
    """
    current = await client.get(
        ENGAGEMENT,
        engagement_id,
        select="name,engagementStatus,mentorProfileId,mentorProfileName,assignedUsersIds",
    )
    old_profile_id = current.get("mentorProfileId")
    if not old_profile_id:
        raise AssignError(
            "This engagement has no mentor yet — use Assign (the row's dropdown "
            "or right-click → Assign mentor) instead of Reassign."
        )
    if old_profile_id == mentor_profile_id:
        raise AssignError(
            "That mentor is already this engagement's assigned mentor — pick a "
            "different mentor to reassign."
        )

    mentor = await client.get(
        MENTOR_PROFILE,
        mentor_profile_id,
        select="name,acceptingNewClients,mentorStatus,"
        "assignedUserId,assignedUserName,assignedUsersIds,assignedUsersNames",
    )
    new_user_id = assigned_user_id(mentor)
    if not new_user_id:
        raise AssignError("The selected mentor has no linked user account.")
    if not mentor.get("acceptingNewClients") or mentor.get("mentorStatus") != MENTOR_STATUS_ACTIVE:
        raise AssignError(
            "The selected mentor is no longer eligible (not Active / not accepting "
            "new clients). Refresh and try again."
        )

    # The outgoing mentor's User (to un-stamp). A deleted/unreadable old profile
    # just means nothing to remove — the swap still proceeds.
    old_name = current.get("mentorProfileName")
    old_user_id = None
    try:
        old = await client.get(
            MENTOR_PROFILE, old_profile_id, select="name,assignedUserId,assignedUsersIds"
        )
        old_user_id = assigned_user_id(old)
        old_name = old.get("name") or old_name
    except EspoError as exc:
        log.warning(
            "outgoing mentor profile %s unreadable during reassign of "
            "CEngagement/%s — their User cannot be un-stamped: %s",
            old_profile_id, engagement_id, exc,
        )
    old_name = old_name or "the previous mentor"

    # Users that must survive every write: the engagement's co-mentors.
    protected: set[str] = set()
    try:
        co = await client.list_related(
            ENGAGEMENT, engagement_id, "additionalMentors",
            select="assignedUserId,assignedUsersIds", max_size=50,
        )
        for r in co.get("list", []):
            uid = assigned_user_id(r)
            if uid:
                protected.add(uid)
    except EspoError as exc:
        # Same consequence as the assign path (P1-10): an unreadable co-mentor
        # list means the swap can drop co-mentors from assignedUsers.
        log.warning(
            "co-mentor list unreadable on CEngagement/%s; the reassign "
            "may drop co-mentors from assignedUsers: %s", engagement_id, exc,
        )

    def _swap(ids: list[str]) -> list[str]:
        """Current assigned users with old -> new swapped: the old mentor's User
        removed (unless a co-mentor shares it), the new mentor's + all
        co-mentors' Users present."""
        out = [u for u in ids if u != old_user_id or u in protected]
        for uid in [new_user_id, *sorted(protected)]:
            if uid not in out:
                out.append(uid)
        return out

    # 3. The core write — everything after this is best-effort.
    await client.update(
        ENGAGEMENT,
        engagement_id,
        {
            "mentorProfileId": mentor_profile_id,
            "assignedUserId": new_user_id,
            "assignedUsersIds": _swap(list(current.get("assignedUsersIds") or [])),
            "engagementAssignedDate": espo_now(),
        },
    )

    reassignment_errors: list[dict[str, str]] = []

    # 4. Related client records.
    contact_ids: set[str] = set()
    client_id = None
    account_id = None
    try:
        eng = await client.get(
            ENGAGEMENT,
            engagement_id,
            select="primaryEngagementContactId,engagementClientId,clientOrganizationId",
        )
        if eng.get("primaryEngagementContactId"):
            contact_ids.add(eng["primaryEngagementContactId"])
        related = await client.list_related(
            ENGAGEMENT, engagement_id, ENGAGEMENT_CONTACTS, select="id", max_size=200
        )
        for r in related.get("list", []):
            contact_ids.add(r["id"])
        client_id = eng.get("engagementClientId")
        account_id = eng.get("clientOrganizationId")
    except EspoError as exc:
        reassignment_errors.append({"entity": ENGAGEMENT, "id": engagement_id, "error": str(exc)})

    async def _swap_update(entity: str, rid: str) -> bool:
        payload: dict[str, Any] = {"assignedUserId": new_user_id}
        if entity in USES_ASSIGNED_USERS:
            rec = await client.get(entity, rid, select="assignedUsersIds")
            payload["assignedUsersIds"] = _swap(list(rec.get("assignedUsersIds") or []))
        await client.update(entity, rid, payload)
        return True

    contacts_updated = 0
    for cid in sorted(contact_ids):
        try:
            await _swap_update(CONTACT, cid)
            contacts_updated += 1
        except EspoError as exc:
            reassignment_errors.append({"entity": CONTACT, "id": cid, "error": str(exc)})

    client_profile_updated = False
    if client_id:
        try:
            client_profile_updated = await _swap_update(CLIENT_PROFILE, client_id)
        except EspoError as exc:
            reassignment_errors.append({"entity": CLIENT_PROFILE, "id": client_id, "error": str(exc)})

    account_updated = False
    if account_id:
        try:
            account_updated = await _swap_update(ACCOUNT, account_id)
        except EspoError as exc:
            reassignment_errors.append({"entity": ACCOUNT, "id": account_id, "error": str(exc)})

    # 5. The engagement's sessions (CSession read/edit=own rides assignedUsers,
    # so without the stamp the new mentor can't see or edit the history).
    # Per-session best-effort; the old mentor keeps sessions they personally own.
    sessions_updated = 0
    sessions_total = 0
    try:
        sess = await client.list_related(
            ENGAGEMENT, engagement_id, ENGAGEMENT_SESSIONS_LINK,
            select="assignedUserId,assignedUsersIds", max_size=200,
        )
        for s in sess.get("list", []):
            sessions_total += 1
            cur = list(s.get("assignedUsersIds") or [])
            new_ids = list(cur)
            if new_user_id not in new_ids:
                new_ids.append(new_user_id)
            if (
                old_user_id
                and old_user_id in new_ids
                and old_user_id not in protected
                and s.get("assignedUserId") != old_user_id
            ):
                new_ids = [u for u in new_ids if u != old_user_id]
            if new_ids == cur:
                sessions_updated += 1  # already correct
                continue
            try:
                await client.update(SESSION, s["id"], {"assignedUsersIds": new_ids})
                sessions_updated += 1
            except EspoError as exc:
                reassignment_errors.append({"entity": SESSION, "id": s["id"], "error": str(exc)})
    except EspoError as exc:
        reassignment_errors.append(
            {"entity": SESSION, "id": engagement_id, "error": str(exc)}
        )

    # 6. History — Doug's exact wording first, audit detail after. Date in
    # CBM's timezone (Cleveland), not UTC, so the stamp matches the office day.
    when = datetime.now(ZoneInfo("America/New_York")).strftime("%m/%d/%Y")
    note = (
        f"Mentor {old_name} was replaced with Mentor {mentor.get('name')} on "
        f"{when} by user {actor or 'unknown'}. "
        f"(Client Administration app — re-homed to the new mentor's user: "
        f"{contacts_updated}/{len(contact_ids)} contact(s), "
        f"{'client profile' if client_profile_updated else ('client profile: FAILED' if client_id else 'client profile: no link')}, "
        f"{'company' if account_updated else ('company: FAILED' if account_id else 'company: no link')}, "
        f"{sessions_updated}/{sessions_total} session(s).)"
    )
    if reassignment_errors:
        note += (
            f" {len(reassignment_errors)} related record(s) could not be re-homed —"
            " reassign them in the CRM."
        )
    await post_stream_note(client, ENGAGEMENT, engagement_id, note)

    log.info(
        "reassigned engagement=%s mentor %s -> %s user %s -> %s contacts=%d/%d "
        "client=%s account=%s sessions=%d/%d errors=%d",
        engagement_id, old_profile_id, mentor_profile_id, old_user_id, new_user_id,
        contacts_updated, len(contact_ids), client_profile_updated, account_updated,
        sessions_updated, sessions_total, len(reassignment_errors),
    )
    if reassignment_errors:
        log.warning("reassign engagement=%s partial re-homing: %s", engagement_id, reassignment_errors)
    return {
        "engagementId": engagement_id,
        "engagementStatus": current.get("engagementStatus"),
        "mentorProfileId": mentor_profile_id,
        "mentorName": mentor.get("name"),
        "oldMentorName": old_name,
        "assignedUserId": new_user_id,
        "contactsUpdated": contacts_updated,
        "contactsTotal": len(contact_ids),
        "clientProfileUpdated": client_profile_updated,
        "accountUpdated": account_updated,
        "sessionsUpdated": sessions_updated,
        "sessionsTotal": sessions_total,
        "reassignmentErrors": reassignment_errors,
    }
