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
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional, Protocol

from assignments.service import (
    ACCOUNT,
    CLIENT_PROFILE,
    ENGAGEMENT_CONTACTS,
    assigned_user_id,
    is_assigned_to,
)
from core.config import get_settings
from core.crm_upsert import create_dropping_invalid, find_create_or_fill
from core.espo import EspoError, is_forbidden
from core.phone import e164_or_none, format_us
from core.stream import post_stream_note

from .config import (
    CONTACT,
    CREATE_COMPANY_FIELDS,
    CREATE_CONTACT_FIELDS,
    CREATE_MANAGER_FIELD,
    CONTRIBUTION_EDIT_NAMES,
    CONTRIBUTION_ENUM_FIELDS,
    CONTRIBUTION_FIELDS,
    CONTRIBUTION_LIST_SELECT,
    DELIVERABLE_EDIT_NAMES,
    DELIVERABLE_ENUM_FIELDS,
    DELIVERABLE_FIELDS,
    DELIVERABLE_LIST_SELECT,
    DETAIL_SESSION_SELECT,
    GRANT_EDIT_NAMES,
    GRANT_ENUM_FIELDS,
    GRANT_FIELDS,
    GRANT_LIST_SELECT,
    ENGAGEMENT,
    MENTOR_PROFILE,
    SESSION,
    SESSION_EDIT_NAMES,
    SESSION_ENUM_FIELDS,
    SESSION_OPTION_FIELDS,
    SESSION_FIELDS,
    AI_SUMMARY_FIELD,
    TRANSCRIPT_DOC_URL_FIELD,
    TRANSCRIPT_FIELD,
    DomainConfig,
)

log = logging.getLogger("cbm_intake.sessions.service")

_PAGE = 200
_COMENTOR_LINK = "additionalMentors"
_ATTENDEE_LINK = "sessionAttendees"

# Preferred meeting service (mentor-supplied Zoom, 2026-07-24): a mentor whose
# profile prefers their own Zoom Personal Meeting room gets its link pre-filled
# into NEW sessions' videoMeetingLink, and the calendar hook already treats a
# present link as external (no Meet is minted). Both fields are feature-detected
# from CRM metadata (the mentorSummary precedent; build spec:
# cmentorprofile-meeting-fields.md), so this is inert until the CRM builds them.
# The provider value must match the CRM enum option verbatim.
MEETING_PROVIDER_FIELD = "preferredMeetingProvider"
MEETING_LINK_FIELD = "zoomPersonalLink"
ZOOM_PMI_PROVIDER = "Zoom Personal Meeting"

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
    async def upload_attachment(
        self, *, filename: str, content_type: str, data_base64: str,
        related_type: str, field: str, role: str = "Attachment",
    ) -> str: ...
    async def download_attachment(self, attachment_id: str) -> tuple[bytes, str]: ...


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


def _is_crm_server_error(exc: EspoError) -> bool:
    """True when the CRM itself failed with a 5xx — its own server-side error
    (e.g. a database rejection), not the caller's data or ACL. Same first-status
    matching rule as :func:`_is_forbidden`."""
    m = _HTTP_STATUS_RE.search(str(exc))
    return bool(m) and m.group(1).startswith("5")


async def resolve_manager_profile(client: SessionClient, user_id: str) -> Optional[str]:
    """The ``CMentorProfile`` id whose assigned login User is ``user_id``.

    Scans the profiles readable by this user and matches in Python — never a
    ``where`` on ``assignedUserId`` (prod forbids it). A regular user whose ACL
    scopes ``CMentorProfile`` to "own" simply gets a one-row list. Returns None
    when no profile is linked to the user. Matching is MEMBERSHIP over the
    whole collaborators list (``is_assigned_to``), not equality against the
    first entry — a profile listing another user first must still resolve.
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
            if is_assigned_to(r, user_id):
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


async def default_meeting_link(client: SessionClient, user_id: str) -> Optional[str]:
    """The acting user's preferred meeting link for NEW sessions, or None for
    the default (a blank link makes the calendar hook create a Google Meet).

    Reads the signed-in user's own ``CMentorProfile``: when the feature-detected
    ``preferredMeetingProvider`` is "Zoom Personal Meeting" AND a
    ``zoomPersonalLink`` is stored, that link is returned so the session editor
    pre-fills it — the user sees exactly what will be used and can clear it to
    get a Meet instead. Entirely best-effort: fields not built in the CRM, no
    linked profile, or any read failure just means None, never an error.
    """
    try:
        fields = await client.metadata(f"entityDefs.{MENTOR_PROFILE}.fields")
        if not (
            isinstance(fields.get(MEETING_PROVIDER_FIELD), dict)
            and isinstance(fields.get(MEETING_LINK_FIELD), dict)
        ):
            return None
        profile_id = await resolve_manager_profile(client, user_id)
        if not profile_id:
            return None
        profile = await client.get(
            MENTOR_PROFILE, profile_id,
            select=f"{MEETING_PROVIDER_FIELD},{MEETING_LINK_FIELD}",
        )
        if (profile.get(MEETING_PROVIDER_FIELD) or "") != ZOOM_PMI_PROVIDER:
            return None
        return (profile.get(MEETING_LINK_FIELD) or "").strip() or None
    except Exception as exc:  # noqa: BLE001 — a preference must never block the editor
        log.warning("meeting preference unavailable for user %s: %s", user_id, exc)
        return None


def _grid_row(cfg: DomainConfig, r: dict[str, Any]) -> dict[str, Any]:
    row = {"id": r["id"], "createdAt": r.get("createdAt")}
    for col in cfg.list_columns:
        row[col.key] = r.get(col.attr)
    if cfg.list_date_column:  # optional trailing date column (Start Date / Created)
        dkey, _, dattr = cfg.list_date_column
        row[dkey] = r.get(dattr)
    if cfg.list_contact_id_attr:
        row["contactId"] = r.get(cfg.list_contact_id_attr)  # for the contact pop-up link
    # Assigned manager (mentor / partner manager) pop-up link — the pop-up's
    # email rows are compose links, so the grid is two clicks from an email.
    if cfg.list_manager_id_attr and r.get(cfg.list_manager_id_attr):
        row["mentorId"] = r.get(cfg.list_manager_id_attr)
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


def company_id_attr(cfg: DomainConfig) -> Optional[str]:
    """The parent attribute holding the org's company Account id, from the
    domain's details entities (``clientOrganizationId`` / ``partnerCompanyId`` /
    ``sponsorCompanyId``). None when the domain has no company card."""
    for _, entity, id_attr in cfg.details_entities:
        if entity == ACCOUNT and id_attr != "id":
            return id_attr
    return None


# Account attributes that together describe "what business is this" — shown as
# one composed Overview fact (the Details Company card renders the same trio).
_INDUSTRY_ATTRS = ("industry", "cIndustrySector", "cIndustrySubsector")


async def _fill_company_industry(
    cfg: DomainConfig, client: SessionClient, parent: dict[str, Any]
) -> None:
    """Merge an ``_companyIndustry`` display value into the parent record, read
    from its company Account (Doug's ruling 2026-07-24: a partner's/funder's
    industry belongs to the company, so the rail reads it from there rather than
    the CRM growing a duplicate field on the profile).

    Best-effort in every direction — no company link, an Account the user's ACL
    can't read, or a failed call all leave the fact empty (rendered "—").
    """
    if not cfg.company_industry_fact:
        return
    attr = company_id_attr(cfg)
    company_id = parent.get(attr) if attr else None
    if not company_id:
        return
    try:
        acct = await client.get(ACCOUNT, company_id, select=",".join(_INDUSTRY_ATTRS))
    except EspoError as exc:
        log.warning("company industry unavailable for %s: %s", company_id, exc)
        return
    # Deduped so a company whose general industry equals its sector reads once.
    parts = dict.fromkeys(v for v in (acct.get(a) for a in _INDUSTRY_ATTRS) if v)
    if parts:
        parent["_companyIndustry"] = " / ".join(parts)


async def list_records(
    cfg: DomainConfig, client: SessionClient, user: dict[str, Any]
) -> dict[str, Any]:
    """The parents the signed-in user owns, as grid rows.

    ``{"records": [...], "profileFound": bool}`` — ``profileFound=False`` means
    the user has no linked ``CMentorProfile`` (so nothing can be scoped to them).

    A ``list_all`` domain (partner, sponsor) skips the manager-profile scoping
    entirely and lists every parent record the user's CRM ACL can read — the
    CRM's team permissions are the visibility gate, so ``profileFound`` is
    always True (a team member without a linked profile still sees the shared
    list). This also keeps CMentorProfile out of the list read path, so a
    team whose role has no CMentorProfile grant can still load the grid.
    """
    rows: list[dict[str, Any]] = []
    if cfg.list_all:
        offset = 0
        while True:
            data = await client.list(
                cfg.parent_entity,
                select=cfg.list_select,
                max_size=_PAGE,
                offset=offset,
            )
            page = data.get("list", [])
            rows.extend(page)
            if len(page) < _PAGE:
                break
            offset += _PAGE
    else:
        profile_id = await resolve_manager_profile(client, user["userId"])
        if not profile_id:
            return {"records": [], "profileFound": False}
        links = [cfg.manager_owned_link]
        if cfg.manager_comentor_link:  # engagements where the user is a CO-mentor
            links.append(cfg.manager_comentor_link)
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


# The client engagements referred by a partner (the Referred Clients tab). One
# read of CPartnerProfile.engagements; "Last Contact" reads the dedicated
# ``lastContactDate`` field, advanced whenever an outbound email is sent or a
# session is recorded on the engagement (see ``touch_last_contact``).
REFERRED_CLIENT_SELECT = (
    "name,engagementStatus,engagementStartDate,lastContactDate,"
    "mentorProfileName,mentorProfileId,"
    "primaryEngagementContactName,primaryEngagementContactId,"
    "totalSessions,createdAt"
)


def _referred_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r["id"],
        "name": r.get("name") or "(unnamed)",
        "status": r.get("engagementStatus"),
        "startDate": r.get("engagementStartDate"),
        "lastContact": r.get("lastContactDate"),
        "mentorName": r.get("mentorProfileName"),
        "mentorId": r.get("mentorProfileId"),
        "contactName": r.get("primaryEngagementContactName"),
        "contactId": r.get("primaryEngagementContactId"),
        "totalSessions": r.get("totalSessions"),
        "createdAt": r.get("createdAt"),
    }


async def list_referred_clients(
    cfg: DomainConfig, client: SessionClient, parent_id: str
) -> dict[str, Any]:
    """Client engagements that name this partner as their referring partner
    (``CEngagement.referringPartner`` → this ``CPartnerProfile``), read through
    the parent's reverse link AS THE SIGNED-IN USER — the related read requires
    read access to the parent, so it is the ACL gate, and the engagements are
    ACL-filtered too. Sorted newest-first. Returns ``{"records": [...]}``.

    Only the partner domain sets ``referred_clients_link``; the endpoint isn't
    registered elsewhere, but guard anyway so a misconfig can't read the wrong
    link."""
    if not cfg.referred_clients_link:
        return {"records": []}
    data = await client.list_related(
        cfg.parent_entity,
        parent_id,
        cfg.referred_clients_link,
        select=REFERRED_CLIENT_SELECT,
        max_size=_PAGE,
    )
    records = [_referred_row(r) for r in data.get("list", [])]
    records.sort(key=lambda x: (x.get("createdAt") or ""), reverse=True)
    return {"records": records}


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
    if not display:
        # No company NAME. Drop the self-pair first — a pop-up of the record you
        # are already looking at tells you nothing — and if that leaves nothing
        # linkable, this is simply an empty fact. It used to render "(details)"
        # over a link to itself, which is what a partner whose company had been
        # silently unlinked looked like: a value, not a gap (Doug, 2026-08-13).
        pairs = [p for p in pairs if p["id"] != parent.get("id")]
        if not pairs:
            if not it.always:
                return None
            return {
                "label": it.label, "value": None, "type": "text",
                "block": it.block, "section": it.section,
            }
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
            if not it.always:
                continue
            value = None  # rendered as "—" — the slot stays discoverable
        entry = {
            "label": it.label, "value": value, "type": it.type,
            "block": it.block, "section": it.section,
        }
        if it.link_entity and it.id_attr and parent.get(it.id_attr):
            entry["link"] = {"entity": it.link_entity, "id": parent[it.id_attr]}
        if it.type == "currency":
            entry["currency"] = parent.get(it.attr + "Currency")
        # The status fact becomes a clickable picker when the domain enables it.
        if cfg.status_edit_attr and it.attr == cfg.status_edit_attr:
            entry["statusEdit"] = True
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
    await _fill_company_industry(cfg, client, parent)
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
    # The panel is ALWAYS present when the domain has a notes field (Doug's
    # ruling 2026-07-18: Partner Notes shows at the top of the Overview even
    # when empty — the frontend renders a muted placeholder then), so managers
    # always see where the record-level notes live.
    overall_notes = None
    if cfg.overall_notes_attr:
        val = parent.get(cfg.overall_notes_attr)
        overall_notes = {
            "label": cfg.overall_notes_label,
            "value": "" if val in (None, []) else val,
            "type": cfg.overall_notes_type,
            # Inline editing on the Overview (Doug's ruling 2026-07-18: notes
            # are the most important item on partners/sponsors — no extra
            # clicks): the frontend PUTs /details/{entity}/{parent id} with
            # {attr: value}, the same whitelisted path the Details tab uses.
            "entity": cfg.parent_entity,
            "attr": cfg.overall_notes_attr,
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
        # The engagement's linked CClientProfile — the Analytics tab uses it to
        # render the client dashboard section alongside the engagement dashboard
        # (Doug's §17.5 ruling 2). None on other domains and on engagements
        # whose profile link is empty; the frontend guards on truthiness.
        "clientProfileId": parent.get("engagementClientId"),
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


async def cbm_member_email_map(
    client: SessionClient,
    cfg: DomainConfig,
    parent_id: Optional[str],
    acting_user_id: Optional[str] = None,
) -> dict[str, str]:
    """Contact id -> CBM mailbox (lowercased) for every CBM member on the record.

    Doug's ruling (2026-07-20): a CBM member is contacted ONLY at their
    ``cbmEmail`` — never the personal address on their Contact record. The
    calendar hook uses this map to substitute each member's CBM mailbox for
    their Contact's primary email when building event invitations; a member
    whose profile has no cbmEmail maps to ``""`` (skip — never invite
    personally). Members = the parent's assigned manager + (mentor domain)
    co-mentors, the same set as the default-invitee list — plus the ACTING
    user's own profile (``acting_user_id``), so the organizer is classified
    even when they aren't the record's manager/co-mentor (e.g. their Contact
    linked to the record as a plain client contact — the self-invite could
    otherwise recur through that side door). Best-effort per read: an
    unreadable profile just isn't in the map (logged), degrading that one
    person to client-contact treatment rather than failing the caller.
    """
    profiles: list[dict[str, Any]] = []
    if acting_user_id:
        try:
            profile_id = await resolve_manager_profile(client, acting_user_id)
            if profile_id:
                profiles.append(
                    await client.get(
                        MENTOR_PROFILE, profile_id,
                        select="name,cbmEmail,contactRecordId",
                    )
                )
        except EspoError as exc:
            log.warning(
                "member-email map: acting user %s profile unreadable: %s",
                acting_user_id, exc,
            )
    if parent_id and cfg.parent_manager_link:
        try:
            parent = await client.get(
                cfg.parent_entity, parent_id, select=f"{cfg.parent_manager_link}Id"
            )
            manager_id = parent.get(f"{cfg.parent_manager_link}Id")
            if manager_id:
                profiles.append(
                    await client.get(
                        MENTOR_PROFILE, manager_id,
                        select="name,cbmEmail,contactRecordId",
                    )
                )
        except EspoError as exc:
            log.warning(
                "member-email map: manager profile unreadable for %s %s: %s",
                cfg.parent_entity, parent_id, exc,
            )
    if parent_id and cfg.supports_comentor:
        try:
            co_data = await client.list_related(
                cfg.parent_entity, parent_id, _COMENTOR_LINK,
                select="name,cbmEmail,contactRecordId", max_size=_PAGE,
            )
            profiles.extend(co_data.get("list", []))
        except EspoError as exc:
            log.warning(
                "member-email map: co-mentors unreadable for %s %s: %s",
                cfg.parent_entity, parent_id, exc,
            )
    mapping: dict[str, str] = {}
    for profile in profiles:
        contact_id = await _resolve_member_contact(client, profile)
        if contact_id:
            mapping[contact_id] = (profile.get("cbmEmail") or "").strip().lower()
    return mapping


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
    has_doc_url = TRANSCRIPT_DOC_URL_FIELD in fields
    has_ai_summary = AI_SUMMARY_FIELD in fields
    has_cal = CAL_FIELD in fields
    select = _SESSION_SELECT
    if has_transcript:
        select += "," + TRANSCRIPT_FIELD
    if has_doc_url:
        select += "," + TRANSCRIPT_DOC_URL_FIELD
    if has_ai_summary:
        select += "," + AI_SUMMARY_FIELD
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
    rec["aiSummaryFieldExists"] = has_ai_summary
    rec["googleCalendarEventIdFieldExists"] = has_cal
    return rec


def _session_payload(changes: dict[str, Any]) -> dict[str, Any]:
    """Whitelisted scalar-field payload for a session write (attendees are synced
    separately via the relationship endpoints, not here)."""
    return {k: v for k, v in changes.items() if k in SESSION_EDIT_NAMES}


# A pasted image lands in the rich-text HTML as a base64 ``data:`` URI — one
# screenshot can exceed the CRM column (MEDIUMTEXT, 16 MB), which MySQL rejects
# with "Data too long" and EspoCRM surfaces as a bare HTTP 500 (live failure
# 2026-07-24, CSession.sessionNotes). Images belong on the Documents tab, so
# they are stripped here (and blocked at paste time in the shared editor).
_EMBEDDED_IMG_RE = re.compile(
    r"<img\b[^>]*\bsrc\s*=\s*[\"']data:[^\"']*[\"'][^>]*/?>", re.IGNORECASE
)
# Generous ceiling well under the column's worst-case byte capacity — typed or
# pasted TEXT never approaches this; only binary blobs smuggled as text can.
_MAX_TEXT_FIELD_CHARS = 4_000_000

_FIELD_LABELS = {f["name"]: f["label"] for f in SESSION_FIELDS}


def _strip_embedded_images(payload: dict[str, Any]) -> list[str]:
    """Remove base64 ``data:`` images from string fields, in place; returns the
    labels of the fields that had any. After stripping, a field still larger
    than the CRM column can hold raises :class:`SessionError` (readable 400)
    instead of letting the CRM 500 on it."""
    stripped: list[str] = []
    for key, value in payload.items():
        if not isinstance(value, str) or "data:" not in value:
            continue
        cleaned, count = _EMBEDDED_IMG_RE.subn("", value)
        if count:
            payload[key] = cleaned
            stripped.append(_FIELD_LABELS.get(key, key))
    for key, value in payload.items():
        if isinstance(value, str) and len(value) > _MAX_TEXT_FIELD_CHARS:
            label = _FIELD_LABELS.get(key, key)
            raise SessionError(
                f"The {label} content is too large to store "
                f"(over {_MAX_TEXT_FIELD_CHARS // 1_000_000} million characters). "
                "Nothing you typed has been lost — it is still in the editor. "
                "Remove pasted files or very large pasted content and save again."
            )
    return stripped


def _embedded_image_warning(stripped: list[str]) -> str:
    fields = " and ".join(stripped)
    return (
        f"The pasted image(s) in {fields} could not be stored and were removed "
        "— images can't be saved inside notes. Everything else was saved. To "
        "keep the image, upload it on the Documents tab instead."
    )


# --- inline images (pasted into the notes editors) --------------------------
#
# The RIGHT way to keep a pasted image: an EspoCRM Attachment (role "Inline
# Attachment") referenced from the wysiwyg HTML as
# ``<img src="?entryPoint=attachment&amp;id=…">`` — EspoCRM's own editor stores
# exactly this, its Wysiwyg saver binds the attachment to the record on save
# (so cleanup never collects it, its ACL follows the record, and the CRM UI
# renders it too), and the app proxies the bytes for display (the browser
# can't reach the CRM). The base64 strip above remains the fallback for
# anything that skips this path.
INLINE_IMAGE_MAX_MB = 5
_INLINE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_INLINE_IMAGE_FIELDS = {
    f["name"] for f in SESSION_FIELDS if f.get("type") == "wysiwyg"
}
# EspoCRM validates an inline attachment by deriving the mime type FROM THE
# FILENAME EXTENSION and requiring it to equal the declared type
# (Tools/Attachment/Checker.php checkTypeImage) — an extensionless name is
# rejected with "Not allowed file type." (found live 2026-07-24), so the
# stored filename always carries the canonical extension for its type.
_INLINE_IMAGE_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


async def upload_inline_image(
    client: SessionClient,
    *,
    filename: str,
    content_type: str,
    data_base64: str,
    field: str,
) -> dict[str, str]:
    """Store a pasted image as an EspoCRM Inline Attachment on ``CSession`` and
    return its id. Validation errors are :class:`SessionError` (readable 400)."""
    if field not in _INLINE_IMAGE_FIELDS:
        raise SessionError("Images can only be pasted into the notes fields.")
    if content_type not in _INLINE_IMAGE_TYPES:
        raise SessionError(
            "Only JPEG, PNG, WebP, or GIF images can be pasted into notes."
        )
    # base64 is ~4/3 of the decoded size; cap before any decode/transfer.
    if len(data_base64) * 3 // 4 > INLINE_IMAGE_MAX_MB * 1024 * 1024:
        raise SessionError(
            f"The pasted image is too large (limit {INLINE_IMAGE_MAX_MB} MB). "
            "Upload it on the Documents tab instead."
        )
    ext = _INLINE_IMAGE_EXT[content_type]
    name = (filename or "pasted-image").strip() or "pasted-image"
    # Exact lowercase extension required (".jpeg" also maps to image/jpeg);
    # anything else — missing, wrong, or upper-case — is rebuilt on the stem.
    if not name.endswith(ext) and not (ext == ".jpg" and name.endswith(".jpeg")):
        name = name.rsplit(".", 1)[0] if "." in name else name
        name = (name or "pasted-image") + ext
    attachment_id = await client.upload_attachment(
        filename=name,
        content_type=content_type,
        data_base64=data_base64,
        related_type=SESSION,
        field=field,
        role="Inline Attachment",
    )
    log.info(
        "inline image stored as Attachment/%s (%s, ~%d KB, field %s)",
        attachment_id, content_type, len(data_base64) * 3 // 4 // 1024, field,
    )
    return {"id": attachment_id}


async def fetch_inline_image(
    client: SessionClient, attachment_id: str
) -> tuple[bytes, str]:
    """The attachment's bytes + content type, read AS THE USER — EspoCRM checks
    access against the related session, so a viewer sees an image iff they can
    read the session it belongs to."""
    return await client.download_attachment(attachment_id)


async def _sync_attendees(
    client: SessionClient, session_id: str, attendees: list[str]
) -> int:
    """Make the session's attendee set exactly ``attendees``, via the relationship
    link endpoints. Setting ``sessionAttendeesIds`` on a record update does NOT
    reliably sync this custom many-to-many (same reason co-mentors use ``relate``),
    so we relate the added contacts and unrelate the removed ones.

    Per-contact best-effort, returning the failure count (2026-07-20, Anthony
    Sacco's live incident): the FIELD edits are already saved when this runs, so
    a relate/unrelate rejection (typically EspoCRM's edit-on-the-foreign-Contact
    requirement) must surface as a warning on a successful save — raising made
    the whole save read as failed, and it was the exact recovery step the
    create-path warning tells users to take."""
    current = set((await get_session(client, session_id)).get("attendees") or [])
    target = set(attendees or [])
    add, remove = target - current, current - target
    if add or remove:
        log.info("session %s attendees: +%d -%d", session_id, len(add), len(remove))
    failed = 0
    for cid in add:
        try:
            await client.relate(SESSION, session_id, _ATTENDEE_LINK, cid)
        except EspoError as exc:
            failed += 1
            log.warning(
                "attendee relate failed on session %s (contact %s): %s",
                session_id, cid, exc,
            )
    for cid in remove:
        try:
            await client.unrelate(SESSION, session_id, _ATTENDEE_LINK, cid)
        except EspoError as exc:
            failed += 1
            log.warning(
                "attendee unrelate failed on session %s (contact %s): %s",
                session_id, cid, exc,
            )
    return failed


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
_SESSION_SCHEDULED = "Scheduled"


def _parse_stamp(value: Any) -> Optional[datetime]:
    """A stored CRM datetime ("YYYY-MM-DD HH:MM:SS", UTC) — or a bare date —
    as an aware UTC datetime; ``None`` when empty/unparseable."""
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _fmt_last_contact(cfg: DomainConfig, when: datetime) -> str:
    """The last-contact value formatted for the domain's field type."""
    if cfg.last_contact_type == "datetime":
        return when.strftime("%Y-%m-%d %H:%M:%S")
    return when.strftime("%Y-%m-%d")


async def touch_last_contact(
    cfg: DomainConfig,
    client: SessionClient,
    parent_id: Optional[str],
    when: Optional[datetime],
) -> None:
    """Advance the parent record's last-contact field to ``when`` — written only
    when it is more recent than the stored value and NOT in the future (a
    future-scheduled session is not a contact yet). Called when an outbound email
    is sent from the record or a session is recorded on it (Doug's request
    2026-07-25; ``DomainConfig.last_contact_attr``).

    Best-effort by contract: any failure (no field configured, the caller's ACL
    can't edit the parent, a CRM error, the field absent on this CRM) is logged
    and swallowed — it never fails the email/session it rode in on. Runs as the
    passed client (normally the signed-in user, so their ACL applies)."""
    attr = cfg.last_contact_attr
    if not attr or not parent_id or when is None:
        return
    if when > datetime.now(timezone.utc):
        return  # a future date is not a contact
    new_val = _fmt_last_contact(cfg, when)
    try:
        rec = await client.get(cfg.parent_entity, parent_id, select=attr)
        current = rec.get(attr)
        # Advance-only: ISO date/datetime strings sort lexicographically. Compare
        # on the shorter granularity so a stored date ("2026-07-25") vs a new
        # datetime ("2026-07-25 14:00:00") is a same-day no-op, never a regress.
        if current:
            cur_s, new_s = str(current), new_val
            n = min(len(cur_s), len(new_s))
            if cur_s[:n] >= new_s[:n]:
                return
        await client.update(cfg.parent_entity, parent_id, {attr: new_val})
        log.info("advanced last contact on %s/%s to %s", cfg.parent_entity, parent_id, new_val)
    except Exception as exc:  # noqa: BLE001 — best-effort decoration, never fatal
        log.warning(
            "could not advance last contact on %s/%s: %s",
            cfg.parent_entity, parent_id, exc,
        )


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


async def _maybe_create_follow_up(
    cfg: DomainConfig,
    client: SessionClient,
    parent_id: str,
    session: dict[str, Any],
    *,
    owner_user_id: str,
    settings: Optional[Any],
    skip_invite: bool,
) -> Optional[dict[str, Any]]:
    """Auto-create the agreed next session when one is closed (Doug's design,
    2026-07-22): a session saved as **Completed** with a future "Next session"
    date books a new **Scheduled** session on the record at that date/time,
    invited to every client contact + every CBM contact — the same default-
    invitee set a hand-created session starts with. The closed session's
    ``nextSessionDateTime`` stays untouched as the record of what was agreed;
    rescheduling happens by editing the created session, never this field.

    Guards (all quiet no-ops, ``None`` returned):
    - status not Completed, no next date, or the date is past/unparseable —
      a past "next date" is reference data, never a booking;
    - a session already exists at exactly that date/time (the re-save case);
    - ANY future Scheduled session already exists on the record — the next
      meeting is already on the books, and re-firing here would resurrect an
      old agreed date after a reschedule.

    Best-effort like the engagement-activation hook: a CRM failure never fails
    the closing save — the result dict carries ``created:false`` + the error
    for the UI. ``skip_invite`` = the user declined calendar invitations in
    the save-time prompt (the session is still created)."""
    if session.get("status") != _SESSION_COMPLETED:
        return None
    raw = session.get("nextSessionDateTime")
    next_dt = _parse_stamp(raw)
    if next_dt is None:
        return None
    if next_dt <= datetime.now(timezone.utc):
        log.info(
            "follow-up: next-session date %r on CSession/%s is in the past — "
            "kept as reference, nothing scheduled", raw, session.get("id"),
        )
        return None
    try:
        existing = await client.list_related(
            cfg.parent_entity, parent_id, cfg.parent_sessions_link,
            select="dateStart,status", max_size=_PAGE,
        )
        now = datetime.now(timezone.utc)
        for s in existing.get("list", []):
            ds = s.get("dateStart")
            if ds == raw:
                log.info(
                    "follow-up: %s/%s already has a session at %s — skipping",
                    cfg.parent_entity, parent_id, raw,
                )
                return None
            d = _parse_stamp(ds)
            if d and d > now and s.get("status") == _SESSION_SCHEDULED:
                log.info(
                    "follow-up: %s/%s already has an upcoming scheduled session "
                    "(%s) — skipping", cfg.parent_entity, parent_id, ds,
                )
                return None
        select = "name"
        if cfg.parent_manager_link:
            select += f",{cfg.parent_manager_link}Id"
        parent = await client.get(cfg.parent_entity, parent_id, select=select)
        contacts = await client.list_related(
            cfg.parent_entity, parent_id, cfg.parent_contacts_link,
            select="name", max_size=_PAGE,
        )
        attendee_ids = [str(c["id"]) for c in contacts.get("list", [])]
        co_mentors: list[dict[str, Any]] = []
        if cfg.supports_comentor:
            co_data = await client.list_related(
                cfg.parent_entity, parent_id, _COMENTOR_LINK,
                select="name,cbmEmail,contactRecordId", max_size=_PAGE,
            )
            co_mentors = co_data.get("list", [])
        for member in await _cbm_contacts(client, cfg, parent, co_mentors):
            if member["contactId"] not in attendee_ids:
                attendee_ids.append(member["contactId"])
        changes = {
            "name": f"{next_dt:%Y-%m-%d} - " + (parent.get("name") or "").strip(),
            "status": _SESSION_SCHEDULED,
            "dateStart": str(raw),
            # Default one-hour slot, the editor's own duration default.
            "dateEnd": (next_dt + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
        }
        # Reuse the normal create path: owner/team stamping, enum sanitizing,
        # attendee relates, and the calendar hook all apply. No recursion — the
        # created session is Scheduled, so its own follow-up check no-ops.
        created = await create_session(
            cfg, client, parent_id, changes, attendee_ids,
            owner_user_id=owner_user_id, settings=settings,
            skip_calendar=skip_invite,
        )
    except EspoError as exc:
        log.warning(
            "follow-up session create failed on %s/%s: %s",
            cfg.parent_entity, parent_id, exc,
        )
        return {"created": False, "error": str(exc)}
    log.info(
        "follow-up session %s created on %s/%s for %s (%d attendee(s), invites %s)",
        created.get("id"), cfg.parent_entity, parent_id, raw,
        len(attendee_ids), "skipped" if skip_invite else "requested",
    )
    result: dict[str, Any] = {
        "created": True,
        "id": created.get("id"),
        "name": created.get("name"),
        "dateStart": str(raw),
        "parentId": parent_id,
    }
    if created.get("calendar") is not None:
        result["calendar"] = created["calendar"]
    if created.get("warning"):
        result["warning"] = created["warning"]
    return result


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


async def status_edit_options(cfg: DomainConfig, client: SessionClient) -> list[str]:
    """Live enum options for the domain's editable status field (CRM = truth),
    for the Overview status picker. Empty when the domain doesn't enable it."""
    if not cfg.status_edit_attr:
        return []
    fields = await client.metadata(f"entityDefs.{cfg.parent_entity}.fields")
    opts = (fields.get(cfg.status_edit_attr) or {}).get("options")
    return [o for o in opts if o] if isinstance(opts, list) else []


async def set_status(
    cfg: DomainConfig,
    client: SessionClient,
    parent_id: str,
    new_status: str,
    actor: Optional[str] = None,
) -> dict[str, Any]:
    """Change the parent record's status to any live enum value from the Overview
    picker, written as the signed-in user so EspoCRM enforces their ACL.

    The value is validated against the live options (a stale/invalid pick raises
    :class:`SessionError` → 400, nothing written); an unchanged pick is a no-op.
    A best-effort stream note stamps the change into history naming the actor
    (the v0.74.0 audit-trail convention)."""
    if not cfg.status_edit_attr:
        raise SessionError("This record's status cannot be changed here.")
    options = await status_edit_options(cfg, client)
    if options and new_status not in options:
        raise SessionError(f'"{new_status}" is not a valid status.')
    rec = await client.get(cfg.parent_entity, parent_id, select=cfg.status_edit_attr)
    current = rec.get(cfg.status_edit_attr)
    if current == new_status:
        return {"status": "ok", "from": current, "to": new_status, "changed": False}
    await client.update(cfg.parent_entity, parent_id, {cfg.status_edit_attr: new_status})
    log.info("%s %s status %s -> %s", cfg.parent_entity, parent_id, current, new_status)
    await post_stream_note(
        client, cfg.parent_entity, parent_id,
        f"Status changed from {current or '—'} to {new_status} "
        f"via the session tools{_by(actor)}.",
    )
    return {"status": "ok", "from": current, "to": new_status, "changed": True}


async def set_primary_contact(
    cfg: DomainConfig,
    client: SessionClient,
    parent_id: str,
    contact_id: str,
    actor: Optional[str] = None,
) -> dict[str, Any]:
    """Designate one of the record's related contacts as its PRIMARY contact —
    the Details contacts table's "Make primary" action (Doug's ruling
    2026-07-24: there must be an easy way to change it).

    Writes the parent's primary-contact FK (``primaryPartnercontact`` /
    ``sponsorContact``) as the signed-in user, so EspoCRM enforces their ACL.
    The contact must already be linked to this record — the picker is the table
    of its own contacts, and setting a primary who isn't on the record would
    leave the Overview pointing at a stranger. An unchanged pick is a no-op.
    A best-effort stream note stamps the change (v0.74.0 audit convention).
    """
    if not cfg.primary_contact_settable:
        raise SessionError("This record's primary contact cannot be changed here.")
    attr = cfg.primary_contact_id_attr
    related = await client.list_related(
        cfg.parent_entity, parent_id, cfg.parent_contacts_link,
        select="name", max_size=_PAGE,
    )
    match = next((c for c in related.get("list", []) if c.get("id") == contact_id), None)
    if match is None:
        raise SessionError(
            "That contact isn't on this record — add it to the contacts list first."
        )
    rec = await client.get(cfg.parent_entity, parent_id, select=attr)
    current = rec.get(attr)
    name = match.get("name") or "the contact"
    if current == contact_id:
        return {"status": "ok", "contactId": contact_id, "contactName": name, "changed": False}
    await client.update(cfg.parent_entity, parent_id, {attr: contact_id})
    log.info(
        "%s %s primary contact %s -> %s", cfg.parent_entity, parent_id, current, contact_id
    )
    await post_stream_note(
        client, cfg.parent_entity, parent_id,
        f"{name} set as the primary contact via the session tools{_by(actor)}.",
    )
    return {"status": "ok", "contactId": contact_id, "contactName": name, "changed": True}


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
    skip_follow_up_invite: bool = False,
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
    stripped_images = _strip_embedded_images(payload)
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
    # The session EXISTS from here on — a failure on any follow-up write must
    # surface as success-with-warning naming the session, never as "Could not
    # create session" (which invites a retry that duplicates it). P2,
    # reliability review 2026-07-17; the create_contact pattern.
    attendee_warning = None
    if stripped_images:
        attendee_warning = _embedded_image_warning(stripped_images)
    if attendees:  # new record => relate all chosen attendees
        failed: list[str] = []
        for cid in attendees:
            try:
                await client.relate(SESSION, created["id"], _ATTENDEE_LINK, cid)
            except EspoError as exc:
                failed.append(cid)
                log.warning(
                    "attendee relate failed on new session %s (contact %s): %s",
                    created.get("id"), cid, exc,
                )
        if failed:
            attendee_warning = ((attendee_warning + " ") if attendee_warning else "") + (
                f"The session was created, but {len(failed)} of "
                f"{len(attendees)} attendee(s) could not be attached — open the "
                "session and re-save its attendees. Do not create it again."
            )
    log.info(
        "created session %s on %s/%s type=%s attendees=%d",
        created.get("id"), cfg.parent_entity, parent_id, payload.get("sessionType"),
        len(attendees or []),
    )
    # Same rule as the attendee relate above: the session EXISTS, so a failure
    # re-reading it must not surface as "Could not create session" — that reads
    # as "nothing was saved" and invites the retry that duplicates it (three
    # identical sessions on one engagement, 2026-07-17). Fall back to the record
    # the create returned; the UI re-fetches the record right after a save.
    try:
        session = await get_session(client, created["id"])
    except EspoError as exc:
        log.warning("could not re-read new session %s: %s", created.get("id"), exc)
        session = dict(created)
        attendee_warning = (attendee_warning or "") + (
            " The session was created, but its details could not be re-read — "
            "refresh the record to see it. Do not create it again."
        ).strip()
    if attendee_warning:
        session["warning"] = attendee_warning
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
    # A session created straight in the Completed state with an agreed next
    # date books the follow-up too (the mentor recorded a held meeting and its
    # agreed next one in a single save).
    if owner_user_id:
        follow_up = await _maybe_create_follow_up(
            cfg, client, parent_id, session,
            owner_user_id=owner_user_id, settings=settings,
            skip_invite=skip_follow_up_invite,
        )
        if follow_up is not None:
            session["followUp"] = follow_up
    # Recording a session is a contact: advance the parent's last-contact date to
    # the meeting date (advance-only; a future scheduled session is skipped).
    await touch_last_contact(
        cfg, client, parent_id,
        _parse_stamp(session.get("dateStart") or changes.get("dateStart")),
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
    skip_follow_up_invite: bool = False,
) -> dict[str, Any]:
    """Update whitelisted fields on a session; sync attendees separately.

    ``attendees=None`` leaves the attendee set untouched; a list (incl. ``[]``)
    replaces it via the relationship endpoints (see :func:`_sync_attendees`)."""
    payload = _session_payload(changes)
    stripped_images = _strip_embedded_images(payload)
    await _sanitize_enum_payload(client, payload)
    if payload:
        await client.update(SESSION, session_id, payload)
    attendee_failures = 0
    if attendees is not None:
        attendee_failures = await _sync_attendees(client, session_id, attendees)
    session = await get_session(client, session_id)
    warnings: list[str] = []
    if stripped_images:
        warnings.append(_embedded_image_warning(stripped_images))
    if attendee_failures:
        warnings.append(
            f"The session was saved, but {attendee_failures} attendee "
            f"change(s) could not be applied — you may not have permission to "
            f"those contact records. Ask CBM staff to check the contact's "
            f"assigned users, then re-save the attendees."
        )
    if warnings:
        session["warning"] = " ".join(warnings)
    # The status / next-date payload triggers below are diff-driven (the
    # frontend sends only changed fields), so a notes-only edit to an
    # already-completed session can neither re-activate a parked engagement
    # nor re-book a follow-up whose date has since been rescheduled.
    follow_up_trigger = (
        "status" in payload or "nextSessionDateTime" in payload
    ) and user_id
    parent_id: Optional[str] = None
    if follow_up_trigger or (
        cfg.parent_entity == ENGAGEMENT and payload.get("status") == _SESSION_COMPLETED
    ):
        parent = await client.get(SESSION, session_id, select=cfg.session_parent_fk)
        parent_id = parent.get(cfg.session_parent_fk)
    # Only a save that CHANGES the status to Completed triggers the engagement
    # activation.
    if cfg.parent_entity == ENGAGEMENT and payload.get("status") == _SESSION_COMPLETED:
        engagement = await _activate_engagement_on_completed(
            cfg, client, parent_id, payload.get("status")
        )
        if engagement is not None:
            session["engagement"] = engagement
    if settings is not None and user_id:
        from sessions import gcal  # lazy — gcal imports this module

        session["calendar"] = await gcal.sync_session_calendar(
            settings, cfg, client, user_id, session, changes,
            attendees_changed=(attendees is not None), is_new=False,
        )
    # A save that leaves the session Completed with an agreed next date books
    # the follow-up session (see _maybe_create_follow_up). Payload-gated: only
    # a save that touched status or the next date can fire.
    if follow_up_trigger and parent_id:
        follow_up = await _maybe_create_follow_up(
            cfg, client, parent_id, session,
            owner_user_id=user_id, settings=settings,
            skip_invite=skip_follow_up_invite,
        )
        if follow_up is not None:
            session["followUp"] = follow_up
    # Recording/updating a session is a contact: advance the parent's last-contact
    # date (advance-only; a future-dated session is skipped inside the helper).
    # Resolve the parent only if a trigger above didn't already.
    if cfg.last_contact_attr:
        if parent_id is None:
            try:
                parent = await client.get(
                    SESSION, session_id, select=cfg.session_parent_fk
                )
                parent_id = parent.get(cfg.session_parent_fk)
            except EspoError as exc:
                log.warning(
                    "could not resolve parent for last-contact on session %s: %s",
                    session_id, exc,
                )
        await touch_last_contact(
            cfg, client, parent_id,
            _parse_stamp(session.get("dateStart") or changes.get("dateStart")),
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
        except EspoError as exc:
            log.warning(
                "linkedCompany fallback read failed for CClientProfile/%s — "
                "the company stays blank: %s", client_id, exc,
            )
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


async def _link_or_escalate(
    client: SessionClient,
    admin_factory,
    op: str,
    engagement_id: str,
    link: str,
    related_id: str,
) -> None:
    """relate/unrelate as the signed-in user, falling back to the provisioning
    admin ONLY for a foreign-record denial.

    EspoCRM checks edit on BOTH sides of a link. Attaching a co-mentor therefore
    needs edit on the OTHER mentor's ``CMentorProfile`` — which a Mentor Role
    scoped to ``edit: own`` does not grant, so the whole feature 403s for every
    non-admin mentor (live on prod 2026-07-26; crm-test had ``edit: all`` and
    prod did not — the two drifted apart on 2026-07-16). Granting every mentor
    edit on every mentor profile just to make the link possible is a poor trade,
    so the narrow escalation is:

    * the user's own token attempts the link FIRST — EspoCRM's check on the
      ENGAGEMENT is the real authorization gate and it must pass on its own;
    * only ``noAccessToForeignRecord`` (the foreign half, which by definition
      means the engagement half already passed) is retried as the admin.

    Anything else — including a denial on the engagement — raises unchanged. If
    no admin credentials are configured, so does the original error, so the user
    still gets the readable "missing grant" 403.
    """
    try:
        await getattr(client, op)(ENGAGEMENT, engagement_id, link, related_id)
        return
    except EspoError as exc:
        escalatable = is_forbidden(exc) and "noAccessToForeignRecord" in str(exc)
        if not escalatable or admin_factory is None:
            raise
        log.info(
            "%s %s/%s/%s denied on the linked record — retrying as the "
            "provisioning admin (the user's edit access to the engagement "
            "already passed)", op, ENGAGEMENT, engagement_id, link,
        )
        try:
            admin = await admin_factory()
            await getattr(admin, op)(ENGAGEMENT, engagement_id, link, related_id)
        except Exception as admin_exc:  # noqa: BLE001
            # Surface the USER's error — it names the missing grant, which is
            # the actionable fact; the admin fallback failing is our problem.
            log.warning("admin fallback for %s also failed: %s", op, admin_exc)
            raise exc from None


async def add_comentor(
    client: SessionClient, engagement_id: str, mentor_profile_id: str,
    actor: Optional[str] = None, admin_factory=None,
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

    The link itself goes through :func:`_link_or_escalate` — see there for why a
    foreign-record denial is retried under the provisioning admin.
    """
    await _link_or_escalate(
        client, admin_factory, "relate", engagement_id, _COMENTOR_LINK, mentor_profile_id
    )
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
    actor: Optional[str] = None, admin_factory=None,
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
    await _link_or_escalate(
        client, admin_factory, "unrelate", engagement_id, _COMENTOR_LINK, mentor_profile_id
    )
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


# --- Contributions (the funder ledger — sponsor domain only) -----------------
# Plan: prds/funder-contributions-plan.md. Business rules (Doug, 2026-07-20):
# totals count status=Received ONLY; Cancelled = soft delete (excluded from
# every number, kept visible for audit; Unsuccessful excluded the same way);
# "future" = effective date on/after today; everything is computed on the fly,
# never stored; the period rollup anchors at the LAST received contribution
# and walks BACK in rolling windows so giving gaps show (the
# continuous-contributions principle).

CONTRIBUTION = "CContribution"
_CONTRIB_RECEIVED = "Received"
_CONTRIB_EXCLUDED = ("Cancelled", "Unsuccessful")
_CONTRIB_SCHEDULED = ("Pledged", "Committed")  # Applied deliberately excluded
# Effective date = first set wins (Doug's ruling): drives ordering, the
# future/past split, and every time window.
_CONTRIB_DATE_CHAIN = (
    "receivedDate", "expectedPaymentDate", "commitmentDate", "applicationDate"
)
_CONTRIB_PERIOD_CAP = 12  # rollup windows walked back from the anchor, max


def contribution_effective_date(row: dict[str, Any]) -> Optional[str]:
    """The row's effective date (``YYYY-MM-DD``) per the fallback chain."""
    for attr in _CONTRIB_DATE_CHAIN:
        if row.get(attr):
            return row[attr]
    return None


def _iso_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _add_months(d: date, months: int) -> date:
    """Calendar-month arithmetic (day clamped to the target month's length)."""
    m = d.month - 1 + months
    year, month = d.year + m // 12, m % 12 + 1
    day = min(d.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def _months_between(earlier: date, later: date) -> int:
    """Whole calendar months from ``earlier`` to ``later`` (floor, >= 0)."""
    months = (later.year - earlier.year) * 12 + later.month - earlier.month
    if later.day < earlier.day:
        months -= 1
    return max(0, months)


def _amount(row: dict[str, Any]) -> float:
    try:
        return float(row.get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


def _contribution_row(r: dict[str, Any], today: date) -> dict[str, Any]:
    """A decorated grid row: raw scalars + the derived flags the tab renders."""
    eff = contribution_effective_date(r)
    eff_d = _iso_date(eff)
    status = r.get("status")
    excluded = status in _CONTRIB_EXCLUDED
    row = {k: r.get(k) for k in (
        "id", "name", "contributionType", "status", "amount", "amountCurrency",
        "applicationDate", "commitmentDate", "expectedPaymentDate",
        "receivedDate", "acknowledgmentDate", "acknowledgmentSent",
        "nextGrantDeadline", "giftType", "designation", "createdAt",
    )}
    row["effectiveDate"] = eff
    # Upcoming = scheduled money still in motion, dated today or later.
    row["upcoming"] = bool(
        eff_d and eff_d >= today and not excluded and status != _CONTRIB_RECEIVED
    )
    row["excluded"] = excluded  # soft-deleted / unsuccessful: visible, never counted
    return row


def _period_rollup(
    received: list[tuple[date, float]], anchor: date, earliest: Optional[date], months: int
) -> list[dict[str, Any]]:
    """Rolling windows of ``months`` walking BACK from ``anchor`` (inclusive).

    Every window renders even when empty — a funder who paused shows the gap.
    Windows stop once they cover ``earliest`` (or after one window when there
    is no data), capped at ``_CONTRIB_PERIOD_CAP``.
    """
    windows: list[dict[str, Any]] = []
    end = anchor
    while len(windows) < _CONTRIB_PERIOD_CAP:
        start = _add_months(end, -months) + timedelta(days=1)
        in_window = [amt for (d, amt) in received if start <= d <= end]
        windows.append({
            "start": start.isoformat(),
            "end": end.isoformat(),
            "count": len(in_window),
            "total": round(sum(in_window), 2),
        })
        if earliest is None or start <= earliest:
            break
        end = start - timedelta(days=1)
    return windows


def contribution_summary(rows: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """The dashboard block: four tiles + recency callout + period rollups.

    Pure math over the decorated rows so every business rule lives (and is
    tested) in one place. Received-only totals; Cancelled/Unsuccessful never
    counted; rolling 12-month tile window; rollups anchored at the last
    received contribution (today when none).
    """
    received_amounts: list[float] = []   # every Received row (count/total tiles)
    received: list[tuple[date, float]] = []  # dated Received rows (time math)
    for r in rows:
        if r.get("status") == _CONTRIB_RECEIVED:
            received_amounts.append(_amount(r))
            d = _iso_date(r.get("effectiveDate"))
            if d:  # an undated Received row counts in totals, never in windows
                received.append((d, _amount(r)))
    year_ago = today - timedelta(days=365)
    scheduled = [
        r for r in rows
        if r.get("status") in _CONTRIB_SCHEDULED
        and (_iso_date(r.get("effectiveDate")) or today) >= today
    ]
    dated = sorted((d for d, _ in received))
    anchor = dated[-1] if dated else today
    counted_dates = [
        _iso_date(r.get("effectiveDate")) for r in rows
        if not r.get("excluded") and _iso_date(r.get("effectiveDate"))
    ]
    earliest = min(counted_dates) if counted_dates else None

    last_received = None
    if received:
        d, amt = max(received, key=lambda t: t[0])
        last_received = {
            "date": d.isoformat(), "amount": amt, "monthsAgo": _months_between(d, today),
        }
    next_expected = None
    upcoming = sorted(
        ((_iso_date(r.get("effectiveDate")) or today, _amount(r)) for r in scheduled),
        key=lambda t: t[0],
    )
    if upcoming:
        next_expected = {"date": upcoming[0][0].isoformat(), "amount": upcoming[0][1]}

    currencies = [r.get("amountCurrency") for r in rows if r.get("amountCurrency")]
    return {
        "totalCount": len(received_amounts),
        "totalAmount": round(sum(received_amounts), 2),
        "last12MonthsAmount": round(sum(a for d, a in received if d >= year_ago), 2),
        "scheduledAmount": round(sum(_amount(r) for r in scheduled), 2),
        "scheduledCount": len(scheduled),
        "lastReceived": last_received,
        "nextExpected": next_expected,
        "currency": currencies[0] if currencies else "USD",
        "periods": {
            "half": _period_rollup(received, anchor, earliest, 6),
            "year": _period_rollup(received, anchor, earliest, 12),
        },
    }


async def list_contributions(
    cfg: DomainConfig, client: SessionClient, parent_id: str
) -> dict[str, Any]:
    """All of a funder's contributions + the computed summary block.

    The parent record is read first AS THE USER — that's the ACL gate (a
    forbidden funder never leaks its ledger) and supplies the funder name for
    the editor's default title.
    """
    parent = await client.get(cfg.parent_entity, parent_id, select="name")
    data = await client.list_related(
        cfg.parent_entity, parent_id, cfg.contributions_link,
        select=CONTRIBUTION_LIST_SELECT, max_size=_PAGE,
    )
    today = datetime.now(timezone.utc).date()
    rows = [_contribution_row(r, today) for r in data.get("list", [])]
    rows.sort(key=lambda r: (r.get("effectiveDate") or "", r.get("createdAt") or ""),
              reverse=True)
    return {
        "records": rows,
        "summary": contribution_summary(rows, today),
        "parentName": parent.get("name"),
    }


async def get_contribution(
    cfg: DomainConfig, client: SessionClient, contribution_id: str
) -> dict[str, Any]:
    """One contribution's full editable values, record-scope checked.

    The row must be linked to a parent of THIS domain's type that the user can
    read (the documents-endpoint precedent) — a bare CContribution id never
    resolves outside the funder workspace.
    """
    rec = await client.get(
        CONTRIBUTION, contribution_id,
        select=CONTRIBUTION_LIST_SELECT + ",notes,description," + cfg.contributions_parent_fk,
    )
    parent_id = rec.get(cfg.contributions_parent_fk)
    if not parent_id:
        raise SessionError("That contribution isn't linked to a funder record.")
    await client.get(cfg.parent_entity, parent_id, select="id")  # ACL gate
    today = datetime.now(timezone.utc).date()
    row = _contribution_row(rec, today)
    row["notes"] = rec.get("notes")
    row["description"] = rec.get("description")
    row["parentId"] = parent_id
    return row


def _contribution_payload(changes: dict[str, Any]) -> dict[str, Any]:
    """Whitelisted payload for a contribution write — anything outside
    ``CONTRIBUTION_EDIT_NAMES`` (smuggled links, FK swaps) is dropped."""
    return {k: v for k, v in changes.items() if k in CONTRIBUTION_EDIT_NAMES}


async def contribution_field_options(client: SessionClient) -> dict[str, list[Any]]:
    """Live option lists for the CContribution enum fields (CRM = truth)."""
    fields = await client.metadata(f"entityDefs.{CONTRIBUTION}.fields")
    options: dict[str, list[Any]] = {}
    for name in CONTRIBUTION_ENUM_FIELDS:
        opts = (fields.get(name) or {}).get("options")
        if isinstance(opts, list):
            options[name] = [o for o in opts if o != ""]
    return options


async def contribution_field_required(client: SessionClient) -> list[str]:
    """Editable CContribution fields the CRM marks required (read live)."""
    fields = await client.metadata(f"entityDefs.{CONTRIBUTION}.fields")
    return [
        name for name in sorted(CONTRIBUTION_EDIT_NAMES)
        if isinstance(fields.get(name), dict) and fields[name].get("required")
    ]


async def _sanitize_contribution_enums(
    client: SessionClient, payload: dict[str, Any]
) -> None:
    """Drop enum values the live CContribution no longer accepts, in place
    (the CSession `_sanitize_enum_payload` contract: single enums omitted,
    fails open when options can't be fetched)."""
    enum_keys = [k for k in payload if k in CONTRIBUTION_ENUM_FIELDS]
    if not enum_keys:
        return
    try:
        options = await contribution_field_options(client)
    except Exception as exc:  # noqa: BLE001 — fail open, never block the save
        log.warning("could not fetch CContribution enum options (%s); keeping values", exc)
        return
    for key in enum_keys:
        opts = options.get(key)
        value = payload[key]
        if opts is None or value in (None, ""):
            continue
        if value not in opts:
            log.warning("CContribution.%s: dropping unrecognized value %r", key, value)
            del payload[key]


# The instance's currency; the editor collects a bare number, the app supplies
# the code. CBM operates in USD only.
_CONTRIB_DEFAULT_CURRENCY = "USD"


def _backfill_amount_currency(
    payload: dict[str, Any], existing_currency: Optional[str] = None
) -> None:
    """EspoCRM's currency type validates ``amount`` against ``amountCurrency``
    (``validCurrency``) — a bare amount on a record whose stored currency is
    null is REJECTED. The editor never collects a currency, so any save that
    sets an amount carries one: the record's existing currency, else USD.
    (Found live 2026-07-21: editing an amount onto a contribution created
    without one 400'd; creates passed only via the instance default.)"""
    if payload.get("amount") is not None and not payload.get("amountCurrency"):
        payload["amountCurrency"] = existing_currency or _CONTRIB_DEFAULT_CURRENCY


async def create_contribution(
    cfg: DomainConfig, client: SessionClient, parent_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    """Create a contribution on a funder record, as the signed-in user.

    The parent read doubles as the ACL gate and supplies the donor-link
    defaults (the funder's company Account + primary Contact) — ``setdefault``,
    so an explicit value in ``changes`` would win if the editor ever collects
    them. Returns the decorated row (the tab refreshes in place).
    """
    select = "name"
    for attr in (cfg.contributions_donor_account_attr, cfg.contributions_donor_contact_attr):
        if attr:
            select += "," + attr
    parent = await client.get(cfg.parent_entity, parent_id, select=select)
    payload = _contribution_payload(changes)
    await _sanitize_contribution_enums(client, payload)
    _backfill_amount_currency(payload)
    payload[cfg.contributions_parent_fk] = parent_id
    if cfg.contributions_donor_account_attr and parent.get(cfg.contributions_donor_account_attr):
        payload.setdefault("donorAccountId", parent[cfg.contributions_donor_account_attr])
    if cfg.contributions_donor_contact_attr and parent.get(cfg.contributions_donor_contact_attr):
        payload.setdefault("donorContactId", parent[cfg.contributions_donor_contact_attr])
    created = await client.create(CONTRIBUTION, payload)
    log.info("contribution created on %s/%s: CContribution/%s",
             cfg.parent_entity, parent_id, created.get("id"))
    return await get_contribution(cfg, client, created["id"])


async def update_contribution(
    cfg: DomainConfig, client: SessionClient, contribution_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    """Whitelisted, enum-sanitized update. Soft delete = status Cancelled
    through this same path; there is NO hard-delete surface anywhere."""
    current = await get_contribution(cfg, client, contribution_id)  # scope + ACL gate first
    payload = _contribution_payload(changes)
    await _sanitize_contribution_enums(client, payload)
    _backfill_amount_currency(payload, current.get("amountCurrency"))
    if payload:
        await client.update(CONTRIBUTION, contribution_id, payload)
        log.info("contribution %s updated (%s)", contribution_id, ", ".join(sorted(payload)))
    return await get_contribution(cfg, client, contribution_id)


# --- Grants + deliverables (the funder grant book — sponsor domain only) ----
# prds/grant-management-plan.md. Doug's rulings 2026-08-23:
#   * the GRANT is the hub — contributions are its payments, deliverables are
#     its obligations, and the two are SIBLINGS, never a chain;
#   * client attribution lives on the grant (``fundedEngagements``), so a
#     renewal starts clean;
#   * a reporting period's numbers freeze as a JSON snapshot on the report.
#
# Phase 2 (this code) is MANUAL measurement: ``currentValue`` is typed in.
# Phase 3 computes it from ``measureKey``; the progress math below is already
# the one place that decides what a number MEANS, so that change lands here and
# nowhere else.
#
# Everything is feature-detected — the CRM entities may not exist yet, and a
# funder workspace must not break because they don't.

GRANT = "CGrant"
DELIVERABLE = "CGrantDeliverable"

#: Grant statuses that count as live money in hand or in flight.
_GRANT_ACTIVE = ("Awarded", "Active", "Reporting")
#: Statuses excluded from every total (visible, never counted) — the
#: Contributions Cancelled/Unsuccessful precedent.
_GRANT_EXCLUDED = ("Declined", "Cancelled")

_DELIV_MILESTONE = "Milestone"
_DELIV_NARRATIVE = "Narrative"
_DELIV_MET = "Met"
_DELIV_BEHIND = "Behind"
_DELIV_ON_TRACK = "On track"

_GRANT_DEFAULT_CURRENCY = "USD"


async def grants_available(client: SessionClient) -> bool:
    """Whether the live CRM actually has the grant entities.

    The three entities are a pending CRM build, so every grant surface asks
    this first: flag ON + entities missing must read as "not built yet", not as
    an error. Fails CLOSED — an unreadable metadata call means we cannot prove
    the entities exist, and offering the tab on a guess would produce forms
    whose saves the CRM rejects.
    """
    try:
        fields = await client.metadata(f"entityDefs.{GRANT}.fields")
        deliv = await client.metadata(f"entityDefs.{DELIVERABLE}.fields")
    except Exception as exc:  # noqa: BLE001 — never raise out of a feature probe
        log.info("grant entities not detectable (%s); grants stay dark", exc)
        return False
    return bool(fields) and bool(deliv)


async def _present_fields(
    client: SessionClient, entity: str, spec: list[dict]
) -> list[dict]:
    """``spec`` filtered to the fields the live CRM really has.

    The standing convention (CLAUDE.md): a CRM-facing feature feature-detects
    its fields rather than requiring a coordinated deploy. Serving a field the
    CRM lacks renders a box whose save must fail; dropping it also drops it
    from the whitelist, because the whitelist IS this spec.
    """
    fields = await client.metadata(f"entityDefs.{entity}.fields") or {}
    return [f for f in spec if f["name"] in fields]


async def grant_fields(client: SessionClient) -> list[dict]:
    """The grant form layout + whitelist, feature-detected."""
    return await _present_fields(client, GRANT, GRANT_FIELDS)


async def deliverable_fields(client: SessionClient) -> list[dict]:
    """The deliverable form layout + whitelist, feature-detected."""
    return await _present_fields(client, DELIVERABLE, DELIVERABLE_FIELDS)


def _num(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def deliverable_progress(row: dict[str, Any], today: date) -> dict[str, Any]:
    """How far along one deliverable is — the single place that decides.

    Returns ``percent`` (None when the type has no number: a Narrative answer
    is not a quantity) and ``derivedStatus``, which is only ever a value from
    the CRM's own status vocabulary. A stored ``deliverableStatus`` always
    wins: staff overriding the arithmetic is the point of a manual phase.
    """
    dtype = row.get("deliverableType")
    target, current = _num(row.get("targetValue")), _num(row.get("currentValue"))
    if dtype == _DELIV_NARRATIVE:
        percent = None
    elif dtype == _DELIV_MILESTONE:
        percent = 100.0 if current else 0.0
    elif target > 0:
        percent = max(0.0, min(100.0, current / target * 100.0))
    else:
        percent = None  # no target set yet — a bar would be a lie

    derived = None
    if percent is not None:
        if percent >= 100.0:
            derived = _DELIV_MET
        else:
            due = _iso_date(row.get("dueBy"))
            derived = _DELIV_BEHIND if (due and due < today) else _DELIV_ON_TRACK
    return {
        "percent": None if percent is None else round(percent, 1),
        "derivedStatus": derived,
        "status": row.get("deliverableStatus") or derived,
        "met": (row.get("deliverableStatus") or derived) == _DELIV_MET,
    }


def _deliverable_row(r: dict[str, Any], today: date) -> dict[str, Any]:
    """A decorated deliverable: raw scalars + the derived progress block."""
    row = {k: r.get(k) for k in (
        "id", "name", "deliverableType", "targetValue", "unit", "ratingScaleMax",
        "currentValue", "currentNote", "dueBy", "deliverableStatus",
        "measurementSource", "measureKey", "measurementNotes", "sortOrder", "createdAt",
    )}
    row["grantId"] = r.get("grantId")
    row.update(deliverable_progress(row, today))
    return row


def _grant_row(r: dict[str, Any], today: date) -> dict[str, Any]:
    """A decorated grant row for the grid (deliverable rollups added later)."""
    status = r.get("grantStatus")
    row = {k: r.get(k) for k in (
        "id", "name", "awardNumber", "grantStatus", "awardAmount", "awardAmountCurrency",
        "programArea", "periodStart", "periodEnd", "reportingFrequency",
        "firstReportDue", "nextReportDue", "renewalDeadline", "createdAt",
    )}
    row["excluded"] = status in _GRANT_EXCLUDED
    row["active"] = status in _GRANT_ACTIVE
    # What the "next report due" column shows: the maintained date if there is
    # one, else the first one — until the report engine (phase 5) maintains it.
    row["reportDue"] = r.get("nextReportDue") or r.get("firstReportDue")
    due = _iso_date(row["reportDue"])
    row["reportOverdue"] = bool(due and due < today and not row["excluded"])
    end = _iso_date(r.get("periodEnd"))
    row["periodEnded"] = bool(end and end < today)
    row["deliverableCount"] = 0
    row["deliverablesMet"] = 0
    return row


def grant_summary(rows: list[dict[str, Any]], today: date) -> dict[str, Any]:
    """The tab's four tiles. Pure math over decorated rows, so the rules are
    tested in one place: Declined/Cancelled grants never count toward anything,
    and the award total is the money CBM is actually committed to delivering
    against (Awarded / Active / Reporting)."""
    live = [r for r in rows if r.get("active")]
    counted = [r for r in rows if not r.get("excluded")]
    awarded = round(sum(_num(r.get("awardAmount")) for r in live), 2)
    total_deliv = sum(r.get("deliverableCount") or 0 for r in counted)
    met_deliv = sum(r.get("deliverablesMet") or 0 for r in counted)
    upcoming = sorted(
        d for d in (_iso_date(r.get("reportDue")) for r in counted) if d and d >= today
    )
    overdue = [r for r in counted if r.get("reportOverdue")]
    currencies = [r.get("awardAmountCurrency") for r in rows if r.get("awardAmountCurrency")]
    return {
        "totalCount": len(rows),
        "activeCount": len(live),
        "awardedAmount": awarded,
        "deliverablesTotal": total_deliv,
        "deliverablesMet": met_deliv,
        "nextReportDue": upcoming[0].isoformat() if upcoming else None,
        "overdueReports": len(overdue),
        "currency": currencies[0] if currencies else _GRANT_DEFAULT_CURRENCY,
    }


async def _attach_deliverable_rollups(
    client: SessionClient, rows: list[dict[str, Any]], today: date
) -> None:
    """Fill each grant row's deliverable count / met count, in ONE list call.

    A per-grant read would be N+1; the ``in`` filter keeps it to one request.
    Best-effort: a funder whose role cannot read deliverables still gets their
    grants, with the rollup columns simply reading zero.
    """
    ids = [r["id"] for r in rows if r.get("id")]
    if not ids:
        return
    try:
        data = await client.list(
            DELIVERABLE,
            select=DELIVERABLE_LIST_SELECT + ",grantId",
            where=[{"type": "in", "attribute": "grantId", "value": ids}],
            max_size=_PAGE,
        )
    except Exception as exc:  # noqa: BLE001 — decoration, never breaks the grid
        log.warning("could not read deliverables for the grants grid: %s", exc)
        return
    by_grant: dict[str, list[dict[str, Any]]] = {}
    for raw in data.get("list", []):
        row = _deliverable_row(raw, today)
        if row.get("grantId"):
            by_grant.setdefault(row["grantId"], []).append(row)
    for r in rows:
        mine = by_grant.get(r["id"], [])
        r["deliverableCount"] = len(mine)
        r["deliverablesMet"] = sum(1 for d in mine if d.get("met"))


async def list_grants(
    cfg: DomainConfig, client: SessionClient, parent_id: str
) -> dict[str, Any]:
    """A funder's grants + the computed summary block.

    The parent read is the ACL gate (a forbidden funder never leaks its grant
    book) and supplies the funder name for the editor's default title — the
    contributions-endpoint contract exactly.
    """
    parent = await client.get(cfg.parent_entity, parent_id, select="name")
    if not await grants_available(client):
        return {
            "records": [], "summary": None, "parentName": parent.get("name"),
            "available": False,
        }
    data = await client.list_related(
        cfg.parent_entity, parent_id, cfg.grants_link,
        select=GRANT_LIST_SELECT, max_size=_PAGE,
    )
    today = datetime.now(timezone.utc).date()
    rows = [_grant_row(r, today) for r in data.get("list", [])]
    await _attach_deliverable_rollups(client, rows, today)
    rows.sort(key=lambda r: (r.get("periodStart") or "", r.get("createdAt") or ""), reverse=True)
    return {
        "records": rows,
        "summary": grant_summary(rows, today),
        "parentName": parent.get("name"),
        "available": True,
    }


async def get_grant(
    cfg: DomainConfig, client: SessionClient, grant_id: str
) -> dict[str, Any]:
    """One grant's full editable values + its deliverables, record-scope checked.

    The grant must belong to a funder of THIS domain that the user can read (the
    contributions/documents precedent) — a bare CGrant id never resolves from
    outside the funder workspace.
    """
    rec = await client.get(
        GRANT, grant_id,
        select=GRANT_LIST_SELECT + ",notes,description," + cfg.grants_parent_fk,
    )
    parent_id = rec.get(cfg.grants_parent_fk)
    if not parent_id:
        raise SessionError("That grant isn't linked to a funder record.")
    await client.get(cfg.parent_entity, parent_id, select="id")  # ACL gate
    today = datetime.now(timezone.utc).date()
    row = _grant_row(rec, today)
    row["notes"] = rec.get("notes")
    row["description"] = rec.get("description")
    row["parentId"] = parent_id
    row["deliverables"] = await list_deliverables(client, grant_id, today=today)
    row["deliverableCount"] = len(row["deliverables"])
    row["deliverablesMet"] = sum(1 for d in row["deliverables"] if d.get("met"))
    return row


async def list_deliverables(
    client: SessionClient, grant_id: str, *, today: Optional[date] = None
) -> list[dict[str, Any]]:
    """A grant's deliverables, in the funder's own order (``sortOrder``, then
    creation). Best-effort: a role that cannot read them shows a grant with no
    deliverables rather than a broken record."""
    today = today or datetime.now(timezone.utc).date()
    try:
        data = await client.list_related(
            GRANT, grant_id, "deliverables",
            select=DELIVERABLE_LIST_SELECT, max_size=_PAGE,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read deliverables for grant %s: %s", grant_id, exc)
        return []
    rows = [_deliverable_row(r, today) for r in data.get("list", [])]
    rows.sort(key=lambda r: (
        _num(r.get("sortOrder")) if r.get("sortOrder") is not None else 1e9,
        r.get("createdAt") or "",
    ))
    return rows


async def _entity_enum_options(
    client: SessionClient, entity: str, names: list[str]
) -> dict[str, list[Any]]:
    """Live option lists for an entity's enum fields (CRM = truth)."""
    fields = await client.metadata(f"entityDefs.{entity}.fields") or {}
    options: dict[str, list[Any]] = {}
    for name in names:
        opts = (fields.get(name) or {}).get("options")
        if isinstance(opts, list):
            options[name] = [o for o in opts if o != ""]
    return options


async def _entity_required(
    client: SessionClient, entity: str, names: set[str]
) -> list[str]:
    """Editable fields the CRM marks required (read live, never hard-coded)."""
    fields = await client.metadata(f"entityDefs.{entity}.fields") or {}
    return [
        name for name in sorted(names)
        if isinstance(fields.get(name), dict) and fields[name].get("required")
    ]


async def grant_field_options(client: SessionClient) -> dict[str, list[Any]]:
    return await _entity_enum_options(client, GRANT, GRANT_ENUM_FIELDS)


async def grant_field_required(client: SessionClient) -> list[str]:
    return await _entity_required(client, GRANT, GRANT_EDIT_NAMES)


async def deliverable_field_options(client: SessionClient) -> dict[str, list[Any]]:
    return await _entity_enum_options(client, DELIVERABLE, DELIVERABLE_ENUM_FIELDS)


async def deliverable_field_required(client: SessionClient) -> list[str]:
    return await _entity_required(client, DELIVERABLE, DELIVERABLE_EDIT_NAMES)


async def _sanitize_entity_enums(
    client: SessionClient, entity: str, enum_names: list[str], payload: dict[str, Any]
) -> None:
    """Drop enum values the live entity no longer accepts, in place.

    The `_sanitize_enum_payload` contract: single enums are OMITTED rather than
    blanked, and it FAILS OPEN — an options read that breaks must never block a
    staff member's save.
    """
    keys = [k for k in payload if k in enum_names]
    if not keys:
        return
    try:
        options = await _entity_enum_options(client, entity, enum_names)
    except Exception as exc:  # noqa: BLE001 — fail open
        log.warning("could not fetch %s enum options (%s); keeping values", entity, exc)
        return
    for key in keys:
        opts, value = options.get(key), payload[key]
        if opts is None or value in (None, ""):
            continue
        if value not in opts:
            log.warning("%s.%s: dropping unrecognized value %r", entity, key, value)
            del payload[key]


def _backfill_award_currency(
    payload: dict[str, Any], existing_currency: Optional[str] = None
) -> None:
    """EspoCRM validates a currency amount against its ``*Currency`` companion,
    so a bare ``awardAmount`` on a record whose stored currency is null is
    REJECTED outright. The editor never collects a currency (CBM is USD only),
    so any save that sets an amount carries one. This exact defect cost the
    contributions ledger a live 400 in v0.123.2 — do not remove it."""
    if payload.get("awardAmount") is not None and not payload.get("awardAmountCurrency"):
        payload["awardAmountCurrency"] = existing_currency or _GRANT_DEFAULT_CURRENCY


def _seed_next_report_due(payload: dict[str, Any], current: Optional[dict] = None) -> None:
    """Until the report engine (phase 5) maintains ``nextReportDue``, seed it
    from ``firstReportDue`` so the tile and the overdue flag have something
    truthful to read. Never overwrites a value that is already set — a date
    someone typed always wins over one we inferred."""
    first = payload.get("firstReportDue")
    if not first:
        return
    already = payload.get("nextReportDue") or (current or {}).get("nextReportDue")
    if not already:
        payload["nextReportDue"] = first


async def create_grant(
    cfg: DomainConfig, client: SessionClient, parent_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    """Create a grant on a funder record, as the signed-in user."""
    if not await grants_available(client):
        raise SessionError("Grants aren't built in this CRM yet.")
    await client.get(cfg.parent_entity, parent_id, select="id")  # ACL gate
    spec = await grant_fields(client)
    payload = _whitelist(changes, {f["name"] for f in spec} | {"awardAmountCurrency"})
    await _sanitize_entity_enums(client, GRANT, GRANT_ENUM_FIELDS, payload)
    _backfill_award_currency(payload)
    _seed_next_report_due(payload)
    payload[cfg.grants_parent_fk] = parent_id
    created = await client.create(GRANT, payload)
    log.info("grant created on %s/%s: CGrant/%s",
             cfg.parent_entity, parent_id, created.get("id"))
    return await get_grant(cfg, client, created["id"])


async def update_grant(
    cfg: DomainConfig, client: SessionClient, grant_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    """Whitelisted, enum-sanitized grant update. There is NO delete surface —
    a grant that falls through is Declined or Cancelled, the Contributions
    soft-delete ruling applied to the award."""
    current = await get_grant(cfg, client, grant_id)  # scope + ACL gate first
    spec = await grant_fields(client)
    payload = _whitelist(changes, {f["name"] for f in spec} | {"awardAmountCurrency"})
    await _sanitize_entity_enums(client, GRANT, GRANT_ENUM_FIELDS, payload)
    _backfill_award_currency(payload, current.get("awardAmountCurrency"))
    _seed_next_report_due(payload, current)
    if payload:
        await client.update(GRANT, grant_id, payload)
        log.info("grant %s updated (%s)", grant_id, ", ".join(sorted(payload)))
    return await get_grant(cfg, client, grant_id)


async def _grant_scope_gate(
    cfg: DomainConfig, client: SessionClient, grant_id: str
) -> str:
    """Confirm a grant belongs to a funder this user can read; return its id."""
    await get_grant(cfg, client, grant_id)
    return grant_id


async def create_deliverable(
    cfg: DomainConfig, client: SessionClient, grant_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    """Add a deliverable to a grant, as the signed-in user."""
    if not await grants_available(client):
        raise SessionError("Grants aren't built in this CRM yet.")
    await _grant_scope_gate(cfg, client, grant_id)
    spec = await deliverable_fields(client)
    payload = _whitelist(changes, {f["name"] for f in spec})
    await _sanitize_entity_enums(client, DELIVERABLE, DELIVERABLE_ENUM_FIELDS, payload)
    payload["grantId"] = grant_id
    created = await client.create(DELIVERABLE, payload)
    log.info("deliverable created on CGrant/%s: %s/%s", grant_id, DELIVERABLE, created.get("id"))
    return await get_deliverable(cfg, client, created["id"])


async def get_deliverable(
    cfg: DomainConfig, client: SessionClient, deliverable_id: str
) -> dict[str, Any]:
    """One deliverable, record-scope checked through its grant's funder."""
    rec = await client.get(
        DELIVERABLE, deliverable_id, select=DELIVERABLE_LIST_SELECT + ",grantId",
    )
    grant_id = rec.get("grantId")
    if not grant_id:
        raise SessionError("That deliverable isn't linked to a grant.")
    await _grant_scope_gate(cfg, client, grant_id)
    return _deliverable_row(rec, datetime.now(timezone.utc).date())


async def update_deliverable(
    cfg: DomainConfig, client: SessionClient, deliverable_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    """Whitelisted, enum-sanitized deliverable update. No delete surface."""
    await get_deliverable(cfg, client, deliverable_id)  # scope + ACL gate first
    spec = await deliverable_fields(client)
    payload = _whitelist(changes, {f["name"] for f in spec})
    await _sanitize_entity_enums(client, DELIVERABLE, DELIVERABLE_ENUM_FIELDS, payload)
    if payload:
        await client.update(DELIVERABLE, deliverable_id, payload)
        log.info("deliverable %s updated (%s)", deliverable_id, ", ".join(sorted(payload)))
    return await get_deliverable(cfg, client, deliverable_id)


def _whitelist(changes: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    """Keep only allowed keys — smuggled links and FK swaps are dropped."""
    return {k: v for k, v in changes.items() if k in allowed}


# --- Quick add: create a new partner / funder -------------------------------
# One screen runs the same three-record sequence the public intake forms do
# (Account → Contact → profile, then relate the contact), as the signed-in user
# so their EspoCRM ACL is the boundary and they are recorded as the creator.
#
# Deduping follows the intake policy exactly: a same-named Account and a
# same-email Contact are REUSED, never duplicated, and an existing record is
# only null-filled — never overwritten with what was typed here.


def manager_fk(cfg: DomainConfig) -> Optional[str]:
    """The FK attr naming this domain's assigned manager's ``CMentorProfile``
    (``partnerManagerId`` / ``cBMSponsorManagerId``), or None."""
    return f"{cfg.parent_manager_link}Id" if cfg.parent_manager_link else None


def create_field_spec(cfg: DomainConfig) -> list[dict[str, Any]]:
    """The Add form's fields: company, primary contact, then the domain's own
    profile fields with the manager picker appended.

    ONE spec, exactly like SESSION_FIELDS/CONTRIBUTION_FIELDS: the frontend
    lays the form out from it and the server writes nothing that isn't in it.
    """
    spec = cfg.create_spec
    if not spec:
        return []
    fields: list[dict[str, Any]] = [
        dict(f, group="Company") for f in CREATE_COMPANY_FIELDS
    ]
    fields += [dict(f, group="Primary contact") for f in CREATE_CONTACT_FIELDS]
    # Long-form fields (notes) go LAST, after the manager picker: a full-height
    # rich-text editor between them pushes the picker and the Create button off
    # the bottom of the modal, which is the opposite of quick entry.
    scalars = [f for f in spec.profile_fields if f["type"] not in ("wysiwyg", "text")]
    longform = [f for f in spec.profile_fields if f["type"] in ("wysiwyg", "text")]
    fields += [dict(f, group=spec.group_label) for f in scalars]
    if manager_fk(cfg):
        fields.append({
            "name": CREATE_MANAGER_FIELD, "label": spec.manager_label,
            "type": "managerselect", "section": "profile", "group": spec.group_label,
            "row": "class",  # shares the line with status / type
        })
    fields += [dict(f, group=spec.group_label) for f in longform]
    return fields


async def create_field_options(cfg: DomainConfig, client: SessionClient) -> dict[str, list[str]]:
    """Live option lists for the Add form's profile enums (CRM = truth), so a
    CRM enum change shows up here without a deploy."""
    names = [
        f["name"] for f in create_field_spec(cfg)
        if f["type"] in ("enum", "multiEnum") and f["section"] == "profile"
    ]
    if not names:
        return {}
    fields = await client.metadata(f"entityDefs.{cfg.parent_entity}.fields")
    options: dict[str, list[str]] = {}
    for name in names:
        opts = (fields.get(name) or {}).get("options")
        if isinstance(opts, list):
            options[name] = [o for o in opts if o != ""]
    return options


async def manager_options(
    cfg: DomainConfig, client: SessionClient, user_id: str
) -> dict[str, Any]:
    """The manager picker: every ``CMentorProfile`` the caller can read, plus
    the id of their own (the default selection).

    Best-effort — a role that can't list CMentorProfile (the sponsor team's may
    not) gets an empty list and a blank picker, never a failed form. The
    manager is optional on the create, so that degrades to "assign it later on
    the Details tab" rather than blocking.
    """
    if not manager_fk(cfg):
        return {"managers": [], "defaultManagerId": None}
    try:
        data = await client.list(
            MENTOR_PROFILE,
            select="name,assignedUserId,assignedUsersIds",
            order_by="name", order="asc", max_size=_PAGE,
        )
    except EspoError as exc:
        log.warning("manager options unavailable (%s): %s", cfg.slug, exc)
        return {"managers": [], "defaultManagerId": None}
    rows = data.get("list", [])
    mine = next((r["id"] for r in rows if is_assigned_to(r, user_id)), None)
    return {
        "managers": [{"id": r["id"], "name": r.get("name") or r["id"]} for r in rows],
        "defaultManagerId": mine,
    }


async def _find_or_create_company(
    cfg: DomainConfig, client: SessionClient, api_client: Any,
    name: str, website: str,
) -> tuple[str, bool]:
    """An Account id for ``name`` — reuse a same-named one, else create it.

    Returns ``(id, created)``. Reads run as the user; the CREATE goes through
    the intake API client, whose role holds Account create where the staff
    gate roles may not (the ``comms_service.resolve_company`` precedent — a
    partner manager without the grant would otherwise get a 403 on a brand-new
    company).

    On a REUSED Account the domain's company type is merged into
    ``cCompanyType`` when missing — a company CBM already knows as a Client
    becoming a Partner must gain the type, since that multiEnum is the
    discriminator the whole CRM filters on. Merge-only and best-effort: an
    existing type is never removed and a failed merge never fails the create.
    """
    spec = cfg.create_spec
    existing = await client.find_one(ACCOUNT, "name", name, select="name,cCompanyType")
    if existing:
        types = list(existing.get("cCompanyType") or [])
        if spec and spec.company_type not in types:
            try:
                await client.update(
                    ACCOUNT, existing["id"], {"cCompanyType": types + [spec.company_type]}
                )
            except EspoError as exc:
                log.warning("could not add %s to Account/%s cCompanyType: %s",
                            spec.company_type, existing["id"], exc)
        return existing["id"], False
    payload: dict[str, Any] = {"name": name}
    if spec:
        payload["cCompanyType"] = [spec.company_type]
    if website:
        payload["website"] = website
    created = await api_client.create(ACCOUNT, payload)
    return created["id"], True


async def _create_quick_contact(
    cfg: DomainConfig, client: SessionClient, values: dict[str, Any], account_id: str
) -> tuple[Optional[str], bool]:
    """Find-or-create the primary contact from the form's contact block.

    Returns ``(id, created)``, or ``(None, False)`` when the block was left
    empty (a contact is optional). A same-email Contact is reused and only
    null-filled — the ``find_create_or_fill`` policy the intake forms use, so
    entering a partner whose contact CBM already knows never duplicates them or
    overwrites curated data.
    """
    first = (values.get("firstName") or "").strip()
    last = (values.get("lastName") or "").strip()
    email = (values.get("emailAddress") or "").strip()
    phone = (values.get("phoneNumber") or "").strip()
    title = (values.get("title") or "").strip()
    if not any((first, last, email, phone, title)):
        return None, False
    if not (first or last):
        raise SessionError(
            "A first or last name is required for the primary contact "
            "(or clear the contact fields to add the company on its own)."
        )
    payload: dict[str, Any] = {"firstName": first, "lastName": last, "accountId": account_id}
    if cfg.create_spec:
        payload["cContactType"] = [cfg.create_spec.contact_type]
    if email:
        payload["emailAddress"] = email
    if title:
        payload["title"] = title
    normalized = e164_or_none(phone)  # an implausible number is dropped, never fatal
    if normalized:
        payload["phoneNumber"] = normalized
    if not email:
        # No natural key to match on — create outright.
        created = await create_dropping_invalid(client, CONTACT, payload)
        return created["id"], True
    contact_id, action = await find_create_or_fill(
        client, CONTACT,
        match_attr="emailAddress", match_value=email,
        create_payload=payload,
        # Never back-write the match key, the company FK or the discriminator
        # onto a contact that already exists.
        fill_keys=("firstName", "lastName", "phoneNumber", "title"),
    )
    return contact_id, action == "created"


async def _quick_add_team_ids(cfg: DomainConfig, client: SessionClient) -> list[str]:
    """Team ids to stamp on the new profile so team-scoped roles can see it in
    the grid. Best-effort — an unresolvable team logs and returns [] rather
    than blocking the create (the intake orchestrators' rule)."""
    spec = cfg.create_spec
    if not spec:
        return []
    name = (getattr(get_settings(), spec.team_name_attr, "") or "").strip()
    if not name:
        return []
    try:
        team = await client.find_one("Team", "name", name)
    except EspoError as exc:
        log.warning("Team %r lookup failed (%s) — %s created without a team",
                    name, exc, cfg.parent_entity)
        return []
    if not team:
        log.warning("Team %r not found/readable — %s created without a team",
                    name, cfg.parent_entity)
        return []
    return [team["id"]]


async def create_record(
    cfg: DomainConfig, client: SessionClient, api_client: Any,
    changes: dict[str, Any], *, user_id: str,
) -> dict[str, Any]:
    """Create a new partner / funder: Account → Contact → profile → relate.

    Every id is captured as its step succeeds and reported back, so a
    later-step failure never leaves the user guessing what was written (the
    intake orchestrators' contract). Returns the new record's id plus what was
    created versus reused, which the frontend reports and the action log
    records.
    """
    spec = cfg.create_spec
    if not spec:
        raise SessionError("This app can't create records.")
    allowed = {f["name"]: f for f in create_field_spec(cfg)}
    values = {k: v for k, v in changes.items() if k in allowed}

    company = (values.get("company") or "").strip()
    if not company:
        raise SessionError("A company name is required.")
    website = (values.get("website") or "").strip()
    if website and "://" not in website:
        website = f"https://{website}"  # Account.website is a url field

    account_id, account_created = await _find_or_create_company(
        cfg, client, api_client, company, website
    )
    contact_id, contact_created = await _create_quick_contact(
        cfg, client, values, account_id
    )

    payload: dict[str, Any] = {"name": (values.get("name") or "").strip() or company}
    for f in spec.profile_fields:
        if f["name"] == "name":
            continue
        value = values.get(f["name"])
        if value not in (None, "", []):
            payload[f["name"]] = value
        elif f.get("default"):
            payload[f["name"]] = f["default"]
    await _sanitize_create_enums(cfg, client, payload)

    company_attr = company_id_attr(cfg)
    if company_attr:
        payload[company_attr] = account_id
    if contact_id and cfg.primary_contact_id_attr:
        payload[cfg.primary_contact_id_attr] = contact_id
    mgr_attr = manager_fk(cfg)
    if mgr_attr:
        manager_id = (values.get(CREATE_MANAGER_FIELD) or "").strip()
        if manager_id:
            payload[mgr_attr] = manager_id
    team_ids = await _quick_add_team_ids(cfg, client)
    if team_ids:
        payload["teamsIds"] = team_ids
    # Owner-stamp the creator, so a role scoped to "own" can read back what it
    # just made (the new-session precedent — without the stamp the CREATE
    # itself 403s, because EspoCRM ACL-checks the read-back).
    if user_id:
        payload["assignedUsersIds"] = [user_id]

    created = await client.create(cfg.parent_entity, payload)
    record_id = created["id"]
    log.info("%s created %s/%s (account %s, contact %s) by %s",
             cfg.slug, cfg.parent_entity, record_id, account_id, contact_id, user_id)

    linked = False
    if contact_id:
        # The profile already names the contact as primary; this is the hasMany
        # the Contacts table lists. Best-effort: the record exists and is usable
        # without it, and the Details tab can re-link in one click.
        try:
            await client.relate(cfg.parent_entity, record_id, cfg.parent_contacts_link, contact_id)
            linked = True
        except EspoError as exc:
            log.warning("could not link Contact/%s to %s/%s: %s",
                        contact_id, cfg.parent_entity, record_id, exc)
    return {
        "id": record_id,
        "name": payload["name"],
        "accountId": account_id,
        "accountCreated": account_created,
        "contactId": contact_id,
        "contactCreated": contact_created,
        "contactLinked": linked,
        "managerId": payload.get(mgr_attr) if mgr_attr else None,
    }


async def _sanitize_create_enums(
    cfg: DomainConfig, client: SessionClient, payload: dict[str, Any]
) -> None:
    """Drop profile enum values outside the live CRM options, in place — the
    ``_sanitize_enum_payload`` contract (single enums omitted, fails open), so
    one drifted option can't 400 a whole new partner."""
    try:
        options = await create_field_options(cfg, client)
    except Exception as exc:  # noqa: BLE001 — fail open, never block the create
        log.warning("could not fetch %s enum options (%s); keeping values as-is",
                    cfg.parent_entity, exc)
        return
    for key, opts in options.items():
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, list):
            payload[key] = [v for v in value if v in opts]
        elif value not in opts:
            log.warning("%s.%s: dropping unrecognized %r (not in live enum)",
                        cfg.parent_entity, key, value)
            payload.pop(key)
