"""Events Phase 1 — the CRM read/derive layer.

Covers the things that would silently corrupt the public page if wrong:
timezone handling, the publish gate, slug collisions, derived counts, and the
key-name compatibility contract.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.youtube import thumbnail_url, video_id_from_url
from events import config as cfg
from events import service


# --- fixtures --------------------------------------------------------------


def make_event(**over):
    event = {
        "id": "ev1",
        "name": "Grant Writing Basics",
        "slug": "grant-writing-basics",
        "description": "Demystifying the dollar signs.",
        # 2026-07-28 18:00 UTC == 2:00 PM Cleveland (EDT)
        "dateStart": "2026-07-28 18:00:00",
        "dateEnd": "2026-07-28 19:30:00",
        "duration": 5400,
        "status": cfg.STATUS_PLANNED,
        "format": cfg.FORMAT_VIRTUAL,
        "eventType": "Online Webinar",
        "topic": "Finance & Accounting",
        "location": "",
        "venueCapacity": None,
        "publishToWebsite": True,
        "registrationCloses": None,
        "recordingUrl": "",
        "zoomWebinarId": "89002896927",
    }
    event.update(over)
    return event


class FakeEspo:
    """Records the queries it is asked to run, so tests can assert on filters."""

    def __init__(self, events=None, registrations=None):
        self.events = events or []
        self.registrations = registrations or []
        self.queries: list[tuple[str, list]] = []

    async def list(self, entity, *, where=None, select=None, max_size=50,
                   offset=0, order_by=None, order=None):
        self.queries.append((entity, where or []))
        rows = self.events if entity == cfg.EVENT else self.registrations
        page = rows[offset: offset + max_size]
        return {"total": len(rows), "list": page}


# --- timezone --------------------------------------------------------------


def test_crm_datetimes_are_utc_not_local():
    """The API returns naive strings that are ALWAYS UTC. Reading them as local
    shifted every session by 4-5 hours once already (v0.39.2)."""
    parsed = service.parse_crm_datetime("2026-07-28 18:00:00")
    assert parsed == datetime(2026, 7, 28, 18, 0, tzinfo=timezone.utc)
    assert service.to_local(parsed).hour == 14  # 2 PM Cleveland


def test_public_payload_formats_local_display_strings():
    payload = service.public_event(make_event())
    assert payload["date"] == "2026-07-28"
    assert payload["month"] == "July 2026"
    assert payload["monthShort"] == "Jul"
    assert payload["day"] == "28"
    # The live page's exact band format.
    assert payload["time"] == "2:00 PM - 3:30 PM | WEBINAR"
    assert payload["durationHrs"] == 1.5
    assert payload["startsAtUtc"].startswith("2026-07-28T18:00")


def test_parse_handles_junk_without_raising():
    assert service.parse_crm_datetime(None) is None
    assert service.parse_crm_datetime("") is None
    assert service.parse_crm_datetime("not a date") is None


# --- the compatibility contract -------------------------------------------


def test_topic_is_the_title_and_category_is_separate():
    """`topic` means the TITLE in the payload (Zoom/Apps-Script vocabulary);
    the CRM's subject category rides as `category`. Swapping these would blank
    every title on the live site."""
    payload = service.public_event(make_event())
    assert payload["topic"] == "Grant Writing Basics"
    assert payload["category"] == "Finance & Accounting"


def test_payload_carries_every_key_the_page_uses_today():
    payload = service.public_event(make_event())
    for key in ("topic", "summary", "date", "month", "monthShort", "day",
                "time", "durationHrs", "webinarId"):
        assert key in payload, f"missing existing-contract key {key}"


def test_payload_carries_no_registrant_data():
    """EV-82: public responses expose event facts and a seat count, never who
    registered."""
    payload = service.public_event(make_event(venueCapacity=50), seats_left=12)
    leaky = {"email", "firstName", "lastName", "registrations", "contacts",
             "attendees", "registered"}
    assert not (leaky & set(payload)), f"public payload leaks {leaky & set(payload)}"
    assert payload["seatsRemaining"] == 12


def test_event_url_uses_the_slug():
    payload = service.public_event(make_event(), base_url="https://x.org/webinars/")
    assert payload["url"] == "https://x.org/webinars/grant-writing-basics"


# --- the publish gate ------------------------------------------------------


async def test_public_reads_always_filter_on_publish_and_cancelled():
    """CEvent doubles as the org calendar (92 internal meetings). Every public
    query must exclude unpublished and cancelled rows."""
    fake = FakeEspo(events=[make_event()])
    await service.list_upcoming(fake, now=datetime(2026, 7, 1, tzinfo=timezone.utc))
    _, where = fake.queries[0]
    assert {"type": "isTrue", "attribute": "publishToWebsite"} in where
    assert {"type": "notEquals", "attribute": "status",
            "value": cfg.STATUS_CANCELLED} in where


async def test_get_by_slug_also_applies_the_publish_gate():
    fake = FakeEspo(events=[make_event()])
    await service.get_by_slug(fake, "grant-writing-basics")
    _, where = fake.queries[0]
    assert {"type": "isTrue", "attribute": "publishToWebsite"} in where


async def test_get_by_slug_missing_returns_none():
    assert await service.get_by_slug(FakeEspo(events=[]), "nope") is None
    assert await service.get_by_slug(FakeEspo(events=[]), "") is None


# --- recordings ------------------------------------------------------------


async def test_recordings_require_a_recording_url():
    fake = FakeEspo(events=[
        make_event(id="a", recordingUrl="https://youtu.be/abcdefghijk"),
        make_event(id="b", recordingUrl=""),
        make_event(id="c", recordingUrl="   "),
    ])
    rows = await service.list_recordings(fake)
    assert [r["id"] for r in rows] == ["a"]


async def test_recording_search_matches_title_summary_and_category():
    fake = FakeEspo(events=[
        make_event(id="a", name="Grant Writing Basics",
                   recordingUrl="https://youtu.be/abcdefghijk"),
        make_event(id="b", name="Marketing 101", description="Selling online",
                   topic="Marketing & Sales",
                   recordingUrl="https://youtu.be/bbcdefghijk"),
    ])
    assert [r["id"] for r in await service.list_recordings(fake, query="grant")] == ["a"]
    assert [r["id"] for r in await service.list_recordings(fake, query="selling")] == ["b"]
    assert [r["id"] for r in await service.list_recordings(fake, query="marketing &")] == ["b"]
    assert len(await service.list_recordings(fake, query="")) == 2


def test_recording_row_derives_thumbnail_without_an_api_key():
    row = service.public_recording(
        make_event(recordingUrl="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    )
    assert row["videoId"] == "dQw4w9WgXcQ"
    assert row["thumbnailUrl"] == "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
    assert row["dateLabel"] == "JUL 28, 2026"


# --- slugs -----------------------------------------------------------------


@pytest.mark.parametrize("name,expected", [
    ("Grant Writing Basics", "grant-writing-basics"),
    ("Is Starting a Nonprofit Right For You?", "is-starting-a-nonprofit-right-for-you"),
    ("Marketing & Sales: 101", "marketing-sales-101"),
    ("  spaced  out  ", "spaced-out"),
    ("Café Résumé", "cafe-resume"),
    ("", "event"),
    ("!!!", "event"),
])
def test_slugify(name, expected):
    assert service.slugify(name) == expected


def test_unique_slug_suffixes_on_collision():
    assert service.unique_slug("Grant Writing", set()) == "grant-writing"
    assert service.unique_slug("Grant Writing", {"grant-writing"}) == "grant-writing-2"
    assert service.unique_slug(
        "Grant Writing", {"grant-writing", "grant-writing-2"}
    ) == "grant-writing-3"


# --- derived counts --------------------------------------------------------


def test_summarise_counts_each_state():
    rows = [
        {"attendanceStatus": "Registered"},
        {"attendanceStatus": "Attended", "minutesAttended": 60},
        {"attendanceStatus": "Attended", "minutesAttended": 30},
        {"attendanceStatus": "No-Show"},
        {"attendanceStatus": "Cancelled"},
        {"attendanceStatus": "Waitlisted"},
    ]
    summary = service.summarise(rows)
    # Attended and No-Show were registrations too - they occupied a seat.
    assert summary["registered"] == 4
    assert summary["attended"] == 2
    assert summary["noShow"] == 1
    assert summary["cancelled"] == 1
    assert summary["waitlisted"] == 1
    assert summary["showRate"] == pytest.approx(2 / 3, abs=0.001)
    assert summary["averageMinutes"] == 45


def test_show_rate_is_none_when_nothing_is_resolved_yet():
    summary = service.summarise([{"attendanceStatus": "Registered"}])
    assert summary["showRate"] is None
    assert summary["averageMinutes"] is None


def test_summarise_on_an_empty_event():
    summary = service.summarise([])
    assert summary["registered"] == 0
    assert summary["showRate"] is None
    assert summary["seatsRemaining"] is None


@pytest.mark.parametrize("capacity,taken,expected", [
    (None, 5, None),   # unlimited
    (0, 5, None),      # zero means unlimited, NOT full
    (10, 3, 7),
    (10, 10, 0),
    (10, 15, 0),       # never negative
])
def test_seats_remaining(capacity, taken, expected):
    assert service.seats_remaining(capacity, taken) == expected


# --- registration open/closed ---------------------------------------------


NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)  # 8 AM Cleveland


def test_registration_open_before_start():
    assert service.registration_open(make_event(), now=NOW) is True


def test_registration_closes_at_start_by_default():
    late = datetime(2026, 7, 28, 18, 30, tzinfo=timezone.utc)
    assert service.registration_open(make_event(), now=late) is False


def test_explicit_registration_close_time_wins():
    event = make_event(registrationCloses="2026-07-28 10:00:00")
    assert service.registration_open(event, now=NOW) is False


def test_cancelled_event_is_closed():
    assert service.registration_open(
        make_event(status=cfg.STATUS_CANCELLED), now=NOW) is False


def test_full_event_is_closed():
    assert service.registration_open(make_event(), now=NOW, seats_left=0) is False
    assert service.registration_open(make_event(), now=NOW, seats_left=3) is True


# --- youtube helpers -------------------------------------------------------


@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://youtube.com/watch?v=dQw4w9WgXcQ&t=42", "dQw4w9WgXcQ"),
    ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://vimeo.com/12345", None),
    ("", None),
    ("not a url", None),
])
def test_video_id_from_url(url, expected):
    assert video_id_from_url(url) == expected


def test_thumbnail_url_rejects_junk():
    assert thumbnail_url("") is None
    assert thumbnail_url("short") is None
