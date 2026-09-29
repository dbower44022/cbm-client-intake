"""F3 — the portal's calendar, member registration and saved filter.

What F3 supplies to F5 (design § 6): the selection of events a member may see,
registration for Internal events that take it, and a per-user preference store.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from events import config as cfg
from events import member
from forms import ALL_SPECS

from tests.test_events_service import make_event

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
SOON = "2099-07-02 12:00:00"

MENTOR = {"userName": "mia.mentor@cbmentors.org", "name": "Mia Mentor", "userId": "u-9",
          "token": "t", "isAdmin": False, "teams": ["Mentor Team"]}
BOARD = {**MENTOR, "userId": "u-8", "teams": ["Mentor Team", "System Administration Team"]}


class PortalCrm:
    def __init__(self, events=(), registrations=(), profiles=(), contacts=(),
                 sources=("Online", "Walk-In", "Staff", "Import", "Portal")):
        self.events = list(events)
        self.registrations = list(registrations)
        self.profiles = list(profiles)
        self.contacts = list(contacts)
        self.sources = list(sources) if sources is not None else None
        self.created = []
        self.updated = []

    async def metadata(self, key):
        return {f: {} for f in cfg.AUDIENCE_FIELDS}

    async def metadata_enum_options(self, entity, field):
        if entity == cfg.REGISTRATION and field == "registrationSource":
            return self.sources
        return None

    async def list(self, entity, *, where=None, select=None, max_size=50,
                   offset=0, order_by=None, order=None):
        rows = {cfg.EVENT: [e for e in self.events if e.get("publishToWebsite")],
                cfg.REGISTRATION: self.registrations,
                "CMentorProfile": self.profiles}.get(entity, [])
        for clause in where or []:
            if entity == cfg.REGISTRATION and clause.get("type") == "equals":
                rows = [r for r in rows if r.get(clause["attribute"]) == clause["value"]]
        return {"total": len(rows), "list": rows[offset: offset + max_size]}

    async def get(self, entity, record_id, select=None):
        pool = {cfg.EVENT: self.events, "CMentorProfile": self.profiles}.get(entity, [])
        for row in pool:
            if row.get("id") == record_id:
                return dict(row)
        return {}

    async def find_one(self, entity, attribute, value, select="id"):
        for row in self.contacts:
            if row.get(attribute) == value:
                return row
        return None

    async def create(self, entity, payload):
        self.created.append((entity, payload))
        return {"id": f"reg{len(self.created)}"}

    async def update(self, entity, record_id, payload):
        self.updated.append((entity, record_id, payload))
        return {}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def build(monkeypatch, user, crm, store=None):
    monkeypatch.setenv("EVENTS_ENABLED", "true")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ESPO_DRY_RUN", "true")
    get_settings.cache_clear()
    app = create_app(ALL_SPECS)
    app.state.events_client_factory = lambda: crm
    app.state.submission_store = store
    monkeypatch.setattr(member, "current_user", lambda request: user)
    import portal.router as portal_router

    monkeypatch.setattr(portal_router, "current_user", lambda request: user)

    async def _no_log(*a, **kw):
        return None

    monkeypatch.setattr(member, "record_action", _no_log)
    return TestClient(app)


# --- the calendar -----------------------------------------------------------


def test_calendar_needs_a_signed_in_member(monkeypatch):
    client = build(monkeypatch, None, PortalCrm())
    assert client.get("/api/portal/events").status_code == 401


def test_calendar_shows_internal_and_public_and_honours_the_team_limit(monkeypatch):
    crm = PortalCrm(events=[
        make_event(id="pub", audience="Public", dateStart=SOON),
        make_event(id="int", audience="Internal", dateStart=SOON),
        make_event(id="board", audience="Internal", dateStart=SOON,
                   internalTeams=["System Administration Team"]),
        make_event(id="draft", audience="Internal", dateStart=SOON, publishToWebsite=False),
        make_event(id="later", audience="Internal", dateStart=SOON,
                   eventReleaseDate="2099-01-01 00:00:00"),
    ])
    mentor_ids = [e["id"] for e in build(monkeypatch, MENTOR, crm)
                  .get("/api/portal/events").json()["events"]]
    assert mentor_ids == ["pub", "int"]
    board_ids = [e["id"] for e in build(monkeypatch, BOARD, crm)
                 .get("/api/portal/events").json()["events"]]
    assert set(board_ids) == {"pub", "int", "board"}


def test_calendar_entry_keeps_staff_data_out():
    entry = member.calendar_entry(make_event(
        audience="Internal", internalTeams=["System Administration Team"],
        reachChapters=["cleveland"], takesRegistrations=True, dateStart=SOON))
    text = repr(entry)
    assert "System Administration Team" not in text
    assert "cleveland" not in text
    assert entry["teamLimited"] is True
    assert entry["canRegister"] is True
    assert entry["publicUrl"] is None


# --- registration -------------------------------------------------------------


def _internal(**over):
    fields = {"id": "ev1", "audience": "Internal", "takesRegistrations": True,
              "dateStart": SOON}
    fields.update(over)
    return make_event(**fields)


async def test_registration_links_the_members_own_contact():
    crm = PortalCrm(
        events=[_internal()],
        profiles=[{"id": "mp1", "assignedUserId": "u-9", "assignedUsersIds": ["u-9"],
                   "contactRecordId": "c-7", "cbmEmail": "Mia.Mentor@cbmentors.org"}],
    )
    result = await member.register_member(crm, MENTOR, "ev1", now=NOW)
    entity, payload = crm.created[-1]
    assert entity == cfg.REGISTRATION
    assert payload["registrationSource"] == "Portal"
    assert payload["contactId"] == "c-7"
    assert payload["email"] == "mia.mentor@cbmentors.org"
    assert payload["attendanceStatus"] == cfg.REG_REGISTERED
    assert result["outcome"] == "created"


async def test_registration_without_a_contact_creates_none():
    crm = PortalCrm(events=[_internal()])
    await member.register_member(crm, MENTOR, "ev1", now=NOW)
    _, payload = crm.created[-1]
    assert "contactId" not in payload
    assert payload["email"] == "mia.mentor@cbmentors.org"   # from the userName
    assert not any(entity == "Contact" for entity, _ in crm.created)


async def test_a_repeat_registration_updates_rather_than_duplicates():
    crm = PortalCrm(events=[_internal()], registrations=[{
        "id": "r1", "eventId": "ev1", "email": "mia.mentor@cbmentors.org",
        "attendanceStatus": cfg.REG_CANCELLED}])
    result = await member.register_member(crm, MENTOR, "ev1", now=NOW)
    assert result["outcome"] == "updated"
    assert crm.created == []


@pytest.mark.parametrize("event,message", [
    (make_event(id="ev1", audience="Public", dateStart=SOON), "public page"),
    (_internal(takesRegistrations=False), "does not take registrations"),
    (_internal(internalTeams=["System Administration Team"]), "could not be found"),
    (_internal(publishToWebsite=False), "could not be found"),
    (_internal(registrationCloses="2020-01-01 00:00:00"), "closed"),
])
async def test_registration_refusals(event, message):
    crm = PortalCrm(events=[event])
    with pytest.raises(member.MemberRegistrationRefused, match=message):
        await member.register_member(crm, MENTOR, "ev1", now=NOW)


async def test_registration_waits_for_the_portal_source_in_the_crm():
    crm = PortalCrm(events=[_internal()], sources=("Online", "Staff"))
    with pytest.raises(member.MemberRegistrationRefused, match="Portal"):
        await member.register_member(crm, MENTOR, "ev1", now=NOW)


def test_register_endpoint_returns_a_readable_400(monkeypatch):
    crm = PortalCrm(events=[_internal(takesRegistrations=False)])
    resp = build(monkeypatch, MENTOR, crm).post("/api/portal/events/ev1/register")
    assert resp.status_code == 400
    assert "does not take registrations" in resp.json()["detail"]


# --- preferences ------------------------------------------------------------------


class PrefStore:
    def __init__(self):
        self.rows = {}

    async def get_user_preference(self, user_id, key):
        return self.rows.get((user_id, key))

    async def set_user_preference(self, user_id, key, value):
        self.rows[(user_id, key)] = value


def test_preference_round_trip_is_per_user(monkeypatch):
    store = PrefStore()
    client = build(monkeypatch, MENTOR, PortalCrm(), store=store)
    url = "/api/portal/preferences/events.calendar"
    assert client.get(url).json() == {"key": "events.calendar", "value": None, "stored": True}
    assert client.put(url, json={"value": {"show": ["Internal"]}}).status_code == 200
    assert client.get(url).json()["value"] == {"show": ["Internal"]}
    assert store.rows == {("u-9", "events.calendar"): {"show": ["Internal"]}}


def test_preference_guards(monkeypatch):
    client = build(monkeypatch, MENTOR, PortalCrm(), store=PrefStore())
    assert client.get("/api/portal/preferences/anything").status_code == 404
    big = {"value": "x" * 5000}
    assert client.put("/api/portal/preferences/events.calendar", json=big).status_code == 400
    signed_out = build(monkeypatch, None, PortalCrm(), store=PrefStore())
    assert signed_out.get("/api/portal/preferences/events.calendar").status_code == 401


def test_preference_without_a_database(monkeypatch):
    client = build(monkeypatch, MENTOR, PortalCrm(), store=None)
    url = "/api/portal/preferences/events.calendar"
    assert client.get(url).json()["stored"] is False
    assert client.put(url, json={"value": {}}).status_code == 503
