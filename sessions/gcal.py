"""Google Calendar sync hook for session saves (all three domains).

Called by :func:`sessions.service.create_session` / ``update_session`` after the
CSession write: a **Scheduled** session gets a Google Calendar event with a
Google Meet conference on the signed-in manager's OWN calendar (delegated as
their ``cbmEmail``); the attendee contacts are invited (Google emails the
invitations); the Meet URL is written back to ``videoMeetingLink`` and the
event id to ``googleCalendarEventId`` so later edits patch the same event and
a Cancelled session cancels it. No NEW event is ever created for a session
whose start is already in the past (recorded after the fact) or whose status
is not Scheduled (e.g. Completed — the meeting already took place).

Attendee addressing (Doug's ruling 2026-07-20, v0.122.0): a CBM member on the
attendee list is invited at their ``cbmEmail`` ONLY — never their Contact
record's personal address (:func:`sessions.service.cbm_member_email_map`
classifies the record's members). Before this, the organizer's own Contact was
invited at their personal email, producing a self-invitation and a duplicate
event copy (the 2026-07-20 customer report).

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
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core.gcalendar import (
    CalendarClient,
    CalendarError,
    build_event_body,
    busy_intervals,
    event_times,
    meet_link,
)
from core.gmeet import MeetClient, meeting_code
from sessions.config import DomainConfig
from sessions.service import (
    CAL_FIELD,
    SESSION,
    SessionClient,
    cbm_member_email_map,
    resolve_user_mailbox,
)

log = logging.getLogger("cbm_intake.sessions.gcal")

# A save only touches the calendar when one of these (or the attendee set)
# changed — a notes-only edit on an old Scheduled session must not suddenly
# create an event and email invitations.
_RELEVANT = {"name", "dateStart", "dateEnd", "status"}

# A session recorded after the fact never gets a NEW event — inviting people
# to a meeting that already happened only confuses their calendars. The grace
# keeps a "starting right now" session (or minor clock skew) eligible.
_PAST_GRACE = timedelta(minutes=5)


def _starts_in_past(date_start: Any) -> bool:
    """True when the CRM UTC stamp is more than the grace window in the past.
    Unparseable/missing values are NOT past (the caller already requires a
    dateStart before creating anything)."""
    try:
        start = datetime.strptime(str(date_start), "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return False
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return start < now - _PAST_GRACE


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
        if _starts_in_past(session.get("dateStart")):
            # Recorded after the fact (a past-dated Scheduled session): never
            # create an event or email invitations for a meeting that already
            # took place. An EXISTING event still patches/cancels as usual.
            return {"ok": True, "skipped": True, "past": True}
        cal = calendar or await _client_for_user(settings, client, user_id, sa_info)
        if isinstance(cal, dict):
            return cal
        return await _create(cfg, client, cal, session, parent_id,
                             user_id=user_id, settings=settings, sa_info=sa_info)

    if not relevant:
        return {"ok": True, "skipped": True}
    cal = calendar or await _client_for_user(settings, client, user_id, sa_info)
    if isinstance(cal, dict):
        return cal
    members = await _member_email_map(cfg, client, session, parent_id, user_id)
    start, end = event_times(session.get("dateStart"), session.get("dateEnd"))
    await cal.patch_event(event_id, {
        "summary": _summary(session),
        "start": start,
        "end": end,
        "attendees": [
            {"email": e} for e in _attendee_emails(session, cal.mailbox, members)
        ],
    })
    return {"ok": True, "eventId": event_id, "updated": True}


#: The busy lookup never scans more than this window in one call (the picker
#: asks for one local day; the cap only bounds a misbehaving client).
_BUSY_WINDOW_MAX = timedelta(days=8)


async def calendar_busy(
    settings: Any,
    client: SessionClient,
    user_id: str,
    time_min: str,
    time_max: str,
    *,
    exclude_session_id: Optional[str] = None,
    calendar: Optional[CalendarClient] = None,
) -> dict[str, Any]:
    """Busy blocks on the signed-in manager's OWN calendar, for the session
    editor's time-picker conflict shading.

    ``time_min``/``time_max`` are CRM-style UTC stamps (``YYYY-MM-DD HH:MM:SS``).
    Read-only and best-effort by design: any failure — flag off, no service
    account, no CBM mailbox, a bad window, Google down — degrades to
    ``{"available": False, "busy": []}`` and the picker simply shows no
    shading. It NEVER blocks a save: a shaded slot stays selectable (the
    user deconflicts manually — Doug's ruling). ``exclude_session_id`` keeps
    the session's own event from reading as a conflict when editing."""
    empty = {"available": False, "busy": []}
    if not getattr(settings, "gcal_events", False):
        return empty
    try:
        lo = datetime.strptime(time_min, "%Y-%m-%d %H:%M:%S")
        hi = datetime.strptime(time_max, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return empty
    if not (lo < hi <= lo + _BUSY_WINDOW_MAX):
        return empty
    try:
        from comms.service import get_service_account  # shared, process-cached

        sa_info = await get_service_account(settings)
        if sa_info is None:
            return empty
        cal = calendar
        if cal is None:
            got = await _client_for_user(settings, client, user_id, sa_info)
            if isinstance(got, dict):  # no CBM mailbox — no calendar to check
                return empty
            cal = got
        exclude_event: Optional[str] = None
        if exclude_session_id:
            try:
                rec = await client.get(SESSION, exclude_session_id, select=CAL_FIELD)
                exclude_event = rec.get(CAL_FIELD)
            except Exception:  # noqa: BLE001 — field missing/unreadable: shade anyway
                exclude_event = None
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        events = await cal.list_events(lo.strftime(fmt), hi.strftime(fmt))
        return {
            "available": True,
            "busy": busy_intervals(events, exclude_event_id=exclude_event),
        }
    except Exception as exc:  # noqa: BLE001 — shading is decoration, never an error
        log.warning("calendar busy lookup failed for user %s: %s", user_id, exc)
        return empty


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


def _attendee_emails(
    session: dict[str, Any],
    organizer: str,
    member_emails: Optional[dict[str, str]] = None,
) -> list[str]:
    """The attendee contacts' emails, deduped, without the organizer (Google
    adds the organizer implicitly) or blank addresses.

    ``member_emails`` (contact id -> CBM mailbox, from
    :func:`sessions.service.cbm_member_email_map`) substitutes each CBM
    member's mailbox for their Contact's personal address — Doug's ruling
    2026-07-20: CBM members are invited ONLY at ``@cbmentors.org``. A member
    with no mailbox is skipped, never invited personally; the acting
    organizer's own contact resolves to the organizer mailbox and drops out
    here (the fix for the self-invite duplicate-event report)."""
    members = member_emails or {}
    seen: list[str] = []
    for d in session.get("attendeeDetails") or []:
        contact_id = str(d.get("id") or "")
        if contact_id in members:
            email = members[contact_id]
            if not email:
                log.warning(
                    "attendee %s is a CBM member with no cbmEmail — not invited",
                    d.get("name") or contact_id,
                )
                continue
        else:
            email = (d.get("email") or "").strip().lower()
        if email and email != organizer and email not in seen:
            seen.append(email)
    return seen


async def _member_email_map(
    cfg: DomainConfig,
    client: SessionClient,
    session: dict[str, Any],
    parent_id: Optional[str],
    user_id: str,
) -> dict[str, str]:
    """Contact id -> CBM mailbox for the record's CBM members + the acting
    user, best-effort.

    The update path doesn't know the parent id, so it is read off the session
    record when missing (the acting user's own profile is still classified
    either way). An empty map only means no substitution happens (logged) —
    the calendar sync itself must never fail over this."""
    pid = parent_id
    if not pid:
        try:
            rec = await client.get(SESSION, session["id"], select=cfg.session_parent_fk)
            pid = rec.get(cfg.session_parent_fk)
        except Exception as exc:  # noqa: BLE001 — classification is best-effort
            log.warning(
                "member-email map: no parent readable for session %s: %s",
                session.get("id"), exc,
            )
    try:
        return await cbm_member_email_map(client, cfg, pid, acting_user_id=user_id)
    except Exception as exc:  # noqa: BLE001 — never break the calendar sync
        log.warning(
            "member-email map failed for %s %s — CBM members may be invited at "
            "their personal address this save: %s", cfg.parent_entity, pid, exc,
        )
    return {}


async def _create(
    cfg: DomainConfig,
    client: SessionClient,
    cal: CalendarClient,
    session: dict[str, Any],
    parent_id: Optional[str],
    *,
    user_id: str = "",
    settings: Any = None,
    sa_info: Optional[dict[str, Any]] = None,
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

    # Id-before-invite (P2, reliability review 2026-07-17): create the event
    # QUIETLY (no attendees, sendUpdates=none), persist its id to the CRM, and
    # only then patch the attendees in with sendUpdates=all. The old order
    # emailed invitations on create — a failed id write-back then left an
    # orphan event, and the next save created + re-emailed a second one (the
    # double-invite bomb).
    attendee_emails = _attendee_emails(
        session, cal.mailbox,
        await _member_email_map(cfg, client, session, parent_id, user_id),
    )
    body = build_event_body(
        summary=_summary(session),
        description="\n".join(parts),
        date_start=session.get("dateStart"),
        date_end=session.get("dateEnd"),
        attendee_emails=[],
        request_id=f"cbm-{sid}-{uuid.uuid4().hex[:8]}" if wants_meet else None,
        external_link=existing_link or None,
    )
    event = await cal.create_event(body, send_updates="none")
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
    try:
        await client.update(SESSION, sid, write_back)
    except Exception as exc:  # noqa: BLE001 — roll the uninvited event back
        log.warning(
            "event id write-back failed for session %s (event %s) — deleting "
            "the uninvited event: %s", sid, event.get("id"), exc,
        )
        try:
            # Nobody was invited, so no cancellation emails go out.
            await cal.delete_event(event["id"], send_updates="none")
        except Exception as exc2:  # noqa: BLE001
            log.warning("orphan event %s could not be deleted: %s", event.get("id"), exc2)
        return {
            "ok": False,
            "error": (
                "the calendar event could not be recorded on the session, so it "
                "was cancelled before any invitations went out — save again to retry"
            ),
        }
    session.update(write_back)
    result = {"ok": True, "eventId": event["id"], "meetLink": link}
    if attendee_emails:
        try:
            await cal.patch_event(
                event["id"],
                {"attendees": [{"email": e} for e in attendee_emails]},
                send_updates="all",
            )
        except Exception as exc:  # noqa: BLE001 — event + id are safe; invites aren't
            log.warning(
                "attendee invitations failed for event %s (session %s): %s",
                event.get("id"), sid, exc,
            )
            result["inviteError"] = (
                "the event was created but the attendee invitations could not be "
                "sent — edit and re-save the session to retry"
            )
    # Auto-enable Meet transcription on the space we just generated (Doug's
    # ruling: every app-scheduled Meet is transcribed — no per-session opt-in).
    # Only generated Meet links: a hand-typed link isn't our space to configure.
    if (
        wants_meet and link and sa_info
        and getattr(settings, "meet_transcripts", False)
    ):
        result["transcription"] = await _enable_transcription(
            settings, sa_info, cal.mailbox, link
        )
    return result


async def _enable_transcription(
    settings: Any, sa_info: dict[str, Any], mailbox: str, link: str
) -> dict[str, Any]:
    """Turn on auto-transcription for the Meet space behind ``link``, as the
    organizer. Best-effort: a failure only means the meeting isn't
    auto-transcribed (the retrieval job still picks up manually-started
    transcripts)."""
    code = meeting_code(link)
    if not code:
        return {"ok": False, "error": f"no Meet meeting code in {link!r}"}
    try:
        meet = MeetClient(
            sa_info, mailbox, getattr(settings, "request_timeout_seconds", 20)
        )
        space = await meet.get_space(code)
        await meet.enable_auto_transcription(space["name"])
        return {"ok": True, "enabled": True}
    except Exception as exc:  # noqa: BLE001 — never break the saved session
        log.warning("could not enable Meet transcription on %s: %s", code, exc)
        return {"ok": False, "error": str(exc)}
