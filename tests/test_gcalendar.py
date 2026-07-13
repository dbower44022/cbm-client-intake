"""core.gcalendar — pure helpers + request shapes (no real Google calls)."""

from __future__ import annotations

import pytest

from core.gcalendar import (
    CalendarClient,
    CalendarError,
    build_event_body,
    event_times,
    meet_link,
)


# --- event_times -------------------------------------------------------------

def test_event_times_utc_rfc3339():
    start, end = event_times("2026-07-15 19:30:00", "2026-07-15 20:30:00")
    assert start == {"dateTime": "2026-07-15T19:30:00Z"}
    assert end == {"dateTime": "2026-07-15T20:30:00Z"}


def test_event_times_missing_end_defaults_to_one_hour():
    start, end = event_times("2026-07-15 19:30:00", None)
    assert end == {"dateTime": "2026-07-15T20:30:00Z"}
    _, end = event_times("2026-07-15 23:30:00", "  ")
    assert end == {"dateTime": "2026-07-16T00:30:00Z"}  # rolls the day


def test_event_times_end_before_start_defaults_to_one_hour():
    _, end = event_times("2026-07-15 19:30:00", "2026-07-15 19:00:00")
    assert end == {"dateTime": "2026-07-15T20:30:00Z"}


def test_event_times_bad_start_raises():
    with pytest.raises(CalendarError):
        event_times("not a date", None)
    with pytest.raises(CalendarError):
        event_times("", None)


# --- build_event_body ---------------------------------------------------------

def test_build_event_body_with_meet():
    body = build_event_body(
        summary="Session",
        description="Engagement: Agape",
        date_start="2026-07-15 19:30:00",
        date_end="2026-07-15 20:30:00",
        attendee_emails=["a@x.com", "b@y.com"],
        request_id="cbm-s1-abc",
    )
    assert body["summary"] == "Session"
    assert body["attendees"] == [{"email": "a@x.com"}, {"email": "b@y.com"}]
    cr = body["conferenceData"]["createRequest"]
    assert cr["requestId"] == "cbm-s1-abc"
    assert cr["conferenceSolutionKey"] == {"type": "hangoutsMeet"}
    assert "location" not in body


def test_build_event_body_external_link_no_conference():
    body = build_event_body(
        summary="Session",
        description="Engagement: Agape",
        date_start="2026-07-15 19:30:00",
        date_end=None,
        attendee_emails=[],
        external_link="https://zoom.us/j/123",
    )
    assert "conferenceData" not in body
    assert body["location"] == "https://zoom.us/j/123"
    assert "Join: https://zoom.us/j/123" in body["description"]


# --- meet_link ----------------------------------------------------------------

def test_meet_link_prefers_hangout_link():
    assert meet_link({"hangoutLink": "https://meet.google.com/abc"}) == "https://meet.google.com/abc"


def test_meet_link_entrypoints_fallback():
    event = {
        "conferenceData": {
            "entryPoints": [
                {"entryPointType": "phone", "uri": "tel:+1"},
                {"entryPointType": "video", "uri": "https://meet.google.com/xyz"},
            ]
        }
    }
    assert meet_link(event) == "https://meet.google.com/xyz"


def test_meet_link_missing():
    assert meet_link({}) == ""
    assert meet_link({"conferenceData": {"entryPoints": []}}) == ""


# --- CalendarClient request shapes ---------------------------------------------

class _Recorder:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or [{}]

    async def __call__(self, method, path, *, params=None, json_body=None, ok_statuses=()):
        self.calls.append({
            "method": method, "path": path, "params": params,
            "json_body": json_body, "ok_statuses": ok_statuses,
        })
        return self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]


def _client(monkeypatch, recorder):
    client = CalendarClient({"client_email": "sa@x"}, "mgr@cbmentors.org")
    monkeypatch.setattr(client, "_request", recorder)
    return client


async def test_create_event_params(monkeypatch):
    rec = _Recorder([{"id": "ev1", "hangoutLink": "https://meet.google.com/a"}])
    client = _client(monkeypatch, rec)
    event = await client.create_event({"summary": "s"})
    assert event["id"] == "ev1"
    call = rec.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/calendars/primary/events"
    assert call["params"] == {"sendUpdates": "all", "conferenceDataVersion": 1}


async def test_patch_event_params(monkeypatch):
    rec = _Recorder()
    client = _client(monkeypatch, rec)
    await client.patch_event("ev1", {"summary": "s2"})
    call = rec.calls[0]
    assert call["method"] == "PATCH"
    assert call["path"] == "/calendars/primary/events/ev1"
    assert call["params"] == {"sendUpdates": "all", "conferenceDataVersion": 1}


async def test_delete_event_tolerates_gone(monkeypatch):
    rec = _Recorder()
    client = _client(monkeypatch, rec)
    await client.delete_event("ev1")
    call = rec.calls[0]
    assert call["method"] == "DELETE"
    assert call["params"] == {"sendUpdates": "all"}
    assert set(call["ok_statuses"]) == {404, 410}
