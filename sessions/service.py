"""The Session Management engine — domain-agnostic CRM reads/writes.

Every function takes a :class:`sessions.config.DomainConfig` so one code path
serves all three domains. All calls run as the logged-in user (their token), so
EspoCRM enforces their ACL on every entity touched.

Resolving "records I own": the manager (mentor / partner manager / sponsor
manager) is a ``CMentorProfile`` whose ``assignedUser`` is their login. We find
that profile, then read the parents through the reverse link the domain config
names (``engagements1`` / ``managedPartners`` / ``managedSponsors``). This avoids
filtering by a link attribute in a ``where`` clause, which prod's field ACL
forbids (see the assignedUserId lesson in assignments.service).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from assignments.service import assigned_user_id
from core.espo import EspoError

from .config import (
    DETAIL_SESSION_SELECT,
    ENGAGEMENT,
    MENTOR_PROFILE,
    SESSION,
    SESSION_EDIT_NAMES,
    SESSION_ENUM_FIELDS,
    SESSION_FIELDS,
    DomainConfig,
)

log = logging.getLogger("cbm_intake.sessions.service")

_PAGE = 200
_COMENTOR_LINK = "additionalMentors"
_ATTENDEE_LINK = "sessionAttendees"

# Pop-up "peek" detail: the record types a contact/company/client link can open,
# with the curated field set each shows. An allowlist so the endpoint can't be
# used to read arbitrary entities (reads still run as the user, ACL-enforced).
PEEK_FIELDS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "Contact": (
        ("title", "Title", "text"),
        ("emailAddress", "Email", "email"),
        ("phoneNumber", "Phone", "phone"),
        ("accountName", "Company", "text"),
        ("addressCity", "City", "text"),
        ("addressState", "State", "text"),
        ("cLinkedInProfile", "LinkedIn", "url"),
        ("description", "Notes", "longtext"),
    ),
    "Account": (
        ("website", "Website", "url"),
        ("emailAddress", "Email", "email"),
        ("phoneNumber", "Phone", "phone"),
        ("cIndustrySector", "Industry", "text"),
        ("cOrganizationType", "Organization type", "text"),
        ("billingAddressCity", "City", "text"),
        ("billingAddressState", "State", "text"),
        ("description", "Notes", "longtext"),
    ),
    "CClientProfile": (
        ("industrySector", "Industry", "text"),
        ("legalEntityType", "Entity type", "text"),
        ("formationDate", "Formed", "date"),
        ("numberOfEmployees", "Employees", "int"),
        ("annualRevenueRange", "Revenue range", "text"),
        ("revenueTrend", "Revenue trend", "text"),
        ("profitabilityStatus", "Profitability", "text"),
        ("geographicMarketReach", "Market reach", "text"),
        ("primaryCustomerType", "Customer type", "multiEnum"),
        ("description", "Notes", "longtext"),
    ),
    "CPartnerProfile": (
        ("partnershipStatus", "Status", "text"),
        ("partnershipType", "Type", "text"),
        ("partnershipStartDate", "Started", "date"),
        ("partnershipAgreementDate", "Agreement", "date"),
        ("partnerContactCadence", "Contact cadence", "text"),
        ("lastContacted", "Last contacted", "date"),
        ("partnershipValue", "Value", "multiEnum"),
        ("cBMValueProvided", "CBM value provided", "multiEnum"),
    ),
    "CSponsorProfile": (
        ("totalContribution", "Total contribution", "currency"),
        ("lastContribution", "Last contribution", "date"),
        ("lastContacted", "Last contacted", "date"),
    ),
}


class SessionClient(Protocol):
    """The slice of ``EspoClient`` this module needs (eases test mocking)."""

    async def get(self, entity: str, record_id: str, select: str | None = ...) -> dict[str, Any]: ...
    async def list(self, entity: str, **kwargs: Any) -> dict[str, Any]: ...
    async def list_related(self, entity: str, record_id: str, link: str, **kwargs: Any) -> dict[str, Any]: ...
    async def create(self, entity: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def update(self, entity: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def relate(self, entity: str, record_id: str, link: str, related_id: str) -> None: ...
    async def unrelate(self, entity: str, record_id: str, link: str, related_id: str) -> None: ...
    async def metadata(self, key: str) -> Any: ...
    async def app_user(self) -> dict[str, Any]: ...


class SessionError(Exception):
    """A user-facing, non-CRM error (e.g. the user has no linked profile)."""


async def resolve_manager_profile(client: SessionClient, user_id: str) -> Optional[str]:
    """The ``CMentorProfile`` id whose assigned login User is ``user_id``.

    Scans the profiles readable by this user and matches in Python — never a
    ``where`` on ``assignedUserId`` (prod forbids it). A regular user whose ACL
    scopes ``CMentorProfile`` to "own" simply gets a one-row list. Returns None
    when no profile is linked to the user.
    """
    offset = 0
    while True:
        data = await client.list(
            MENTOR_PROFILE,
            select="id,assignedUserId,assignedUsersIds",
            max_size=_PAGE,
            offset=offset,
        )
        rows = data.get("list", [])
        for r in rows:
            if assigned_user_id(r) == user_id:
                return r["id"]
        if len(rows) < _PAGE:
            return None
        offset += _PAGE


def _grid_row(cfg: DomainConfig, r: dict[str, Any]) -> dict[str, Any]:
    row = {"id": r["id"], "createdAt": r.get("createdAt")}
    for col in cfg.list_columns:
        row[col.key] = r.get(col.attr)
    return row


async def list_records(
    cfg: DomainConfig, client: SessionClient, user: dict[str, Any]
) -> dict[str, Any]:
    """The parents the signed-in user owns, as grid rows.

    ``{"records": [...], "profileFound": bool}`` — ``profileFound=False`` means
    the user has no linked ``CMentorProfile`` (so nothing can be scoped to them).
    """
    profile_id = await resolve_manager_profile(client, user["userId"])
    if not profile_id:
        return {"records": [], "profileFound": False}
    data = await client.list_related(
        MENTOR_PROFILE,
        profile_id,
        cfg.manager_owned_link,
        select=cfg.list_select,
        max_size=_PAGE,
    )
    rows = data.get("list", [])
    if cfg.status_attr and cfg.status_values:
        rows = [r for r in rows if r.get(cfg.status_attr) in cfg.status_values]
    records = [_grid_row(cfg, r) for r in rows]
    records.sort(key=lambda x: (x.get("createdAt") or ""), reverse=True)
    return {"records": records, "profileFound": True}


def _contact_row(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": c["id"],
        "name": c.get("name"),
        "email": c.get("emailAddress"),
        "phone": c.get("phoneNumber"),
        "title": c.get("title"),
    }


def _session_row(s: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": s["id"],
        "name": s.get("name"),
        "status": s.get("status"),
        "sessionType": s.get("sessionType"),
        "dateStart": s.get("dateStart") or s.get("dateStartDate"),
    }


async def _attendees(client: SessionClient, session_id: str) -> list[dict[str, Any]]:
    """A session's attendee contacts (id + name). ``sessionAttendees`` is a
    RELATIONSHIP, not a select-field, so it must be read through the link
    (``list_related``) — reading ``sessionAttendeesIds`` off the record returns
    nothing (which is why attendees looked empty). Same pattern as co-mentors."""
    try:
        data = await client.list_related(
            SESSION, session_id, _ATTENDEE_LINK, select="name", max_size=_PAGE
        )
    except EspoError:
        return []
    return data.get("list", [])


def _note_entry(s: dict[str, Any]) -> dict[str, Any]:
    """A session's contribution to the Overview note feed: notes + next steps
    stamped with when it happened (attendees are attached by the caller)."""
    return {
        "id": s["id"],
        "name": s.get("name"),
        "sessionType": s.get("sessionType"),
        "status": s.get("status"),
        "dateStart": s.get("dateStart") or s.get("dateStartDate"),
        "attendees": [],
        "notes": s.get("sessionNotes") or "",
        "nextSteps": s.get("nextSteps") or "",
    }


async def _note_attendees(client: SessionClient, s: dict[str, Any]) -> list[str]:
    """Attendee display names for a session's note-feed entry."""
    return [c.get("name") for c in await _attendees(client, s["id"]) if c.get("name")]


def _next_session(sessions: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The soonest upcoming session (earliest start still in the future), derived
    from the actual session records so it's accurate for every domain. Compares
    the CRM's ``YYYY-MM-DD HH:MM:SS`` UTC stamps as strings (same format => sorts
    chronologically). Returns None when nothing is scheduled ahead."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    upcoming = [
        s for s in sessions if (s.get("dateStart") or s.get("dateStartDate") or "") > now
    ]
    if not upcoming:
        return None
    nxt = min(upcoming, key=lambda s: s.get("dateStart") or s.get("dateStartDate") or "")
    return {
        "id": nxt["id"],
        "name": nxt.get("name"),
        "sessionType": nxt.get("sessionType"),
        "dateStart": nxt.get("dateStart") or nxt.get("dateStartDate"),
        "videoMeetingLink": nxt.get("videoMeetingLink") or "",
    }


def _company_item(it: Any, parent: dict[str, Any]) -> Optional[dict[str, Any]]:
    """The single aggregated "Company" fact: one link labelled with the company
    name whose pop-up merges the org's 1:1 records (Account + profile). Drops any
    pair whose id is absent; returns None if nothing links."""
    display = parent.get(it.attr) or (
        parent.get(it.name_fallback_attr) if it.name_fallback_attr else None
    )
    pairs = [
        {"entity": entity, "id": parent.get(id_attr)}
        for entity, id_attr in it.aggregate
        if parent.get(id_attr)
    ]
    if not display and not pairs:
        return None
    return {
        "label": it.label, "value": display or "(details)", "type": "text",
        "block": it.block, "section": it.section, "link": {"aggregate": pairs},
    }


def _overview_items(cfg: DomainConfig, parent: dict[str, Any]) -> list[dict[str, Any]]:
    """The curated Overview facts, in config order, dropping empties. A linkable
    value carries a ``link`` so the UI opens its pop-up detail panel — either a
    single {entity,id} or an {aggregate:[…]} of 1:1 org records; currency carries
    its ``currency`` code for formatting."""
    items: list[dict[str, Any]] = []
    for it in cfg.overview_items:
        if it.aggregate:
            entry = _company_item(it, parent)
            if entry:
                items.append(entry)
            continue
        value = parent.get(it.attr)
        if value in (None, "", []):
            continue
        entry = {
            "label": it.label, "value": value, "type": it.type,
            "block": it.block, "section": it.section,
        }
        if it.link_entity and it.id_attr and parent.get(it.id_attr):
            entry["link"] = {"entity": it.link_entity, "id": parent[it.id_attr]}
        if it.type == "currency":
            entry["currency"] = parent.get(it.attr + "Currency")
        items.append(entry)
    return items


async def get_detail(
    cfg: DomainConfig, client: SessionClient, parent_id: str
) -> dict[str, Any]:
    """The parent detail view: curated Overview facts + an aggregated feed of
    every session's notes, plus related contacts and the sessions list (+
    co-mentors, mentor domain). All reads are as the user."""
    parent = await client.get(cfg.parent_entity, parent_id, select=cfg.detail_select)
    overview = _overview_items(cfg, parent)

    contacts_data = await client.list_related(
        cfg.parent_entity, parent_id, cfg.parent_contacts_link,
        select="name,emailAddress,phoneNumber,title", max_size=_PAGE,
    )
    contacts = [_contact_row(c) for c in contacts_data.get("list", [])]

    sessions_data = await client.list_related(
        cfg.parent_entity, parent_id, cfg.parent_sessions_link,
        select=DETAIL_SESSION_SELECT, max_size=_PAGE,
    )
    raw_sessions = sorted(
        sessions_data.get("list", []),
        key=lambda x: (x.get("dateStart") or x.get("dateStartDate") or ""),
        reverse=True,  # most recent first — the review order for the note feed
    )
    sessions = [_session_row(s) for s in raw_sessions]
    note_feed = [_note_entry(s) for s in raw_sessions]
    # Fill in attendees (custom link-multiple, absent from the list query) with a
    # concurrent per-session get where the list row didn't carry them.
    attendee_lists = await asyncio.gather(
        *(_note_attendees(client, s) for s in raw_sessions)
    )
    for entry, names in zip(note_feed, attendee_lists):
        entry["attendees"] = names

    # Overall notes about the whole engagement/partner/sponsor (not a session).
    overall_notes = None
    if cfg.overall_notes_attr:
        val = parent.get(cfg.overall_notes_attr)
        if val not in (None, "", []):
            overall_notes = {
                "label": cfg.overall_notes_label, "value": val, "type": cfg.overall_notes_type,
            }

    detail: dict[str, Any] = {
        "id": parent_id,
        "name": parent.get("name"),
        "parentLabel": cfg.parent_label,
        "overview": overview,
        "overallNotes": overall_notes,
        "nextSession": _next_session(raw_sessions),
        "noteFeed": note_feed,
        "contacts": contacts,
        # the primary contact is shown in the key facts; the frontend lists the
        # rest under "Other contacts" on the Overview rail.
        "primaryContactId": parent.get(cfg.primary_contact_id_attr),
        "sessions": sessions,
        "supportsComentor": cfg.supports_comentor,
    }
    if cfg.supports_comentor:
        co_data = await client.list_related(
            cfg.parent_entity, parent_id, _COMENTOR_LINK, select="name", max_size=_PAGE
        )
        detail["coMentors"] = [
            {"id": m["id"], "name": m.get("name")} for m in co_data.get("list", [])
        ]
    return detail


async def peek(client: SessionClient, entity: str, record_id: str) -> dict[str, Any]:
    """A pop-up detail read for a linked contact / company / client.

    ``entity`` must be in :data:`PEEK_FIELDS` (allowlist). Returns the record's
    name + its curated non-empty fields for the modal. Runs as the user, so
    EspoCRM enforces their ACL on the record.
    """
    spec = PEEK_FIELDS.get(entity)
    if spec is None:
        raise SessionError(f"Cannot look up {entity} records.")
    select = ",".join(["name", *(attr for attr, _, _ in spec)])
    rec = await client.get(entity, record_id, select=select)
    fields = [
        {"label": label, "value": rec.get(attr), "type": ftype}
        for attr, label, ftype in spec
        if rec.get(attr) not in (None, "", [])
    ]
    return {"entity": entity, "name": rec.get("name"), "fields": fields}


_SESSION_SELECT = ",".join(["id", *sorted(SESSION_EDIT_NAMES)])


async def get_session(client: SessionClient, session_id: str) -> dict[str, Any]:
    """An existing session's editable values + its attendee contact ids (read via
    the sessionAttendees relationship — see :func:`_attendees`)."""
    rec = await client.get(SESSION, session_id, select=_SESSION_SELECT)
    rec["attendees"] = [c["id"] for c in await _attendees(client, session_id)]
    return rec


def _session_payload(changes: dict[str, Any]) -> dict[str, Any]:
    """Whitelisted scalar-field payload for a session write (attendees are synced
    separately via the relationship endpoints, not here)."""
    return {k: v for k, v in changes.items() if k in SESSION_EDIT_NAMES}


async def _sync_attendees(
    client: SessionClient, session_id: str, attendees: list[str]
) -> None:
    """Make the session's attendee set exactly ``attendees``, via the relationship
    link endpoints. Setting ``sessionAttendeesIds`` on a record update does NOT
    reliably sync this custom many-to-many (same reason co-mentors use ``relate``),
    so we relate the added contacts and unrelate the removed ones."""
    current = set((await get_session(client, session_id)).get("attendees") or [])
    target = set(attendees or [])
    add, remove = target - current, current - target
    log.info("sync attendees %s: current=%s target=%s +%s -%s",
             session_id, sorted(current), sorted(target), sorted(add), sorted(remove))
    for cid in add:
        await client.relate(SESSION, session_id, _ATTENDEE_LINK, cid)
    for cid in remove:
        await client.unrelate(SESSION, session_id, _ATTENDEE_LINK, cid)


async def _sanitize_enum_payload(client: SessionClient, payload: dict[str, Any]) -> None:
    """Drop enum/multiEnum values the live ``CSession`` no longer accepts, in place.

    So one drifted option can't 400 the whole create/update
    (``validationFailure``) — a non-required enum must never block a save (Doug's
    policy). Mirrors ``core.enum_filter.EnumSanitizer`` for the intake
    orchestrators, using the same live-options fetch this module already does for
    the editor (:func:`field_options`).

    - **single enum:** an unrecognized value is *omitted* (the key removed) — on an
      update that preserves the record's existing value rather than clearing it; on
      a create the field is left unset (server default / null).
    - **multiEnum:** only the unrecognized members are dropped; valid selections
      are kept.

    **Fails open:** if options can't be fetched (metadata error, dry-run) the
    payload is left untouched, so it never drops data it couldn't verify.
    """
    enum_keys = [k for k in payload if k in SESSION_ENUM_FIELDS]
    if not enum_keys:
        return
    try:
        options = await field_options(client)
    except Exception as exc:  # noqa: BLE001 — fail open, never block the save
        log.warning("could not fetch CSession enum options (%s); keeping values as-is", exc)
        return
    for key in enum_keys:
        opts = options.get(key)
        if opts is None:  # field not in the live options map — unverifiable, keep
            continue
        value = payload[key]
        if isinstance(value, list):  # multiEnum
            kept = [v for v in value if v in opts]
            dropped = [v for v in value if v not in opts]
            if dropped:
                log.warning("CSession.%s: dropping unrecognized %s (not in live enum)", key, dropped)
            payload[key] = kept
        elif value not in (None, "") and value not in opts:
            log.warning("CSession.%s: dropping unrecognized value %r (not in live enum)", key, value)
            del payload[key]


async def create_session(
    cfg: DomainConfig,
    client: SessionClient,
    parent_id: str,
    changes: dict[str, Any],
    attendees: Optional[list[str]] = None,
    owner_user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Create a ``CSession`` linked to ``parent_id`` and return it (with id).

    Stamps the creating user as the session's assigned user so it is theirs to
    read/edit — required because these tools run under a role whose ``CSession``
    read/edit scope is ``own``: an unassigned session would be invisible to its
    own author right after creation. Written to BOTH ``assignedUser`` and
    ``assignedUsers`` (CSession has both, like CEngagement) so it sticks whichever
    the instance uses.
    """
    payload = _session_payload(changes)
    payload[cfg.session_parent_fk] = parent_id
    payload.setdefault("sessionType", cfg.default_session_type)
    payload.setdefault("status", "Planned")
    if owner_user_id:
        payload.setdefault("assignedUserId", owner_user_id)
        payload.setdefault("assignedUsersIds", [owner_user_id])
    await _sanitize_enum_payload(client, payload)
    created = await client.create(SESSION, payload)
    if attendees:  # new record => relate all chosen attendees
        for cid in attendees:
            await client.relate(SESSION, created["id"], _ATTENDEE_LINK, cid)
    log.info(
        "created session %s on %s/%s type=%s attendees=%d",
        created.get("id"), cfg.parent_entity, parent_id, payload.get("sessionType"),
        len(attendees or []),
    )
    return await get_session(client, created["id"])


async def update_session(
    client: SessionClient,
    session_id: str,
    changes: dict[str, Any],
    attendees: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Update whitelisted fields on a session; sync attendees separately.

    ``attendees=None`` leaves the attendee set untouched; a list (incl. ``[]``)
    replaces it via the relationship endpoints (see :func:`_sync_attendees`)."""
    payload = _session_payload(changes)
    await _sanitize_enum_payload(client, payload)
    if payload:
        await client.update(SESSION, session_id, payload)
    if attendees is not None:
        await _sync_attendees(client, session_id, attendees)
    return await get_session(client, session_id)


async def add_comentor(
    client: SessionClient, engagement_id: str, mentor_profile_id: str
) -> None:
    """Attach a co-mentor (CMentorProfile) to an engagement (additionalMentors)."""
    await client.relate(ENGAGEMENT, engagement_id, _COMENTOR_LINK, mentor_profile_id)


async def mentor_options(client: SessionClient) -> list[dict[str, Any]]:
    """id/name of mentor profiles, for the co-mentor picker (mentor domain)."""
    data = await client.list(MENTOR_PROFILE, select="name", max_size=_PAGE, order_by="name")
    return [{"id": r["id"], "name": r.get("name")} for r in data.get("list", [])]


async def field_options(client: SessionClient) -> dict[str, list[str]]:
    """Live option lists for the CSession enum/multi-enum fields (CRM = truth)."""
    fields = await client.metadata(f"entityDefs.{SESSION}.fields")
    options: dict[str, list[str]] = {}
    for name in SESSION_ENUM_FIELDS:
        opts = (fields.get(name) or {}).get("options")
        if isinstance(opts, list):
            options[name] = [o for o in opts if o != ""]
    return options


async def field_required(client: SessionClient) -> list[str]:
    """Names of editable ``CSession`` fields the CRM marks **required**.

    Read live from metadata (CRM = truth) so the form requires exactly what the
    CRM does — e.g. ``dateStart`` — instead of hard-coding it and drifting.
    """
    fields = await client.metadata(f"entityDefs.{SESSION}.fields")
    return [
        name
        for name in SESSION_EDIT_NAMES
        if isinstance(fields.get(name), dict) and fields[name].get("required")
    ]


def field_spec() -> list[dict]:
    """The editor field spec served to the frontend."""
    return SESSION_FIELDS
