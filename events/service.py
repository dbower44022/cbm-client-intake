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
#: How many event ids to put in one `in` filter.
_ID_CHUNK = 100
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


async def summaries_for(
    client: EspoApi, events: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Counts for MANY events in a couple of queries, not one per event.

    The obvious loop (``event_summary`` per row) is an N+1: the staff grid
    lists every event, so on a real CRM that was ~100 sequential round-trips
    and several seconds of blank page. Here the registrations are fetched in
    batches with an ``in`` filter and grouped in Python.
    """
    ids = [e["id"] for e in events if e.get("id")]
    by_event: dict[str, list[dict[str, Any]]] = {i: [] for i in ids}
    for chunk_start in range(0, len(ids), _ID_CHUNK):
        chunk = ids[chunk_start: chunk_start + _ID_CHUNK]
        offset = 0
        while True:
            data = await client.list(
                cfg.REGISTRATION,
                select=cfg.REGISTRATION_SELECT,
                where=[{"type": "in", "attribute": "eventId", "value": chunk}],
                max_size=_PAGE,
                offset=offset,
            )
            rows = data.get("list", [])
            for row in rows:
                by_event.setdefault(row.get("eventId"), []).append(row)
            offset += len(rows)
            if len(rows) < _PAGE or offset >= int(data.get("total") or 0):
                break
    return {
        e["id"]: summarise(by_event.get(e["id"], []), e.get("venueCapacity"))
        for e in events if e.get("id")
    }


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


# --- cancellation + waitlist promotion (Phase 3) ---------------------------


async def cancel_registration(
    client: EspoApi, registration_id: str, *, settings: Any = None
) -> dict[str, Any]:
    """Cancel one registration from its self-service link (EV-16).

    Frees the seat, removes the person from Zoom, and promotes the
    longest-waiting person off the waitlist. Every downstream step is
    best-effort: the cancellation itself must succeed even if Zoom is down,
    because the registrant has been told it worked.
    """
    try:
        registration = await client.get(cfg.REGISTRATION, registration_id)
    except EspoError:
        return {"ok": False, "reason": "not found"}
    if not registration:
        return {"ok": False, "reason": "not found"}

    if registration.get("attendanceStatus") == cfg.REG_CANCELLED:
        # Clicking the link twice is not an error.
        return {"ok": True, "alreadyCancelled": True,
                "message": "Your registration was already cancelled."}

    await client.update(cfg.REGISTRATION, registration_id, {
        "attendanceStatus": cfg.REG_CANCELLED,
        "cancellationDate": to_crm_datetime(datetime.now(timezone.utc)),
        "cancellationReason": "Cancelled by the registrant",
    })

    await _remove_from_zoom(client, registration, settings)

    promoted = None
    event_id = registration.get("eventId")
    if event_id:
        promoted = await _promote_from_waitlist(client, event_id, settings)

    return {
        "ok": True,
        "message": "Your registration has been cancelled.",
        "promoted": bool(promoted),
    }


async def _remove_from_zoom(
    client: EspoApi, registration: dict[str, Any], settings: Any
) -> None:
    """Free the Zoom seat too. Best-effort — a stale Zoom registrant is far
    less harmful than a failed cancellation the user was told had worked."""
    registrant_id = (registration.get("zoomRegistrantId") or "").strip()
    if not registrant_id or settings is None:
        return
    try:
        from core.zoom import make_client

        api = make_client(settings)
        if api is None:
            return
        # The webinar id lives on the EVENT — a registration only knows its own
        # id, so it has to be fetched (reading it off the registration returns
        # nothing and the Zoom seat would silently never be freed).
        event = await client.get(cfg.EVENT, registration.get("eventId") or "")
        webinar_id = ((event or {}).get("zoomWebinarId") or "").strip()
        if not webinar_id:
            return
        await api.cancel_registrant(
            webinar_id, registrant_id=registrant_id,
            email=registration.get("email") or "",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("registration %s: could not cancel the Zoom registrant: %s",
                    registration.get("id"), exc)


async def _promote_from_waitlist(
    client: EspoApi, event_id: str, settings: Any
) -> Optional[dict[str, Any]]:
    """Move the longest-waiting person into the freed seat (EV-15).

    Returns the promoted row, or None when there is no waitlist or no room.
    Best-effort: a failure leaves the waitlist intact for the next attempt
    rather than half-promoting someone.
    """
    try:
        event = await client.get(cfg.EVENT, event_id)
        capacity = (event or {}).get("venueCapacity")
        if not capacity or capacity <= 0:
            return None  # unlimited: nobody is ever waitlisted
        rows = await list_registrations(client, event_id)
        taken = sum(1 for r in rows if r.get("attendanceStatus") in cfg.SEAT_TAKING)
        if taken >= capacity:
            return None
        waiting = sorted(
            (r for r in rows if r.get("attendanceStatus") == cfg.REG_WAITLISTED),
            key=lambda r: r.get("registrationDate") or r.get("createdAt") or "",
        )
        if not waiting:
            return None
        winner = waiting[0]
        await client.update(cfg.REGISTRATION, winner["id"],
                            {"attendanceStatus": cfg.REG_REGISTERED})
        log.info("event %s: promoted registration %s off the waitlist",
                 event_id, winner["id"])
        return winner
    except Exception as exc:  # noqa: BLE001
        log.warning("event %s: waitlist promotion failed: %s", event_id, exc)
        return None


# --- staff writes (Phase 5) ------------------------------------------------


async def list_events(
    client: EspoApi, *, status: Optional[str] = None, limit: int = 500
) -> list[dict[str, Any]]:
    """The staff grid: EVERY event the user can read, newest first.

    Deliberately NOT filtered by ``publishToWebsite`` — staff need to see the
    internal calendar entries too, if only to notice one wrongly published.
    The frontend defaults its filter to published so the grid opens on the
    workshop programme rather than on 92 team meetings.
    """
    where = None
    if status:
        where = [{"type": "equals", "attribute": "status", "value": status}]
    return await _all_events(
        client, select=cfg.PUBLIC_SELECT, where=where,
        order_by="dateStart", order="desc", limit=limit,
    )


async def field_options(client: EspoApi) -> dict[str, list[str]]:
    """Live enum options for the editor, straight from CRM metadata.

    Read live rather than hard-coded so the CRM stays the source of truth — the
    same reason the mentor and session editors do it. A missing field yields an
    empty list rather than failing the form.
    """
    options: dict[str, list[str]] = {}
    for name in ("eventType", "format", "status", "topic"):
        try:
            values = await client.metadata_enum_options(cfg.EVENT, name)
        except EspoError:
            values = None
        options[name] = [v for v in (values or []) if v]
    return options


def _writable(changes: dict[str, Any], *, allow_managed: bool = False) -> dict[str, Any]:
    """Drop anything not in the field spec.

    The spec is the whitelist (the SESSION_FIELDS convention): a smuggled
    ``zoomWebinarId`` or an invented attribute never reaches the CRM.
    """
    allowed = cfg.EVENT_WRITABLE_NAMES if allow_managed else cfg.EVENT_EDIT_NAMES
    return {k: v for k, v in changes.items() if k in allowed}


async def create_event(client: EspoApi, changes: dict[str, Any]) -> dict[str, Any]:
    """Create an event, giving it a unique URL slug."""
    payload = _writable(changes)
    name = (payload.get("name") or "").strip()
    if not name:
        raise EventError("An event needs a title.")
    payload["name"] = name
    payload["slug"] = unique_slug(name, await existing_slugs(client))
    payload.setdefault("status", cfg.STATUS_PLANNED)
    payload.setdefault("publishToWebsite", False)
    created = await client.create(cfg.EVENT, payload)
    return await client.get(cfg.EVENT, created["id"], select=cfg.PUBLIC_SELECT)


async def update_event(
    client: EspoApi, event_id: str, changes: dict[str, Any]
) -> dict[str, Any]:
    """Apply whitelisted changes; give the event a slug if it never had one."""
    payload = _writable(changes)
    if "name" in payload and not (payload["name"] or "").strip():
        raise EventError("An event needs a title.")
    current = await client.get(cfg.EVENT, event_id, select=cfg.PUBLIC_SELECT)
    if not current.get("slug"):
        source = payload.get("name") or current.get("name") or ""
        if source:
            taken = await existing_slugs(client)
            payload["slug"] = unique_slug(source, taken)
    if payload:
        await client.update(cfg.EVENT, event_id, payload)
    return await client.get(cfg.EVENT, event_id, select=cfg.PUBLIC_SELECT)


async def set_recording(
    client: EspoApi, event_id: str, url: str
) -> dict[str, Any]:
    """Attach the published recording (D-07 — staff upload to YouTube, then
    paste the link). Blank clears it."""
    url = (url or "").strip()
    if url and not video_id_from_url(url):
        raise EventError(
            "That does not look like a YouTube link. Paste the watch URL, "
            "e.g. https://www.youtube.com/watch?v=…"
        )
    await client.update(cfg.EVENT, event_id, {"recordingUrl": url})
    return await client.get(cfg.EVENT, event_id, select=cfg.PUBLIC_SELECT)


async def set_attendance(
    client: EspoApi, registration_id: str, status: str,
    *, minutes: Optional[int] = None,
) -> dict[str, Any]:
    """Mark someone attended / no-show / registered by hand.

    Stamps ``attendanceSource='Manual'`` so the automatic Zoom pull (Phase 6)
    never overwrites a human's correction (EV-34).
    """
    allowed = (cfg.REG_REGISTERED, cfg.REG_ATTENDED, cfg.REG_NO_SHOW,
               cfg.REG_WAITLISTED, cfg.REG_CANCELLED)
    if status not in allowed:
        raise EventError(f"{status!r} is not a registration status.")
    payload: dict[str, Any] = {
        "attendanceStatus": status,
        "attendanceSource": "Manual",
    }
    if status == cfg.REG_ATTENDED and minutes is not None:
        payload["minutesAttended"] = int(minutes)
    await client.update(cfg.REGISTRATION, registration_id, payload)
    return await client.get(cfg.REGISTRATION, registration_id)


async def check_in(client: EspoApi, registration_id: str) -> dict[str, Any]:
    """Door check-in for an in-person event (EV-33): attended, stamped now."""
    now = to_crm_datetime(datetime.now(timezone.utc))
    await client.update(cfg.REGISTRATION, registration_id, {
        "attendanceStatus": cfg.REG_ATTENDED,
        "attendanceSource": "Check-in",
        "joinTime": now,
    })
    return await client.get(cfg.REGISTRATION, registration_id)


async def add_registrant(
    client: EspoApi, event_id: str, *, first_name: str, last_name: str = "",
    email: str = "", phone: str = "", source: str = cfg.SOURCE_STAFF,
    status: str = cfg.REG_REGISTERED,
) -> dict[str, Any]:
    """Register someone by hand — a phone booking, or a walk-in at the door.

    Reuses the public path's Contact rules so a walk-in is a first-class lead
    rather than a name on a list: find-or-create by email, never relabel an
    existing Contact.
    """
    from core.crm_upsert import find_create_or_fill
    from core.phone import e164_or_none
    from forms.event_registration.orchestrator import (
        C_CONTACT_TYPE, CONTACT, PROSPECT, _CONTACT_FILL_KEYS,
    )

    first_name = (first_name or "").strip()
    if not first_name:
        raise EventError("A name is required.")
    event = await client.get(cfg.EVENT, event_id, select=cfg.PUBLIC_SELECT)
    if not event:
        raise EventError("That event could not be found.")

    contact_id = None
    email = (email or "").strip()
    if email:
        existing = await client.find_one(CONTACT, "emailAddress", email, select="id")
        payload: dict[str, Any] = {
            "firstName": first_name, "lastName": last_name or "",
            "emailAddress": email,
        }
        if existing is None:
            payload[C_CONTACT_TYPE] = [PROSPECT]
        normalised = e164_or_none(phone)
        if normalised:
            payload["phoneNumber"] = normalised
        contact_id, _ = await find_create_or_fill(
            client, CONTACT, match_attr="emailAddress", match_value=email,
            create_payload=payload, fill_keys=_CONTACT_FILL_KEYS,
        )

    registration = {
        "name": f"{event.get('name') or 'Event'} — {first_name} {last_name}".strip()[:255],
        "eventId": event_id,
        "email": email,
        "firstName": first_name,
        "lastName": last_name or "",
        "attendanceStatus": status,
        "registrationSource": source,
        "registrationDate": to_crm_datetime(datetime.now(timezone.utc)),
    }
    if contact_id:
        registration["contactId"] = contact_id
    created = await client.create(cfg.REGISTRATION, registration)
    return await client.get(cfg.REGISTRATION, created["id"])
