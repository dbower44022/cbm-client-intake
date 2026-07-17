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
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol

from assignments.service import (
    ACCOUNT,
    CLIENT_PROFILE,
    ENGAGEMENT_CONTACTS,
    assigned_user_id,
)
from core.espo import EspoError
from core.phone import format_us
from core.stream import post_stream_note

from .config import (
    CONTACT,
    DETAIL_SESSION_SELECT,
    ENGAGEMENT,
    MENTOR_PROFILE,
    SESSION,
    SESSION_EDIT_NAMES,
    SESSION_ENUM_FIELDS,
    SESSION_OPTION_FIELDS,
    SESSION_FIELDS,
    TRANSCRIPT_FIELD,
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
    "CMentorProfile": (
        ("mentorType", "Mentor type", "text"),
        ("mentorStatus", "Status", "text"),
        ("cbmEmail", "CBM email", "email"),
        ("areaOfExpertise", "Areas of expertise", "multiEnum"),
        ("industryExperience", "Industry experience", "multiEnum"),
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


_HTTP_STATUS_RE = re.compile(r"HTTP (\d{3})")


def _is_forbidden(exc: EspoError) -> bool:
    """True when a CRM read failed with 403 — the user simply lacks the ACL to
    read this record (e.g. a mentor with no read grant on ``CClientProfile``).
    Matches the *first* ``HTTP <code>`` in the message (``EspoError`` puts the
    real status ahead of the echoed body), so it's not fooled by a 403 that only
    appears in a response body."""
    m = _HTTP_STATUS_RE.search(str(exc))
    return bool(m) and m.group(1) == "403"


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


async def resolve_user_mailbox(client: SessionClient, user_id: str) -> Optional[str]:
    """The signed-in user's own CBM mailbox (``CMentorProfile.cbmEmail``),
    lowercased — the delegation ``subject`` for Google operations performed on
    their behalf (calendar events). None when no linked profile / no cbmEmail.
    """
    profile_id = await resolve_manager_profile(client, user_id)
    if not profile_id:
        return None
    profile = await client.get(MENTOR_PROFILE, profile_id, select="cbmEmail")
    return (profile.get("cbmEmail") or "").strip().lower() or None


def _grid_row(cfg: DomainConfig, r: dict[str, Any]) -> dict[str, Any]:
    row = {"id": r["id"], "createdAt": r.get("createdAt")}
    for col in cfg.list_columns:
        row[col.key] = r.get(col.attr)
    if cfg.list_date_column:  # optional trailing date column (Start Date / Created)
        dkey, _, dattr = cfg.list_date_column
        row[dkey] = r.get(dattr)
    if cfg.list_contact_id_attr:
        row["contactId"] = r.get(cfg.list_contact_id_attr)  # for the contact pop-up link
    if r.get("mentorProfileId"):  # mentor domain: the Assigned Mentor pop-up link
        row["mentorId"] = r.get("mentorProfileId")
    if cfg.list_company_aggregate:
        pairs = [
            {"entity": entity, "id": r["id"] if attr == "id" else r.get(attr)}
            for entity, attr in cfg.list_company_aggregate
        ]
        pairs = [p for p in pairs if p["id"]]
        if pairs:
            row["companyPeek"] = pairs  # the standard company/client pop-up
    return row


async def fill_company_fallback(
    cfg: DomainConfig, client: SessionClient, records: list[dict[str, Any]]
) -> None:
    """Resolve the company link through the client profile when the parent's own
    link is empty (``DomainConfig.company_fallback``).

    Intake-created engagements carry the Account on ``CClientProfile.linkedCompany``
    only — ``CEngagement.clientOrganization`` is null — so the grid / Overview /
    Details would show no company at all. Injects the resolved id + name into the
    raw record in place. Best-effort: a profile the user can't read just leaves
    the company blank.
    """
    if not cfg.company_fallback:
        return
    own_id, own_name, via_id, via_entity, comp_id, comp_name = cfg.company_fallback
    need = {r[via_id] for r in records if not r.get(own_id) and r.get(via_id)}
    if not need:
        return

    async def _resolve(pid: str):
        try:
            return pid, await client.get(via_entity, pid, select=f"{comp_id},{comp_name}")
        except EspoError:
            return pid, None

    resolved = dict(await asyncio.gather(*(_resolve(p) for p in need)))
    for r in records:
        via = resolved.get(r.get(via_id))
        if via and not r.get(own_id) and via.get(comp_id):
            r[own_id] = via[comp_id]
            r[own_name] = via.get(comp_name)


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
    links = [cfg.manager_owned_link]
    if cfg.manager_comentor_link:  # engagements where the user is a CO-mentor
        links.append(cfg.manager_comentor_link)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in links:
        data = await client.list_related(
            MENTOR_PROFILE,
            profile_id,
            link,
            select=cfg.list_select,
            max_size=_PAGE,
        )
        for r in data.get("list", []):
            if r["id"] not in seen:
                seen.add(r["id"])
                rows.append(r)
    if cfg.status_attr and cfg.status_values:
        rows = [r for r in rows if r.get(cfg.status_attr) in cfg.status_values]
    await fill_company_fallback(cfg, client, rows)
    records = [_grid_row(cfg, r) for r in rows]
    records.sort(key=lambda x: (x.get("createdAt") or ""), reverse=True)
    await _attach_sessions_near_now(cfg, client, records)
    return {"records": records, "profileFound": True}


async def _attach_sessions_near_now(
    cfg: DomainConfig, client: SessionClient, records: list[dict[str, Any]]
) -> None:
    """Stamp each grid row with its sessions from now−36h onward
    (``upcomingSessions``: ``[{dateStart, status}, ...]``, UTC stamps, soonest
    first).

    Two grid features read this: the "session scheduled TODAY" flag and the
    Next Session column (the stored ``CEngagement.nextSessionDateTime`` is
    never populated, so the column derives from real sessions). The frontend
    resolves "today"/"upcoming" in the VIEWER's local timezone (the server
    can't know it) — the 36-hour lower margin covers every real-world UTC
    offset. One CSession query for the whole grid, ACL-scoped to the user
    like every other read; best-effort — on any failure the grid simply
    shows no flags and falls back to the stored column value."""
    if not records:
        return
    now = datetime.now(timezone.utc)
    horizon = (now - timedelta(hours=36)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        data = await client.list(
            SESSION,
            select=f"dateStart,status,{cfg.session_parent_fk}",
            where=[{"type": "after", "attribute": "dateStart", "value": horizon}],
            order_by="dateStart",
            order="asc",
            max_size=_PAGE,
        )
    except Exception as exc:  # noqa: BLE001 — decoration, never breaks the grid
        log.warning("could not read upcoming sessions for the %s grid: %s", cfg.slug, exc)
        return
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for s in data.get("list", []):
        pid = s.get(cfg.session_parent_fk)
        if pid:
            by_parent.setdefault(pid, []).append(
                {"dateStart": s.get("dateStart"), "status": s.get("status")}
            )
    for r in records:
        near = by_parent.get(r["id"])
        if near:
            r["upcomingSessions"] = near


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
        "dateEnd": s.get("dateEnd"),
    }


# What the session view's attendee grid shows about each contact; company via
# the Contact→Account link fields so the cell can peek the Account record.
_ATTENDEE_SELECT = "name,emailAddress,phoneNumber,accountName,accountId"


async def _attendees(client: SessionClient, session_id: str) -> list[dict[str, Any]]:
    """A session's attendee contacts (id + grid detail). ``sessionAttendees`` is a
    RELATIONSHIP, not a select-field, so it must be read through the link
    (``list_related``) — reading ``sessionAttendeesIds`` off the record returns
    nothing (which is why attendees looked empty). Same pattern as co-mentors."""
    try:
        data = await client.list_related(
            SESSION, session_id, _ATTENDEE_LINK, select=_ATTENDEE_SELECT, max_size=_PAGE
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
        "dateEnd": s.get("dateEnd"),
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
    await fill_company_fallback(cfg, client, [parent])
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
    # Same names feed the note feed's attendee stamps AND the Sessions grid's
    # Participants column (sessions/note_feed are parallel over raw_sessions).
    for entry, row, names in zip(note_feed, sessions, attendee_lists):
        entry["attendees"] = names
        row["participants"] = names

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
    co_mentors: list[dict[str, Any]] = []
    if cfg.supports_comentor:
        co_data = await client.list_related(
            cfg.parent_entity, parent_id, _COMENTOR_LINK,
            select="name,cbmEmail,contactRecordId", max_size=_PAGE,
        )
        co_mentors = co_data.get("list", [])
        # ``contactId`` = the co-mentor's linked Contact, so the Overview can link
        # each CBM contact to its contact-info pop-up (email/phone). None when the
        # mentor profile has no linked Contact — the frontend shows plain text then.
        detail["coMentors"] = [
            {"id": m["id"], "name": m.get("name"), "contactId": m.get("contactRecordId")}
            for m in co_mentors
        ]
    # The default-invitee set for a NEW session (Doug's ruling: every CBM
    # person on the record starts invited): assigned manager + co-mentors,
    # each resolved to a Contact — live data showed most engagements carry NO
    # co-mentors and some profiles no contact link, which is exactly why this
    # resolves through the manager link and the cbmEmail fallback.
    detail["cbmContacts"] = await _cbm_contacts(client, cfg, parent, co_mentors)
    return detail


async def _resolve_member_contact(
    client: SessionClient, profile: dict[str, Any]
) -> Optional[str]:
    """A CBM member's Contact id, or ``None`` when nothing resolves.

    The profile's linked ``contactRecord`` when set; otherwise a Contact
    matched by the profile's ``cbmEmail`` (the comms precedent — many live
    profiles carry the mailbox but no contact link). No resolution is not an
    error: there is simply no Contact to relate as an attendee.
    """
    contact_id = profile.get("contactRecordId")
    if contact_id:
        return str(contact_id)
    mailbox = (profile.get("cbmEmail") or "").strip()
    if not mailbox:
        return None
    try:
        data = await client.list(
            CONTACT,
            where=[{"type": "equals", "attribute": "emailAddress", "value": mailbox}],
            select="name",
            max_size=1,
        )
    except EspoError:
        return None
    rows = data.get("list", [])
    return str(rows[0]["id"]) if rows else None


async def _cbm_contacts(
    client: SessionClient,
    cfg: DomainConfig,
    parent: dict[str, Any],
    co_mentors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Every CBM person on the record as an invitable contact, deduped.

    The parent's assigned manager (``parent_manager_link``) leads, then the
    co-mentors; each resolves via :func:`_resolve_member_contact`. Profiles
    that resolve to no Contact are skipped — the fix for those is linking the
    profile's contactRecord (or cbmEmail) in the CRM, not a broken invite.
    """
    profiles: list[dict[str, Any]] = []
    manager_id = (
        parent.get(f"{cfg.parent_manager_link}Id") if cfg.parent_manager_link else None
    )
    if manager_id:
        try:
            profiles.append(
                await client.get(
                    MENTOR_PROFILE, manager_id, select="name,cbmEmail,contactRecordId"
                )
            )
        except EspoError:
            log.warning("cbm-contacts: manager profile %s unreadable", manager_id)
    profiles.extend(co_mentors)
    resolved: list[dict[str, Any]] = []
    seen: set[str] = set()
    for profile in profiles:
        contact_id = await _resolve_member_contact(client, profile)
        if not contact_id or contact_id in seen:
            continue
        seen.add(contact_id)
        resolved.append({"contactId": contact_id, "name": profile.get("name")})
    return resolved


# Address parts read for a Contact peek (shown as one combined "Address" field
# and used to build the copy-to-clipboard contact card).
_CONTACT_ADDRESS_ATTRS = (
    "addressStreet", "addressCity", "addressState", "addressPostalCode", "addressCountry",
)


def _address_lines(rec: dict[str, Any]) -> list[str]:
    """A postal address as display lines: street / "City, ST 12345" / country."""
    lines: list[str] = []
    if rec.get("addressStreet"):
        lines.append(str(rec["addressStreet"]))
    region = " ".join(
        str(rec[k]) for k in ("addressState", "addressPostalCode") if rec.get(k)
    )
    city_line = ", ".join(p for p in [rec.get("addressCity"), region] if p)
    if city_line:
        lines.append(city_line)
    if rec.get("addressCountry"):
        lines.append(str(rec["addressCountry"]))
    return lines


def _contact_card(rec: dict[str, Any], address_lines: list[str]) -> str:
    """A paste-ready contact block: name, full address, email, phone (phone in
    the US display format — this text is for reading, not for the CRM)."""
    parts = [rec.get("name") or "", *address_lines]
    if rec.get("emailAddress"):
        parts.append(str(rec["emailAddress"]))
    if rec.get("phoneNumber"):
        parts.append(format_us(str(rec["phoneNumber"])))
    return "\n".join(p for p in parts if p)


async def peek(client: SessionClient, entity: str, record_id: str) -> dict[str, Any]:
    """A pop-up detail read for a linked contact / company / client.

    ``entity`` must be in :data:`PEEK_FIELDS` (allowlist). Returns the record's
    name + its curated non-empty fields for the modal. For a Contact it also adds a
    combined "Address" field and a ``copyText`` contact card (name/address/email/
    phone) for the copy-to-clipboard button. Runs as the user (ACL enforced).
    """
    spec = PEEK_FIELDS.get(entity)
    if spec is None:
        raise SessionError(f"Cannot look up {entity} records.")
    extra: tuple[str, ...] = ()
    if entity == CONTACT:
        extra = _CONTACT_ADDRESS_ATTRS
    elif entity == MENTOR_PROFILE:
        extra = ("contactRecordId",)  # → the linked Contact's personal email
    select = ",".join(dict.fromkeys(["name", *(attr for attr, _, _ in spec), *extra]))
    try:
        rec = await client.get(entity, record_id, select=select)
    except EspoError as exc:
        # A forbidden read is an expected ACL outcome, not a server failure — a
        # manager may not be granted read on a linked record (e.g. the client's
        # CClientProfile). Degrade to a "restricted" marker so the pop-up shows a
        # friendly note (and, for the aggregated Company link, the sections the
        # user CAN read still render) instead of a 502.
        if _is_forbidden(exc):
            return {"entity": entity, "name": None, "fields": [], "restricted": True}
        raise
    fields = [
        {"label": label, "value": rec.get(attr), "type": ftype}
        for attr, label, ftype in spec
        if rec.get(attr) not in (None, "", [])
    ]
    result: dict[str, Any] = {"entity": entity, "name": rec.get("name"), "fields": fields}
    if entity == CONTACT:
        address = _address_lines(rec)
        if address:
            fields.append({"label": "Address", "value": "\n".join(address), "type": "longtext"})
        result["copyText"] = _contact_card(rec, address)
    elif entity == MENTOR_PROFILE:
        # The mentor's personal (home) email lives on the linked Contact — shown
        # next to the CBM address so a colleague can also reach them personally.
        email = await _mentor_personal_email(client, rec.get("contactRecordId"))
        if email:
            pos = next(
                (i + 1 for i, f in enumerate(fields) if f["label"] == "CBM email"),
                sum(1 for f in fields if f["label"] in ("Mentor type", "Status")),
            )
            fields.insert(pos, {"label": "Personal email", "value": email, "type": "email"})
    return result


async def _mentor_personal_email(client: SessionClient, contact_id: Any) -> Optional[str]:
    """The mentor's linked Contact's email address — best-effort (a missing
    link, a forbidden read, or any CRM failure just means no row is shown)."""
    if not contact_id:
        return None
    try:
        contact = await client.get(CONTACT, str(contact_id), select="emailAddress")
    except EspoError as exc:
        log.debug("mentor personal email unavailable (contact %s): %s", contact_id, exc)
        return None
    return contact.get("emailAddress") or None


# The transcript column stays out of the base select: it is feature-detected
# per read (§12.5 — the CRM field is a planned build), and once present it is
# the record's longest text, so it must never ride reads that don't render it.
_SESSION_SELECT = ",".join(["id", *sorted(SESSION_EDIT_NAMES - {TRANSCRIPT_FIELD})])


async def transcript_field_exists(client: SessionClient) -> bool:
    """Whether the live CRM has the §12.5 transcript field (CRM = truth)."""
    fields = await client.metadata(f"entityDefs.{SESSION}.fields")
    return TRANSCRIPT_FIELD in fields


# The Google Calendar event id (csession-calendar-field.md): app-managed, never
# user-editable (not in SESSION_FIELDS), feature-detected like the transcript so
# the calendar hook stays inert until the CRM field is built.
CAL_FIELD = "googleCalendarEventId"


async def get_session(client: SessionClient, session_id: str) -> dict[str, Any]:
    """An existing session's editable values + its attendees (read via the
    sessionAttendees relationship — see :func:`_attendees`). ``attendees`` = contact
    ids (for the editor's picker); ``attendeeNames`` = names (kept for the note
    feed); ``attendeeDetails`` = the session view's grid rows (email/phone/
    company). ``transcriptFieldExists`` gates the §12.5 transcript zone — the
    transcript column itself is selected only when the CRM has it."""
    fields = await client.metadata(f"entityDefs.{SESSION}.fields")
    has_transcript = TRANSCRIPT_FIELD in fields
    has_cal = CAL_FIELD in fields
    select = _SESSION_SELECT
    if has_transcript:
        select += "," + TRANSCRIPT_FIELD
    if has_cal:
        select += "," + CAL_FIELD
    rec = await client.get(SESSION, session_id, select=select)
    atts = await _attendees(client, session_id)
    rec["attendees"] = [c["id"] for c in atts]
    rec["attendeeNames"] = [c.get("name") for c in atts if c.get("name")]
    rec["attendeeDetails"] = [
        {
            "id": c["id"],
            "name": c.get("name"),
            "email": c.get("emailAddress"),
            "phone": c.get("phoneNumber"),
            "companyName": c.get("accountName"),
            "companyId": c.get("accountId"),
        }
        for c in atts
    ]
    rec["transcriptFieldExists"] = has_transcript
    rec["googleCalendarEventIdFieldExists"] = has_cal
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
    if add or remove:
        log.info("session %s attendees: +%d -%d", session_id, len(add), len(remove))
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


# Engagement statuses a completed session upgrades to Active: the engagement was
# assigned (or went dormant before any activity happened) and a completed session
# IS the activity that makes it live. Once Active the guard no longer matches, so
# only the first completed session flips it — later ones are no-ops, and a status
# a staffer set deliberately (On-Hold, Dormant, Completed, …) is never touched.
_ACTIVATE_ON_COMPLETED = ("Assigned", "Assignment Dormant")
_ENGAGEMENT_ACTIVE = "Active"
_SESSION_COMPLETED = "Completed"


async def _activate_engagement_on_completed(
    cfg: DomainConfig,
    client: SessionClient,
    parent_id: Optional[str],
    session_status: Optional[str],
) -> Optional[dict[str, Any]]:
    """Move an Assigned / Assignment Dormant engagement to Active when a session
    on it is saved as Completed. Mentor domain only (the other domains' parents
    have no engagement lifecycle). Best-effort — a CRM failure (e.g. the user's
    role can't edit the engagement) never fails the session save; the result dict
    tells the UI what happened (``None`` = the rule didn't apply)."""
    if cfg.parent_entity != ENGAGEMENT or not parent_id or session_status != _SESSION_COMPLETED:
        return None
    try:
        eng = await client.get(ENGAGEMENT, parent_id, select="engagementStatus")
        current = eng.get("engagementStatus")
        if current not in _ACTIVATE_ON_COMPLETED:
            return None
        await client.update(ENGAGEMENT, parent_id, {"engagementStatus": _ENGAGEMENT_ACTIVE})
        log.info("engagement %s: %s -> %s (completed session saved)",
                 parent_id, current, _ENGAGEMENT_ACTIVE)
        return {"activated": True, "from": current, "to": _ENGAGEMENT_ACTIVE}
    except EspoError as exc:
        log.warning("could not activate engagement %s after a completed session: %s",
                    parent_id, exc)
        return {"activated": False, "error": str(exc)}


async def accept_engagement(
    cfg: DomainConfig,
    client: SessionClient,
    parent_id: str,
    actor: Optional[str] = None,
) -> dict[str, Any]:
    """The mentor accepts a newly-assigned engagement from the grid: the domain's
    ``list_status_accept`` transition (Pending Acceptance → Assigned), written as
    the signed-in user so EspoCRM enforces their ACL.

    The status is re-read first and the call rejected (:class:`SessionError` →
    a 400, nothing written) when the record has moved on — the stale-grid guard,
    same shape as Client Administration's assign (v0.72.1). A best-effort stream
    note stamps the acceptance into the engagement's history naming the actor
    (the v0.74.0 audit-trail convention)."""
    if not cfg.list_status_accept or cfg.parent_entity != ENGAGEMENT:
        raise SessionError("This record's status cannot be changed here.")
    from_status, to_status = cfg.list_status_accept
    eng = await client.get(ENGAGEMENT, parent_id, select="engagementStatus")
    current = eng.get("engagementStatus")
    if current != from_status:
        raise SessionError(
            f'This engagement is no longer "{from_status}"'
            f'{f" (it is now {current!r})" if current else ""} — refresh the list.'
        )
    await client.update(ENGAGEMENT, parent_id, {"engagementStatus": to_status})
    log.info("engagement %s accepted: %s -> %s", parent_id, from_status, to_status)
    await post_stream_note(
        client, ENGAGEMENT, parent_id,
        f"Engagement accepted via the session tools{_by(actor)} — "
        f"status {from_status} → {to_status}.",
    )
    return {"status": "ok", "from": from_status, "to": to_status}


async def create_session(
    cfg: DomainConfig,
    client: SessionClient,
    parent_id: str,
    changes: dict[str, Any],
    attendees: Optional[list[str]] = None,
    owner_user_id: Optional[str] = None,
    *,
    settings: Optional[Any] = None,
    skip_calendar: bool = False,
) -> dict[str, Any]:
    """Create a ``CSession`` linked to ``parent_id`` and return it (with id).

    ``skip_calendar=True`` = the user declined the automatic Google Calendar
    invite in the pre-save prompt (they'll schedule it manually), so the
    calendar hook is not called; the response says so via
    ``calendar={ok, skipped, declined}``.

    Stamps the creating user as the session's assigned user so it is theirs to
    read/edit — required because these tools run under a role whose ``CSession``
    read/edit scope is ``own``: an unassigned session would be invisible to its
    own author right after creation. Written to BOTH ``assignedUser`` and
    ``assignedUsers`` (CSession has both, like CEngagement) so it sticks whichever
    the instance uses.

    Mentor domain: the engagement's WHOLE mentor team (assigned mentor +
    co-mentors) is stamped into ``assignedUsers``, not just the creator —
    every mentor on the engagement must see every session on it (read=own).
    """
    payload = _session_payload(changes)
    payload[cfg.session_parent_fk] = parent_id
    payload.setdefault("sessionType", cfg.default_session_type)
    payload.setdefault("status", "Scheduled")  # CRM status vocabulary: Scheduled/Completed/Cancelled/No Show
    if owner_user_id:
        payload.setdefault("assignedUserId", owner_user_id)
        team = await _engagement_mentor_user_ids(cfg, client, parent_id)
        payload.setdefault(
            "assignedUsersIds",
            [owner_user_id] + [u for u in team if u != owner_user_id],
        )
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
    session = await get_session(client, created["id"])
    engagement = await _activate_engagement_on_completed(
        cfg, client, parent_id, payload.get("status")
    )
    if engagement is not None:
        session["engagement"] = engagement
    if skip_calendar:
        session["calendar"] = {"ok": True, "skipped": True, "declined": True}
    elif settings is not None and owner_user_id:
        from sessions import gcal  # lazy — gcal imports this module

        session["calendar"] = await gcal.sync_session_calendar(
            settings, cfg, client, owner_user_id, session, changes,
            attendees_changed=bool(attendees), is_new=True, parent_id=parent_id,
        )
    return session


async def update_session(
    cfg: DomainConfig,
    client: SessionClient,
    session_id: str,
    changes: dict[str, Any],
    attendees: Optional[list[str]] = None,
    *,
    user_id: Optional[str] = None,
    settings: Optional[Any] = None,
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
    session = await get_session(client, session_id)
    # Only a save that CHANGES the status to Completed triggers the engagement
    # activation (the frontend diffs, so an untouched status never rides the
    # payload) — a notes-only edit to an already-completed session can't
    # re-activate an engagement a staffer deliberately parked.
    if cfg.parent_entity == ENGAGEMENT and payload.get("status") == _SESSION_COMPLETED:
        parent = await client.get(SESSION, session_id, select=cfg.session_parent_fk)
        engagement = await _activate_engagement_on_completed(
            cfg, client, parent.get(cfg.session_parent_fk), payload.get("status")
        )
        if engagement is not None:
            session["engagement"] = engagement
    if settings is not None and user_id:
        from sessions import gcal  # lazy — gcal imports this module

        session["calendar"] = await gcal.sync_session_calendar(
            settings, cfg, client, user_id, session, changes,
            attendees_changed=(attendees is not None), is_new=False,
        )
    return session


async def _profile_user_id(client: SessionClient, mentor_profile_id: str) -> Optional[str]:
    """The login User linked to a CMentorProfile (either assignment shape)."""
    profile = await client.get(
        MENTOR_PROFILE, mentor_profile_id, select="assignedUserId,assignedUsersIds"
    )
    return assigned_user_id(profile)


# CEngagement's hasMany link to its sessions (the mentor domain's
# parent_sessions_link) — used by the co-mentor add/remove session stamping.
_ENGAGEMENT_SESSIONS_LINK = "engagementSessions"


async def _engagement_mentor_user_ids(
    cfg: DomainConfig, client: SessionClient, parent_id: str
) -> list[str]:
    """Login Users of the engagement's whole mentor team — the assigned mentor
    (``mentorProfile``) plus every co-mentor (``additionalMentors``). Mentor
    domain only (other domains have no co-mentors); best-effort — an unreadable
    link just yields fewer users, never an error.
    """
    if not cfg.supports_comentor:
        return []
    ids: list[str] = []
    try:
        eng = await client.get(ENGAGEMENT, parent_id, select="mentorProfileId")
        if eng.get("mentorProfileId"):
            uid = await _profile_user_id(client, eng["mentorProfileId"])
            if uid:
                ids.append(uid)
        co = await client.list_related(
            ENGAGEMENT, parent_id, _COMENTOR_LINK,
            select="assignedUserId,assignedUsersIds", max_size=_PAGE,
        )
        for r in co.get("list", []):
            uid = assigned_user_id(r)
            if uid and uid not in ids:
                ids.append(uid)
    except EspoError as exc:
        log.warning("could not resolve mentor-team users for engagement %s: %s",
                    parent_id, exc)
    return ids


async def _profile_display_name(client: SessionClient, mentor_profile_id: str) -> str:
    """The mentor profile's name, for stream notes — 'CBM contact' when unreadable."""
    try:
        rec = await client.get(MENTOR_PROFILE, mentor_profile_id, select="name")
        return rec.get("name") or "CBM contact"
    except EspoError:
        return "CBM contact"


async def _engagement_client_records(
    client: SessionClient, engagement_id: str
) -> list[tuple[str, str]]:
    """(entity, id) pairs for the engagement's client-side records — the same set
    Client Administration re-homes on an assignment: every related contact, the
    client profile, and the company (``clientOrganization``, falling back to the
    client profile's ``linkedCompany`` — intake-created engagements carry the
    Account only there).
    """
    eng = await client.get(
        ENGAGEMENT,
        engagement_id,
        select="primaryEngagementContactId,engagementClientId,clientOrganizationId",
    )
    contact_ids: list[str] = []
    if eng.get("primaryEngagementContactId"):
        contact_ids.append(eng["primaryEngagementContactId"])
    related = await client.list_related(
        ENGAGEMENT, engagement_id, ENGAGEMENT_CONTACTS, select="id", max_size=_PAGE
    )
    for r in related.get("list", []):
        if r["id"] not in contact_ids:
            contact_ids.append(r["id"])
    client_id = eng.get("engagementClientId")
    account_id = eng.get("clientOrganizationId")
    if client_id and not account_id:
        try:
            prof = await client.get(CLIENT_PROFILE, client_id, select="linkedCompanyId")
            account_id = prof.get("linkedCompanyId")
        except EspoError:
            pass
    pairs: list[tuple[str, str]] = [(CONTACT, cid) for cid in contact_ids]
    if client_id:
        pairs.append((CLIENT_PROFILE, client_id))
    if account_id:
        pairs.append((ACCOUNT, account_id))
    return pairs


async def _stamp_client_records(
    client: SessionClient, engagement_id: str, user_id: str, *, remove: bool = False
) -> tuple[int, int]:
    """Add (or remove) ``user_id`` in ``assignedUsers`` of the engagement's client
    records (contacts / client profile / company) so a co-mentor gets the same
    access to them as the assigned mentor — Doug's defect report 2026-07-16: the
    co-mentor add stamped only the engagement itself.

    Touches ONLY the multi-user ``assignedUsersIds``; the single ``assignedUser``
    (the primary owner, e.g. the assigned mentor on a Contact) is never changed.
    An entity without "Multiple Assigned Users" enabled silently ignores the
    write (Contact needed that checkbox — enabled on the prod CRM 2026-07-16).
    Per-record best-effort; returns ``(updated, total)``.
    """
    try:
        pairs = await _engagement_client_records(client, engagement_id)
    except EspoError as exc:
        log.warning(
            "co-mentor client-record stamp: engagement %s unreadable: %s",
            engagement_id, exc,
        )
        return 0, 0
    updated = 0
    for entity, rid in pairs:
        try:
            rec = await client.get(entity, rid, select="assignedUsersIds")
            current = list(rec.get("assignedUsersIds") or [])
            if remove:
                if user_id not in current:
                    continue
                await client.update(
                    entity, rid,
                    {"assignedUsersIds": [u for u in current if u != user_id]},
                )
            else:
                if user_id in current:
                    continue
                await client.update(
                    entity, rid, {"assignedUsersIds": current + [user_id]}
                )
            updated += 1
        except EspoError as exc:
            log.warning(
                "co-mentor client-record stamp skipped (%s %s): %s", entity, rid, exc
            )
    return updated, len(pairs)


def _by(actor: Optional[str]) -> str:
    """`` by <name>`` for the co-mentor stream notes. The Note is created as the
    acting user, so Espo's stream already shows them as the author — naming them
    in the text as well keeps the record self-contained when it's read via the
    API, an export, or a quoted copy where authorship isn't visible.
    """
    return f" by {actor}" if actor else ""


async def add_comentor(
    client: SessionClient, engagement_id: str, mentor_profile_id: str,
    actor: Optional[str] = None,
) -> dict[str, Any]:
    """Attach a co-mentor (CMentorProfile) to an engagement (additionalMentors).
    ``actor`` (the signed-in user's display name) is woven into the stream note
    so the history reads "who did this" even outside the stream UI.

    Also adds the co-mentor's login User to the engagement's ``assignedUsers``:
    the Mentor Role reads CEngagement at "own", and with ``assignedUser``
    disabled "own" means membership in ``assignedUsers`` — without this the
    engagement never appears in the co-mentor's own engagement list. The same
    User is also stamped onto the engagement's client records (contacts / client
    profile / company — :func:`_stamp_client_records`) so the co-mentor can work
    them like the assigned mentor. Best-effort (the relate is the source of
    truth); a failure returns a ``warning`` the UI shows instead of silently
    leaving the co-mentor blind. A stream note on the engagement records what
    was done (and via which app).
    """
    await client.relate(ENGAGEMENT, engagement_id, _COMENTOR_LINK, mentor_profile_id)
    name = await _profile_display_name(client, mentor_profile_id)
    try:
        user_id = await _profile_user_id(client, mentor_profile_id)
        if not user_id:
            await post_stream_note(
                client, ENGAGEMENT, engagement_id,
                f"Added co-mentor {name} via the session tools{_by(actor)} — "
                "they have no linked login user, so no record access was granted "
                "(assign one in Mentor Administration).",
            )
            return {
                "status": "ok",
                "warning": (
                    "Added — but this CBM contact has no linked login user, so the "
                    "engagement will not appear in their engagement list until one "
                    "is assigned in Mentor Administration."
                ),
            }
        eng = await client.get(ENGAGEMENT, engagement_id, select="assignedUsersIds")
        current = list(eng.get("assignedUsersIds") or [])
        if user_id not in current:
            await client.update(
                ENGAGEMENT, engagement_id, {"assignedUsersIds": current + [user_id]}
            )
        # Backfill the engagement's EXISTING sessions so the co-mentor sees the
        # whole session history, not just sessions created from now on (CSession
        # read=own). Per-session best-effort: under edit=own the acting mentor
        # can only stamp sessions they own — anything else is logged and skipped.
        sessions_data = await client.list_related(
            ENGAGEMENT, engagement_id, _ENGAGEMENT_SESSIONS_LINK,
            select="assignedUsersIds", max_size=_PAGE,
        )
        for s in sessions_data.get("list", []):
            cur = list(s.get("assignedUsersIds") or [])
            if user_id in cur:
                continue
            try:
                await client.update(
                    SESSION, s["id"], {"assignedUsersIds": cur + [user_id]}
                )
            except EspoError as exc:
                log.warning("co-mentor session stamp skipped (session %s): %s",
                            s["id"], exc)
        # The defect fix (2026-07-16): the co-mentor must also become an
        # assigned user on the engagement's client records, not just the
        # engagement — otherwise the client's contact/profile/company stay
        # invisible/read-only to them under read-own roles.
        stamped, total = await _stamp_client_records(client, engagement_id, user_id)
    except EspoError as exc:
        log.warning(
            "co-mentor visibility stamp failed (engagement %s, profile %s): %s",
            engagement_id, mentor_profile_id, exc,
        )
        await post_stream_note(
            client, ENGAGEMENT, engagement_id,
            f"Added co-mentor {name} via the session tools{_by(actor)} — but "
            "granting their user access to the engagement failed; they may not "
            "see it in their list.",
        )
        return {
            "status": "ok",
            "warning": (
                "Added — but they could not be given access to the engagement, so "
                "it may not appear in their engagement list. (Their user may be on "
                "a different team, or your role may not allow assigning users.)"
            ),
        }
    await post_stream_note(
        client, ENGAGEMENT, engagement_id,
        f"Added co-mentor {name} via the session tools{_by(actor)} — their user "
        f"was added to the assigned users on the engagement, its sessions, and "
        f"{stamped}/{total} related client record(s) (contacts / client profile "
        "/ company).",
    )
    return {"status": "ok"}


async def remove_comentor(
    client: SessionClient, engagement_id: str, mentor_profile_id: str,
    actor: Optional[str] = None,
) -> dict[str, Any]:
    """Detach a co-mentor from an engagement — the reverse of :func:`add_comentor`.
    ``actor`` names the signed-in user in the stream note, like the add.
    Only the ``additionalMentors`` relation: the assigned mentor
    (``CEngagement.mentorProfile``) is managed in Client Administration, not here.

    Also removes their login User from ``assignedUsers`` (undoing the add-time
    visibility stamp) and from the engagement's client records
    (:func:`_stamp_client_records` in reverse) — unless that User also belongs
    to the assigned mentor or to a co-mentor still on the engagement. Best-effort:
    a failure here leaves harmless extra visibility, never a broken remove. A
    stream note on the engagement records what was done.
    """
    await client.unrelate(ENGAGEMENT, engagement_id, _COMENTOR_LINK, mentor_profile_id)
    name = await _profile_display_name(client, mentor_profile_id)
    note = f"Removed co-mentor {name} via the session tools{_by(actor)}."
    try:
        user_id = await _profile_user_id(client, mentor_profile_id)
        if not user_id:
            await post_stream_note(client, ENGAGEMENT, engagement_id, note)
            return {"status": "ok"}
        eng = await client.get(
            ENGAGEMENT, engagement_id, select="mentorProfileId,assignedUsersIds"
        )
        current = list(eng.get("assignedUsersIds") or [])
        if user_id not in current:
            await post_stream_note(client, ENGAGEMENT, engagement_id, note)
            return {"status": "ok"}
        protected: set[str] = set()
        if eng.get("mentorProfileId"):
            assigned = await _profile_user_id(client, eng["mentorProfileId"])
            if assigned:
                protected.add(assigned)
        remaining = await client.list_related(
            ENGAGEMENT, engagement_id, _COMENTOR_LINK,
            select="assignedUserId,assignedUsersIds", max_size=_PAGE,
        )
        for r in remaining.get("list", []):
            uid = assigned_user_id(r)
            if uid:
                protected.add(uid)
        if user_id not in protected:
            await client.update(
                ENGAGEMENT, engagement_id,
                {"assignedUsersIds": [u for u in current if u != user_id]},
            )
            # Un-stamp the engagement's sessions too (the reverse of the
            # add-time backfill) — except sessions the removed co-mentor
            # personally owns (their assignedUser), which stay theirs.
            sessions_data = await client.list_related(
                ENGAGEMENT, engagement_id, _ENGAGEMENT_SESSIONS_LINK,
                select="assignedUserId,assignedUsersIds", max_size=_PAGE,
            )
            for s in sessions_data.get("list", []):
                cur = list(s.get("assignedUsersIds") or [])
                if user_id not in cur or s.get("assignedUserId") == user_id:
                    continue
                try:
                    await client.update(
                        SESSION, s["id"],
                        {"assignedUsersIds": [u for u in cur if u != user_id]},
                    )
                except EspoError as exc:
                    log.warning("co-mentor session un-stamp skipped (session %s): %s",
                                s["id"], exc)
            # Reverse of the add-time client-record stamp (contacts / client
            # profile / company).
            stamped, total = await _stamp_client_records(
                client, engagement_id, user_id, remove=True
            )
            note = (
                f"Removed co-mentor {name} via the session tools{_by(actor)} — "
                f"their user's access was removed from the engagement, its "
                f"sessions, and {stamped}/{total} related client record(s)."
            )
        else:
            note = (
                f"Removed co-mentor {name} via the session tools{_by(actor)} — "
                "assigned-user access kept (their user is shared with the "
                "assigned mentor or another co-mentor)."
            )
    except EspoError as exc:
        log.warning(
            "co-mentor visibility un-stamp failed (engagement %s, profile %s): %s",
            engagement_id, mentor_profile_id, exc,
        )
        note += " (Access cleanup failed — their user may retain visibility.)"
    await post_stream_note(client, ENGAGEMENT, engagement_id, note)
    return {"status": "ok"}


async def mentor_options(client: SessionClient) -> list[dict[str, Any]]:
    """id/name of mentor profiles, for the co-mentor picker (mentor domain)."""
    data = await client.list(MENTOR_PROFILE, select="name", max_size=_PAGE, order_by="name")
    return [{"id": r["id"], "name": r.get("name")} for r in data.get("list", [])]


async def field_options(client: SessionClient) -> dict[str, list[Any]]:
    """Live option lists for the CSession enum/multi-enum/duration fields (CRM =
    truth). Duration options are seconds ints (the CRM's preset choices)."""
    fields = await client.metadata(f"entityDefs.{SESSION}.fields")
    options: dict[str, list[Any]] = {}
    for name in SESSION_OPTION_FIELDS:
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


async def field_spec_live(client: SessionClient) -> list[dict]:
    """The editor field spec as the live CRM can honor it.

    The transcript entry is the one feature-gated field (§12.5): serving it
    while the CRM lacks the column would render an editor box whose save the
    CRM must reject, so it appears only once the field really exists.
    """
    if await transcript_field_exists(client):
        return SESSION_FIELDS
    return [f for f in SESSION_FIELDS if f["name"] != TRANSCRIPT_FIELD]
