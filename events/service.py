"""Events & Webinars — the CRM read/derive layer.

Everything the website and (later) the staff app need from ``CEvent`` /
``CEventRegistration``, plus the derived numbers.

Two rules this module exists to enforce:

**1. Nothing is served publicly unless the visibility rule allows it.**
``CEvent`` is also the organisation's calendar entity — it holds internal team
meetings and mentoring-session mirrors. Whether an event may be shown, where
and from when is decided in ONE place, :mod:`events.visibility` ("Show this
event" ticked, audience Public, display time passed, not cancelled). Every
public read goes through :func:`_public_where` AND re-checks each row with
``visibility.is_shown``. Do not hand-roll a public query elsewhere.

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

from core.espo import EspoApi, EspoError, is_forbidden
from core.youtube import thumbnail_url, video_id_from_url

from . import config as cfg
from . import visibility

log = logging.getLogger("cbm_intake.events")

_PAGE = 200
#: How many event ids to put in one `in` filter.
_ID_CHUNK = 100
_LOCAL = ZoneInfo(cfg.PUBLIC_TIMEZONE)

#: CRM datetime wire format.
_FMT = "%Y-%m-%d %H:%M:%S"

#: Enum fields on CEvent, from the one spec that also drives the form.
_ENUM_FIELD_NAMES = frozenset(f.name for f in cfg.EVENT_FIELDS if f.type == "enum")
#: Multiple-choice fields (F2/F3: the reach's chapters, the team limit).
_MULTI_FIELD_NAMES = frozenset(f.name for f in cfg.EVENT_FIELDS if f.type == "multiEnum")
#: Every field whose options the editor reads live.
_OPTION_FIELD_NAMES = ("status", *(
    f.name for f in cfg.EVENT_FIELDS if f.type in ("enum", "multiEnum")
))


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


async def live_event_fields(client: EspoApi) -> frozenset[str]:
    """Which of the F2/F3 fields the live CRM has (CRM = truth).

    A client with no metadata reader (the dry-run client, simple test fakes) has
    none of them, which is exactly the behaviour before those fields existed.
    A metadata read that FAILS raises: the visibility filter depends on this
    answer, and guessing "absent" during an outage would drop the audience
    filter and put Internal events on the public pages.
    """
    reader = getattr(client, "metadata", None)
    if reader is None:
        return frozenset()
    fields = await reader(f"entityDefs.{cfg.EVENT}.fields") or {}
    return frozenset(name for name in cfg.AUDIENCE_FIELDS if name in fields)


def _public_where(
    extra: Optional[list[dict[str, Any]]] = None,
    *,
    fields: Iterable[str] = (),
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """The non-negotiable public filter — :mod:`events.visibility`'s rule as CRM
    ``where`` clauses, for the fields the live CRM has. Every public read starts
    here, and then re-checks each row with ``visibility.is_shown``.
    """
    where = visibility.public_where_clauses(fields, now)
    if extra:
        where.extend(extra)
    return where


def _shown_publicly(
    rows: list[dict[str, Any]], now: Optional[datetime] = None
) -> list[dict[str, Any]]:
    return [r for r in rows if visibility.is_shown(r, visibility.SURFACE_PUBLIC, now=now)]


async def list_upcoming(
    client: EspoApi, *, now: Optional[datetime] = None
) -> list[dict[str, Any]]:
    """Published, non-cancelled events starting from now, soonest first."""
    moment = now or datetime.now(timezone.utc)
    # A little slack so an event that has just started still shows while it runs.
    horizon = moment - timedelta(hours=2)
    fields = await live_event_fields(client)
    rows = await _all_events(
        client,
        select=cfg.PUBLIC_SELECT,
        where=_public_where(
            [{"type": "after", "attribute": "dateStart", "value": to_crm_datetime(horizon)}],
            fields=fields, now=moment,
        ),
        order_by="dateStart",
        order="asc",
    )
    return _shown_publicly(rows, moment)


async def published_recordings(client: EspoApi) -> list[dict[str, Any]]:
    """Every past published event that has a recording, newest first.

    One read. The filtering below is pure, so the topic list and the filtered
    results come from the same fetch rather than one query each.
    """
    fields = await live_event_fields(client)
    now = datetime.now(timezone.utc)
    rows = await _all_events(
        client,
        select=cfg.PUBLIC_SELECT,
        where=_public_where(fields=fields, now=now),
        order_by="dateStart",
        order="desc",
        limit=1000,
    )
    return [r for r in _shown_publicly(rows, now) if (r.get("recordingUrl") or "").strip()]


def recording_topics(rows: list[dict[str, Any]]) -> list[str]:
    """The topics that actually have a recording, in the CRM's own order.

    Derived from the recordings rather than from the CRM's ten curated options,
    because a filter offering a topic with nothing behind it is a dead end — the
    visitor picks it and the panel empties. Deliberately NOT narrowed by the
    current search, so the list does not shift under the reader between one
    search and the next.
    """
    present = {(r.get("topic") or "").strip() for r in rows}
    present.discard("")
    ordered = [t for t in cfg.TOPIC_ORDER if t in present]
    # Anything the CRM has since added to the enum, or a stored value that has
    # drifted out of it, still appears rather than vanishing from the filter.
    return ordered + sorted(present - set(ordered))


def filter_recordings(
    rows: list[dict[str, Any]], *, query: str = "", topic: str = "", limit: int = 50
) -> list[dict[str, Any]]:
    """Search and topic filter, both server-side (EV-04), so the browser never
    receives the whole archive to sift. Pure — testable without a CRM."""
    hits = rows
    wanted = (topic or "").strip().lower()
    if wanted:
        hits = [r for r in hits if (r.get("topic") or "").strip().lower() == wanted]
    needle = (query or "").strip().lower()
    if needle:
        hits = [
            r for r in hits
            if needle in " ".join(
                str(r.get(key) or "") for key in ("name", "description", "topic")
            ).lower()
        ]
    return hits[: max(1, limit)]


async def list_recordings(
    client: EspoApi, *, query: str = "", limit: int = 50, topic: str = ""
) -> list[dict[str, Any]]:
    """Past published events that have a recording, newest first, filtered."""
    return filter_recordings(
        await published_recordings(client), query=query, topic=topic, limit=limit
    )


async def get_by_slug(client: EspoApi, slug: str) -> Optional[dict[str, Any]]:
    """One published event by its URL slug (EV-06), or None.

    Deliberately goes through the public filter: an unpublished event's page
    must 404 rather than leak an internal calendar entry to anyone who guesses
    the URL.
    """
    if not slug:
        return None
    fields = await live_event_fields(client)
    now = datetime.now(timezone.utc)
    rows = await _all_events(
        client,
        select=cfg.PUBLIC_SELECT,
        where=_public_where([{"type": "equals", "attribute": "slug", "value": slug}],
                            fields=fields, now=now),
        limit=2,
    )
    rows = _shown_publicly(rows, now)
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


def public_image_url(event: dict[str, Any], *, base_url: str = "") -> str:
    """Absolute URL of this event's uploaded graphic, or "" when it has none.

    Points at THIS app's public image proxy, not at EspoCRM — the browser can't
    reach the CRM. The attachment id rides as ``?v=`` so the response can be
    cached hard while still changing the URL when the picture is replaced.

    ``base_url`` is the app's own public root (``APP_BASE_URL``). With it unset
    the URL is site-relative, which still works for a same-origin caller and is
    what the WordPress proxy will rewrite anyway.
    """
    attachment_id = event.get("eventGraphicId") or ""
    slug = event.get("slug") or ""
    if not attachment_id or not slug:
        return ""
    path = f"/api/events/{slug}/image?v={attachment_id[:12]}"
    return f"{base_url.rstrip('/')}{path}" if base_url else path


def public_event(
    event: dict[str, Any],
    *,
    base_url: str = "",
    api_base_url: str = "",
    default_image: str = "",
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
        # An uploaded graphic WINS over the derived YouTube thumbnail: if
        # someone took the trouble to make a card image, use it. Blank when
        # there is none, so the renderer falls back to thumbnailUrl.
        "imageUrl": public_image_url(event, base_url=api_base_url),
    }
    # LAST fallback, after the event's own graphic and after a recording's video
    # thumbnail: the configured house image. Ordering matters — a recorded
    # webinar's own still frame says more about it than a generic card, so the
    # default only fills a hole neither of the other two could.
    if not payload["imageUrl"] and not payload["thumbnailUrl"] and default_image:
        payload["imageUrl"] = default_image
    return payload


def public_event_detail(event: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """:func:`public_event` plus the long-form content for the per-event page."""
    payload = public_event(event, **kwargs)
    payload["overview"] = event.get("eventOverview") or ""
    payload["syllabus"] = event.get("eventSyllabus") or ""
    payload["joinUrl"] = event.get("virtualMeetingUrl") or ""
    return payload


def public_recording(
    event: dict[str, Any], *, base_url: str = "", api_base_url: str = "",
    default_image: str = "",
) -> dict[str, Any]:
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
        # A recording always has a video thumbnail to fall back on, so the
        # default is reached only when the video id could not be read.
        "imageUrl": (
            public_image_url(event, base_url=api_base_url)
            or ("" if video_id else default_image)
        ),
    }


async def upcoming_payload(
    client: EspoApi,
    *,
    base_url: str = "",
    api_base_url: str = "",
    default_image: str = "",
    now: Optional[datetime] = None,
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
            public_event(
                event,
                base_url=base_url,
                api_base_url=api_base_url,
                default_image=default_image,
                seats_left=seats_left,
                now=now,
            )
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
    for name in _OPTION_FIELD_NAMES:
        try:
            values = await client.metadata_enum_options(cfg.EVENT, name)
        except (EspoError, ValueError):
            # ValueError: a body that is not JSON. The client now answers None
            # for an empty body, but a field the CRM lacks must never take the
            # whole editor down whatever the transport hands back.
            values = None
        options[name] = [v for v in (values or []) if v]
    return options


async def option_labels(client: EspoApi) -> dict[str, dict[str, str]]:
    """The CRM's own display labels for option values, where it has them.

    The chapter list stores each chapter's short label (``boston``) and shows
    its full name, which lives in the CRM's translations, not its metadata.
    Best-effort: without labels the editor shows the stored values.
    """
    reader = getattr(client, "i18n", None)
    if reader is None:
        return {}
    try:
        data = await reader(cfg.EVENT)
    except EspoError:
        return {}
    options = ((data or {}).get(cfg.EVENT) or {}).get("options") or {}
    return {
        name: labels for name, labels in options.items()
        if name in _OPTION_FIELD_NAMES and isinstance(labels, dict)
    }


def editor_fields(available: Iterable[str]) -> list[cfg.EventField]:
    """The field spec, less the F2/F3 fields the live CRM does not have."""
    present = set(available)
    return [
        f for f in cfg.EVENT_FIELDS
        if f.name not in cfg.AUDIENCE_FIELDS or f.name in present
    ]


def _writable(
    changes: dict[str, Any],
    *,
    allow_managed: bool = False,
    available: Iterable[str] = (),
    current: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Drop anything not in the field spec, and any F2/F3 field the live CRM
    does not have.

    The spec is the whitelist (the SESSION_FIELDS convention): a smuggled
    ``zoomWebinarId`` or an invented attribute never reaches the CRM.

    A conditionally editable app-managed field (``EVENT_CONDITIONAL_EDITS``)
    is accepted only when the record AS SAVED meets its condition — the value
    in this very change set if it carries the deciding field, else the stored
    one in ``current``. The Join URL is the case: typed for an Internal event,
    Zoom's for a Public one, and a Public event's posted-back value is dropped
    here rather than overwriting what Zoom wrote. A CRM without the deciding
    field unlocks nothing.
    """
    allowed = set(cfg.EVENT_WRITABLE_NAMES if allow_managed else cfg.EVENT_EDIT_NAMES)
    allowed -= set(cfg.AUDIENCE_FIELDS) - set(available)
    if not allow_managed:
        present = set(available)
        stored = current or {}
        for name, (decider, values) in cfg.EVENT_CONDITIONAL_EDITS.items():
            if decider in cfg.AUDIENCE_FIELDS and decider not in present:
                continue
            value = changes[decider] if decider in changes else stored.get(decider)
            if value in values:
                allowed.add(name)
    return {k: v for k, v in changes.items() if k in allowed}


async def _clean_multi_enums(client: EspoApi, payload: dict[str, Any]) -> None:
    """A multi-choice value is a de-duplicated list of live options.

    EspoCRM refuses the whole save when one value is not an option, so a value
    that has drifted out of the list (a renamed team) is dropped here rather
    than failing the save. Fails open when the options cannot be read.
    """
    for name in _MULTI_FIELD_NAMES & payload.keys():
        value = payload[name]
        if value in (None, ""):
            payload[name] = []
            continue
        if isinstance(value, str):
            value = [value]
        values = [v for v in value if isinstance(v, str) and v.strip()]
        try:
            options = await client.metadata_enum_options(cfg.EVENT, name)
        except EspoError:
            options = None
        if options is not None:
            values = [v for v in values if v in options]
        payload[name] = list(dict.fromkeys(values))


async def _include_own_chapter(
    client: EspoApi,
    payload: dict[str, Any],
    current: dict[str, Any],
    *,
    available: Iterable[str],
    chapter_key: str,
) -> None:
    """The creating chapter is always in an event's reach (Doug's F3 ruling 6).

    Enforced here, on every save, rather than only in the browser, so no
    caller can leave it out. Skipped — with a warning in the log — when this
    chapter's key is not one of the CRM's chapter options, because writing an
    unknown value would fail the whole save.
    """
    key = (chapter_key or "").strip()
    if not key or cfg.REACH_CHAPTERS_FIELD not in set(available):
        return
    chapters = payload.get(cfg.REACH_CHAPTERS_FIELD)
    if chapters is None:
        chapters = list(current.get(cfg.REACH_CHAPTERS_FIELD) or [])
    if key in chapters:
        return
    try:
        options = await client.metadata_enum_options(cfg.EVENT, cfg.REACH_CHAPTERS_FIELD)
    except EspoError:
        options = None
    if not options or key not in options:
        log.warning(
            "chapter key %r is not an option of CEvent.%s; the reach was left alone",
            key, cfg.REACH_CHAPTERS_FIELD,
        )
        return
    payload[cfg.REACH_CHAPTERS_FIELD] = [*chapters, key]


async def create_event(
    client: EspoApi, changes: dict[str, Any], *, chapter_key: str = ""
) -> dict[str, Any]:
    """Create an event, giving it a unique URL slug.

    A new event is Public, reach this chapter, unless the editor says
    otherwise: Event Administration is the public programme's tool, and the
    "Show this event" tick still decides whether it appears at all.
    """
    available = await live_event_fields(client)
    payload = _blank_enums_to_null(_writable(changes, available=available))
    name = (payload.get("name") or "").strip()
    if not name:
        raise EventError("An event needs a title.")
    payload["name"] = name
    payload["slug"] = unique_slug(name, await existing_slugs(client))
    payload.setdefault("status", cfg.STATUS_PLANNED)
    payload.setdefault(cfg.SHOW_FIELD, False)
    if cfg.AUDIENCE_FIELD in available and not payload.get(cfg.AUDIENCE_FIELD):
        payload[cfg.AUDIENCE_FIELD] = cfg.AUDIENCE_PUBLIC
    if cfg.REACH_FIELD in available and not payload.get(cfg.REACH_FIELD):
        payload[cfg.REACH_FIELD] = cfg.REACH_THIS
    await _clean_multi_enums(client, payload)
    await _include_own_chapter(client, payload, {}, available=available,
                               chapter_key=chapter_key)
    created = await client.create(cfg.EVENT, payload)
    return await client.get(cfg.EVENT, created["id"], select=cfg.PUBLIC_SELECT)




def _blank_enums_to_null(payload: dict[str, Any]) -> dict[str, Any]:
    """An unset enum is ``null``, never ``""``.

    The editor posts every field rather than only the changed ones, so an event
    with no topic sends ``topic: ""``. EspoCRM's ``topic`` enum has no empty
    option, and it answers ``400 Field validation failure`` — which the router
    used to report as a 502 "the CRM is unavailable".

    Found live on 2026-09-14: publishing an imported recording failed every
    time, and only succeeded once a topic was chosen as well, because that
    replaced the empty string with a real option. Nothing about publishing was
    at fault; the empty enum riding along with it was.

    ``null`` is what EspoCRM means by "no value": accepted for an optional enum,
    and correctly refused for a required one — where the user now gets a message
    naming the field instead of a gateway error.
    """
    return {
        key: (None if key in _ENUM_FIELD_NAMES and value == "" else value)
        for key, value in payload.items()
    }


async def update_event(
    client: EspoApi, event_id: str, changes: dict[str, Any], *, chapter_key: str = ""
) -> dict[str, Any]:
    """Apply whitelisted changes; give the event a slug if it never had one."""
    available = await live_event_fields(client)
    current = await client.get(cfg.EVENT, event_id, select=cfg.PUBLIC_SELECT)
    payload = _blank_enums_to_null(
        _writable(changes, available=available, current=current)
    )
    if "name" in payload and not (payload["name"] or "").strip():
        raise EventError("An event needs a title.")
    await _clean_multi_enums(client, payload)
    await _include_own_chapter(client, payload, current, available=available,
                               chapter_key=chapter_key)
    if not current.get("slug"):
        source = payload.get("name") or current.get("name") or ""
        if source:
            taken = await existing_slugs(client)
            payload["slug"] = unique_slug(source, taken)
    if payload:
        await client.update(cfg.EVENT, event_id, payload)
    return await client.get(cfg.EVENT, event_id, select=cfg.PUBLIC_SELECT)


async def set_event_graphic(
    client: EspoApi,
    event_id: str,
    *,
    filename: str,
    content_type: str,
    data_base64: str,
) -> dict[str, Any]:
    """Upload the website card image and point the event at it.

    An EspoCRM file field: the Attachment is created bound to
    ``CEvent.eventGraphic`` and its id stored in ``eventGraphicId``.
    """
    if content_type not in cfg.ALLOWED_IMAGE_TYPES:
        raise EventError(
            "Please choose a JPEG, PNG, WebP or GIF image for the event graphic."
        )
    if len(data_base64) > cfg.MAX_IMAGE_B64_CHARS:
        raise EventError("That image is too large — please use one under 5 MB.")
    attachment_id = await client.upload_attachment(
        filename=filename or "event-graphic",
        content_type=content_type,
        data_base64=data_base64,
        related_type=cfg.EVENT,
        field=cfg.GRAPHIC_FIELD,
    )
    await client.update(
        cfg.EVENT, event_id, {f"{cfg.GRAPHIC_FIELD}Id": attachment_id}
    )
    return await client.get(cfg.EVENT, event_id, select=cfg.PUBLIC_SELECT)


async def clear_event_graphic(client: EspoApi, event_id: str) -> dict[str, Any]:
    """Remove the graphic (clears the link; the Attachment itself stays, like
    any detached upload)."""
    await client.update(cfg.EVENT, event_id, {f"{cfg.GRAPHIC_FIELD}Id": None})
    return await client.get(cfg.EVENT, event_id, select=cfg.PUBLIC_SELECT)


async def get_event_graphic(
    client: EspoApi, event_id: str
) -> Optional[tuple[bytes, str]]:
    """The graphic's bytes + content type, or None when the event has none."""
    record = await client.get(
        cfg.EVENT, event_id, select=f"id,{cfg.GRAPHIC_FIELD}Id"
    )
    attachment_id = (record or {}).get(f"{cfg.GRAPHIC_FIELD}Id")
    if not attachment_id:
        return None
    return await client.download_attachment(attachment_id)


async def get_published_graphic(
    client: EspoApi, slug: str
) -> Optional[tuple[bytes, str]]:
    """The graphic for a PUBLISHED event, by slug — the public path.

    Goes through :func:`get_by_slug`, so the ``publishToWebsite`` gate applies:
    an internal calendar entry's image is no more reachable than its page. This
    is why the public route is keyed on the slug and not on an attachment id —
    an id-keyed endpoint would happily serve any attachment in the CRM,
    resumes included.
    """
    event = await get_by_slug(client, slug)
    if not event:
        return None
    attachment_id = event.get(f"{cfg.GRAPHIC_FIELD}Id")
    if not attachment_id:
        return None
    return await client.download_attachment(attachment_id)


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


# --- the portal calendar (F3 supplies it; F5 builds the surface) -------------


async def portal_calendar(
    client: EspoApi, user: dict[str, Any], *, now: Optional[datetime] = None
) -> list[dict[str, Any]]:
    """Upcoming events a signed-in member may see on the portal, soonest first.

    Internal events (to the member's teams, if limited) and this chapter's
    Public events (F3-8), all ticked, not cancelled and past their display time.
    ``client`` is the ORGANISATION-WIDE API key: a Standard User role reads
    events at "own" and would see an empty calendar, and the team limit is the
    application's to apply (design § 6).
    """
    moment = now or datetime.now(timezone.utc)
    fields = await live_event_fields(client)
    horizon = moment - timedelta(hours=2)
    where = visibility.public_where_clauses(fields, moment, surface=visibility.SURFACE_PORTAL)
    where.append({"type": "after", "attribute": "dateStart", "value": to_crm_datetime(horizon)})
    rows = await _all_events(
        client, select=cfg.PUBLIC_SELECT, where=where, order_by="dateStart", order="asc",
    )
    return [
        r for r in rows
        if visibility.is_shown(r, visibility.SURFACE_PORTAL, now=moment, user=user)
    ]


# --- Sponsorship: an event's partners and funders (Phase B) --------------------
# prds/mailing-list-and-event-sponsorship-plan.md § 5. Both links are
# relationships, so a ``*Ids`` write would be silently ignored — everything here
# goes through list_related / relate / unrelate (CLAUDE.md § Gotchas).


async def live_sponsor_links(client: EspoApi) -> tuple[cfg.EventLink, ...]:
    """Which sponsorship links the live CRM has, pointing where the spec says.

    Fails CLOSED: a client with no metadata reader, or a metadata read that
    fails, yields no links and the editor shows no pickers. Offering a picker
    whose save the CRM must refuse is worse than a missing one, and unlike the
    audience fields nothing public depends on this answer.
    """
    reader = getattr(client, "metadata", None)
    if reader is None:
        return ()
    try:
        links = await reader(f"entityDefs.{cfg.EVENT}.links") or {}
    except EspoError as exc:
        log.warning("event links not detectable (%s); sponsorship pickers stay dark", exc)
        return ()
    return tuple(
        link for link in cfg.SPONSOR_LINKS
        if isinstance(links.get(link.name), dict)
        and links[link.name].get("entity") == link.entity
    )


async def sponsor_options(
    client: EspoApi, link: cfg.EventLink
) -> Optional[list[dict[str, Any]]]:
    """The far entity's records for the picker — id and name, name order.

    Paged at 200 (an oversized page is a 403, not a truncation — the lesson of
    v0.198.0). A FORBIDDEN list degrades the picker to read-only, which is what
    ``None`` means to the caller: the role can edit events but cannot see
    partners, and the editor says so instead of offering an empty list.
    """
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        try:
            page = await client.list(
                link.entity, select="id,name", max_size=200, offset=offset,
            )
        except EspoError as exc:
            if is_forbidden(exc):
                log.info("%s list forbidden for the picker: %s", link.entity, exc)
                return None
            raise
        batch = page.get("list", [])
        rows.extend(
            {"id": r["id"], "name": r.get("name") or "(unnamed)"}
            for r in batch if r.get("id")
        )
        if len(batch) < 200 or offset >= 2000:
            break
        offset += 200
    rows.sort(key=lambda r: r["name"].lower())
    return rows


async def event_sponsors(
    client: EspoApi, event_id: str, links: Iterable[cfg.EventLink]
) -> dict[str, Optional[list[dict[str, Any]]]]:
    """The records on each live sponsorship link of one event.

    Best-effort per link: an unreadable link is ``None`` (rendered "—"), never
    an empty list — an empty slot reads as "no partners", which may be false.
    """
    out: dict[str, Optional[list[dict[str, Any]]]] = {}
    for link in links:
        try:
            data = await client.list_related(
                cfg.EVENT, event_id, link.name, select="id,name", max_size=200,
            )
            out[link.name] = [
                {"id": r["id"], "name": r.get("name") or "(unnamed)"}
                for r in data.get("list", []) if r.get("id")
            ]
        except EspoError as exc:
            log.warning("could not read %s of event %s: %s", link.name, event_id, exc)
            out[link.name] = None
    return out


async def _relate_or_escalate(
    client: EspoApi, admin_factory, op: str, event_id: str, link: str, related_id: str
) -> None:
    """relate/unrelate as the signed-in user, retrying ONLY a foreign-record
    denial as the provisioning admin.

    EspoCRM checks edit on BOTH sides of a link, and the Marketing Admin Role
    reads partner and funder profiles without editing them (Doug's ruling
    2026-10-07: ``read: all``, nothing more). The user's own edit access to
    the EVENT is the real gate and must pass on its own; only
    ``noAccessToForeignRecord`` — which by definition means the event half
    passed — is retried as the admin. The same shape as
    ``sessions.service._link_or_escalate``; duplicated because that one is
    bound to CEngagement.
    """
    try:
        await getattr(client, op)(cfg.EVENT, event_id, link, related_id)
        return
    except EspoError as exc:
        escalatable = is_forbidden(exc) and "noAccessToForeignRecord" in str(exc)
        if not escalatable or admin_factory is None:
            raise
        log.info(
            "%s %s/%s/%s denied on the linked record — retrying as the "
            "provisioning admin", op, cfg.EVENT, event_id, link,
        )
        try:
            admin = await admin_factory()
            await getattr(admin, op)(cfg.EVENT, event_id, link, related_id)
        except Exception as admin_exc:  # noqa: BLE001
            log.warning("admin fallback for %s also failed: %s", op, admin_exc)
            raise exc from None


async def set_event_sponsors(
    client: EspoApi,
    event_id: str,
    wanted: dict[str, list[str]],
    *,
    links: Iterable[cfg.EventLink],
    admin_factory=None,
) -> dict[str, dict[str, int]]:
    """Make each named live link hold exactly the ids given.

    The spec is the whitelist: a name that is not a live sponsorship link is
    ignored, never written. Missing ids are related, surplus ones unrelated;
    the rest are left alone, so re-saving an unchanged picker writes nothing.
    A refused write raises — the router turns it into the 403 that names the
    missing grant.
    """
    live = {link.name: link for link in links}
    result: dict[str, dict[str, int]] = {}
    for name, ids in wanted.items():
        if name not in live:
            continue
        current = await client.list_related(
            cfg.EVENT, event_id, name, select="id", max_size=200,
        )
        have = {r["id"] for r in current.get("list", []) if r.get("id")}
        want = {str(i) for i in (ids or []) if i}
        added = removed = 0
        for rid in sorted(want - have):
            await _relate_or_escalate(client, admin_factory, "relate", event_id, name, rid)
            added += 1
        for rid in sorted(have - want):
            await _relate_or_escalate(client, admin_factory, "unrelate", event_id, name, rid)
            removed += 1
        result[name] = {"added": added, "removed": removed}
    return result
