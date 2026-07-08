"""Session Management engine: config, service (list/detail/create/update), and
router auth-gating — across the three domains."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from forms import info_request
from sessions import service
from sessions.config import DOMAINS, MENTOR, PARTNER, SPONSOR

_USER = {"userId": "u1", "userName": "boss", "name": "The Boss", "isAdmin": True, "token": "tok"}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- fake CRM client -------------------------------------------------------

class Fake:
    def __init__(self, *, mentors=None, related=None, records=None, meta_fields=None):
        self.mentors = mentors or []            # rows returned by list(CMentorProfile)
        self.related = related or {}            # link name -> [rows]
        self.records = dict(records or {})      # (entity, id) -> dict
        self.meta_fields = meta_fields or {}
        self.created = []
        self.updates = []
        self.relates = []
        self._seq = 0

    async def list(self, entity, **kw):
        if entity == "CMentorProfile":
            return {"list": self.mentors}
        return {"list": []}

    async def list_related(self, entity, record_id, link, **kw):
        return {"list": self.related.get(link, [])}

    async def get(self, entity, record_id, select=None):
        return dict(self.records.get((entity, record_id), {}), id=record_id)

    async def create(self, entity, payload):
        self._seq += 1
        rid = f"{entity.lower()}-{self._seq}"
        self.created.append((entity, payload))
        self.records[(entity, rid)] = dict(payload, id=rid)
        return {"id": rid}

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        rec = self.records.setdefault((entity, record_id), {"id": record_id})
        rec.update(payload)
        return {"id": record_id}

    async def relate(self, entity, record_id, link, related_id):
        self.relates.append((entity, record_id, link, related_id))

    async def metadata(self, key):
        return self.meta_fields


# --- config ----------------------------------------------------------------

def test_domains_registered():
    assert set(DOMAINS) == {"mentorsessions", "partnersessions", "sponsorsessions"}


def test_domain_links_match_crm():
    """Lock the live-verified CSession parent links / reverse links per domain."""
    assert MENTOR.session_parent_link == "engagement" and MENTOR.session_parent_fk == "engagementId"
    assert MENTOR.manager_owned_link == "engagements1"
    assert MENTOR.parent_sessions_link == "engagementSessions"
    assert MENTOR.supports_comentor is True and MENTOR.status_values

    assert PARTNER.session_parent_link == "partnerSession" and PARTNER.session_parent_fk == "partnerSessionId"
    assert PARTNER.manager_owned_link == "managedPartners"
    assert PARTNER.parent_sessions_link == "sessions"
    assert PARTNER.supports_comentor is False

    assert SPONSOR.session_parent_link == "sponsorProfile" and SPONSOR.session_parent_fk == "sponsorProfileId"
    assert SPONSOR.manager_owned_link == "managedSponsors"  # reverse of cBMSponsorManager
    assert SPONSOR.parent_sessions_link == "sponsorSessions"


# --- resolve manager profile ----------------------------------------------

@pytest.mark.asyncio
async def test_resolve_manager_profile_single_field():
    fake = Fake(mentors=[{"id": "p9", "assignedUserId": "u1"}, {"id": "pX", "assignedUserId": "u2"}])
    assert await service.resolve_manager_profile(fake, "u1") == "p9"


@pytest.mark.asyncio
async def test_resolve_manager_profile_collaborators_field():
    # prod: CMentorProfile uses assignedUsers (collaborators), not assignedUser.
    fake = Fake(mentors=[{"id": "p9", "assignedUsersIds": ["u1"]}])
    assert await service.resolve_manager_profile(fake, "u1") == "p9"


@pytest.mark.asyncio
async def test_resolve_manager_profile_none_when_unlinked():
    fake = Fake(mentors=[{"id": "pX", "assignedUserId": "u2"}])
    assert await service.resolve_manager_profile(fake, "u1") is None


# --- list_records ----------------------------------------------------------

@pytest.mark.asyncio
async def test_list_records_no_profile():
    fake = Fake(mentors=[])
    res = await service.list_records(PARTNER, fake, _USER)
    assert res == {"records": [], "profileFound": False}


@pytest.mark.asyncio
async def test_list_records_maps_columns():
    fake = Fake(
        mentors=[{"id": "p9", "assignedUserId": "u1"}],
        related={"managedPartners": [
            {"id": "P1", "name": "Acme", "partnershipStatus": "Active",
             "partnerCompanyName": "Acme Co", "createdAt": "2026-01-02 00:00:00"},
        ]},
    )
    res = await service.list_records(PARTNER, fake, _USER)
    assert res["profileFound"] is True
    row = res["records"][0]
    assert row["id"] == "P1" and row["name"] == "Acme"
    assert row["status"] == "Active" and row["company"] == "Acme Co"


@pytest.mark.asyncio
async def test_mentor_list_filters_active_statuses():
    fake = Fake(
        mentors=[{"id": "p9", "assignedUserId": "u1"}],
        related={"engagements1": [
            {"id": "E1", "name": "Active one", "engagementStatus": "Active", "createdAt": "2026-01-03"},
            {"id": "E2", "name": "Done one", "engagementStatus": "Completed", "createdAt": "2026-01-04"},
            {"id": "E3", "name": "Pending one", "engagementStatus": "Pending Acceptance", "createdAt": "2026-01-05"},
        ]},
    )
    res = await service.list_records(MENTOR, fake, _USER)
    ids = {r["id"] for r in res["records"]}
    assert ids == {"E1", "E3"}  # Completed excluded


# --- get_detail ------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_detail_assembles_partner():
    fake = Fake(
        records={("CPartnerProfile", "P1"): {
            "name": "Acme", "partnershipStatus": "Active", "partnerCompanyName": "Acme Co"}},
        related={
            "contacts": [{"id": "c1", "name": "Pat", "emailAddress": "pat@x.org"}],
            "sessions": [{"id": "s1", "name": "Kickoff", "status": "Held", "dateStart": "2026-02-01 10:00:00"}],
        },
    )
    d = await service.get_detail(PARTNER, fake, "P1")
    assert d["name"] == "Acme"
    assert {"label": "Partnership status", "value": "Active"} in d["summary"]
    assert d["contacts"][0]["email"] == "pat@x.org"
    assert d["sessions"][0]["status"] == "Held"
    assert "coMentors" not in d  # partner domain has no co-mentors


@pytest.mark.asyncio
async def test_get_detail_includes_comentors_for_mentor():
    fake = Fake(
        records={("CEngagement", "E1"): {"name": "Eng", "engagementStatus": "Active"}},
        related={"additionalMentors": [{"id": "m2", "name": "Co Mentor"}]},
    )
    d = await service.get_detail(MENTOR, fake, "E1")
    assert d["supportsComentor"] is True
    assert d["coMentors"] == [{"id": "m2", "name": "Co Mentor"}]


# --- create / update session ----------------------------------------------

@pytest.mark.asyncio
async def test_create_session_sets_parent_and_defaults_and_whitelists():
    fake = Fake()
    await service.create_session(
        PARTNER, fake, "P1",
        {"name": "Check-in", "sessionNotes": "<p>notes</p>", "id": "hack", "bogus": 1},
        ["c1", "c2"],
    )
    entity, payload = fake.created[0]
    assert entity == "CSession"
    assert payload["partnerSessionId"] == "P1"
    assert payload["sessionType"] == "Partner Session"  # domain default
    assert payload["status"] == "Planned"               # default
    assert payload["name"] == "Check-in" and payload["sessionNotes"] == "<p>notes</p>"
    assert payload["sessionAttendeesIds"] == ["c1", "c2"]
    assert "id" not in payload and "bogus" not in payload


@pytest.mark.asyncio
async def test_create_session_keeps_explicit_type_and_status():
    fake = Fake()
    await service.create_session(
        MENTOR, fake, "E1", {"sessionType": "Other Session", "status": "Held"}, None
    )
    _, payload = fake.created[0]
    assert payload["sessionType"] == "Other Session" and payload["status"] == "Held"
    assert payload["engagementId"] == "E1"
    assert "sessionAttendeesIds" not in payload  # attendees=None => untouched


@pytest.mark.asyncio
async def test_update_session_whitelists_and_sets_attendees():
    fake = Fake(records={("CSession", "s1"): {"name": "old"}})
    await service.update_session(fake, "s1", {"name": "new", "hack": 1}, ["c3"])
    entity, rid, payload = fake.updates[0]
    assert (entity, rid) == ("CSession", "s1")
    assert payload["name"] == "new" and payload["sessionAttendeesIds"] == ["c3"]
    assert "hack" not in payload


@pytest.mark.asyncio
async def test_get_session_exposes_attendees():
    fake = Fake(records={("CSession", "s1"): {"name": "x", "sessionAttendeesIds": ["c1", "c2"]}})
    rec = await service.get_session(fake, "s1")
    assert rec["attendees"] == ["c1", "c2"]


@pytest.mark.asyncio
async def test_add_comentor_relates():
    fake = Fake()
    await service.add_comentor(fake, "E1", "m2")
    assert fake.relates == [("CEngagement", "E1", "additionalMentors", "m2")]


@pytest.mark.asyncio
async def test_field_options_reads_live_enums_and_drops_blank():
    fake = Fake(meta_fields={
        "status": {"type": "enum", "options": ["Planned", "Held", "Not Held"]},
        "meetingType": {"type": "multiEnum", "options": ["", "In Person", "Virtual Video"]},
        "name": {"type": "varchar"},
    })
    opts = await service.field_options(fake)
    assert opts["status"] == ["Planned", "Held", "Not Held"]
    assert opts["meetingType"] == ["In Person", "Virtual Video"]  # blank dropped
    assert "name" not in opts


# --- router ----------------------------------------------------------------

def _app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


def _as(monkeypatch, user):
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, user: object())


def test_requires_auth(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/mentorsessions/api/records").status_code == 401
        assert c.get("/partnersessions/api/session").status_code == 401


def test_wrong_team_403_names_team(monkeypatch):
    _as(monkeypatch, dict(_USER, isAdmin=False, teams=["Mentor Team"], roles=[]))
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/partnersessions/api/records")
    assert r.status_code == 403
    assert "Partner Management Team" in r.json()["detail"]


def test_team_member_passes(monkeypatch):
    _as(monkeypatch, dict(_USER, isAdmin=False, teams=["Partner Management Team"], roles=[]))

    async def fake_list(cfg, client, user):
        return {"records": [{"id": "P1", "name": "Acme"}], "profileFound": True}

    monkeypatch.setattr("sessions.service.list_records", fake_list)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/partnersessions/api/records")
    assert r.status_code == 200 and r.json()["records"][0]["name"] == "Acme"


def test_session_endpoint_reports_domain(monkeypatch):
    _as(monkeypatch, _USER)
    with TestClient(_app(monkeypatch)) as c:
        data = c.get("/mentorsessions/api/session").json()
    assert data["domain"] == "mentorsessions"
    assert data["supportsComentor"] is True
    assert data["defaultSessionType"] == "Client Session"


def test_partner_has_no_comentor_endpoints(monkeypatch):
    _as(monkeypatch, _USER)

    async def fake_mentors(client):
        return []

    monkeypatch.setattr("sessions.service.mentor_options", fake_mentors)
    with TestClient(_app(monkeypatch)) as c:
        # /mentors is mentor-only: registered for mentor, absent for partner.
        assert c.get("/partnersessions/api/mentors").status_code == 404
        assert c.get("/mentorsessions/api/mentors").status_code == 200


def test_create_session_endpoint(monkeypatch):
    _as(monkeypatch, _USER)

    async def fake_create(cfg, client, parent_id, changes, attendees):
        return {"id": "s1", "parent": parent_id, "attendees": attendees, **changes}

    monkeypatch.setattr("sessions.service.create_session", fake_create)
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/sponsorsessions/api/records/SP1/sessions",
                   json={"changes": {"name": "Visit"}, "attendees": ["c1"]})
    assert r.status_code == 200
    body = r.json()
    assert body["parent"] == "SP1" and body["attendees"] == ["c1"] and body["name"] == "Visit"


def test_expired_token_returns_401(monkeypatch):
    _as(monkeypatch, _USER)

    async def boom(cfg, client, user):
        raise EspoError("list CMentorProfile failed: HTTP 401 Unauthorized")

    monkeypatch.setattr("sessions.service.list_records", boom)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentorsessions/api/records")
    assert r.status_code == 401 and "expired" in r.json()["detail"].lower()


def test_other_crm_error_returns_502(monkeypatch):
    _as(monkeypatch, _USER)

    async def boom(cfg, client, user):
        raise EspoError("list failed: HTTP 500 Server Error")

    monkeypatch.setattr("sessions.service.list_records", boom)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentorsessions/api/records")
    assert r.status_code == 502
