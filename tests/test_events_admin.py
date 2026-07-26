"""Events Phase 5 — the /events staff app.

Focused on the boundaries: who may reach it, what a save is allowed to write,
and the writes that would corrupt data if they misbehaved.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from events import config as cfg
from events import service
from forms import ALL_SPECS

from tests.test_events_registration import FakeCrm, NoZoom
from tests.test_events_service import make_event

MARKETING = {"userName": "marcus", "name": "Marcus Admin", "userId": "u-1",
             "token": "t", "isAdmin": False, "teams": ["Marketing Admin Team"]}
OUTSIDER = {"userName": "nobody", "name": "No Body", "userId": "u-2",
            "token": "t", "isAdmin": False, "teams": ["Mentor Team"]}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def build(monkeypatch, user=None, crm=None):
    monkeypatch.setenv("EVENTS_ENABLED", "true")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ESPO_DRY_RUN", "true")
    get_settings.cache_clear()
    app = create_app(ALL_SPECS)

    import events.router as router_mod
    monkeypatch.setattr(router_mod, "current_user", lambda request: user)
    if crm is not None:
        monkeypatch.setattr(router_mod, "client_for", lambda settings, u: crm)
    # The action log writes a stream note + reporting row; irrelevant here and
    # it would reach for a real CRM.
    async def _no_log(*a, **kw):
        return None
    monkeypatch.setattr(router_mod, "record_action", _no_log)
    return TestClient(app)


# --- the gate --------------------------------------------------------------


def test_signed_out_is_401(monkeypatch):
    client = build(monkeypatch, user=None)
    assert client.get("/events/api/session").status_code == 401


def test_wrong_team_is_403_naming_the_team(monkeypatch):
    client = build(monkeypatch, user=OUTSIDER)
    resp = client.get("/events/api/session")
    assert resp.status_code == 403
    assert "Marketing Admin Team" in resp.json()["detail"]


def test_marketing_admin_gets_in(monkeypatch):
    client = build(monkeypatch, user=MARKETING, crm=FakeCrm())
    body = client.get("/events/api/session").json()
    assert body["name"] == "Marcus Admin"
    assert body["zoomEnabled"] is False   # no Zoom credentials in tests


def test_app_absent_when_the_feature_is_off(monkeypatch):
    monkeypatch.setenv("EVENTS_ENABLED", "false")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()
    app = create_app(ALL_SPECS)
    assert TestClient(app).get("/events/api/session").status_code == 404


# --- the write whitelist ---------------------------------------------------


def test_create_rejects_a_missing_title(monkeypatch):
    client = build(monkeypatch, user=MARKETING, crm=FakeCrm())
    resp = client.post("/events/api/events", json={"changes": {"name": "  "}})
    assert resp.status_code == 400
    assert "title" in resp.json()["detail"]


async def test_create_assigns_a_slug():
    crm = FakeCrm(events=[])
    event = await service.create_event(crm, {"name": "Grant Writing Basics"})
    assert event["slug"] == "grant-writing-basics"


async def test_create_avoids_a_slug_collision():
    crm = FakeCrm(events=[make_event(slug="grant-writing-basics")])
    event = await service.create_event(crm, {"name": "Grant Writing Basics"})
    assert event["slug"] == "grant-writing-basics-2"


async def test_smuggled_fields_are_dropped():
    """The field spec IS the whitelist: an invented or app-managed attribute
    must never reach the CRM."""
    crm = FakeCrm(events=[])
    await service.create_event(crm, {
        "name": "Legit", "venueCapacity": 40,
        "zoomWebinarId": "999999",        # app-managed
        "createdById": "hacker",          # not in the spec at all
        "publishToWebsite": True,
    })
    _, payload = crm.created[0]
    assert payload["venueCapacity"] == 40
    assert "createdById" not in payload
    assert payload.get("zoomWebinarId") != "999999"


async def test_update_backfills_a_missing_slug():
    crm = FakeCrm(events=[make_event(id="ev1", slug="")])
    event = await service.update_event(crm, "ev1", {"name": "Renamed Event"})
    assert event["slug"] == "renamed-event"


async def test_update_keeps_an_existing_slug_stable():
    """A published URL must not move because someone fixed a typo in the
    title — that would break every link already shared."""
    crm = FakeCrm(events=[make_event(id="ev1", slug="grant-writing-basics")])
    event = await service.update_event(crm, "ev1", {"name": "Grant Writing Basics 2026"})
    assert event["slug"] == "grant-writing-basics"


# --- recordings ------------------------------------------------------------


async def test_recording_url_must_look_like_youtube():
    crm = FakeCrm(events=[make_event(id="ev1")])
    with pytest.raises(service.EventError, match="YouTube"):
        await service.set_recording(crm, "ev1", "https://example.com/video")


async def test_recording_can_be_cleared():
    crm = FakeCrm(events=[make_event(id="ev1", recordingUrl="https://youtu.be/dQw4w9WgXcQ")])
    await service.set_recording(crm, "ev1", "")
    assert crm.updated[-1][2]["recordingUrl"] == ""


# --- attendance ------------------------------------------------------------


async def test_manual_attendance_is_marked_as_manual():
    """attendanceSource=Manual is what stops the automatic Zoom pull (Phase 6)
    from overwriting a human's correction."""
    crm = FakeCrm(registrations=[{"id": "r1", "eventId": "ev1",
                                  "attendanceStatus": "Registered"}])
    await service.set_attendance(crm, "r1", cfg.REG_ATTENDED, minutes=45)
    payload = crm.updated[-1][2]
    assert payload["attendanceStatus"] == "Attended"
    assert payload["attendanceSource"] == "Manual"
    assert payload["minutesAttended"] == 45


async def test_an_invented_attendance_status_is_refused():
    crm = FakeCrm(registrations=[{"id": "r1", "eventId": "ev1"}])
    with pytest.raises(service.EventError):
        await service.set_attendance(crm, "r1", "Maybe")


async def test_check_in_stamps_arrival():
    crm = FakeCrm(registrations=[{"id": "r1", "eventId": "ev1",
                                  "attendanceStatus": "Registered"}])
    await service.check_in(crm, "r1")
    payload = crm.updated[-1][2]
    assert payload["attendanceStatus"] == "Attended"
    assert payload["attendanceSource"] == "Check-in"
    assert payload["joinTime"]


# --- staff-added registrants ----------------------------------------------


async def test_walk_in_creates_a_contact_like_the_public_form():
    """A walk-in is a lead, not a name on a list."""
    crm = FakeCrm(events=[make_event(id="ev1")])
    await service.add_registrant(
        crm, "ev1", first_name="Ada", last_name="Lovelace",
        email="ada@example.com", source=cfg.SOURCE_WALK_IN, status=cfg.REG_ATTENDED,
    )
    contact = [p for e, p in crm.created if e == "Contact"][0]
    assert contact["cContactType"] == ["Prospect"]
    registration = [p for e, p in crm.created if e == cfg.REGISTRATION][0]
    assert registration["registrationSource"] == cfg.SOURCE_WALK_IN
    assert registration["attendanceStatus"] == cfg.REG_ATTENDED


async def test_a_registrant_without_an_email_still_records():
    """People do turn up without giving an address; the roster must not refuse
    them just because no Contact can be made."""
    crm = FakeCrm(events=[make_event(id="ev1")])
    await service.add_registrant(crm, "ev1", first_name="Walk", last_name="In")
    registration = [p for e, p in crm.created if e == cfg.REGISTRATION][0]
    assert "contactId" not in registration
    assert not [p for e, p in crm.created if e == "Contact"]


async def test_a_nameless_registrant_is_refused():
    crm = FakeCrm(events=[make_event(id="ev1")])
    with pytest.raises(service.EventError, match="name"):
        await service.add_registrant(crm, "ev1", first_name="   ")


# --- the staff grid --------------------------------------------------------


async def test_the_staff_grid_shows_unpublished_events_too():
    """Staff need to see internal calendar rows — if only to notice one that
    has been wrongly published."""
    crm = FakeCrm(events=[
        make_event(id="a", name="Public Workshop", publishToWebsite=True),
        make_event(id="b", name="Operations/Team Meeting", publishToWebsite=False),
    ])
    rows = await service.list_events(crm)
    assert {r["name"] for r in rows} == {"Public Workshop", "Operations/Team Meeting"}
