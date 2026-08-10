"""Phase 6c — event reporting (EV-70…EV-74).

Four questions the programme needs answered, all computed live from the
registration rows. Nothing here is stored: the funder-contributions precedent
applies (EV-35), so no total can drift out of step with the records it counts.

* **EV-71 person history** — every event one Contact registered for or attended.
* **EV-72 engagement rollup** — events attended across ALL of an engagement's
  contacts, deduplicated, newest first, naming who went. *Doug's explicit
  requirement*, and the reason this module exists rather than a per-contact
  view only: a client is a company, and "did this client engage with the
  programme?" is not answerable one person at a time.
* **EV-73 attendee → client conversion** — attendees who later became clients.
* **EV-74 programme totals** — events held, unique attendees, repeat rate.

Per-event counts (EV-70) already live in ``service.summarise`` and are not
duplicated here.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Iterable, Optional

from core.espo import EspoApi, EspoError

from . import config as cfg
from . import service

log = logging.getLogger("cbm_intake.events.reporting")

#: Statuses that mean the person was actually in the room.
ATTENDED = (cfg.REG_ATTENDED,)


def _event_ref(event: dict[str, Any]) -> dict[str, Any]:
    start = service.parse_crm_datetime(event.get("dateStart"))
    local = service.to_local(start) if start else None
    return {
        "id": event.get("id"),
        "title": event.get("name") or "(untitled)",
        "slug": event.get("slug") or "",
        "date": local.strftime("%Y-%m-%d") if local else None,
        "dateLabel": local.strftime("%b %-d, %Y") if local else "",
        "startsAtUtc": start.isoformat() if start else None,
        "category": event.get("topic") or "",
        "format": event.get("format") or "",
    }


async def _events_by_id(
    client: EspoApi, event_ids: Iterable[str]
) -> dict[str, dict[str, Any]]:
    """Fetch the referenced events in chunks (never one query per row)."""
    ids = [i for i in dict.fromkeys(event_ids) if i]
    out: dict[str, dict[str, Any]] = {}
    for start in range(0, len(ids), 100):
        chunk = ids[start:start + 100]
        data = await client.list(
            cfg.EVENT,
            select=cfg.PUBLIC_SELECT,
            where=[{"type": "in", "attribute": "id", "value": chunk}],
            max_size=len(chunk),
        )
        for row in data.get("list", []):
            out[row["id"]] = row
    return out


async def _registrations_for_contacts(
    client: EspoApi, contact_ids: list[str]
) -> list[dict[str, Any]]:
    if not contact_ids:
        return []
    rows: list[dict[str, Any]] = []
    for start in range(0, len(contact_ids), 100):
        chunk = contact_ids[start:start + 100]
        data = await client.list(
            cfg.REGISTRATION,
            select=cfg.REGISTRATION_SELECT,
            where=[{"type": "in", "attribute": "contactId", "value": chunk}],
            max_size=200,
        )
        rows.extend(data.get("list", []))
    return rows


# --- EV-71: one person's history --------------------------------------------


async def contact_history(client: EspoApi, contact_id: str) -> list[dict[str, Any]]:
    """Every event this Contact registered for, newest first, with status."""
    if not contact_id:
        return []
    regs = await _registrations_for_contacts(client, [contact_id])
    events = await _events_by_id(client, [r.get("eventId") for r in regs])
    out = []
    for reg in regs:
        event = events.get(reg.get("eventId") or "")
        if not event:
            continue
        out.append({
            **_event_ref(event),
            "status": reg.get("attendanceStatus") or "",
            "attended": (reg.get("attendanceStatus") or "") in ATTENDED,
            "minutesAttended": reg.get("minutesAttended"),
            "registrationId": reg.get("id"),
        })
    out.sort(key=lambda r: r.get("startsAtUtc") or "", reverse=True)
    return out


# --- EV-72: the engagement rollup (Doug's explicit requirement) --------------


async def engagement_rollup(
    client: EspoApi, contacts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Events attended across all of an engagement's contacts.

    **Deduplicated by event**, newest first, each row naming which of the
    engagement's people were there — three colleagues at one webinar is one row,
    not three, because the question is "did this client engage?", not "how many
    seats did we fill?".

    Registrations are the source; a contact with no registration simply
    contributes nothing.
    """
    by_id = {c["id"]: c for c in contacts if c.get("id")}
    if not by_id:
        return []
    regs = await _registrations_for_contacts(client, list(by_id))
    attended = [r for r in regs if (r.get("attendanceStatus") or "") in ATTENDED]
    events = await _events_by_id(client, [r.get("eventId") for r in attended])

    rolled: dict[str, dict[str, Any]] = {}
    for reg in attended:
        event = events.get(reg.get("eventId") or "")
        if not event:
            continue
        row = rolled.get(event["id"])
        if row is None:
            row = {**_event_ref(event), "attendees": []}
            rolled[event["id"]] = row
        contact = by_id.get(reg.get("contactId") or "")
        name = (contact or {}).get("name") or (
            f"{reg.get('firstName') or ''} {reg.get('lastName') or ''}".strip()
        )
        if name and name not in row["attendees"]:
            row["attendees"].append(name)
    out = list(rolled.values())
    out.sort(key=lambda r: r.get("startsAtUtc") or "", reverse=True)
    return out


# --- EV-73 / EV-74: programme-level reports ---------------------------------


def _in_period(stamp: Optional[str], start: Optional[str], end: Optional[str]) -> bool:
    if not stamp:
        return False
    day = str(stamp)[:10]
    if start and day < start:
        return False
    if end and day > end:
        return False
    return True


async def program_totals(
    client: EspoApi, *, start: str = "", end: str = ""
) -> dict[str, Any]:
    """EV-74 — events held, unique attendees, repeat-attendee rate for a period.

    "Held" counts events that actually happened (not Cancelled) and have ended.
    The repeat rate is the share of unique attendees who came to more than one
    event **in the period** — a deliberately conservative reading, since
    attendance before the window is not evidence about it.
    """
    events = await service._all_events(
        client, select=cfg.PUBLIC_SELECT, where=None, order_by="dateStart",
        order="desc", limit=1000,
    )
    held = [
        e for e in events
        if e.get("status") != cfg.STATUS_CANCELLED
        and _in_period(e.get("dateStart"), start, end)
    ]
    if not held:
        return {
            "eventsHeld": 0, "uniqueAttendees": 0, "repeatAttendees": 0,
            "repeatRate": None, "totalAttendances": 0,
            "from": start or None, "to": end or None,
        }

    counts: dict[str, int] = {}
    total = 0
    for chunk_start in range(0, len(held), 100):
        chunk = [e["id"] for e in held[chunk_start:chunk_start + 100]]
        data = await client.list(
            cfg.REGISTRATION,
            select=cfg.REGISTRATION_SELECT,
            where=[
                {"type": "in", "attribute": "eventId", "value": chunk},
                {"type": "equals", "attribute": "attendanceStatus",
                 "value": cfg.REG_ATTENDED},
            ],
            max_size=200,
        )
        for reg in data.get("list", []):
            # Identify a person by contact when linked, else by email — an
            # unmatched attendee still counts as a person.
            key = reg.get("contactId") or (reg.get("email") or "").strip().lower()
            if not key:
                continue
            counts[key] = counts.get(key, 0) + 1
            total += 1

    unique = len(counts)
    repeat = sum(1 for n in counts.values() if n > 1)
    return {
        "eventsHeld": len(held),
        "uniqueAttendees": unique,
        "repeatAttendees": repeat,
        "repeatRate": round(repeat / unique, 4) if unique else None,
        "totalAttendances": total,
        "from": start or None,
        "to": end or None,
    }


async def conversion_report(
    client: EspoApi, *, start: str = "", end: str = ""
) -> dict[str, Any]:
    """EV-73 — attendees who subsequently became clients.

    "Became a client" = the Contact has a client engagement created **after**
    their first attended event in the period. Ordering matters: a client who
    happens to attend a webinar is not a conversion, and counting them as one
    would flatter the programme.
    """
    events = await service._all_events(
        client, select=cfg.PUBLIC_SELECT, where=None, order_by="dateStart",
        order="desc", limit=1000,
    )
    in_window = [e for e in events if _in_period(e.get("dateStart"), start, end)]
    first_attended: dict[str, str] = {}
    for chunk_start in range(0, len(in_window), 100):
        chunk = [e["id"] for e in in_window[chunk_start:chunk_start + 100]]
        if not chunk:
            continue
        data = await client.list(
            cfg.REGISTRATION,
            select=cfg.REGISTRATION_SELECT,
            where=[
                {"type": "in", "attribute": "eventId", "value": chunk},
                {"type": "equals", "attribute": "attendanceStatus",
                 "value": cfg.REG_ATTENDED},
            ],
            max_size=200,
        )
        by_event = {e["id"]: e for e in in_window}
        for reg in data.get("list", []):
            contact_id = reg.get("contactId")
            if not contact_id:
                continue      # an unmatched attendee cannot be traced to a client
            event = by_event.get(reg.get("eventId") or "")
            when = (event or {}).get("dateStart") or ""
            if not when:
                continue
            prior = first_attended.get(contact_id)
            if prior is None or when < prior:
                first_attended[contact_id] = when

    converted: list[dict[str, Any]] = []
    contact_ids = list(first_attended)
    for chunk_start in range(0, len(contact_ids), 100):
        chunk = contact_ids[chunk_start:chunk_start + 100]
        try:
            data = await client.list(
                "CEngagement",
                select="id,name,createdAt,contactId,engagementStatus",
                where=[{"type": "in", "attribute": "contactId", "value": chunk}],
                max_size=200,
            )
        except EspoError as exc:
            log.warning("conversion report: engagement lookup failed: %s", exc)
            break
        for eng in data.get("list", []):
            contact_id = eng.get("contactId")
            attended_at = first_attended.get(contact_id or "")
            created = eng.get("createdAt") or ""
            if attended_at and created and created > attended_at:
                converted.append({
                    "contactId": contact_id,
                    "engagementId": eng.get("id"),
                    "engagement": eng.get("name"),
                    "firstAttendedUtc": attended_at,
                    "engagementCreatedUtc": created,
                    "status": eng.get("engagementStatus") or "",
                })

    attendees = len(first_attended)
    unique_converted = len({c["contactId"] for c in converted})
    return {
        "attendees": attendees,
        "converted": unique_converted,
        "conversionRate": round(unique_converted / attendees, 4) if attendees else None,
        "rows": sorted(converted, key=lambda r: r["engagementCreatedUtc"], reverse=True),
        "from": start or None,
        "to": end or None,
    }
