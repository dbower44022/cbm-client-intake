"""The portal's events — what a signed-in member sees and can do (F3 → F5).

Design: ``prds/events/CBM_Events_Audience_and_Display_Design.md`` § 6. F3
supplies the selection and the actions; F5 builds the surface on the portal's
home page. Mounted with Event Administration (``EVENTS_ENABLED``), open to any
signed-in user — the portal signs in every active CRM user, and the calendar is
theirs to read.

* ``GET  /api/portal/events`` — the member's calendar, with the member's own
  registration on each row and the rail's window (F5).
* ``GET  /api/portal/events/{id}`` — one event for the member page (F5-1).
* ``GET  /api/portal/events/{id}/image`` — its graphic, gated the same way.
* ``POST /api/portal/events/{id}/register`` — register for an Internal event
  that takes registrations (F3-7).
* ``POST /api/portal/events/{id}/cancel`` — cancel the member's own
  registration (F5-4).

F5 design: ``prds/events/CBM_Events_Portal_Calendar_Design.md``.

Both run under the **organisation-wide API key**. Every role that reads events
reads them at "all" or "own", and Mentor Role holds no access to registrations
at all (roles standard, verified 2026-09-29), so a member acting as themselves
could neither see the calendar nor register. The member is recorded as the
actor in the action history instead.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, Response

from assignments.auth import current_user
from core.action_log import CAT_RECORD_EDIT, record_action
from core.config import get_settings
from core.espo import EspoApi, EspoError

from . import config as cfg
from . import service
from . import visibility

log = logging.getLogger("cbm_intake.events.member")

member_router = APIRouter(prefix="/api/portal/events", tags=["portal-events"])

APP_PORTAL = "Portal"

CONTACT = "Contact"
MENTOR_PROFILE = "CMentorProfile"

#: Registration statuses that make a member "registered" for the rail. A
#: cancelled registration is the same as none: Register is offered again and
#: ``register_member`` turns it into an update, never a duplicate.
_LIVE_REGISTRATION = frozenset({
    cfg.REG_REGISTERED, cfg.REG_WAITLISTED, cfg.REG_ATTENDED, cfg.REG_NO_SHOW,
})

#: Same wording for "not shown to you" and "no such event", so a member page
#: address confirms nothing about events outside the member's teams.
NOT_FOUND = "That event could not be found."


class MemberRegistrationRefused(Exception):
    """A plain refusal a member can read — never retried, never a 5xx."""


def _user(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user


def _client(request: Request) -> EspoApi:
    factory = getattr(request.app.state, "events_client_factory", None)
    if factory is None:  # pragma: no cover - misconfiguration
        raise HTTPException(status_code=503, detail="Events are not configured.")
    return factory()


def portal_image_url(event: dict[str, Any]) -> str:
    """The event's graphic through the PORTAL image route, or "".

    The public route is keyed on the slug so it inherits the public gate, which
    makes an Internal event's graphic unreachable there (and Internal events
    often have no slug at all). This route is keyed on the id and gated on the
    portal surface instead. ``?v=`` changes with the picture, as the public one
    does, so a replaced graphic is not served from cache.
    """
    attachment_id = event.get(f"{cfg.GRAPHIC_FIELD}Id") or ""
    if not attachment_id or not event.get("id"):
        return ""
    return f"/api/portal/events/{event['id']}/image?v={attachment_id[:12]}"


def registration_summary(registration: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """``{id, status}`` for a live registration, else None."""
    if not registration:
        return None
    status = registration.get("attendanceStatus") or cfg.REG_REGISTERED
    if status not in _LIVE_REGISTRATION:
        return None
    return {"id": registration.get("id"), "status": status}


def calendar_entry(
    event: dict[str, Any], *, base_url: str = "",
    my_registration: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """One row of the member's calendar. Deliberately NOT the staff record:
    the team limit's contents and the reach stay staff data."""
    audience = visibility.effective_audience(event)
    internal = audience == cfg.AUDIENCE_INTERNAL
    return {
        **service.public_event(event, base_url=base_url),
        "imageUrl": portal_image_url(event),
        "id": event.get("id"),
        "audience": audience,
        # The member's own live registration, or None (F5 finding 5).
        "myRegistration": registration_summary(my_registration),
        "teamLimited": bool(internal and visibility.team_limit(event)),
        # Whether staff switched sign-up on at all — the member page tells
        # "registration has closed" from "no sign-up needed" by it (F5 § 5).
        "takesRegistrations": bool(internal and event.get(cfg.TAKES_REGISTRATIONS_FIELD)),
        # Internal + staff switched it on + still open. A Public event is
        # registered for on its own public page (design § 6).
        "canRegister": bool(
            internal
            and event.get(cfg.TAKES_REGISTRATIONS_FIELD)
            and service.registration_open(event)
        ),
        # Where a Public event's own page lives; None for Internal.
        "publicUrl": None if internal else service.public_event(event, base_url=base_url).get("url"),
    }


def join_url_for(event: dict[str, Any], my_registration: Optional[dict[str, Any]]) -> str:
    """D2 (ruled 09-30-26): an online Internal event's join link goes to every
    member when the event takes no registrations, and only to registered
    members when it does. A Public event's link is never served here — the
    member signs up on the website and is told there."""
    if visibility.effective_audience(event) != cfg.AUDIENCE_INTERNAL:
        return ""
    if event.get(cfg.TAKES_REGISTRATIONS_FIELD):
        summary = registration_summary(my_registration)
        if not summary or summary["status"] == cfg.REG_WAITLISTED:
            return ""
    return (event.get("virtualMeetingUrl") or "").strip()


def detail_entry(
    event: dict[str, Any], *, base_url: str = "",
    my_registration: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """The member page's payload: the calendar row plus the long-form content
    the public detail carries (F5 finding 1), with the join link under D2."""
    entry = calendar_entry(event, base_url=base_url, my_registration=my_registration)
    entry["overview"] = event.get("eventOverview") or ""
    entry["syllabus"] = event.get("eventSyllabus") or ""
    entry["joinUrl"] = join_url_for(event, my_registration)
    return entry


async def _my_registrations(
    client: EspoApi, email: str, event_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """The member's registrations for these events, keyed by event id.

    One list read per hundred events (the ``in`` clause), paged at 200 — never
    one read per row. Best-effort: a failure returns what was read and logs,
    and the rail then offers Register, which the one-registration rule turns
    into an update rather than a duplicate.
    """
    found: dict[str, dict[str, Any]] = {}
    if not email or not event_ids:
        return found
    for start in range(0, len(event_ids), 100):
        chunk = event_ids[start:start + 100]
        offset = 0
        try:
            while True:
                data = await client.list(
                    cfg.REGISTRATION,
                    select=cfg.REGISTRATION_SELECT,
                    where=[
                        {"type": "in", "attribute": "eventId", "value": chunk},
                        {"type": "equals", "attribute": "email", "value": email},
                    ],
                    max_size=200,
                    offset=offset,
                )
                rows = data.get("list", [])
                for row in rows:
                    found[row.get("eventId") or ""] = row
                if len(rows) < 200:
                    break
                offset += 200
        except EspoError as exc:
            log.warning("member registrations read failed: %s", exc)
            break
    return found


async def _member_event(
    client: EspoApi, user: dict[str, Any], event_id: str,
    *, now: Optional[datetime] = None,
) -> Optional[dict[str, Any]]:
    """One event, by id, if it is shown to this member on the portal — else
    None. Unknown, unticked, before its display time and outside the member's
    teams are all the same None (design § 5)."""
    if not event_id:
        return None
    try:
        event = await client.get(cfg.EVENT, event_id, select=cfg.PUBLIC_SELECT)
    except EspoError:
        return None
    if not event or not event.get("id"):
        return None
    if not visibility.is_shown(event, visibility.SURFACE_PORTAL, now=now, user=user):
        return None
    return event


@member_router.get("")
async def calendar(request: Request) -> dict[str, Any]:
    user = _user(request)
    settings = get_settings()
    client = _client(request)
    try:
        rows = await service.portal_calendar(client, user)
    except EspoError as exc:
        log.warning("portal calendar failed for %s: %s", user.get("userName"), exc)
        raise HTTPException(
            status_code=502, detail="The events calendar is unavailable right now."
        ) from exc
    email = await _member_email(client, user)
    mine = await _my_registrations(client, email, [r["id"] for r in rows if r.get("id")])
    return {
        "events": [
            calendar_entry(r, base_url=settings.events_public_base,
                           my_registration=mine.get(r.get("id") or ""))
            for r in rows
        ],
        # The rail lists this many days in full and folds the rest (F5-2).
        "windowDays": max(0, settings.portal_events_window_days),
    }


@member_router.get("/{event_id}")
async def detail(event_id: str, request: Request) -> dict[str, Any]:
    """The member page's read (F5-1). 404 for anything not shown to this
    member, worded exactly as an unknown id."""
    user = _user(request)
    settings = get_settings()
    client = _client(request)
    event = await _member_event(client, user, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    email = await _member_email(client, user)
    mine = await _my_registrations(client, email, [event["id"]])
    entry = detail_entry(
        event, base_url=settings.events_public_base,
        my_registration=mine.get(event["id"]),
    )
    # A Public event with no slug has no page ANYWHERE (crm-test's seeded
    # events; an event created in the CRM by hand). The page must tell that
    # apart from "the public pages are switched off in this deployment" —
    # it said the latter for the former on 2026-10-07 (F5 live pass, step 12).
    entry["publicPagesActive"] = bool(settings.events_public_active)
    return {"event": entry}


@member_router.get("/{event_id}/image")
async def image(event_id: str, request: Request) -> Response:
    """The event's graphic for the rail and the member page.

    The portal twin of the public image route: keyed on the id, gated on the
    portal surface, and cached only for the public read lifetime — never
    ``immutable`` — because unticking an event must take its picture offline
    too (the public route's docstring has the history).
    """
    user = _user(request)
    client = _client(request)
    event = await _member_event(client, user, event_id)
    attachment_id = (event or {}).get(f"{cfg.GRAPHIC_FIELD}Id")
    if event is None or not attachment_id:
        raise HTTPException(status_code=404, detail="Not found.")
    try:
        data, content_type = await client.download_attachment(attachment_id)
    except EspoError as exc:
        raise HTTPException(status_code=502, detail="Image unavailable.") from exc
    ttl = max(0, get_settings().events_cache_seconds)
    return Response(
        content=data,
        media_type=content_type or "application/octet-stream",
        headers={"Cache-Control": f"private, max-age={ttl}, must-revalidate"},
    )


# --- registration -----------------------------------------------------------


async def _member_profile(
    client: EspoApi, user: dict[str, Any]
) -> tuple[Optional[str], str]:
    """``(contact id from the mentor profile or None, lower-cased address)``.

    The address follows the members-at-cbmEmail rule: the profile's
    ``cbmEmail`` first, then the User's address, then a userName that is one.
    """
    from sessions.service import resolve_manager_profile

    user_id = user.get("userId") or ""
    contact_id: Optional[str] = None
    email = ""
    if user_id:
        try:
            profile_id = await resolve_manager_profile(client, user_id)
            if profile_id:
                prof = await client.get(
                    MENTOR_PROFILE, profile_id, select="contactRecordId,cbmEmail"
                )
                contact_id = prof.get("contactRecordId") or None
                email = (prof.get("cbmEmail") or "").strip()
        except EspoError as exc:
            log.warning("member %s: mentor profile lookup failed: %s", user_id, exc)
        if not email:
            try:
                rec = await client.get("User", user_id, select="emailAddress")
                email = (rec.get("emailAddress") or "").strip()
            except EspoError as exc:
                log.info("member %s: User email not readable: %s", user_id, exc)
    if not email and "@" in (user.get("userName") or ""):
        email = user["userName"].strip()
    return contact_id, email.lower()


async def _member_email(client: EspoApi, user: dict[str, Any]) -> str:
    """Just the address — what the registration reads key on."""
    _, email = await _member_profile(client, user)
    return email


async def _member_identity(client: EspoApi, user: dict[str, Any]) -> dict[str, Any]:
    """Who is registering: their Contact, their address, their name.

    The member's own Contact is found through their mentor profile's linked
    Contact first, then by address. With neither, the registration is recorded
    with no Contact rather than creating a second record for a person the CRM
    already knows (design § 6). The address follows the members-at-cbmEmail
    rule: the profile's ``cbmEmail`` first.
    """
    contact_id, email = await _member_profile(client, user)
    if not contact_id and email:
        try:
            found = await client.find_one(CONTACT, "emailAddress", email, select="id")
            contact_id = (found or {}).get("id") or None
        except EspoError as exc:
            log.warning("member %s: contact lookup failed: %s", user_id, exc)
    name = (user.get("name") or user.get("userName") or "").strip()
    first, _, last = name.partition(" ")
    return {"contactId": contact_id, "email": email, "firstName": first, "lastName": last}


async def register_member(
    client: EspoApi, user: dict[str, Any], event_id: str,
    *, now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Register the signed-in member for an Internal event (F3-7).

    Refused, readably, unless the event is Internal, shown to this member, takes
    registrations and is still open — and unless the CRM holds the ``Portal``
    registration source, since an unknown option would fail the create.
    """
    moment = now or datetime.now(timezone.utc)
    try:
        event = await client.get(cfg.EVENT, event_id, select=cfg.PUBLIC_SELECT)
    except EspoError:
        event = None
    if not event or not visibility.is_shown(
        event, visibility.SURFACE_PORTAL, now=moment, user=user
    ):
        raise MemberRegistrationRefused("That event could not be found.")
    if visibility.effective_audience(event) != cfg.AUDIENCE_INTERNAL:
        raise MemberRegistrationRefused(
            "Register for this event on its public page — it is a public event."
        )
    if not event.get(cfg.TAKES_REGISTRATIONS_FIELD):
        raise MemberRegistrationRefused("This event does not take registrations.")
    if not service.registration_open(event, now=moment):
        raise MemberRegistrationRefused("Registration for this event has closed.")
    sources = await client.metadata_enum_options(cfg.REGISTRATION, "registrationSource")
    if sources is not None and cfg.SOURCE_PORTAL not in sources:
        raise MemberRegistrationRefused(
            "Registering from the portal is not switched on yet: the CRM needs the "
            f"registration source “{cfg.SOURCE_PORTAL}”. Ask an administrator."
        )

    who = await _member_identity(client, user)
    if not who["email"]:
        raise MemberRegistrationRefused(
            "Your account has no email address in the CRM, so a registration "
            "cannot be recorded. Ask an administrator to add one."
        )

    # The same seat rule and one-registration-per-person rule as the public form.
    from forms.event_registration.orchestrator import _existing_registration, _seat_status

    existing = await _existing_registration(client, event["id"], who["email"])
    status = await _seat_status(
        client, event, excluding_id=existing.get("id") if existing else None
    )
    payload: dict[str, Any] = {
        "name": f"{event.get('name') or 'Event'} — {who['firstName']} {who['lastName']}".strip()[:255],
        "eventId": event["id"],
        "email": who["email"],
        "firstName": who["firstName"],
        "lastName": who["lastName"],
        "registrationSource": cfg.SOURCE_PORTAL,
    }
    if who["contactId"]:
        payload["contactId"] = who["contactId"]
    if existing:
        if existing.get("attendanceStatus") in (None, "", cfg.REG_REGISTERED,
                                                cfg.REG_WAITLISTED, cfg.REG_CANCELLED):
            payload["attendanceStatus"] = status
        else:
            status = existing.get("attendanceStatus")
        await client.update(cfg.REGISTRATION, existing["id"], payload)
        registration_id, outcome = existing["id"], "updated"
    else:
        payload["attendanceStatus"] = status
        payload["registrationDate"] = moment.strftime("%Y-%m-%d %H:%M:%S")
        created = await client.create(cfg.REGISTRATION, payload)
        registration_id, outcome = created["id"], "created"
    return {
        "registrationId": registration_id,
        "status": status,
        "outcome": outcome,
        "contactLinked": bool(who["contactId"]),
        "event": {"id": event["id"], "name": event.get("name")},
    }


async def cancel_member(
    client: EspoApi, user: dict[str, Any], event_id: str, *, settings: Any = None,
) -> dict[str, Any]:
    """Cancel the member's OWN registration for an event (F5-4).

    The registration is found by the member's resolved address, never by an id
    the browser supplies, so a member can cancel nobody's place but their own.
    Then the same cancellation the emailed link runs: seat freed, Zoom removal,
    waitlist promotion.
    """
    event = await _member_event(client, user, event_id)
    if event is None:
        raise MemberRegistrationRefused(NOT_FOUND)
    email = await _member_email(client, user)
    mine = await _my_registrations(client, email, [event["id"]])
    summary = registration_summary(mine.get(event["id"]))
    if not summary:
        raise MemberRegistrationRefused("You are not registered for this event.")
    result = await service.cancel_registration(client, summary["id"], settings=settings)
    if not result.get("ok"):
        raise MemberRegistrationRefused("This registration could not be cancelled.")
    return {
        "ok": True,
        "registrationId": summary["id"],
        "alreadyCancelled": bool(result.get("alreadyCancelled")),
        "event": {"id": event["id"], "name": event.get("name")},
    }


@member_router.post("/{event_id}/cancel")
async def cancel(event_id: str, request: Request) -> dict[str, Any]:
    user = _user(request)
    client = _client(request)
    try:
        result = await cancel_member(client, user, event_id, settings=get_settings())
    except MemberRegistrationRefused as exc:
        status = 404 if str(exc) == NOT_FOUND else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except EspoError as exc:
        log.warning("portal cancellation failed for %s on %s: %s",
                    user.get("userName"), event_id, exc)
        raise HTTPException(
            status_code=502, detail="The cancellation could not be saved right now."
        ) from exc
    await record_action(
        client, app=APP_PORTAL, category=CAT_RECORD_EDIT,
        action="Event Registration Cancelled",
        parent_type=cfg.EVENT, parent_id=event_id,
        summary=f"Cancelled their registration for “{result['event'].get('name')}” "
                "from the portal",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return result


@member_router.post("/{event_id}/register")
async def register(event_id: str, request: Request) -> dict[str, Any]:
    user = _user(request)
    client = _client(request)
    try:
        result = await register_member(client, user, event_id)
    except MemberRegistrationRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EspoError as exc:
        log.warning("portal registration failed for %s on %s: %s",
                    user.get("userName"), event_id, exc)
        raise HTTPException(
            status_code=502, detail="The registration could not be saved right now."
        ) from exc
    await record_action(
        client, app=APP_PORTAL, category=CAT_RECORD_EDIT, action="Event Registration",
        parent_type=cfg.EVENT, parent_id=event_id,
        summary=f"Registered for “{result['event'].get('name')}” from the portal "
                f"({result['status']})",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return result
