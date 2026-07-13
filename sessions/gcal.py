"""Google Calendar sync hook for session saves (all three domains).

Called by :func:`sessions.service.create_session` / ``update_session`` after the
CSession write: a **Scheduled** session gets a Google Calendar event with a
Google Meet conference on the signed-in manager's OWN calendar (delegated as
their ``cbmEmail``); the attendee contacts are invited (Google emails the
invitations); the Meet URL is written back to ``videoMeetingLink`` and the
event id to ``googleCalendarEventId`` so later edits patch the same event and
a Cancelled session cancels it.

Best-effort by design (the mentoradmin ``provision`` precedent): this module
NEVER raises — the session save must never fail because of Google. Every call
returns ``{"ok": bool, ...}`` which the router response carries as
``session["calendar"]`` and the frontend shows as a non-blocking notice.

Inert until ALL of: ``GCAL_EVENTS=true``, the shared Google service account is
configured (with the ``calendar.events`` scope authorized for domain-wide
delegation), and the CRM has the ``CSession.googleCalendarEventId`` field
(csession-calendar-field.md) — feature-detected per read, so the app deploys
safely ahead of the CRM build.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Optional

from core.gcalendar import CalendarClient, CalendarError, build_event_body, event_times, meet_link
from sessions.config import DomainConfig
from sessions.service import CAL_FIELD, SESSION, SessionClient, resolve_user_mailbox

log = logging.getLogger("cbm_intake.sessions.gcal")

# A save only touches the calendar when one of these (or the attendee set)
# changed — a notes-only edit on an old Scheduled session must not suddenly
# create an event and email invitations.
_RELEVANT = {"name", "dateStart", "dateEnd", "status"}


async def sync_session_calendar(
    settings: Any,
    cfg: DomainConfig,
    client: SessionClient,
    user_id: str,
    session: dict[str, Any],
    changes: dict[str, Any],
    *,
    attendees_changed: bool,
    is_new: bool,
    parent_id: Optional[str] = None,
    calendar: Optional[CalendarClient] = None,
) -> dict[str, Any]:
    """Reconcile the session's Google Calendar event with its saved state.

    Mutates ``session`` in place when it writes back (event id / Meet link) so
    the response reflects the final record without a re-read. ``calendar`` is a
    test-injection seam (any object with create/get/patch/delete_event).
    """
    if not getattr(settings, "gcal_events", False):
        return {"ok": False, "disabled": True}
    try:
        from comms.service import get_service_account  # shared, process-cached

        sa_info = await get_service_account(settings)
        if sa_info is None:
            return {
                "ok": False, "disabled": True,
                "error": "no Google service account is configured",
            }
        if not session.get("googleCalendarEventIdFieldExists"):
            return {
                "ok": False, "disabled": True,
                "error": "the CRM has no googleCalendarEventId field yet",
            }
        return await _sync(
            settings, cfg, client, user_id, session, changes,
            sa_info=sa_info, attendees_changed=attendees_changed,
            is_new=is_new, parent_id=parent_id, calendar=calendar,
        )
    except Exception as exc:  # noqa: BLE001 — never break the saved session
        log.warning("calendar sync failed for session %s: %s", session.get("id"), exc)
        return {"ok": False, "error": str(exc)}


async def _sync(
    settings: Any,
    cfg: DomainConfig,
    client: SessionClient,
    user_id: str,
    session: dict[str, Any],
    changes: dict[str, Any],
    *,
    sa_info: dict[str, Any],
    attendees_changed: bool,
    is_new: bool,
    parent_id: Optional[str],
    calendar: Optional[CalendarClient],
) -> dict[str, Any]:
    sid = session["id"]
    status = session.get("status") or ""
    event_id = session.get(CAL_FIELD) or ""
    relevant = is_new or bool(set(changes) & _RELEVANT) or attendees_changed

    if status == "Cancelled":
        if not event_id:
            return {"ok": True, "skipped": True}
        cal = calendar or await _client_for_user(settings, client, user_id, sa_info)
        if isinstance(cal, dict):  # the no-mailbox error result
            return cal
        await cal.delete_event(event_id)
        clear: dict[str, Any] = {CAL_FIELD: None}
        # Only a Meet link the hook generated is cleared — never a hand-typed
        # Zoom/other link the user put there themselves.
        if "meet.google.com" in (session.get("videoMeetingLink") or ""):
            clear["videoMeetingLink"] = None
        await client.update(SESSION, sid, clear)
        session.update(clear)
        return {"ok": True, "cancelled": True}

    if status != "Scheduled":
        # Doug's rule: only Scheduled sessions get events. Logging a Completed
        # past session never creates one, and a Completed session's existing
        # event is left as it happened.
        return {"ok": True, "skipped": True}

    if not event_id:
        if not (session.get("dateStart") and relevant):
            return {"ok": True, "skipped": True}
        cal = calendar or await _client_for_user(settings, client, user_id, sa_info)
        if isinstance(cal, dict):
            return cal
        return await _create(cfg, client, cal, session, parent_id)

    if not relevant:
        return {"ok": True, "skipped": True}
    cal = calendar or await _client_for_user(settings, client, user_id, sa_info)
    if isinstance(cal, dict):
        return cal
    start, end = event_times(session.get("dateStart"), session.get("dateEnd"))
    await cal.patch_event(event_id, {
        "summary": _summary(session),
        "start": start,
        "end": end,
        "attendees": [{"email": e} for e in _attendee_emails(session, cal.mailbox)],
    })
    return {"ok": True, "eventId": event_id, "updated": True}


async def _client_for_user(
    settings: Any, client: SessionClient, user_id: str, sa_info: dict[str, Any]
) -> CalendarClient | dict[str, Any]:
    """A CalendarClient impersonating the signed-in user's own CBM mailbox, or
    the error result dict when they have none (the session still saves)."""
    mailbox = await resolve_user_mailbox(client, user_id)
    if not mailbox:
        return {
            "ok": False,
            "error": "your profile has no CBM email address, so no calendar event was created",
        }
    return CalendarClient(sa_info, mailbox, getattr(settings, "request_timeout_seconds", 20))


def _summary(session: dict[str, Any]) -> str:
    return session.get("name") or f"CBM {session.get('sessionType') or 'Session'}"


def _attendee_emails(session: dict[str, Any], organizer: str) -> list[str]:
    """The attendee contacts' emails, deduped, without the organizer (Google
    adds the organizer implicitly) or blank addresses."""
    seen: list[str] = []
    for d in session.get("attendeeDetails") or []:
        email = (d.get("email") or "").strip().lower()
        if email and email != organizer and email not in seen:
            seen.append(email)
    return seen


async def _create(
    cfg: DomainConfig,
    client: SessionClient,
    cal: CalendarClient,
    session: dict[str, Any],
    parent_id: Optional[str],
) -> dict[str, Any]:
    sid = session["id"]
    existing_link = (session.get("videoMeetingLink") or "").strip()
    wants_meet = not existing_link  # auto-fill only when blank (Doug's rule)

    # PII-minimal description: the parent record's name + provenance, no notes.
    parts = []
    if parent_id:
        try:
            parent = await client.get(cfg.parent_entity, parent_id, select="name")
            if parent.get("name"):
                parts.append(f"{cfg.parent_label}: {parent['name']}")
        except Exception as exc:  # noqa: BLE001 — description is nice-to-have
            log.warning("could not read parent name for calendar event: %s", exc)
    parts.append(f"Scheduled from CBM {cfg.title}.")

    body = build_event_body(
        summary=_summary(session),
        description="\n".join(parts),
        date_start=session.get("dateStart"),
        date_end=session.get("dateEnd"),
        attendee_emails=_attendee_emails(session, cal.mailbox),
        request_id=f"cbm-{sid}-{uuid.uuid4().hex[:8]}" if wants_meet else None,
        external_link=existing_link or None,
    )
    event = await cal.create_event(body)
    link = meet_link(event)
    if wants_meet and not link:
        # The Meet createRequest can resolve just after the create response;
        # one short retry, then give up (the event exists either way).
        await asyncio.sleep(1)
        try:
            link = meet_link(await cal.get_event(event["id"]))
        except CalendarError:
            pass
        if not link:
            log.warning("Meet link still pending for event %s (session %s)", event.get("id"), sid)

    write_back: dict[str, Any] = {CAL_FIELD: event["id"]}
    if wants_meet and link:
        write_back["videoMeetingLink"] = link
    await client.update(SESSION, sid, write_back)
    session.update(write_back)
    return {"ok": True, "eventId": event["id"], "meetLink": link}
