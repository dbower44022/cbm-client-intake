"""Event Administration — the staff app at ``/events`` (Phase 5).

Uses the shared staff session (sign in once at the portal ``/``), gated per
request on ``EVENTS_ALLOWED_TEAMS`` (Marketing Admin Team by default; admins
always pass). Everything runs **as the signed-in user**, so EspoCRM enforces
their ACL and records them as the modifier — except Zoom, which has one shared
account.

What it does: create and edit events, provision the Zoom webinar, manage the
registrant list, run door check-in for in-person events, and publish the
recording. The public website reads the same records through
``events/public.py``.

Every mutation is recorded through the standard action-log path, so event
administration leaves the same audit trail as the rest of the system.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from assignments.auth import current_user, is_member
from assignments.espo_user import client_for
from core.action_log import CAT_RECORD_EDIT, CAT_STATUS, record_action
from core.config import get_settings
from core.espo import EspoError, forbidden_hint, is_forbidden

from . import config as cfg
from . import reporting
from . import service
from .zoom_sync import adopt_existing_webinar, sync_event_webinar

log = logging.getLogger("cbm_intake.events")

api_router = APIRouter(prefix="/events/api", tags=["events-admin"])

APP_EVENTS = "Event Administration"


def _require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    settings = get_settings()
    teams = settings.events_allowed_teams_list
    if not is_member(user, teams):
        raise HTTPException(
            status_code=403,
            detail=(
                "Your account is not authorized to use Event Administration "
                f"(requires the {', '.join(teams) or 'admin'} team)."
            ),
        )
    return user


def _crm_failure(exc: EspoError, what: str) -> HTTPException:
    """Turn a CRM error into something a staff member can act on.

    A 403 names the exact grant that is missing (``forbidden_hint``) rather
    than surfacing as an opaque 502 — the lesson from the funder-list and
    session-tool 403s.
    """
    log.warning("events %s failed: %s", what, exc)
    if is_forbidden(exc):
        raise HTTPException(
            status_code=403,
            detail=forbidden_hint(exc)
            or "Your CRM role does not allow that — ask CBM staff to grant it.",
        )
    raise HTTPException(
        status_code=502,
        detail=f"The CRM could not complete this request ({what}).",
    )


async def _actor(request: Request):
    """The signed-in user plus a CRM client acting AS them, so EspoCRM enforces
    their ACL and records them as the modifier."""
    user = _require_user(request)
    return user, client_for(get_settings(), user)


# --- payloads --------------------------------------------------------------


class EventIn(BaseModel):
    changes: dict[str, Any] = {}


class RecordingIn(BaseModel):
    url: str = ""


class GraphicIn(BaseModel):
    filename: str = ""
    contentType: str = ""
    dataBase64: str = ""


class WebinarIn(BaseModel):
    webinarId: str = ""


class AttendanceIn(BaseModel):
    status: str
    minutes: Optional[int] = None


class RegistrantIn(BaseModel):
    firstName: str
    lastName: str = ""
    email: str = ""
    phone: str = ""
    walkIn: bool = False


# --- session + reference data ---------------------------------------------


@api_router.get("/session")
async def session(request: Request) -> dict[str, Any]:
    user = _require_user(request)
    settings = get_settings()
    return {
        "userName": user.get("userName"),
        "name": user.get("name"),
        "crmUrl": settings.espo_base_url,
        "zoomEnabled": settings.zoom_active,
        "publicBaseUrl": settings.events_public_base_url,
        "websiteLive": settings.events_public_api,
    }


@api_router.get("/fields")
async def fields(request: Request) -> dict[str, Any]:
    _, client = await _actor(request)
    try:
        options = await service.field_options(client)
    except EspoError as exc:
        raise _crm_failure(exc, "read the event field options") from exc
    return {
        "fields": [
            {
                "name": f.name, "label": f.label, "type": f.type,
                "group": f.group, "big": f.big, "help": f.help,
                "appManaged": f.app_managed, "hidden": f.hidden,
            }
            for f in cfg.EVENT_FIELDS
        ],
        "options": options,
    }


# --- events ----------------------------------------------------------------


@api_router.get("/events")
async def list_events(request: Request, status: str = "") -> dict[str, Any]:
    _, client = await _actor(request)
    try:
        rows = await service.list_events(client, status=status or None)
        # Batched: one query per 100 events, not one per event (the grid lists
        # them all, so the naive loop was ~100 round-trips and a blank page).
        counts = await service.summaries_for(client, rows)
    except EspoError as exc:
        raise _crm_failure(exc, "list events") from exc
    return {
        "events": [
            {
                **service.public_event(row),
                "publishToWebsite": bool(row.get("publishToWebsite")),
                "summary_counts": counts.get(row["id"], {}),
            }
            for row in rows
        ]
    }


@api_router.get("/events/{event_id}")
async def get_event(event_id: str, request: Request) -> dict[str, Any]:
    _, client = await _actor(request)
    try:
        raw = await client.get(cfg.EVENT, event_id, select=cfg.PUBLIC_SELECT)
        if not raw:
            raise HTTPException(status_code=404, detail="Event not found.")
        registrations = await service.list_registrations(client, event_id)
        counts = service.summarise(registrations, raw.get("venueCapacity"))
    except EspoError as exc:
        raise _crm_failure(exc, "read the event") from exc
    settings = get_settings()
    return {
        "event": {
            **service.public_event_detail(
                raw, base_url=settings.events_public_base_url
            ),
            "raw": raw,
        },
        "counts": counts,
        "registrations": registrations,
    }


@api_router.post("/events")
async def create_event(payload: EventIn, request: Request) -> dict[str, Any]:
    user, client = await _actor(request)
    try:
        event = await service.create_event(client, payload.changes)
    except service.EventError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EspoError as exc:
        raise _crm_failure(exc, "create the event") from exc
    await record_action(
        client, app=APP_EVENTS, category=CAT_RECORD_EDIT, action="Event Created",
        parent_type=cfg.EVENT, parent_id=event["id"],
        summary=f"Created the event \"{event.get('name')}\"",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return {"event": service.public_event_detail(event), "raw": event}


@api_router.put("/events/{event_id}")
async def update_event(
    event_id: str, payload: EventIn, request: Request
) -> dict[str, Any]:
    user, client = await _actor(request)
    settings = get_settings()
    try:
        before = await client.get(cfg.EVENT, event_id, select=cfg.PUBLIC_SELECT)
        event = await service.update_event(client, event_id, payload.changes)
    except service.EventError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EspoError as exc:
        raise _crm_failure(exc, "save the event") from exc

    # Zoom reconciles itself from the SAVED state — best-effort, so a Zoom
    # outage can never undo an event save.
    zoom = await sync_event_webinar(settings, client, event, previous=before)

    changed = sorted(payload.changes.keys())
    await record_action(
        client, app=APP_EVENTS, category=CAT_RECORD_EDIT, action="Event Updated",
        parent_type=cfg.EVENT, parent_id=event_id,
        summary=f"Updated {', '.join(changed) or 'the event'}",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
        details={"fields": changed, "zoom": zoom.get("action")},
    )
    return {"event": service.public_event_detail(event), "raw": event, "zoom": zoom}


@api_router.post("/events/{event_id}/zoom")
async def sync_zoom(event_id: str, request: Request) -> dict[str, Any]:
    """The explicit 'Create / sync Zoom webinar' action (EV-54).

    ``force`` is on: staff sometimes want the webinar (and its registration
    URL) before the event goes on the website.
    """
    user, client = await _actor(request)
    settings = get_settings()
    try:
        event = await client.get(cfg.EVENT, event_id, select=cfg.PUBLIC_SELECT)
    except EspoError as exc:
        raise _crm_failure(exc, "read the event") from exc
    result = await sync_event_webinar(settings, client, event, force=True)
    if result.get("ok"):
        await record_action(
            client, app=APP_EVENTS, category=CAT_STATUS, action="Zoom Webinar Synced",
            parent_type=cfg.EVENT, parent_id=event_id,
            summary=f"Zoom webinar {result.get('action')}",
            actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
            details=result,
        )
    return {"zoom": result, "raw": event}


@api_router.post("/events/{event_id}/zoom/link")
async def link_zoom(
    event_id: str, payload: WebinarIn, request: Request
) -> dict[str, Any]:
    """Adopt a webinar created directly in Zoom (EV-23)."""
    user, client = await _actor(request)
    settings = get_settings()
    try:
        event = await client.get(cfg.EVENT, event_id, select=cfg.PUBLIC_SELECT)
    except EspoError as exc:
        raise _crm_failure(exc, "read the event") from exc
    result = await adopt_existing_webinar(settings, client, event, payload.webinarId)
    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=result.get("error") or result.get("reason")
            or "That webinar could not be linked.",
        )
    await record_action(
        client, app=APP_EVENTS, category=CAT_STATUS, action="Zoom Webinar Linked",
        parent_type=cfg.EVENT, parent_id=event_id,
        summary=f"Linked Zoom webinar {result.get('webinarId')}",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return {"zoom": result, "raw": event}


@api_router.post("/events/{event_id}/recording")
async def set_recording(
    event_id: str, payload: RecordingIn, request: Request
) -> dict[str, Any]:
    user, client = await _actor(request)
    try:
        event = await service.set_recording(client, event_id, payload.url)
    except service.EventError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EspoError as exc:
        raise _crm_failure(exc, "save the recording link") from exc
    await record_action(
        client, app=APP_EVENTS, category=CAT_RECORD_EDIT, action="Recording Published",
        parent_type=cfg.EVENT, parent_id=event_id,
        summary="Added the recording link" if payload.url else "Removed the recording link",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return {"event": service.public_event_detail(event), "raw": event}


# --- reporting (Phase 6c) --------------------------------------------------


@api_router.get("/reports/program")
async def program_report(
    request: Request, start: str = "", end: str = ""
) -> dict[str, Any]:
    """EV-74 — events held, unique attendees, repeat rate for a period."""
    _, client = await _actor(request)
    try:
        return await reporting.program_totals(client, start=start, end=end)
    except EspoError as exc:
        raise _crm_failure(exc, "build the programme report") from exc


@api_router.get("/reports/conversion")
async def conversion_report(
    request: Request, start: str = "", end: str = ""
) -> dict[str, Any]:
    """EV-73 — attendees who became clients AFTER their first attended event."""
    _, client = await _actor(request)
    try:
        return await reporting.conversion_report(client, start=start, end=end)
    except EspoError as exc:
        raise _crm_failure(exc, "build the conversion report") from exc


@api_router.get("/contacts/{contact_id}/events")
async def contact_events(contact_id: str, request: Request) -> dict[str, Any]:
    """EV-71 — one person's event history."""
    _, client = await _actor(request)
    try:
        return {"events": await reporting.contact_history(client, contact_id)}
    except EspoError as exc:
        raise _crm_failure(exc, "read the contact's event history") from exc


# --- event graphic ---------------------------------------------------------
#
# A file field can't ride the generic field PUT, and the browser can't reach
# EspoCRM, so upload and display each get their own endpoint. Display proxies
# the attachment through the app exactly as the mentor photo does.


@api_router.post("/events/{event_id}/graphic")
async def upload_graphic(
    event_id: str, payload: GraphicIn, request: Request
) -> dict[str, Any]:
    user, client = await _actor(request)
    try:
        event = await service.set_event_graphic(
            client, event_id,
            filename=payload.filename,
            content_type=payload.contentType,
            data_base64=payload.dataBase64,
        )
    except service.EventError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EspoError as exc:
        raise _crm_failure(exc, "save the event graphic") from exc
    await record_action(
        client, app=APP_EVENTS, category=CAT_RECORD_EDIT, action="Event Graphic Updated",
        parent_type=cfg.EVENT, parent_id=event_id,
        summary="Uploaded the website graphic",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return {"event": service.public_event_detail(event), "raw": event}


@api_router.delete("/events/{event_id}/graphic")
async def delete_graphic(event_id: str, request: Request) -> dict[str, Any]:
    user, client = await _actor(request)
    try:
        event = await service.clear_event_graphic(client, event_id)
    except EspoError as exc:
        raise _crm_failure(exc, "remove the event graphic") from exc
    await record_action(
        client, app=APP_EVENTS, category=CAT_RECORD_EDIT, action="Event Graphic Updated",
        parent_type=cfg.EVENT, parent_id=event_id,
        summary="Removed the website graphic",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return {"event": service.public_event_detail(event), "raw": event}


@api_router.get("/events/{event_id}/graphic")
async def get_graphic(event_id: str, request: Request) -> Response:
    """The staff-side preview. Authenticated, so it works for an unpublished
    event — unlike the public route, which is behind the publish gate."""
    _user, client = await _actor(request)
    try:
        result = await service.get_event_graphic(client, event_id)
    except EspoError as exc:
        raise _crm_failure(exc, "load the event graphic") from exc
    if result is None:
        raise HTTPException(status_code=404, detail="This event has no graphic.")
    data, content_type = result
    return Response(
        content=data,
        media_type=content_type or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=60"},
    )


# --- registrants -----------------------------------------------------------


@api_router.post("/events/{event_id}/registrants")
async def add_registrant(
    event_id: str, payload: RegistrantIn, request: Request
) -> dict[str, Any]:
    user, client = await _actor(request)
    try:
        registration = await service.add_registrant(
            client, event_id,
            first_name=payload.firstName, last_name=payload.lastName,
            email=payload.email, phone=payload.phone,
            source=cfg.SOURCE_WALK_IN if payload.walkIn else cfg.SOURCE_STAFF,
            status=cfg.REG_ATTENDED if payload.walkIn else cfg.REG_REGISTERED,
        )
    except service.EventError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EspoError as exc:
        raise _crm_failure(exc, "add the registrant") from exc
    await record_action(
        client, app=APP_EVENTS, category=CAT_RECORD_EDIT,
        action="Walk-in Added" if payload.walkIn else "Registrant Added",
        parent_type=cfg.EVENT, parent_id=event_id,
        summary=f"Added {payload.firstName} {payload.lastName}".strip(),
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return {"registration": registration}


@api_router.put("/registrations/{registration_id}/attendance")
async def set_attendance(
    registration_id: str, payload: AttendanceIn, request: Request
) -> dict[str, Any]:
    user, client = await _actor(request)
    try:
        registration = await service.set_attendance(
            client, registration_id, payload.status, minutes=payload.minutes
        )
    except service.EventError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EspoError as exc:
        raise _crm_failure(exc, "save the attendance") from exc
    await record_action(
        client, app=APP_EVENTS, category=CAT_STATUS, action="Attendance Recorded",
        parent_type=cfg.REGISTRATION, parent_id=registration_id,
        summary=f"Marked {payload.status}",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return {"registration": registration}


@api_router.post("/registrations/{registration_id}/checkin")
async def check_in(registration_id: str, request: Request) -> dict[str, Any]:
    user, client = await _actor(request)
    try:
        registration = await service.check_in(client, registration_id)
    except EspoError as exc:
        raise _crm_failure(exc, "check the registrant in") from exc
    await record_action(
        client, app=APP_EVENTS, category=CAT_STATUS, action="Checked In",
        parent_type=cfg.REGISTRATION, parent_id=registration_id,
        summary="Checked in at the door",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return {"registration": registration}


@api_router.post("/registrations/{registration_id}/cancel")
async def cancel(registration_id: str, request: Request) -> dict[str, Any]:
    """Staff cancellation — frees the seat and promotes the waitlist, exactly
    like the registrant's own cancel link."""
    user, client = await _actor(request)
    settings = get_settings()
    try:
        result = await service.cancel_registration(
            client, registration_id, settings=settings
        )
    except EspoError as exc:
        raise _crm_failure(exc, "cancel the registration") from exc
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail="That registration was not found.")
    await record_action(
        client, app=APP_EVENTS, category=CAT_STATUS, action="Registration Cancelled",
        parent_type=cfg.REGISTRATION, parent_id=registration_id,
        summary="Cancelled the registration",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return result
