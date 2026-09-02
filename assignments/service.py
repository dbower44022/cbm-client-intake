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
  * ``CMentorProfile.lastClientAssignedDate`` (datetime) — the mentor-side
    "last given a new client" stamp, written by the Assign/Reassign actions
    here and by nothing else. Feature-detected, so it is inert until the CRM
    field is built (spec: ``cmentorprofile-last-client-assigned-field.md``).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol
from zoneinfo import ZoneInfo

from core import inline_images
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

# Default filter: every status that needs staff action on first login.
DEFAULT_FILTER_STATUSES = [STATUS_SUBMITTED, "Assignment Declined", "Assignment Dormant"]

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
    so it works on both crm-test (single) and prod (collaborators).

    NOTE: on the collaborators shape this returns the FIRST listed user — the
    right semantic for "the mentor a profile belongs to". To test whether a
    record is assigned to a PARTICULAR user, use :func:`is_assigned_to` (which
    checks the whole list), never ``assigned_user_id(rec) == user_id``.
    """
    return rec.get("assignedUserId") or next(iter(rec.get("assignedUsersIds") or []), None)


def is_assigned_to(rec: dict[str, Any], user_id: Optional[str]) -> bool:
    """Whether ``user_id`` is the record's assigned user — the single
    ``assignedUser`` OR ANY member of the ``assignedUsers`` collaborators list.

    Membership must be tested over the whole list, never ``[0]`` (P2,
    reliability review 2026-07-17): on a collaborators-shaped CRM a profile
    listing someone else first would make the mentor's own profile
    unresolvable — and an equality test against the first entry could resolve
    someone ELSE's profile as "mine".
    """
    if not user_id:
        return False
    if rec.get("assignedUserId") == user_id:
        return True
    return user_id in (rec.get("assignedUsersIds") or [])


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
    async def metadata_enum_options(self, entity: str, field: str) -> list[str] | None: ...


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
            "engagementClientName,engagementClientId,"
            "clientOrganizationName,clientOrganizationId,"
            "mentorProfileId,mentorProfileName,"
            "engagementAssignedDate,description"
        ),
        max_size=200,
        order_by="createdAt",
        order="desc",
    )
    rows = data.get("list", [])
    await _fill_company_names(client, rows)
    return [
        {
            "id": r["id"],
            "name": r.get("name"),
            "createdAt": r.get("createdAt"),
            "status": r.get("engagementStatus"),
            "contactName": r.get("primaryEngagementContactName"),
            "clientName": r.get("engagementClientName"),
            # The client's COMPANY (CEngagement.clientOrganization, or resolved
            # through the client profile — see _fill_company_names). Its own
            # grid column; blank when the CRM holds no company for the client.
            "companyName": r.get("clientOrganizationName"),
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
        for r in rows
    ]


async def _fill_company_names(
    client: AssignClient, rows: list[dict[str, Any]]
) -> None:
    """Fill each row's ``clientOrganizationName`` through its client profile.

    Intake-created engagements carry the Account on ``CClientProfile.linkedCompany``
    only — ``CEngagement.clientOrganization`` is null — so the grid's Company
    column would be empty for exactly the rows this tool exists to work. Mirrors
    ``sessions.service.fill_company_fallback`` (duplicated rather than imported:
    sessions imports FROM this module). Mutates ``rows`` in place, one read per
    DISTINCT profile. Best-effort — a profile the user can't read stays blank.
    """
    need = {
        r["engagementClientId"] for r in rows
        if not r.get("clientOrganizationName") and r.get("engagementClientId")
    }
    if not need:
        return

    async def _resolve(profile_id: str) -> tuple[str, dict[str, Any] | None]:
        try:
            return profile_id, await client.get(
                CLIENT_PROFILE, profile_id,
                select="linkedCompanyId,linkedCompanyName",
            )
        except EspoError:
            log.warning("assignments: company lookup failed for CClientProfile %s",
                        profile_id)
            return profile_id, None

    resolved = dict(await asyncio.gather(*(_resolve(p) for p in need)))
    for r in rows:
        if r.get("clientOrganizationName") or not r.get("engagementClientId"):
            continue
        profile = resolved.get(r["engagementClientId"]) or {}
        if profile.get("linkedCompanyName"):
            r["clientOrganizationName"] = profile["linkedCompanyName"]


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


# --- Engagement editing (the detail popup's Edit mode) -----------------------
#
# ONE declared field spec serves as BOTH the edit-form layout and the
# server-side update whitelist — the pattern every staff tool in this suite
# follows, so a field that is not listed here can never be smuggled into the
# update by a hand-rolled request. Enum options are read LIVE from CRM
# metadata (the CRM stays the source of truth for its own vocabulary), and a
# value outside the live options is DROPPED rather than allowed to 400 the
# whole save — the platform-wide rule that optional fields never block a save.
#
# The assigned MENTOR is deliberately NOT here. Changing `mentorProfile` is not
# a field write: it has to re-home the contacts, client profile, company and
# sessions, stamp the mentor, post the history note and re-derive the Drive
# grants. That is `assign_engagement` / `reassign_engagement`, and the edit
# form hands off to them instead of writing the link itself.

PARTNER_PROFILE = "CPartnerProfile"

ENGAGEMENT_EDIT_FIELDS: tuple[dict[str, Any], ...] = (
    {
        "name": "name", "label": "Engagement name", "type": "varchar",
        "group": "Engagement", "required": True, "maxLength": 255,
    },
    {
        "name": "engagementStatus", "label": "Status", "type": "enum",
        "group": "Engagement", "required": True, "fallback": ENGAGEMENT_STATUSES,
    },
    {
        "name": "meetingCadence", "label": "Meeting cadence", "type": "enum",
        "group": "Engagement",
    },
    {
        "name": "mentoringFocusAreas", "label": "Focus areas", "type": "multiEnum",
        "group": "Engagement",
    },
    {
        "name": "referringPartner", "label": "Referring partner", "type": "link",
        "entity": PARTNER_PROFILE, "group": "Attribution",
    },
    {
        "name": "requestedMentor", "label": "Requested mentor", "type": "link",
        "entity": MENTOR_PROFILE, "group": "Attribution",
    },
    {
        "name": "mentoringNeedsDescription", "label": "Mentoring needs",
        "type": "wysiwyg", "group": "Narrative",
    },
    {
        "name": "engagementNotes", "label": "Engagement notes",
        "type": "wysiwyg", "group": "Narrative",
    },
    {
        "name": "description", "label": "Internal notes", "type": "text",
        "group": "Narrative",
        "help": "Staff-only. The same notes as the grid's Notes column — never shown to the mentor.",
    },
)

_EDIT_FIELDS_BY_NAME = {f["name"]: f for f in ENGAGEMENT_EDIT_FIELDS}

# EspoCRM refuses a page larger than `recordListMaxSizeLimit` (200) with a 403
# rather than truncating, so link-picker options are PAGED, never asked for in
# one big page — the defect that emptied every curated picker in production
# (v0.202.2). The overall cap keeps a large roster from becoming an unusable
# select; a stored value outside it is added back by :func:`_link_field_options`.
_LINK_OPTION_PAGE = 200
_LINK_OPTION_MAX = 1000

_TEXT_MAX_LENGTH = 65535


async def _link_options(client: AssignClient, entity: str) -> list[dict[str, str]]:
    """Every readable record of ``entity`` as ``{id, name}``, A→Z, paged."""
    out: list[dict[str, str]] = []
    offset = 0
    while len(out) < _LINK_OPTION_MAX:
        data = await client.list(
            entity, select="name", max_size=_LINK_OPTION_PAGE, offset=offset,
            order_by="name", order="asc",
        )
        rows = data.get("list") or []
        for r in rows:
            if r.get("id"):
                out.append({"id": r["id"], "name": r.get("name") or "(unnamed)"})
        offset += len(rows)
        total = data.get("total")
        if not rows or (isinstance(total, int) and offset >= total):
            break
    return out


async def _link_field_options(
    client: AssignClient, spec: dict[str, Any], value_id: Any, value_name: Any
) -> dict[str, Any]:
    """The option list for one link field, degraded rather than broken.

    A list the user's role forbids leaves the picker read-only (``options``
    absent) instead of failing the whole form, and the record's STORED value is
    always present in the list — so a save can never silently drop a linked
    record just because it fell outside the page cap.
    """
    try:
        options = await _link_options(client, spec["entity"])
    except EspoError as exc:
        log.warning(
            "assignments: %s options unavailable for the %s picker: %s",
            spec["entity"], spec["name"], exc,
        )
        return {"optionsUnavailable": True}
    if value_id and not any(o["id"] == value_id for o in options):
        options.insert(0, {"id": value_id, "name": value_name or "(no longer in the system)"})
    return {"options": options}


async def _live_options(
    client: AssignClient, spec: dict[str, Any]
) -> Optional[list[str]]:
    """The live CRM options for an enum/multiEnum field, with the module's own
    list as the fallback when the metadata read fails — None when neither is
    available, which every caller reads as "don't filter" (fail open, like
    every other enum path in this product)."""
    try:
        options = await client.metadata_enum_options(ENGAGEMENT, spec["name"])
    except EspoError as exc:
        log.warning("assignments: enum options unavailable for %s: %s", spec["name"], exc)
        options = None
    if options is None:
        options = spec.get("fallback")
    return list(options) if options else None


async def _enum_field_options(
    client: AssignClient, spec: dict[str, Any]
) -> dict[str, Any]:
    """:func:`_live_options` in the shape the edit form wants."""
    options = await _live_options(client, spec)
    return {"options": options} if options else {"optionsUnavailable": True}


def _edit_select() -> str:
    """The ``select`` covering every editable field (links read as id + name)."""
    names: list[str] = []
    for f in ENGAGEMENT_EDIT_FIELDS:
        if f["type"] == "link":
            names.extend((f"{f['name']}Id", f"{f['name']}Name"))
        else:
            names.append(f["name"])
    return ",".join(names)


async def get_engagement_edit_form(
    client: AssignClient, engagement_id: str
) -> dict[str, Any]:
    """The Edit-mode form for one engagement: the spec, its current values, and
    the live option sets. Fetched only when the user presses Edit, so the read
    path of the detail popup keeps its two reads.
    """
    eng = await client.get(ENGAGEMENT, engagement_id, select=_edit_select())
    # Long-form fields render as the type the LIVE CRM gives them — this is how
    # `description` upgrades from a textarea to the rich editor the day the CRM
    # field is converted to wysiwyg, with no deploy (see live_wysiwyg_fields).
    live_wysiwyg = await live_wysiwyg_fields(client)

    async def _one(spec: dict[str, Any]) -> dict[str, Any]:
        field: dict[str, Any] = {
            k: spec[k] for k in ("name", "label", "type", "group") if k in spec
        }
        if spec["type"] in ("text", "wysiwyg"):
            field["type"] = "wysiwyg" if spec["name"] in live_wysiwyg else "text"
        if spec.get("required"):
            field["required"] = True
        if spec.get("help"):
            field["help"] = spec["help"]
        if spec["type"] == "link":
            value_id = eng.get(f"{spec['name']}Id")
            field["value"] = value_id or ""
            field["valueName"] = eng.get(f"{spec['name']}Name") or ""
            field["entity"] = spec["entity"]
            field.update(await _link_field_options(client, spec, value_id, field["valueName"]))
        elif spec["type"] == "multiEnum":
            value = eng.get(spec["name"]) or []
            field["value"] = [value] if isinstance(value, str) else list(value)
            field.update(await _enum_field_options(client, spec))
        elif spec["type"] == "enum":
            field["value"] = eng.get(spec["name"]) or ""
            field.update(await _enum_field_options(client, spec))
        else:
            field["value"] = eng.get(spec["name"]) or ""
        return field

    fields = await asyncio.gather(*(_one(spec) for spec in ENGAGEMENT_EDIT_FIELDS))
    return {"id": engagement_id, "name": eng.get("name"), "fields": list(fields)}


def _clean_enum(value: Any, options: Optional[list[str]]) -> tuple[Any, list[str]]:
    """An enum value filtered to the live options — drifted values are dropped,
    never allowed to 400 the save. Returns ``(kept, dropped)``; a missing option
    list means the metadata read failed, so nothing is dropped (fail open)."""
    if options is None:
        return value, []
    if isinstance(value, list):
        kept = [v for v in value if v in options]
        return kept, [v for v in value if v not in options]
    if value and value not in options:
        return "", [value]
    return value, []


async def update_engagement(
    client: AssignClient, engagement_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    """Apply an Edit-mode save to ``CEngagement``.

    Only fields declared in :data:`ENGAGEMENT_EDIT_FIELDS` are written —
    anything else in ``changes`` is dropped silently, because the whitelist IS
    the contract. Enum values outside the live CRM options are dropped too (and
    named in the result) rather than failing the save; a required field the
    caller tried to blank is an :class:`AssignError`, so the user gets a message
    naming the field instead of a 502.
    """
    payload: dict[str, Any] = {}
    changed_labels: list[str] = []
    dropped: list[str] = []

    for name, raw in changes.items():
        spec = _EDIT_FIELDS_BY_NAME.get(name)
        if spec is None:
            log.info("assignments: ignoring non-editable field %r in an engagement edit", name)
            continue
        kind = spec["type"]

        if kind == "link":
            value: Any = str(raw or "").strip()
            if spec.get("required") and not value:
                raise AssignError(f"{spec['label']} is required.")
            payload[f"{name}Id"] = value or None
        elif kind == "multiEnum":
            values = [str(v) for v in (raw or []) if str(v).strip()]
            options = await _live_options(client, spec)
            values, gone = _clean_enum(values, options)
            dropped.extend(gone)
            payload[name] = values
        elif kind == "enum":
            value = str(raw or "").strip()
            if spec.get("required") and not value:
                raise AssignError(f"{spec['label']} is required.")
            options = await _live_options(client, spec)
            value, gone = _clean_enum(value, options)
            if gone:
                dropped.extend(gone)
                # A required field cannot be blanked by drift — leave it alone.
                if spec.get("required"):
                    continue
            payload[name] = value or None
        else:
            value = "" if raw is None else str(raw)
            limit = spec.get("maxLength", _TEXT_MAX_LENGTH)
            if len(value) > limit:
                raise AssignError(
                    f"{spec['label']} is too long ({len(value)} characters; "
                    f"the CRM allows {limit})."
                )
            if spec.get("required") and not value.strip():
                raise AssignError(f"{spec['label']} is required.")
            payload[name] = value

        changed_labels.append(spec["label"])

    if not payload:
        raise AssignError("Nothing to save — no editable field was changed.")

    await client.update(ENGAGEMENT, engagement_id, payload)
    return {
        "engagementId": engagement_id,
        "changedFields": changed_labels,
        "droppedValues": dropped,
    }


# --- inline images (the popup's wysiwyg fields + the Notes column) ----------
#
# Mechanics in ``core/inline_images.py`` (the session tools' pattern). What is
# local here is the whitelist: only ``ENGAGEMENT_EDIT_FIELDS`` entries whose
# LIVE CRM type is wysiwyg may hold one — EspoCRM's Wysiwyg saver is what binds
# the attachment to the engagement on save, and an attachment referenced from a
# plain-text field is never bound, so cleanup would collect it later.


async def live_wysiwyg_fields(client: AssignClient) -> set[str]:
    """The ``ENGAGEMENT_EDIT_FIELDS`` names whose LIVE CRM type is wysiwyg.

    This is the feature switch for rich internal notes: ``description`` is
    declared plain text here and stays a plain textarea until the CRM field is
    converted to wysiwyg (cengagement-description-wysiwyg-crm-handoff.md), at
    which point the served edit spec, the grid's Notes editor and the
    inline-image whitelist all upgrade with no deploy — the established
    feature-detection pattern. A failed metadata read falls back to the
    statically-declared wysiwyg fields, never a guess that a text field can
    hold an attachment.
    """
    declared = {f["name"] for f in ENGAGEMENT_EDIT_FIELDS if f["type"] == "wysiwyg"}
    fetch = getattr(client, "metadata", None)  # dry-run clients have none
    if fetch is None:
        return declared
    try:
        fields = await fetch(f"entityDefs.{ENGAGEMENT}.fields") or {}
    except EspoError as exc:
        log.warning("assignments: %s field metadata unavailable: %s", ENGAGEMENT, exc)
        return declared
    return {
        f["name"] for f in ENGAGEMENT_EDIT_FIELDS
        if (fields.get(f["name"]) or {}).get("type") == "wysiwyg"
    }


async def upload_inline_image(
    client: AssignClient,
    *,
    filename: str,
    content_type: str,
    data_base64: str,
    field: str,
) -> dict[str, str]:
    """Store a pasted/picked image as an EspoCRM Inline Attachment on
    ``CEngagement``. Validation refusals are :class:`AssignError` (readable 400)."""
    allowed = await live_wysiwyg_fields(client)
    try:
        return await inline_images.upload_inline_image(
            client,
            filename=filename,
            content_type=content_type,
            data_base64=data_base64,
            related_type=ENGAGEMENT,
            field=field,
            allowed_fields=allowed,
            field_error="Images can't be stored in this field.",
        )
    except inline_images.InlineImageError as exc:
        raise AssignError(str(exc)) from exc


async def fetch_inline_image(
    client: AssignClient, attachment_id: str
) -> tuple[bytes, str]:
    """The attachment's bytes + content type, read AS THE USER — EspoCRM checks
    access against the related engagement."""
    return await inline_images.fetch_inline_image(client, attachment_id)


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

async def _mentor_select(client: AssignClient) -> str:
    """:data:`_MENTOR_SELECT`, plus the last-assigned stamp when the CRM has it.

    Feature-detected rather than appended unconditionally: what EspoCRM does
    with an unknown attribute in ``select`` is not something to bet the mentor
    roster on, and this list is read on every open of the Available Mentors
    picker. One cached-free metadata GET per open is the cheaper risk.
    """
    if await last_assigned_field_exists(client):
        return _MENTOR_SELECT + "," + LAST_ASSIGNED_FIELD
    return _MENTOR_SELECT


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


# --- The mentor-side "last assigned a new client" stamp ----------------------
# CMentorProfile carries the date the mentor was last given a NEW client, so the
# roster answers "who hasn't had one lately?" in the CRM itself (grids, filters,
# reports) rather than only through this app's derived metrics. Nothing CRM-side
# maintains it: the Assign and Reassign actions below are what write it.
#
# Feature-detected per write (the documentsFolderUrl/transcript precedent), so
# this stays inert until the CRM field is built and activates with no deploy.
# Spec: cmentorprofile-last-client-assigned-field.md.
LAST_ASSIGNED_FIELD = "lastClientAssignedDate"


async def last_assigned_field_exists(client: AssignClient) -> bool:
    """Whether the live CRM has the mentor-side stamp field (CRM = truth).

    ``metadata`` is reached by ``getattr`` rather than the Protocol because the
    dry-run client doesn't implement it (the ``metadata_enum_options``
    convention in this module); no metadata access simply means no stamp.
    A failed lookup is NOT cached as absent — it is a CRM hiccup, not a schema
    fact.
    """
    fetch = getattr(client, "metadata", None)
    if fetch is None:
        return False
    try:
        fields = await fetch(f"entityDefs.{MENTOR_PROFILE}.fields") or {}
    except EspoError as exc:
        log.warning("%s.%s metadata unavailable: %s", MENTOR_PROFILE, LAST_ASSIGNED_FIELD, exc)
        return False
    return LAST_ASSIGNED_FIELD in fields


async def stamp_mentor_last_assigned(
    client: AssignClient, mentor_profile_id: str, when: Optional[str] = None
) -> Optional[str]:
    """Record on the mentor's profile that they were just given a new client.

    **Advance-only** (the ``touch_last_contact`` rule): a stored value at or
    after ``when`` is left alone, so re-driving an old action can never move the
    date backward. **Best-effort** — a Client Administration staffer's EspoCRM
    role may not grant edit on ``CMentorProfile``, and that must never fail an
    assignment that has already been written. Returns the stamp written, or
    None when nothing was (field not built, not an advance, or the write was
    refused); the caller reports it in the action payload.
    """
    if not await last_assigned_field_exists(client):
        return None
    stamp = when or espo_now()
    try:
        current = await client.get(
            MENTOR_PROFILE, mentor_profile_id, select=LAST_ASSIGNED_FIELD
        )
        existing = _parse_espo_datetime(current.get(LAST_ASSIGNED_FIELD))
        new = _parse_espo_datetime(stamp)
        if existing and new and existing >= new:
            return None
        await client.update(MENTOR_PROFILE, mentor_profile_id, {LAST_ASSIGNED_FIELD: stamp})
    except EspoError as exc:
        log.warning(
            "%s not stamped on %s/%s (the assignment itself stands): %s",
            LAST_ASSIGNED_FIELD, MENTOR_PROFILE, mentor_profile_id, exc,
        )
        return None
    return stamp


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
        # None until the CRM field is built (and for any mentor not yet given a
        # client since it was) — the grid renders that as "—", not as a zero.
        "lastClientAssigned": r.get(LAST_ASSIGNED_FIELD),
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
        select=await _mentor_select(client),
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
        MENTOR_PROFILE, select=await _mentor_select(client), max_size=200,
        order_by="name",
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
         assignment already saved by someone else. EXCEPTION (P1-9, reliability
         review 2026-07-17): if the stored mentor EQUALS the requested mentor,
         this is a **repair run** — a previous assignment died mid re-homing
         (or a transport error aborted it), and the stale guard used to make
         that state unrepairable in-app. The repair skips the engagement write
         (already done) and re-executes the idempotent re-homing + stream note;
         the response carries ``"repaired": true``.
      1. Resolve + re-validate the mentor -> their User.
      2. Engagement: set assignedUser + mentorProfile, status -> Pending Acceptance.
      2b. Mentor profile: stamp ``lastClientAssignedDate`` (best-effort,
         feature-detected, skipped on a repair — see
         :func:`stamp_mentor_last_assigned`).
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
    repair = current.get("mentorProfileId") == mentor_profile_id
    if current.get("mentorProfileId") and not repair:
        raise AssignError(
            "This engagement has already been assigned to "
            + (current.get("mentorProfileName") or "another mentor")
            + " — likely from another window or an out-of-date list. Nothing was "
            "changed; refresh the list to see its current state."
        )
    if not repair and current.get("engagementStatus") != STATUS_SUBMITTED:
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
    # A repair finishes an assignment that already happened — the mentor having
    # since paused new clients must not block completing THEIR OWN assignment.
    if not repair and (
        not mentor.get("acceptingNewClients")
        or mentor.get("mentorStatus") != MENTOR_STATUS_ACTIVE
    ):
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
    if not repair:
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

    # 2b. The mentor-side stamp. A repair is NOT a new client — it re-runs the
    # re-homing for an assignment that already happened, which is also why the
    # engagement's own date is left alone above.
    mentor_stamp = (
        None if repair else await stamp_mentor_last_assigned(client, mentor_profile_id)
    )

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

    if repair:
        note = (
            f"Finished the assignment to {mentor.get('name') or 'the assigned mentor'} "
            f"via the Client Administration app (repair run — a previous attempt did "
            f"not complete the re-homing); re-homed to the mentor's user: "
            f"{contacts_updated}/{len(contact_ids)} contact(s), "
            f"{_rehomed('client profile', client_id, client_profile_updated)}, "
            f"{_rehomed('company', account_id, account_updated)}."
        )
    else:
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
        "%s engagement=%s -> mentor=%s user=%s contacts=%d/%d client=%s account=%s errors=%d",
        "repaired" if repair else "assigned",
        engagement_id, mentor_profile_id, user_id, contacts_updated, len(contact_ids),
        client_profile_updated, account_updated, len(reassignment_errors),
    )
    if reassignment_errors:
        log.warning("assign engagement=%s partial re-homing: %s", engagement_id, reassignment_errors)
    return {
        "engagementId": engagement_id,
        "repaired": repair,
        "engagementStatus": (
            current.get("engagementStatus") if repair else STATUS_PENDING
        ),
        "mentorProfileId": mentor_profile_id,
        "mentorName": mentor.get("name"),
        "assignedUserId": user_id,
        "assignedUserName": mentor.get("assignedUserName"),
        "contactsUpdated": contacts_updated,
        "contactsTotal": len(contact_ids),
        "clientProfileUpdated": client_profile_updated,
        "accountUpdated": account_updated,
        "mentorLastAssignedDate": mentor_stamp,
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
         changed — a replacement doesn't restart the acceptance flow. The NEW
         mentor's ``lastClientAssignedDate`` is stamped (best-effort); the old
         mentor's is left alone — the field records gaining a client, not
         losing one.
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

    # 3b. The new mentor was just handed a client they did not have — stamp
    # them. The OLD mentor is deliberately untouched: the field records when a
    # mentor last GAINED a client, not when they last lost one.
    mentor_stamp = await stamp_mentor_last_assigned(client, mentor_profile_id)

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
        "mentorLastAssignedDate": mentor_stamp,
        "reassignmentErrors": reassignment_errors,
    }


# --- Mentor detail popup (Available Mentors list -> click a name) ------------
# Read-only by ruling (Doug 2026-09-01): editing stays in Mentor Administration
# — one write surface per record. Plan: prds/mentor-detail-popup-plan.md.

# The linked Contact's reachability facts, shown as a "Contact" panel — the
# CMentorProfile detail layout doesn't carry them. Same fields Mentor
# Administration merges from the Contact.
_CONTACT_PANEL_SELECT = (
    "firstName,lastName,emailAddress,phoneNumber,cEmploymentStatus,"
    "addressStreet,addressCity,addressState,addressPostalCode,addressCountry,"
    "cLinkedInProfile"
)


def _contact_panel_fields(contact: dict[str, Any]) -> list[dict[str, Any]]:
    """The Contact panel's rows, in the shared detail-panel field shape."""

    def _f(key: str, label: str, type_: str, value: Any) -> dict[str, Any]:
        return {"key": key, "label": label, "type": type_, "value": value,
                "editable": False, "options": None, "phone": False}

    name = " ".join(
        str(contact.get(k) or "").strip() for k in ("firstName", "lastName")
    ).strip()
    region = " ".join(
        str(contact[k]) for k in ("addressState", "addressPostalCode")
        if contact.get(k)
    )
    city_line = ", ".join(
        str(part) for part in (contact.get("addressCity"), region) if part
    )
    address = "\n".join(
        str(part) for part in
        (contact.get("addressStreet"), city_line, contact.get("addressCountry"))
        if part
    )
    return [
        _f("contactName", "Name", "text", name),
        _f("contactEmail", "Email", "email", contact.get("emailAddress")),
        _f("contactPhone", "Phone", "phone", contact.get("phoneNumber")),
        # The volunteer form's "are you employed" answer (Doug, 2026-09-01).
        _f("contactEmployment", "Employment status", "text",
           contact.get("cEmploymentStatus")),
        _f("contactAddress", "Address", "address", address),
        _f("contactLinkedIn", "LinkedIn", "url", contact.get("cLinkedInProfile")),
    ]


async def mentor_detail(
    client: Any, mentor_id: str, user_id: Optional[str] = None
) -> dict[str, Any]:
    """ALL of one mentor's field values for the read-only detail popup.

    Reuses the Workspace Directory detail engine — the CRM's own detail-layout
    panels, live labels and types — with ``include_unplaced=True`` so scalars
    the layout omits land in a final "Other fields" panel, plus a best-effort
    "Contact" panel from the linked Contact. Runs as the signed-in user, so
    their field ACL decides what comes back (an ACL-stripped field is simply
    absent — correct, not a defect).

    ``client`` is the full ``EspoClient``: the directory engine needs
    ``layout``/``i18n``/``metadata``/``app_user`` beyond ``AssignClient``'s
    slice. Every ``editable`` flag is forced off — the MENTORS directory config
    is already read-only, but this popup must stay view-only even if that
    config ever changes.
    """
    # Imported here, not at module top: directory -> sessions -> assignments is
    # the existing import chain, so a top-level import back would be circular.
    from directory import service as directory_service
    from directory.config import MENTORS

    payload = await directory_service.detail(
        client, MENTORS, mentor_id, user_id, include_unplaced=True
    )
    payload["editable"] = False
    payload["editHandoff"] = None
    for panel in payload.get("panels") or []:
        for field in panel.get("fields") or []:
            field["editable"] = False
            if field.get("subFields"):
                field["subFields"] = []

    contact_panel = None
    try:
        rec = await client.get(MENTOR_PROFILE, mentor_id, select="contactRecordId")
        contact_id = rec.get("contactRecordId")
        if contact_id:
            contact = await client.get(
                CONTACT, contact_id, select=_CONTACT_PANEL_SELECT
            )
            contact_panel = {
                "key": "contact", "title": "Contact",
                "fields": _contact_panel_fields(contact),
            }
    except EspoError as exc:  # readable mentor, unreadable Contact — no panel
        log.debug("mentor %s contact panel skipped: %s", mentor_id, exc)
    if contact_panel:
        panels = payload["panels"]
        pos = next(
            (i for i, pn in enumerate(panels) if pn.get("key") == "unplaced"),
            len(panels),
        )
        panels.insert(pos, contact_panel)
    return payload
