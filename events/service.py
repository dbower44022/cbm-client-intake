"""Events & Webinars — the CRM read/derive layer.

Everything the website and (later) the staff app need from ``CEvent`` /
``CEventRegistration``, plus the derived numbers.

Two rules this module exists to enforce:

**1. Nothing is served publicly without ``publishToWebsite``.** ``CEvent`` is
also the organisation's calendar entity — it holds internal team meetings and
mentoring-session mirrors (92 of them at the time of writing). That flag is the
only thing separating them from the public website, so every public read goes
through :func:`_public_where`, which always includes it. Do not hand-roll a
public query elsewhere.

**2. Counts are computed, never stored.** Registered/attended/show-rate/seats
remaining are derived from the registration rows on every read
(:func:`event_summary`). No denormalised totals exist, so none can drift — the
same ruling applied to funder contributions.

Times: the CRM speaks UTC over the API; the public payload carries both the UTC
instant and pre-formatted Cleveland-local display strings so the website does no
timezone maths (EV-85).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

from core.espo import EspoApi, EspoError
from core.youtube import thumbnail_url, video_id_from_url

from . import config as cfg

log = logging.getLogger("cbm_intake.events")

_PAGE = 200
_LOCAL = ZoneInfo(cfg.PUBLIC_TIMEZONE)

#: CRM datetime wire format.
_FMT = "%Y-%m-%d %H:%M:%S"


class EventError(RuntimeError):
    """A problem the caller should surface, not a CRM transport failure."""


# --- time helpers ----------------------------------------------------------


def parse_crm_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse an EspoCRM datetime, which is always UTC despite carrying no
    offset (the v0.39.2 lesson: treating these as local silently shifts every
    event by 4-5 hours)."""
    if not value:
        return None
    text = str(value).strip().replace("T", " ").removesuffix("Z")
    for fmt in (_FMT, "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def to_crm_datetime(value: datetime) -> str:
    """Render a datetime for the CRM wire format (UTC, no offset)."""
    return value.astimezone(timezone.utc).strftime(_FMT)


def to_local(value: datetime) -> datetime:
    return value.astimezone(_LOCAL)


def _fmt_time_range(start: datetime, end: Optional[datetime], label: str) -> str:
    """The website's time band, e.g. ``2:00 PM - 3:30 PM | WEBINAR``."""
    def clock(moment: datetime) -> str:
        return moment.strftime("%-I:%M %p")

    local_start = to_local(start)
    span = clock(local_start)
    if end:
        span = f"{span} - {clock(to_local(end))}"
    return f"{span} | {label.upper()}" if label else span


# --- slugs -----------------------------------------------------------------


def slugify(name: str) -> str:
    """A URL segment for the per-event page (EV-06)."""
    normalised = unicodedata.normalize("NFKD", name or "")
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return slug[:90] or "event"


def unique_slug(name: str, taken: Iterable[str]) -> str:
    """``slugify`` with a numeric suffix when the slug is already in use.

    Mirrors the userName-collision handling in mentor provisioning: never fail,
    never overwrite someone else's URL.
    """
    used = {s for s in taken if s}
    base = slugify(name)
    if base not in used:
        return base
    for suffix in range(2, 1000):
        candidate = f"{base}-{suffix}"
        if candidate not in used:
            return candidate
    raise EventError(f"Could not find a free slug for {name!r}.")


async def existing_slugs(client: EspoApi) -> set[str]:
    rows = await _all_events(client, select="id,slug", where=None)
    return {r.get("slug") for r in rows if r.get("slug")}


# --- CRM reads -------------------------------------------------------------


async def _all_events(
    client: EspoApi,
    *,
    select: str,
    where: Optional[list[dict[str, Any]]],
    order_by: str = "dateStart",
    order: str = "asc",
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Paginated list, so a growing archive never silently truncates."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while len(rows) < limit:
        data = await client.list(
            cfg.EVENT,
            select=select,
            where=where,
            max_size=min(_PAGE, limit - len(rows)),
            offset=offset,
            order_by=order_by,
            order=order,
        )
        page = data.get("list", [])
        rows.extend(page)
        offset += len(page)
        if len(page) < _PAGE or offset >= int(data.get("total") or 0):
            break
    return rows


def _public_where(extra: Optional[list[dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """The non-negotiable public filter.

    ``publishToWebsite`` is true and the event is not cancelled. Every public
    read starts here — see the module docstring for why.
    """
    where: list[dict[str, Any]] = [
        {"type": "isTrue", "attribute": "publishToWebsite"},
        {"type": "notEquals", "attribute": "status", "value": cfg.STATUS_CANCELLED},
    ]
    if extra:
        where.extend(extra)
    return where


async def list_upcoming(
    client: EspoApi, *, now: Optional[datetime] = None
) -> list[dict[str, Any]]:
    """Published, non-cancelled events starting from now, soonest first."""
    moment = now or datetime.now(timezone.utc)
    # A little slack so an event that has just started still shows while it runs.
    horizon = moment - timedelta(hours=2)
    rows = await _all_events(
        client,
        select=cfg.PUBLIC_SELECT,
        where=_public_where(
            [{"type": "after", "attribute": "dateStart", "value": to_crm_datetime(horizon)}]
        ),
        order_by="dateStart",
        order="asc",
    )
    return rows


async def list_recordings(
    client: EspoApi, *, query: str = "", limit: int = 50
) -> list[dict[str, Any]]:
    """Past published events that have a recording, newest first.

    The search runs **server-side** over title, summary and topic (EV-04) so the
    browser never receives the whole archive to filter.
    """
    rows = await _all_events(
        client,
        select=cfg.PUBLIC_SELECT,
        where=_public_where(),
        order_by="dateStart",
        order="desc",
        limit=1000,
    )
    with_recording = [r for r in rows if (r.get("recordingUrl") or "").strip()]
    needle = (query or "").strip().lower()
    if needle:
        with_recording = [
            r for r in with_recording
            if needle in " ".join(
                str(r.get(key) or "") for key in ("name", "description", "topic")
            ).lower()
        ]
    return with_recording[: max(1, limit)]


async def get_by_slug(client: EspoApi, slug: str) -> Optional[dict[str, Any]]:
    """One published event by its URL slug (EV-06), or None.

    Deliberately goes through the public filter: an unpublished event's page
    must 404 rather than leak an internal calendar entry to anyone who guesses
    the URL.
    """
    if not slug:
        return None
    rows = await _all_events(
        client,
        select=cfg.PUBLIC_SELECT,
        where=_public_where([{"type": "equals", "attribute": "slug", "value": slug}]),
        limit=2,
    )
    return rows[0] if rows else None


async def list_registrations(client: EspoApi, event_id: str) -> list[dict[str, Any]]:
    """Every registration row for one event."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = await client.list(
            cfg.REGISTRATION,
            select=cfg.REGISTRATION_SELECT,
            where=[{"type": "equals", "attribute": "eventId", "value": event_id}],
            max_size=_PAGE,
            offset=offset,
        )
        page = data.get("list", [])
        rows.extend(page)
        offset += len(page)
        if len(page) < _PAGE or offset >= int(data.get("total") or 0):
            break
    return rows


# --- derived numbers -------------------------------------------------------


def summarise(
    registrations: list[dict[str, Any]], capacity: Optional[int] = None
) -> dict[str, Any]:
    """Counts for one event, computed from its registration rows.

    Never stored (EV-35). ``showRate`` is attended / (attended + no-show) — it
    deliberately excludes cancellations and waitlisted people, who were never
    expected in the room.
    """
    counts = {
        "registered": 0, "waitlisted": 0, "cancelled": 0,
        "attended": 0, "noShow": 0,
    }
    minutes: list[int] = []
    for row in registrations:
        status = row.get("attendanceStatus")
        if status == cfg.REG_WAITLISTED:
            counts["waitlisted"] += 1
        elif status == cfg.REG_CANCELLED:
            counts["cancelled"] += 1
        elif status == cfg.REG_ATTENDED:
            counts["attended"] += 1
            counts["registered"] += 1
        elif status == cfg.REG_NO_SHOW:
            counts["noShow"] += 1
            counts["registered"] += 1
        elif status == cfg.REG_REGISTERED:
            counts["registered"] += 1
        if status == cfg.REG_ATTENDED and isinstance(row.get("minutesAttended"), int):
            minutes.append(row["minutesAttended"])

    resolved = counts["attended"] + counts["noShow"]
    counts["showRate"] = (
        round(counts["attended"] / resolved, 3) if resolved else None
    )
    counts["averageMinutes"] = (
        round(sum(minutes) / len(minutes)) if minutes else None
    )
    counts["seatsRemaining"] = seats_remaining(capacity, counts["registered"])
    return counts


def seats_remaining(capacity: Optional[int], taken: int) -> Optional[int]:
    """None means unlimited — an empty or zero capacity is not a full event."""
    if not capacity or capacity <= 0:
        return None
    return max(0, capacity - taken)


async def event_summary(
    client: EspoApi, event: dict[str, Any]
) -> dict[str, Any]:
    """:func:`summarise` for a single event record, reading its registrations."""
    registrations = await list_registrations(client, event["id"])
    return summarise(registrations, event.get("venueCapacity"))


# --- public payload --------------------------------------------------------


def registration_open(
    event: dict[str, Any], *, now: Optional[datetime] = None,
    seats_left: Optional[int] = None,
) -> bool:
    """Is registration still open? (EV-14, EV-15)

    Closes at ``registrationCloses`` when set, otherwise at ``dateStart``.
    """
    moment = now or datetime.now(timezone.utc)
    if event.get("status") == cfg.STATUS_CANCELLED:
        return False
    if seats_left is not None and seats_left <= 0:
        return False
    closes = parse_crm_datetime(event.get("registrationCloses")) or parse_crm_datetime(
        event.get("dateStart")
    )
    return bool(closes and moment < closes)


def _type_label(event: dict[str, Any]) -> str:
    """The word in the time band. The live page shows ``WEBINAR``."""
    fmt = event.get("format")
    if fmt == cfg.FORMAT_IN_PERSON:
        return "In Person"
    if fmt == cfg.FORMAT_HYBRID:
        return "Hybrid"
    return "Webinar"


def public_event(
    event: dict[str, Any],
    *,
    base_url: str = "",
    seats_left: Optional[int] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Shape one event for the public API.

    **The key names are a compatibility contract, not a design.** They match
    what the Apps Script returns today so the website's existing rendering code
    ports across with near-zero change — including ``topic`` meaning the event
    *title* (Zoom's vocabulary). The CRM's subject category is exposed
    separately as ``category``. See the note in ``events/config.py``.
    """
    start = parse_crm_datetime(event.get("dateStart"))
    end = parse_crm_datetime(event.get("dateEnd"))
    local = to_local(start) if start else None
    duration_seconds = event.get("duration")
    if not duration_seconds and start and end:
        duration_seconds = int((end - start).total_seconds())

    video_id = video_id_from_url(event.get("recordingUrl") or "")
    slug = event.get("slug") or ""

    payload: dict[str, Any] = {
        # --- the existing contract (do not rename) ---
        "topic": event.get("name") or "",          # the TITLE (Zoom vocabulary)
        "summary": (event.get("description") or "").strip(),
        "date": local.strftime("%Y-%m-%d") if local else None,
        "month": local.strftime("%B %Y") if local else None,
        "monthShort": local.strftime("%b") if local else None,
        "day": local.strftime("%-d") if local else None,
        "time": _fmt_time_range(start, end, _type_label(event)) if start else "",
        "durationHrs": round(duration_seconds / 3600, 2) if duration_seconds else None,
        "webinarId": event.get("zoomWebinarId") or "",
        # --- additive ---
        "id": event.get("id"),
        "slug": slug,
        "url": f"{base_url.rstrip('/')}/{slug}" if base_url and slug else "",
        "startsAtUtc": start.isoformat() if start else None,
        "endsAtUtc": end.isoformat() if end else None,
        "eventType": event.get("eventType") or "",
        "format": event.get("format") or "",
        "category": event.get("topic") or "",      # the CRM subject category
        "location": (event.get("location") or "").strip(),
        "status": event.get("status") or "",
        "seatsRemaining": seats_left,
        "registrationOpen": registration_open(event, now=now, seats_left=seats_left),
        "recordingUrl": event.get("recordingUrl") or "",
        "videoId": video_id or "",
        "thumbnailUrl": thumbnail_url(video_id) if video_id else "",
    }
    return payload


def public_event_detail(event: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """:func:`public_event` plus the long-form content for the per-event page."""
    payload = public_event(event, **kwargs)
    payload["overview"] = event.get("eventOverview") or ""
    payload["syllabus"] = event.get("eventSyllabus") or ""
    payload["joinUrl"] = event.get("virtualMeetingUrl") or ""
    return payload


def public_recording(event: dict[str, Any], *, base_url: str = "") -> dict[str, Any]:
    """One row of the recorded-webinar library."""
    start = parse_crm_datetime(event.get("dateStart"))
    local = to_local(start) if start else None
    video_id = video_id_from_url(event.get("recordingUrl") or "")
    slug = event.get("slug") or ""
    return {
        "id": event.get("id"),
        "title": event.get("name") or "",
        "summary": (event.get("description") or "").strip(),
        "date": local.strftime("%Y-%m-%d") if local else None,
        "dateLabel": local.strftime("%b %-d, %Y").upper() if local else "",
        "category": event.get("topic") or "",
        "recordingUrl": event.get("recordingUrl") or "",
        "videoId": video_id or "",
        "thumbnailUrl": thumbnail_url(video_id) if video_id else "",
        "slug": slug,
        "url": f"{base_url.rstrip('/')}/{slug}" if base_url and slug else "",
    }


async def upcoming_payload(
    client: EspoApi, *, base_url: str = "", now: Optional[datetime] = None
) -> list[dict[str, Any]]:
    """The public calendar, with seat counts.

    Seat counts need one registration query per event, which is fine at this
    volume (a handful of upcoming events) and is skipped entirely for events
    with no capacity set.
    """
    events = await list_upcoming(client, now=now)
    payload: list[dict[str, Any]] = []
    for event in events:
        seats_left = None
        if event.get("venueCapacity"):
            try:
                seats_left = (await event_summary(client, event))["seatsRemaining"]
            except EspoError as exc:  # counts are a nicety; never fail the page
                log.warning("event %s: could not count registrations: %s",
                            event.get("id"), exc)
        payload.append(
            public_event(event, base_url=base_url, seats_left=seats_left, now=now)
        )
    return payload
