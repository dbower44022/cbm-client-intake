"""The portal's events — what a signed-in member sees and can do (F3 → F5).

Design: ``prds/events/CBM_Events_Audience_and_Display_Design.md`` § 6. F3
supplies the selection and the actions; F5 builds the surface on the portal's
home page. Mounted with Event Administration (``EVENTS_ENABLED``), open to any
signed-in user — the portal signs in every active CRM user, and the calendar is
theirs to read.

* ``GET  /api/portal/events`` — the member's calendar.
* ``POST /api/portal/events/{id}/register`` — register for an Internal event
  that takes registrations (F3-7).

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

from fastapi import APIRouter, HTTPException, Request

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


def calendar_entry(event: dict[str, Any], *, base_url: str = "") -> dict[str, Any]:
    """One row of the member's calendar. Deliberately NOT the staff record:
    the team limit's contents and the reach stay staff data."""
    audience = visibility.effective_audience(event)
    internal = audience == cfg.AUDIENCE_INTERNAL
    return {
        **service.public_event(event, base_url=base_url),
        "id": event.get("id"),
        "audience": audience,
        "teamLimited": bool(internal and visibility.team_limit(event)),
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


@member_router.get("")
async def calendar(request: Request) -> dict[str, Any]:
    user = _user(request)
    settings = get_settings()
    try:
        rows = await service.portal_calendar(_client(request), user)
    except EspoError as exc:
        log.warning("portal calendar failed for %s: %s", user.get("userName"), exc)
        raise HTTPException(
            status_code=502, detail="The events calendar is unavailable right now."
        ) from exc
    return {"events": [
        calendar_entry(r, base_url=settings.events_public_base) for r in rows
    ]}


# --- registration -----------------------------------------------------------


async def _member_identity(client: EspoApi, user: dict[str, Any]) -> dict[str, Any]:
    """Who is registering: their Contact, their address, their name.

    The member's own Contact is found through their mentor profile's linked
    Contact first, then by address. With neither, the registration is recorded
    with no Contact rather than creating a second record for a person the CRM
    already knows (design § 6). The address follows the members-at-cbmEmail
    rule: the profile's ``cbmEmail`` first.
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
    email = email.lower()
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
