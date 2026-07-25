"""Events Phase 1 — the public read API.

The website is the consumer, so these tests are about the contract and the
blast radius of getting it wrong: the router must not exist when the feature is
off, unpublished events must be invisible, and a CRM outage must degrade
politely rather than leak internals.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from events import config as cfg
from forms import info_request

from tests.test_events_service import make_event


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeEspo:
    def __init__(self, events=None, registrations=None, fail=False):
        self.events = events or []
        self.registrations = registrations or []
        self.fail = fail

    async def list(self, entity, *, where=None, select=None, max_size=50,
                   offset=0, order_by=None, order=None):
        if self.fail:
            raise EspoError("CRM is down")
        rows = self.events if entity == cfg.EVENT else self.registrations
        # Honour the publish gate the way the CRM would, so "unpublished is
        # invisible" is genuinely exercised rather than assumed.
        if entity == cfg.EVENT and where:
            for clause in where:
                if clause.get("attribute") == "publishToWebsite":
                    rows = [r for r in rows if r.get("publishToWebsite")]
                if clause.get("type") == "notEquals" and clause.get("attribute") == "status":
                    rows = [r for r in rows if r.get("status") != clause["value"]]
                if clause.get("attribute") == "slug" and clause.get("type") == "equals":
                    rows = [r for r in rows if r.get("slug") == clause["value"]]
        return {"total": len(rows), "list": rows[offset: offset + max_size]}


def build(monkeypatch, *, events=None, registrations=None, fail=False,
          public_api=True, enabled=True, cache_seconds=0):
    monkeypatch.setenv("EVENTS_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("EVENTS_PUBLIC_API", "true" if public_api else "false")
    monkeypatch.setenv("ESPO_DRY_RUN", "false")
    monkeypatch.setenv("ESPO_BASE_URL", "https://crm.example.test")
    monkeypatch.setenv("ESPO_API_KEY", "k")
    # No caching by default: each test gets a clean read of its own fixture.
    monkeypatch.setenv("EVENTS_CACHE_SECONDS", str(cache_seconds))
    get_settings.cache_clear()
    app = create_app([info_request.SPEC])
    fake = FakeEspo(events=events, registrations=registrations, fail=fail)
    app.state.events_client_factory = lambda: fake
    return TestClient(app), fake


# --- mounting --------------------------------------------------------------


def test_endpoints_absent_when_the_public_api_is_off(monkeypatch):
    """An unconfigured deploy must expose nothing at all."""
    client, _ = build(monkeypatch, events=[make_event()], public_api=False)
    assert client.get("/api/events/upcoming").status_code == 404


def test_endpoints_absent_when_the_feature_is_off(monkeypatch):
    client, _ = build(monkeypatch, events=[make_event()], enabled=False)
    assert client.get("/api/events/upcoming").status_code == 404


# --- upcoming --------------------------------------------------------------


def test_upcoming_returns_the_existing_envelope(monkeypatch):
    client, _ = build(monkeypatch, events=[make_event()])
    body = client.get("/api/events/upcoming").json()
    assert body["success"] is True
    assert isinstance(body["webinars"], list)
    row = body["webinars"][0]
    assert row["topic"] == "Grant Writing Basics"   # title, per the contract
    assert row["webinarId"] == "89002896927"


def test_unpublished_events_never_appear(monkeypatch):
    """The 92 internal calendar rows must not reach the website."""
    client, _ = build(monkeypatch, events=[
        make_event(id="pub", name="Public Workshop", publishToWebsite=True),
        make_event(id="int", name="Operations/Team Meeting", publishToWebsite=False),
    ])
    titles = [r["topic"] for r in client.get("/api/events/upcoming").json()["webinars"]]
    assert titles == ["Public Workshop"]


def test_cancelled_events_never_appear(monkeypatch):
    client, _ = build(monkeypatch, events=[
        make_event(id="ok", name="Live One"),
        make_event(id="x", name="Called Off", status=cfg.STATUS_CANCELLED),
    ])
    titles = [r["topic"] for r in client.get("/api/events/upcoming").json()["webinars"]]
    assert titles == ["Live One"]


def test_seats_remaining_reflects_registrations(monkeypatch):
    client, _ = build(
        monkeypatch,
        events=[make_event(venueCapacity=10)],
        registrations=[{"attendanceStatus": "Registered"}] * 4,
    )
    row = client.get("/api/events/upcoming").json()["webinars"][0]
    assert row["seatsRemaining"] == 6


def test_no_capacity_means_unlimited_seats(monkeypatch):
    client, _ = build(monkeypatch, events=[make_event(venueCapacity=None)])
    row = client.get("/api/events/upcoming").json()["webinars"][0]
    assert row["seatsRemaining"] is None


def test_responses_are_marked_cacheable(monkeypatch):
    client, _ = build(monkeypatch, events=[make_event()], cache_seconds=60)
    resp = client.get("/api/events/upcoming")
    assert resp.headers.get("cache-control") == "public, max-age=60"


def test_repeat_requests_hit_the_cache_not_the_crm(monkeypatch):
    """A traffic burst must cost the CRM one query, not one per visitor."""
    from events.public import _cache
    _cache.clear()

    class Counting(FakeEspo):
        calls = 0

        async def list(self, *a, **kw):
            Counting.calls += 1
            return await super().list(*a, **kw)

    client, _ = build(monkeypatch, events=[make_event()], cache_seconds=60)
    client.app.state.events_client_factory = lambda: Counting(events=[make_event()])
    client.get("/api/events/upcoming")
    first = Counting.calls
    client.get("/api/events/upcoming")
    assert Counting.calls == first, "second request should have been served from cache"
    _cache.clear()


# --- recordings ------------------------------------------------------------


def test_recordings_list_and_search(monkeypatch):
    client, _ = build(monkeypatch, events=[
        make_event(id="a", name="Grant Writing Basics",
                   recordingUrl="https://youtu.be/dQw4w9WgXcQ"),
        make_event(id="b", name="Marketing 101",
                   recordingUrl="https://youtu.be/aaaaaaaaaaa"),
        make_event(id="c", name="No Recording Yet", recordingUrl=""),
    ])
    body = client.get("/api/events/recordings").json()
    assert [r["title"] for r in body["recordings"]] == [
        "Grant Writing Basics", "Marketing 101"]

    found = client.get("/api/events/recordings", params={"q": "grant"}).json()
    assert [r["title"] for r in found["recordings"]] == ["Grant Writing Basics"]
    assert found["query"] == "grant"


def test_recordings_limit_is_bounded(monkeypatch):
    client, _ = build(monkeypatch, events=[
        make_event(id=str(i), recordingUrl="https://youtu.be/dQw4w9WgXcQ")
        for i in range(5)
    ])
    body = client.get("/api/events/recordings", params={"limit": 2}).json()
    assert len(body["recordings"]) == 2
    # A silly limit must not blow up or return the world.
    assert client.get("/api/events/recordings", params={"limit": 99999}).status_code == 200
    assert client.get("/api/events/recordings", params={"limit": -3}).status_code == 200


# --- per-event page --------------------------------------------------------


def test_event_detail_by_slug(monkeypatch):
    client, _ = build(monkeypatch, events=[
        make_event(eventOverview="<p>Full description</p>")
    ])
    body = client.get("/api/events/grant-writing-basics").json()
    assert body["event"]["topic"] == "Grant Writing Basics"
    assert body["event"]["overview"] == "<p>Full description</p>"


def test_unknown_slug_is_404(monkeypatch):
    client, _ = build(monkeypatch, events=[make_event()])
    assert client.get("/api/events/nope").status_code == 404


def test_unpublished_event_page_is_404_not_a_leak(monkeypatch):
    """Guessing an internal meeting's URL must not reveal it."""
    client, _ = build(monkeypatch, events=[
        make_event(slug="ops-team-meeting", name="Operations/Team Meeting",
                   publishToWebsite=False)
    ])
    resp = client.get("/api/events/ops-team-meeting")
    assert resp.status_code == 404
    assert "Operations" not in resp.text


# --- failure behaviour -----------------------------------------------------


def test_crm_outage_returns_a_plain_502_without_leaking_details(monkeypatch):
    """The WordPress plugin serves its cached copy on failure (EV-07); our job
    is to fail plainly and not expose CRM internals to the public."""
    client, _ = build(monkeypatch, events=[make_event()], fail=True)
    resp = client.get("/api/events/upcoming")
    assert resp.status_code == 502
    assert "CRM is down" not in resp.text
    assert "temporarily unavailable" in resp.json()["detail"]
