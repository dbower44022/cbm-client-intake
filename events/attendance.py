"""Phase 6a — attendance from the Zoom participant report (EV-30…EV-35).

After an online event ends the worker pulls Zoom's participant report and
matches participants to registrations **by email**, recording attended /
no-show, first join, last leave and total minutes.

Four rules this module exists to hold:

* **Empty is "not ready", never "nobody came" (EV-31).** Zoom does not publish
  the report the instant a webinar ends. An empty report leaves the event
  unresolved so the next pass retries, until the give-up window closes. Reading
  empty as zero attendance would mark a whole roster No-Show.
* **A human correction is never overwritten (EV-34).** A registration whose
  ``attendanceSource`` is ``Manual`` or ``Check-in`` is skipped by every later
  automatic pull. Staff win.
* **An unmatched attendee is recorded, not dropped (EV-32).** Someone who was
  forwarded the link — or a panelist — becomes a registration flagged
  ``unmatchedParticipant`` for staff review, rather than vanishing.
* **Nothing is denormalised (EV-35).** No totals are stored; counts and
  show-rates stay computed from the rows, as they already are.

Inert unless Zoom is configured — with ``ZOOM_EVENTS`` off there is no report to
pull and the cycle is a no-op.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core.config import Settings
from core.espo import EspoApi, EspoError
from core.zoom import make_client as make_zoom_client
from core.zoom import parse_zoom_time

from . import config as cfg
from . import service

log = logging.getLogger("cbm_intake.events.attendance")

#: Attendance sources the automatic pull must never overwrite (EV-34).
PROTECTED_SOURCES = ("Manual", "Check-in")
SOURCE_ZOOM = "Zoom Report"


def _norm_email(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_resolved(registrations: list[dict[str, Any]]) -> bool:
    """Whether a pull has already landed for this event.

    True once ANY registration carries the Zoom source — the report arrives for
    the whole webinar at once, so one stamped row means the pass completed.
    """
    return any(
        (r.get("attendanceSource") or "") == SOURCE_ZOOM for r in registrations
    )


async def attendance_candidates(
    client: EspoApi, settings: Settings, *, now: Optional[datetime] = None
) -> list[dict[str, Any]]:
    """Online events that ended recently enough to still be worth a pull.

    Bounded at both ends: past the grace period (the report needs time to
    appear) and inside the give-up window (an event nobody ever held must not be
    retried forever).
    """
    moment = now or datetime.now(timezone.utc)
    grace = moment - timedelta(minutes=max(0, settings.events_attendance_grace_minutes))
    give_up = moment - timedelta(hours=max(1, settings.events_attendance_give_up_hours))

    rows = await service._all_events(
        client,
        select=cfg.PUBLIC_SELECT,
        where=[
            {"type": "before", "attribute": "dateEnd",
             "value": service.to_crm_datetime(grace)},
            {"type": "after", "attribute": "dateEnd",
             "value": service.to_crm_datetime(give_up)},
        ],
        order_by="dateEnd",
        order="asc",
        limit=200,
    )
    return [
        row for row in rows
        if (row.get("format") in cfg.ONLINE_FORMATS)
        and (row.get("zoomWebinarId") or "").strip()
        and (row.get("status") != cfg.STATUS_CANCELLED)
    ]


def match_participants(
    registrations: list[dict[str, Any]], participants: list[dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Fold the Zoom report into per-registration facts, plus the unmatched.

    A participant can appear several times (they dropped and rejoined), so the
    fold takes the EARLIEST join, the LATEST leave, and the SUM of the minutes.
    Returns ``({registration_id: facts}, [unmatched participant facts])``.
    """
    by_email: dict[str, dict[str, Any]] = {}
    for reg in registrations:
        email = _norm_email(reg.get("email"))
        if email:
            by_email.setdefault(email, reg)

    matched: dict[str, dict[str, Any]] = {}
    unmatched: dict[str, dict[str, Any]] = {}

    for part in participants:
        email = _norm_email(part.get("user_email") or part.get("email"))
        join = parse_zoom_time(part.get("join_time"))
        leave = parse_zoom_time(part.get("leave_time"))
        seconds = int(part.get("duration") or 0)

        target = by_email.get(email) if email else None
        bucket = matched if target is not None else unmatched
        key = target["id"] if target is not None else (email or str(part.get("name") or "?"))

        facts = bucket.get(key)
        if facts is None:
            facts = {
                "join": join, "leave": leave, "seconds": seconds,
                "email": email, "name": str(part.get("name") or "").strip(),
            }
            bucket[key] = facts
        else:
            if join and (facts["join"] is None or join < facts["join"]):
                facts["join"] = join
            if leave and (facts["leave"] is None or leave > facts["leave"]):
                facts["leave"] = leave
            facts["seconds"] += seconds

    return matched, list(unmatched.values())


def _fmt(value: Optional[datetime]) -> Optional[str]:
    return service.to_crm_datetime(value) if value else None


async def apply_attendance(
    client: EspoApi,
    event: dict[str, Any],
    registrations: list[dict[str, Any]],
    participants: list[dict[str, Any]],
) -> dict[str, int]:
    """Write the report's findings. Returns a per-event summary."""
    matched, unmatched = match_participants(registrations, participants)
    summary = {"attended": 0, "noShow": 0, "skippedManual": 0, "unmatched": 0, "errors": 0}

    for reg in registrations:
        source = reg.get("attendanceSource") or ""
        if source in PROTECTED_SOURCES:
            summary["skippedManual"] += 1
            continue
        # A cancelled registration is not a no-show; leave it alone.
        if (reg.get("attendanceStatus") or "") == cfg.REG_CANCELLED:
            continue
        facts = matched.get(reg["id"])
        if facts:
            payload = {
                "attendanceStatus": cfg.REG_ATTENDED,
                "attendanceSource": SOURCE_ZOOM,
                "joinTime": _fmt(facts["join"]),
                "leaveTime": _fmt(facts["leave"]),
                "minutesAttended": max(1, round(facts["seconds"] / 60)),
            }
            summary["attended"] += 1
        else:
            payload = {
                "attendanceStatus": cfg.REG_NO_SHOW,
                "attendanceSource": SOURCE_ZOOM,
            }
            summary["noShow"] += 1
        try:
            await client.update(cfg.REGISTRATION, reg["id"], payload)
        except EspoError as exc:
            summary["errors"] += 1
            log.warning(
                "attendance: could not update registration %s for event %s: %s",
                reg["id"], event.get("id"), exc,
            )

    for facts in unmatched:
        # EV-32: recorded for review, NOT silently dropped. No Contact is
        # created — staff decide who this person is.
        payload = {
            "name": f"{event.get('name') or 'Event'} — {facts['name'] or facts['email'] or 'Unknown'}",
            "eventId": event.get("id"),
            "email": facts["email"] or None,
            "firstName": (facts["name"].split(" ")[0] if facts["name"] else "") or "Unknown",
            "lastName": " ".join(facts["name"].split(" ")[1:]) if facts["name"] else "",
            "attendanceStatus": cfg.REG_ATTENDED,
            "attendanceSource": SOURCE_ZOOM,
            "registrationSource": cfg.SOURCE_IMPORT,
            "unmatchedParticipant": True,
            "joinTime": _fmt(facts["join"]),
            "leaveTime": _fmt(facts["leave"]),
            "minutesAttended": max(1, round(facts["seconds"] / 60)),
        }
        try:
            await client.create(cfg.REGISTRATION, payload)
            summary["unmatched"] += 1
        except EspoError as exc:
            summary["errors"] += 1
            log.warning(
                "attendance: could not record unmatched participant %r on event %s: %s",
                facts.get("email") or facts.get("name"), event.get("id"), exc,
            )
    return summary


async def resolve_event(
    client: EspoApi, zoom: Any, event: dict[str, Any]
) -> Optional[dict[str, int]]:
    """One event's pull. None when the report isn't ready yet (retry later)."""
    registrations = await service.list_registrations(client, event["id"])
    if _is_resolved(registrations):
        return None
    participants = await zoom.list_participants(event["zoomWebinarId"])
    if not participants:
        # EV-31: empty means "not published yet", NOT "nobody came". Marking the
        # roster No-Show here would be a lie that staff then have to undo.
        log.info(
            "attendance: Zoom report not ready for event %s (%s) — will retry",
            event.get("id"), event.get("name"),
        )
        return None
    return await apply_attendance(client, event, registrations, participants)


async def run_attendance_cycle(
    settings: Settings, *, client: Optional[EspoApi] = None, zoom: Any = None
) -> dict[str, int]:
    """The worker's timer body. Best-effort: never raises."""
    totals = {"events": 0, "resolved": 0, "pending": 0, "attended": 0,
              "noShow": 0, "unmatched": 0, "errors": 0}
    if not settings.events_active or settings.espo_dry_run:
        return totals
    zoom = zoom or make_zoom_client(settings)
    if zoom is None:
        return totals              # Zoom not configured — nothing to pull
    if client is None:
        from core.espo import EspoClient

        client = EspoClient(
            settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
        )
    try:
        candidates = await attendance_candidates(client, settings)
    except EspoError as exc:
        log.warning("attendance: could not list candidate events: %s", exc)
        totals["errors"] += 1
        return totals

    totals["events"] = len(candidates)
    for event in candidates:
        try:
            result = await resolve_event(client, zoom, event)
        except Exception as exc:  # noqa: BLE001 — one bad event never stops the rest
            totals["errors"] += 1
            log.warning(
                "attendance: pull failed for event %s (%s): %s",
                event.get("id"), event.get("name"), exc,
            )
            continue
        if result is None:
            totals["pending"] += 1
            continue
        totals["resolved"] += 1
        for key in ("attended", "noShow", "unmatched", "errors"):
            totals[key] += result.get(key, 0)

    if totals["events"]:
        # EV-86: per-pass totals, so a silent stall is visible in the log.
        log.info("attendance pass: %s", totals)
    return totals
