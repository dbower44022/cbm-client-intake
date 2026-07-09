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

import logging
from typing import Any, Optional, Protocol

from assignments.service import assigned_user_id
from core.espo import EspoError

from .config import (
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


class SessionClient(Protocol):
    """The slice of ``EspoClient`` this module needs (eases test mocking)."""

    async def get(self, entity: str, record_id: str, select: str | None = ...) -> dict[str, Any]: ...
    async def list(self, entity: str, **kwargs: Any) -> dict[str, Any]: ...
    async def list_related(self, entity: str, record_id: str, link: str, **kwargs: Any) -> dict[str, Any]: ...
    async def create(self, entity: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def update(self, entity: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def relate(self, entity: str, record_id: str, link: str, related_id: str) -> None: ...
    async def metadata(self, key: str) -> Any: ...


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


async def get_detail(
    cfg: DomainConfig, client: SessionClient, parent_id: str
) -> dict[str, Any]:
    """The parent detail view: summary fields + related contacts + existing
    sessions (+ co-mentors, mentor domain). All reads are as the user."""
    parent = await client.get(cfg.parent_entity, parent_id, select=cfg.detail_select)
    summary = [
        {"label": col.label, "value": parent.get(col.attr)}
        for col in cfg.detail_fields
        if parent.get(col.attr) not in (None, "")
    ]

    contacts_data = await client.list_related(
        cfg.parent_entity, parent_id, cfg.parent_contacts_link,
        select="name,emailAddress,phoneNumber,title", max_size=_PAGE,
    )
    contacts = [_contact_row(c) for c in contacts_data.get("list", [])]

    sessions_data = await client.list_related(
        cfg.parent_entity, parent_id, cfg.parent_sessions_link,
        select="name,status,sessionType,dateStart,dateStartDate", max_size=_PAGE,
    )
    sessions = [_session_row(s) for s in sessions_data.get("list", [])]
    sessions.sort(key=lambda x: (x.get("dateStart") or ""), reverse=True)

    detail: dict[str, Any] = {
        "id": parent_id,
        "name": parent.get("name"),
        "parentLabel": cfg.parent_label,
        "summary": summary,
        "contacts": contacts,
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


_SESSION_SELECT = ",".join(
    ["id", *sorted(SESSION_EDIT_NAMES), "sessionAttendeesIds", "sessionAttendeesNames"]
)


async def get_session(client: SessionClient, session_id: str) -> dict[str, Any]:
    """An existing session's editable values + its attendee contact ids."""
    rec = await client.get(SESSION, session_id, select=_SESSION_SELECT)
    rec["attendees"] = rec.get("sessionAttendeesIds") or []
    return rec


def _session_payload(
    changes: dict[str, Any], attendees: Optional[list[str]]
) -> dict[str, Any]:
    payload = {k: v for k, v in changes.items() if k in SESSION_EDIT_NAMES}
    if attendees is not None:
        # sessionAttendees is a many-to-many link; setting the id list replaces
        # the attendee set (no per-row relate/unrelate needed).
        payload["sessionAttendeesIds"] = attendees
    return payload


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
    payload = _session_payload(changes, attendees)
    payload[cfg.session_parent_fk] = parent_id
    payload.setdefault("sessionType", cfg.default_session_type)
    payload.setdefault("status", "Planned")
    if owner_user_id:
        payload.setdefault("assignedUserId", owner_user_id)
        payload.setdefault("assignedUsersIds", [owner_user_id])
    await _sanitize_enum_payload(client, payload)
    created = await client.create(SESSION, payload)
    log.info(
        "created session %s on %s/%s type=%s",
        created.get("id"), cfg.parent_entity, parent_id, payload.get("sessionType"),
    )
    return await get_session(client, created["id"])


async def update_session(
    client: SessionClient,
    session_id: str,
    changes: dict[str, Any],
    attendees: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Update whitelisted fields (+ attendees) on an existing session."""
    payload = _session_payload(changes, attendees)
    await _sanitize_enum_payload(client, payload)
    if payload:
        await client.update(SESSION, session_id, payload)
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
