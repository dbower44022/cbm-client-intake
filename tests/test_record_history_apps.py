"""The History tab in Client Administration, Partner and Funder Management and
Event Administration, and ruling Q5.4 — every one of them records old and new
values (mentor login integrity step 5b; build prompt v0.6)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core import history
from core.app import create_app
from core.config import get_settings
from forms import ALL_SPECS, info_request
from sessions.config import MENTOR, PARTNER, SPONSOR
from sessions.router import _detail_tabs

_USER = {"userId": "u1", "userName": "staff", "name": "Jane Staff", "isAdmin": True,
         "token": "tok", "teams": []}


@pytest.fixture(autouse=True)
def _clear():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class Crm:
    """Reads return the current state; an update moves it."""

    def __init__(self, records):
        self.records = records
        self.updates = []

    async def get(self, entity, record_id, select=None):
        rec = dict(self.records.get((entity, record_id), {}))
        rec["id"] = record_id
        return rec

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        self.records.setdefault((entity, record_id), {}).update(payload)
        return {"id": record_id}

    async def metadata(self, key):
        return {}

    async def i18n(self, scope):
        return {scope: {"fields": {"partnershipStatus": "Partnership Status"}}}


def _capture(monkeypatch, target):
    logged = []

    async def fake(*args, **kw):
        logged.append(kw)
        return True
    monkeypatch.setattr(target, fake)
    return logged


# --- the helpers ---------------------------------------------------------------


def test_field_details_values_when_read_back_else_names():
    before = {"engagementStatus": "Submitted", "mentorProfileId": "6a87e738294d32aac",
              "mentorProfileName": "Old Mentor"}
    after = {"engagementStatus": "Assigned", "mentorProfileId": "6a87e738294d32aad",
             "mentorProfileName": "New Mentor"}
    assert history.field_details(before, after, ["engagementStatus", "mentorProfileId"]) == {
        "engagementStatus": {"from": "Submitted", "to": "Assigned"},
        "mentorProfile": {"from": "Old Mentor", "to": "New Mentor"}}
    assert history.field_details(before, {}, ["engagementStatus", "mentorProfileId"]) == [
        "engagementStatus", "mentorProfile"]
    assert history.link_attrs(["notes", "referringPartnerId"]) == [
        "notes", "referringPartnerId", "referringPartnerId", "referringPartnerName"]


# --- Partner and Funder Management; never Client Management ----------------------


def test_no_tab_anywhere_while_the_switch_is_off():
    for cfg in (PARTNER, SPONSOR, MENTOR):
        assert "history" not in [t["key"] for t in _detail_tabs(cfg)]


def test_the_tab_when_switched_on(monkeypatch):
    monkeypatch.setenv("RECORD_HISTORY_TAB", "true")
    get_settings.cache_clear()
    assert [t["key"] for t in _detail_tabs(PARTNER)][-1] == "history"
    assert [t["key"] for t in _detail_tabs(SPONSOR)][-1] == "history"
    assert "history" not in [t["key"] for t in _detail_tabs(MENTOR)]


def _sessions_app(monkeypatch, crm, **env):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: _USER)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, u: crm)
    return create_app([info_request.SPEC])


def test_client_management_is_refused_on_the_server(monkeypatch):
    called = []

    async def fake(*a, **kw):
        called.append(a)
        return {"lines": []}
    monkeypatch.setattr("sessions.router.history.record_history", fake)
    with TestClient(_sessions_app(monkeypatch, Crm({}), RECORD_HISTORY_TAB="true")) as c:
        assert c.get("/mentorsessions/api/records/E1/history").status_code == 404
        assert c.get("/partnersessions/api/records/P1/history").status_code == 200
        assert c.get("/sponsorsessions/api/records/S1/history").status_code == 200
    assert [a[1] for a in called] == ["CPartnerProfile", "CSponsorProfile"]


def test_partner_and_funder_tabs_are_off_until_the_switch(monkeypatch):
    with TestClient(_sessions_app(monkeypatch, Crm({}))) as c:
        assert c.get("/partnersessions/api/records/P1/history").status_code == 404


def test_a_partner_details_save_records_old_and_new_values(monkeypatch):
    crm = Crm({("CPartnerProfile", "P1"): {"partnershipStatus": "Prospect"}})

    async def save(client, entity, record_id, changes):
        await client.update(entity, record_id, changes)
        return {"entity": entity, "id": record_id, "saved": list(changes)}
    monkeypatch.setattr("sessions.router.details_svc.save_details", save)
    logged = _capture(monkeypatch, "sessions.router.action_log.log_action")
    noted = _capture(monkeypatch, "sessions.router.action_log.record_action")
    with TestClient(_sessions_app(monkeypatch, crm)) as c:
        r = c.put("/partnersessions/api/details/CPartnerProfile/P1",
                  json={"changes": {"partnershipStatus": "Active"}})
    assert r.status_code == 200
    [kw] = logged
    assert kw["details"] == {"fields": {"partnershipStatus": {"from": "Prospect", "to": "Active"}}}
    assert kw["summary"] == "Saved Partnership Status."
    assert kw["app"] == "Partner Management"
    assert noted == [], "no stream note: the save posted none before (review 5b)"


def test_a_client_management_details_save_is_not_recorded(monkeypatch):
    crm = Crm({("CEngagement", "E1"): {"meetingCadence": "Weekly"}})

    async def save(client, entity, record_id, changes):
        return {"entity": entity, "id": record_id, "saved": list(changes)}
    monkeypatch.setattr("sessions.router.details_svc.save_details", save)
    logged = _capture(monkeypatch, "sessions.router.action_log.log_action")
    with TestClient(_sessions_app(monkeypatch, crm)) as c:
        c.put("/mentorsessions/api/details/CEngagement/E1", json={"changes": {"meetingCadence": "Monthly"}})
    assert logged == []


# --- Client Administration -------------------------------------------------------


def _assign_app(monkeypatch, crm, **env):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    monkeypatch.setattr("assignments.auth.current_user", lambda request: _USER)
    monkeypatch.setattr("assignments.router.client_for", lambda settings, user: crm)
    return create_app([info_request.SPEC])


def test_client_administration_tab(monkeypatch):
    async def fake(client, entity, record_id, *, viewer):
        return {"lines": [], "entity": entity}
    monkeypatch.setattr("assignments.router.history.record_history", fake)
    with TestClient(_assign_app(monkeypatch, Crm({}))) as c:
        assert c.get("/assignments/api/session").json()["historyEnabled"] is False
        assert c.get("/assignments/api/engagements/E1/history").status_code == 404
    get_settings.cache_clear()
    with TestClient(_assign_app(monkeypatch, Crm({}), RECORD_HISTORY_TAB="true")) as c:
        assert c.get("/assignments/api/session").json()["historyEnabled"] is True
        assert c.get("/assignments/api/engagements/E1/history").json()["entity"] == "CEngagement"


def test_an_engagement_edit_records_old_and_new_values(monkeypatch):
    crm = Crm({("CEngagement", "E1"): {"engagementStatus": "Submitted", "meetingCadence": "Weekly"}})

    async def update(client, engagement_id, changes):
        await client.update("CEngagement", engagement_id, changes)
        return {"engagementId": engagement_id, "changedFields": ["Status"], "droppedValues": []}

    async def detail(client, engagement_id):
        return {}
    monkeypatch.setattr("assignments.router.service.update_engagement", update)
    monkeypatch.setattr("assignments.router.service.get_engagement_detail", detail)
    logged = _capture(monkeypatch, "assignments.router.action_log.record_action")
    with TestClient(_assign_app(monkeypatch, crm)) as c:
        r = c.put("/assignments/api/engagements/E1", json={"changes": {"engagementStatus": "On-Hold"}})
    assert r.status_code == 200
    assert logged[0]["details"]["fields"] == {
        "engagementStatus": {"from": "Submitted", "to": "On-Hold"}}


def test_internal_notes_are_recorded_without_a_stream_note(monkeypatch):
    crm = Crm({("CEngagement", "E1"): {"description": "old"}})
    logged = _capture(monkeypatch, "assignments.router.action_log.log_action")
    noted = _capture(monkeypatch, "assignments.router.action_log.record_action")
    with TestClient(_assign_app(monkeypatch, crm)) as c:
        c.put("/assignments/api/engagements/E1/notes", json={"notes": "new"})
    assert noted == []
    assert logged[0]["details"] == {"fields": {"description": {"from": "old", "to": "new"}}}


# --- Event Administration -----------------------------------------------------------


def test_event_administration_tab_and_values(monkeypatch):
    from tests.test_events_registration import FakeCrm
    from tests.test_events_service import make_event
    import events.router as router_mod

    monkeypatch.setenv("EVENTS_ENABLED", "true")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ESPO_DRY_RUN", "true")
    get_settings.cache_clear()
    app = create_app(ALL_SPECS)
    crm = FakeCrm(events=[make_event(name="Old title")])
    monkeypatch.setattr(router_mod, "current_user", lambda request: _USER)
    monkeypatch.setattr(router_mod, "client_for", lambda settings, u: crm)
    logged = _capture(monkeypatch, "events.router.record_action")
    with TestClient(app) as c:
        assert c.get("/events/api/session").json()["historyEnabled"] is False
        assert c.get("/events/api/events/ev1/history").status_code == 404
        # The real form sends every field; only what moved is recorded.
        r = c.put("/events/api/events/ev1", json={"changes": {
            "name": "New title", "description": "Demystifying the dollar signs."}})
    assert r.status_code == 200, r.text
    assert logged[-1]["details"]["fields"] == {"name": {"from": "Old title", "to": "New title"}}


# --- the 5b review's findings ---------------------------------------------------------


def test_without_the_read_before_only_the_field_names_are_recorded():
    after = {"name": "x", "description": "y"}
    assert history.field_details({}, after, ["name", "description"]) == ["description", "name"]


def test_a_link_without_its_name_is_recorded_by_field_never_by_id():
    moved = history.value_changes({"referringPartnerId": "6a87e738294d32aac"},
                                  {"referringPartnerId": "6a87e738294d32aad"},
                                  ["referringPartnerId"])
    assert moved == {"referringPartner": {}}
    from core import action_log
    row = {"createdAt": "2026-11-06 12:00:00", "actorName": "A", "summary": "s",
           "category": action_log.CAT_RECORD_EDIT, "details": {"fields": moved}}
    [ln] = history.merge([row], [], labels={}, key_user="")
    assert ln["valuesRecorded"] is False and ln["changes"] == [{"field": "Referring Partner"}]


def test_long_text_is_clipped_when_recorded():
    moved = history.value_changes({"notes": "a"}, {"notes": "b" * 5000}, ["notes"])
    assert len(moved["notes"]["to"]) == 2000


def test_the_edit_button_stays_on_the_history_tab():
    js = (Path(__file__).resolve().parent.parent / "assignments" / "frontend" / "app.js").read_text()
    body = js[js.index("function showModalTab"):js.index("function showModalTab") + 900]
    assert "modalViewActions" not in body, "action buttons are never hidden"
