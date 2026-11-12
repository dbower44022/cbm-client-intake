"""Events Phase 5 — the /events staff app.

Focused on the boundaries: who may reach it, what a save is allowed to write,
and the writes that would corrupt data if they misbehaved.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from events import config as cfg
from events import service
from forms import ALL_SPECS

from tests.test_events_registration import FakeCrm, NoZoom
from tests.test_events_service import make_event

ROOT = Path(__file__).resolve().parents[1]

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


# --- the Needs review filter -------------------------------------------------


def _events_app_js() -> str:
    from pathlib import Path

    return (
        Path(__file__).resolve().parents[1] / "events" / "frontend" / "app.js"
    ).read_text(encoding="utf-8")


def test_the_grid_offers_a_needs_review_scope():
    """The import creates events UNPUBLISHED so a person can check the date, and
    the grid opened on "Published to the website" — hiding every one of them, so
    an import looked like it had done nothing. Found live on 2026-09-13 when ten
    imported recordings were reported missing."""
    from pathlib import Path

    html = (
        Path(__file__).resolve().parents[1] / "events" / "frontend" / "index.html"
    ).read_text(encoding="utf-8")
    assert '<option value="review">Needs review</option>' in html
    js = _events_app_js()
    assert 'state.scope === "review"' in js
    assert "function needsReview(e)" in js


def test_needs_review_means_unpublished_with_a_recording():
    """Precision is what makes the automatic switch safe. That entity doubles as
    the organisation's internal calendar, and a team meeting has no recording
    link — so this can never land the grid on ninety internal meetings."""
    js = _events_app_js()
    assert "return !e.publishToWebsite && !!e.recordingUrl;" in js


def test_the_grid_opens_on_the_work_but_yields_to_the_user():
    """Switch once, and never yank someone back out of the view they chose."""
    js = _events_app_js()
    assert "if (!state.scopeChosen && state.events.some(needsReview))" in js
    assert "state.scopeChosen = true;" in js
    assert "scopeChosen: false," in js


# --- an unset enum is null, not "" (found live 2026-09-14) -------------------


def test_an_empty_enum_is_sent_as_null_not_empty_string():
    """The editor posts every field, not only the changed ones, so an event with
    no topic sends `topic: ""`. EspoCRM's topic enum has no empty option and
    answers 400 Field validation failure.

    Found in production: publishing an imported recording failed every time and
    only worked once a topic was chosen too — because that replaced the empty
    string with a real option. Publishing was never the problem; the empty enum
    riding along with it was."""
    from events.service import _blank_enums_to_null

    out = _blank_enums_to_null(
        {"topic": "", "eventType": "", "format": "", "name": "", "location": ""}
    )
    assert out["topic"] is None
    assert out["eventType"] is None
    assert out["format"] is None
    # Only enums. An empty text field is a legitimate "cleared this".
    assert out["name"] == ""
    assert out["location"] == ""


def test_a_real_enum_value_passes_through():
    from events.service import _blank_enums_to_null

    out = _blank_enums_to_null({"topic": "Operations", "format": "Virtual"})
    assert out == {"topic": "Operations", "format": "Virtual"}


def test_every_enum_in_the_spec_is_covered():
    """The list is derived from the one field spec that also drives the form, so
    a new enum field cannot be forgotten here."""
    from events import config as cfg
    from events.service import _ENUM_FIELD_NAMES

    assert _ENUM_FIELD_NAMES == frozenset(
        f.name for f in cfg.EVENT_FIELDS if f.type == "enum"
    )
    assert "topic" in _ENUM_FIELD_NAMES


def test_a_rejected_field_reads_as_a_message_not_an_outage():
    """A 400 naming a field is the user's to fix. Mapping it to 502 told them
    the CRM was unavailable — wrong, and nothing they could act on."""
    from core.espo import EspoError, validation_failure

    exc = EspoError(
        "update CEvent/6aa7f859056d868f5 failed: HTTP 400 "
        "[Field validation failure; entityType: CEvent, field: topic, type: valid.]"
    )
    message = validation_failure(exc)
    assert message and "topic" in message
    assert "unavailable" not in message.lower()

    # Anything that is not a 400 is left to the existing handling.
    assert validation_failure(EspoError("read CEvent failed: HTTP 403 [Forbidden]")) is None
    assert validation_failure(EspoError("read CEvent failed: HTTP 500 [Boom]")) is None


# --- the editor survives a field the CRM does not have (production, 2026-10-01) ---

@pytest.mark.asyncio
async def test_field_options_survive_a_field_the_crm_lacks():
    """``/events/api/fields`` 500'd on production because the F2/F3 enum fields
    do not exist there yet and the metadata read raised a non-EspoError. A
    missing field yields an empty list; the rest of the editor still loads."""
    from events import service

    class Crm:
        async def metadata_enum_options(self, entity, field):
            if field in ("audience", "publicReach", "reachChapters", "internalTeams"):
                raise ValueError("Expecting value: line 1 column 1 (char 0)")
            return ["A", "B"]

    options = await service.field_options(Crm())
    assert options["audience"] == []
    assert options["topic"] == ["A", "B"]


# --- the Join URL: editable for Internal events only (D3, OPEN-ITEMS #38) ----

from tests.test_events_visibility import MetaEspo  # noqa: E402


class EditEspo(MetaEspo):
    """MetaEspo whose ``get`` answers with the stored event, so an update can
    be judged against the record as the CRM holds it."""

    async def get(self, entity, record_id, select=None):
        for row in self.events:
            if row.get("id") == record_id:
                return dict(row)
        return await super().get(entity, record_id, select)


MEET = "https://meet.google.com/abc-defg-hij"


def test_join_url_is_app_managed_but_unlocked_for_internal_events():
    spec = next(f for f in cfg.EVENT_FIELDS if f.name == "virtualMeetingUrl")
    assert spec.app_managed
    assert cfg.rules_of(spec.editable_when) == (
        ("audience", ("Internal",)), ("hostedBy", ("Outside host",)))
    assert "virtualMeetingUrl" not in cfg.EVENT_EDIT_NAMES
    assert cfg.EVENT_CONDITIONAL_EDITS == {"virtualMeetingUrl": (
        ("audience", ("Internal",)), ("hostedBy", ("Outside host",)))}


async def test_internal_event_takes_a_typed_join_url():
    crm = EditEspo([make_event(id="ev1", audience="Internal")])
    await service.update_event(crm, "ev1", {"virtualMeetingUrl": MEET})
    assert crm.updated[-1]["virtualMeetingUrl"] == MEET


async def test_public_event_keeps_zooms_join_url():
    """The editor posts every field back, so a Public event's Join URL rides
    the save unchanged — and must be dropped, not written over Zoom's."""
    zoom_url = "https://zoom.us/j/999"
    crm = EditEspo([make_event(id="ev1", audience="Public", virtualMeetingUrl=zoom_url)])
    await service.update_event(crm, "ev1", {"name": "Renamed",
                                            "virtualMeetingUrl": MEET})
    assert crm.updated[-1]["name"] == "Renamed"
    assert "virtualMeetingUrl" not in crm.updated[-1]


async def test_turning_internal_in_the_same_save_unlocks_the_join_url():
    crm = EditEspo([make_event(id="ev1", audience="Public")])
    await service.update_event(crm, "ev1", {"audience": "Internal",
                                            "virtualMeetingUrl": MEET})
    assert crm.updated[-1]["virtualMeetingUrl"] == MEET


async def test_turning_public_in_the_same_save_locks_it_again():
    crm = EditEspo([make_event(id="ev1", audience="Internal", virtualMeetingUrl=MEET)])
    await service.update_event(crm, "ev1", {"audience": "Public",
                                            "virtualMeetingUrl": "https://x.example/typed"})
    assert "virtualMeetingUrl" not in crm.updated[-1]


async def test_a_crm_without_the_audience_field_unlocks_nothing():
    """Before F2/F3 every event is the public programme's: nothing to unlock."""
    crm = EditEspo([make_event(id="ev1")], fields=())
    await service.update_event(crm, "ev1", {"virtualMeetingUrl": MEET})
    assert crm.updated == []   # nothing left to write


async def test_create_accepts_a_join_url_for_an_internal_event():
    crm = MetaEspo([])
    await service.create_event(crm, {"name": "Team Meeting", "audience": "Internal",
                                     "virtualMeetingUrl": MEET}, chapter_key="cleveland")
    assert crm.created[-1]["virtualMeetingUrl"] == MEET


def test_session_payload_carries_the_unlock_rule(monkeypatch):
    client = build(monkeypatch, user=MARKETING, crm=MetaEspo([]))
    fields = {f["name"]: f for f in client.get("/events/api/fields").json()["fields"]}
    assert fields["virtualMeetingUrl"]["appManaged"] is True
    # The CRM fake lacks hostedBy, but the rule rides along; the server
    # ignores a rule whose field the CRM does not have.
    assert fields["virtualMeetingUrl"]["editableWhen"] == [
        {"field": "audience", "values": ["Internal"]},
        {"field": "hostedBy", "values": ["Outside host"]}]
    assert fields["publicReach"]["showWhen"] == [
        {"field": "audience", "values": ["Public"]}]


def test_editor_renders_a_conditionally_editable_field():
    """The editor skips app-managed fields; one carrying editableWhen must get
    a control, shown under its rule."""
    source = (ROOT / "events" / "frontend" / "app.js").read_text()
    assert "!spec.editableWhen" in source
    assert "spec.showWhen ? { all: spec.showWhen }" in source
    assert "{ any: spec.editableWhen }" in source


# --- An event run by an outside host (rulings D3-3 and D3-4, OPEN-ITEMS #80) --

HOSTED = cfg.AUDIENCE_FIELDS + cfg.HOSTING_FIELDS
HOST_LINK = "https://partner.example/webinar/register"


class HostedEspo(EditEspo):
    """EditEspo on a CRM with ``hostedBy``, whose registrations can be set."""

    def __init__(self, events, registrations=()):
        super().__init__(events, fields=HOSTED)
        self.registrations = list(registrations)

    async def list(self, entity, *, where=None, select=None, max_size=50,
                   offset=0, order_by=None, order=None):
        if entity == cfg.REGISTRATION:
            return {"total": len(self.registrations), "list": self.registrations}
        return await super().list(entity, where=where, select=select,
                                  max_size=max_size, offset=offset,
                                  order_by=order_by, order=order)


def public_online(**over):
    base = dict(id="ev1", audience="Public", format=cfg.FORMAT_HYBRID,
                virtualMeetingUrl="")
    base.update(over)
    return make_event(**base)


async def test_outside_host_takes_a_typed_link():
    crm = HostedEspo([public_online()])
    await service.update_event(crm, "ev1", {"hostedBy": "Outside host",
                                            "virtualMeetingUrl": HOST_LINK})
    assert crm.updated[-1]["virtualMeetingUrl"] == HOST_LINK
    assert crm.updated[-1]["hostedBy"] == "Outside host"


async def test_cbm_zoom_event_still_drops_a_typed_link():
    crm = HostedEspo([public_online(hostedBy="CBM Zoom")])
    await service.update_event(crm, "ev1", {"name": "Renamed",
                                            "virtualMeetingUrl": HOST_LINK})
    assert "virtualMeetingUrl" not in crm.updated[-1]


async def test_a_crm_without_hosted_by_ignores_the_choice():
    """Before the CRM change, the choice is dropped and the link stays Zoom's."""
    crm = EditEspo([public_online()])
    await service.update_event(crm, "ev1", {"name": "Renamed",
                                            "hostedBy": "Outside host",
                                            "virtualMeetingUrl": HOST_LINK})
    assert "hostedBy" not in crm.updated[-1]
    assert "virtualMeetingUrl" not in crm.updated[-1]


async def test_the_host_link_must_be_https():
    crm = HostedEspo([public_online()])
    with pytest.raises(service.EventError, match="https://"):
        await service.update_event(crm, "ev1", {"hostedBy": "Outside host",
                                                "virtualMeetingUrl": "partner.example/x"})
    assert crm.updated == []


async def test_create_accepts_an_outside_host_link():
    crm = HostedEspo([])
    await service.create_event(crm, {"name": "Partner Webinar", "audience": "Public",
                                     "format": cfg.FORMAT_VIRTUAL,
                                     "hostedBy": "Outside host",
                                     "virtualMeetingUrl": HOST_LINK},
                               chapter_key="cleveland")
    assert crm.created[-1]["virtualMeetingUrl"] == HOST_LINK


async def test_switching_to_outside_host_is_refused_while_people_are_registered():
    crm = HostedEspo([public_online(virtualMeetingUrl="https://zoom.us/j/1",
                                    zoomWebinarId="1")],
                     registrations=[{"attendanceStatus": "Registered"},
                                    {"attendanceStatus": "Waitlisted"},
                                    {"attendanceStatus": "Cancelled"}])
    with pytest.raises(service.EventError, match="2 people are registered"):
        await service.update_event(crm, "ev1", {"hostedBy": "Outside host",
                                                "virtualMeetingUrl": HOST_LINK})
    assert crm.updated == []


async def test_switching_with_only_cancelled_registrations_goes_through():
    crm = HostedEspo([public_online(zoomWebinarId="1")],
                     registrations=[{"attendanceStatus": "Cancelled"}])
    await service.update_event(crm, "ev1", {"hostedBy": "Outside host",
                                            "virtualMeetingUrl": HOST_LINK})
    assert crm.updated[-1]["hostedBy"] == "Outside host"


async def test_an_outside_host_event_already_switched_is_not_refused_again():
    crm = HostedEspo([public_online(hostedBy="Outside host", virtualMeetingUrl=HOST_LINK)],
                     registrations=[{"attendanceStatus": "Registered"}])
    await service.update_event(crm, "ev1", {"name": "Renamed"})
    assert crm.updated[-1]["name"] == "Renamed"


def test_editor_offers_hosted_by_for_public_online_events_only():
    spec = next(f for f in cfg.EVENT_FIELDS if f.name == "hostedBy")
    assert spec.type == "enum"
    assert cfg.rules_of(spec.show_when) == (
        ("audience", ("Public",)), ("format", cfg.ONLINE_FORMATS))
    assert "hostedBy" in cfg.DETECTED_FIELDS
    assert "hostedBy" in cfg.PUBLIC_SELECT.split(",")


def test_registrants_tab_says_the_host_takes_registrations():
    html = (ROOT / "events" / "frontend" / "index.html").read_text()
    source = (ROOT / "events" / "frontend" / "app.js").read_text()
    assert 'id="regHostNote"' in html
    assert "outsideHost()" in source
