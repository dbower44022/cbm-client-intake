"""Session Management engine: config, service (list/detail/create/update), and
router auth-gating — across the three domains."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from forms import info_request
from sessions import details, service
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
            "name": "Acme", "partnershipStatus": "Active",
            "partnerCompanyName": "Acme Co", "partnerCompanyId": "acct1",
            "primaryPartnercontactId": "cprimary", "partnerNotes": "<p>key relationship</p>"}},
        related={
            "contacts": [{"id": "c1", "name": "Pat", "emailAddress": "pat@x.org"}],
            "sessions": [{"id": "s1", "name": "Kickoff", "status": "Held",
                          "dateStart": "2026-02-01 10:00:00", "sessionNotes": "<p>went well</p>",
                          "sessionAttendeesNames": {"c1": "Pat", "c9": "Dana"}}],
        },
    )
    d = await service.get_detail(PARTNER, fake, "P1")
    assert d["name"] == "Acme"
    # curated Overview facts (in config order), grouped into sections, with the
    # company linkable to a peek
    status = next(i for i in d["overview"] if i["label"] == "Partnership status")
    assert status == {"label": "Partnership status", "value": "Active",
                      "type": "badge", "block": False, "section": "key"}
    # single "Company" link aggregates the Account + the partner profile (parent)
    company = next(i for i in d["overview"] if i["label"] == "Company")
    assert company["value"] == "Acme Co"
    assert company["link"]["aggregate"] == [
        {"entity": "Account", "id": "acct1"},
        {"entity": "CPartnerProfile", "id": "P1"},
    ]
    # aggregated note feed carries each session's notes + attendees, stamped with time
    assert d["noteFeed"][0]["notes"] == "<p>went well</p>"
    assert d["noteFeed"][0]["dateStart"] == "2026-02-01 10:00:00"
    assert d["noteFeed"][0]["attendees"] == ["Pat", "Dana"]
    assert d["contacts"][0]["email"] == "pat@x.org"
    assert d["primaryContactId"] == "cprimary"
    assert d["sessions"][0]["status"] == "Held"
    # overall (partner-level) notes surface above the per-session feed
    assert d["overallNotes"] == {"label": "Partner Notes", "value": "<p>key relationship</p>", "type": "html"}
    # the only session is in the past => nothing scheduled ahead
    assert d["nextSession"] is None
    assert "coMentors" not in d  # partner domain has no co-mentors


@pytest.mark.asyncio
async def test_get_detail_next_session_is_soonest_upcoming():
    fake = Fake(
        records={("CPartnerProfile", "P1"): {"name": "Acme"}},
        related={"sessions": [
            {"id": "past", "dateStart": "2020-01-01 09:00:00"},
            {"id": "soon", "name": "Check-in", "sessionType": "Partner Session",
             "dateStart": "2099-03-01 09:00:00"},
            {"id": "later", "dateStart": "2099-09-01 09:00:00"},
        ]},
    )
    d = await service.get_detail(PARTNER, fake, "P1")
    assert d["nextSession"]["id"] == "soon"  # earliest still in the future
    assert d["nextSession"]["name"] == "Check-in"


@pytest.mark.asyncio
async def test_get_detail_note_feed_sorted_desc():
    fake = Fake(
        records={("CPartnerProfile", "P1"): {"name": "Acme"}},
        related={"sessions": [
            {"id": "old", "dateStart": "2026-01-01 09:00:00", "sessionNotes": "first"},
            {"id": "new", "dateStart": "2026-03-01 09:00:00", "sessionNotes": "latest"},
        ]},
    )
    d = await service.get_detail(PARTNER, fake, "P1")
    assert [n["id"] for n in d["noteFeed"]] == ["new", "old"]  # most recent first


@pytest.mark.asyncio
async def test_peek_allowlists_entities_and_drops_empties():
    fake = Fake(records={("Contact", "c1"): {
        "name": "Pat Lee", "emailAddress": "pat@x.org", "title": "COO", "phoneNumber": ""}})
    res = await service.peek(fake, "Contact", "c1")
    assert res["name"] == "Pat Lee"
    labels = {f["label"]: f["value"] for f in res["fields"]}
    assert labels["Email"] == "pat@x.org" and labels["Title"] == "COO"
    assert "Phone" not in labels  # empty value dropped

    with pytest.raises(service.SessionError):
        await service.peek(fake, "User", "u1")  # not on the allowlist


@pytest.mark.asyncio
async def test_get_detail_includes_comentors_for_mentor():
    fake = Fake(
        records={("CEngagement", "E1"): {"name": "Eng", "engagementStatus": "Active"}},
        related={"additionalMentors": [{"id": "m2", "name": "Co Mentor"}]},
    )
    d = await service.get_detail(MENTOR, fake, "E1")
    assert d["supportsComentor"] is True
    assert d["coMentors"] == [{"id": "m2", "name": "Co Mentor"}]


# --- Details tab -----------------------------------------------------------

def test_details_label_humanizes_field_names():
    assert details._label("partnershipStartDate") == "Partnership Start Date"
    assert details._label("cIndustrySector") == "Industry Sector"
    assert details._label("cBMValueProvided") == "CBM Value Provided"


def test_details_field_spec_filters_and_flags():
    spec = {f["name"]: f for f in details._field_spec({
        "name": {"type": "personName"},              # composite name — excluded
        "title": {"type": "varchar"},                # editable
        "industrySector": {"type": "enum", "options": ["A", "B", ""]},  # blank dropped
        "assignedUser": {"type": "link"},            # link — excluded
        "createdAt": {"type": "datetime"},           # system — excluded
        "emailAddressIsInvalid": {"type": "bool"},   # noise suffix — excluded
        "totalContribution": {"type": "currency"},   # shown but read-only
    })}
    assert spec["title"]["editable"] is True
    assert spec["industrySector"]["options"] == ["A", "B"]
    assert spec["totalContribution"]["editable"] is False
    for gone in ("name", "assignedUser", "createdAt", "emailAddressIsInvalid"):
        assert gone not in spec


@pytest.mark.asyncio
async def test_save_details_whitelists_and_drops_drifted_enum():
    fake = Fake(meta_fields={
        "title": {"type": "varchar"},
        "industrySector": {"type": "enum", "options": ["A", "B"]},
    })
    res = await details.save_details(
        fake, "Account", "acct1",
        {"title": "COO", "industrySector": "Z", "bogus": "x", "id": "hack"},
    )
    # non-editable/unknown keys dropped, drifted enum "Z" dropped, title kept
    assert fake.updates == [("Account", "acct1", {"title": "COO"})]
    assert res["saved"] == ["title"]


@pytest.mark.asyncio
async def test_build_details_has_company_profile_and_contact_sections():
    fake = Fake(
        records={
            ("CPartnerProfile", "P1"): {"name": "Acme", "partnerCompanyId": "acct1"},
            ("Account", "acct1"): {"name": "Acme Co"},
        },
        related={"contacts": [{"id": "c1", "name": "Pat", "title": "COO"}]},
        meta_fields={"title": {"type": "varchar"}, "website": {"type": "url"}},
    )
    d = await details.build_details(PARTNER, fake, "P1")
    kinds = [(s["title"], s["entity"]) for s in d["sections"]]
    assert ("Company", "Account") in kinds
    assert ("Partnership Profile", "CPartnerProfile") in kinds
    assert ("Pat", "Contact") in kinds


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
async def test_create_session_stamps_owner_for_read_own():
    # The creating user is set as assignedUser (both shapes) so a read-own role
    # can still see the session they just made.
    fake = Fake()
    await service.create_session(MENTOR, fake, "E1", {"name": "S"}, None, owner_user_id="u1")
    _, payload = fake.created[0]
    assert payload["assignedUserId"] == "u1" and payload["assignedUsersIds"] == ["u1"]


@pytest.mark.asyncio
async def test_update_session_whitelists_and_sets_attendees():
    fake = Fake(records={("CSession", "s1"): {"name": "old"}})
    await service.update_session(fake, "s1", {"name": "new", "hack": 1}, ["c3"])
    entity, rid, payload = fake.updates[0]
    assert (entity, rid) == ("CSession", "s1")
    assert payload["name"] == "new" and payload["sessionAttendeesIds"] == ["c3"]
    assert "hack" not in payload


@pytest.mark.asyncio
async def test_update_drops_drifted_enum_but_keeps_valid_fields():
    # A stored sessionType value that's no longer a live option must be omitted
    # (not sent) rather than 400 the whole update; other fields still save.
    meta = {"sessionType": {"options": ["Client Session", "Follow-up"]}}
    fake = Fake(records={("CSession", "s1"): {}}, meta_fields=meta)
    await service.update_session(
        fake, "s1", {"sessionType": "In-Person", "name": "Kickoff"}, None
    )
    _, _, payload = fake.updates[0]
    assert "sessionType" not in payload      # drifted value dropped, not sent
    assert payload["name"] == "Kickoff"      # valid field still updated


@pytest.mark.asyncio
async def test_multienum_keeps_only_valid_values():
    meta = {"meetingType": {"options": ["Virtual", "Phone"]}}
    fake = Fake(records={("CSession", "s1"): {}}, meta_fields=meta)
    await service.update_session(
        fake, "s1", {"meetingType": ["Virtual", "Carrier Pigeon"]}, None
    )
    _, _, payload = fake.updates[0]
    assert payload["meetingType"] == ["Virtual"]


@pytest.mark.asyncio
async def test_field_required_reads_crm_metadata():
    # Only fields the CRM marks required (and are editable) are returned.
    meta = {
        "dateStart": {"type": "datetime", "required": True},
        "name": {"type": "varchar", "required": True},
        "status": {"type": "enum"},          # not required
        "notAField": {"required": True},      # not in the editable set
    }
    fake = Fake(meta_fields=meta)
    required = await service.field_required(fake)
    assert set(required) == {"dateStart", "name"}


@pytest.mark.asyncio
async def test_sanitizer_fails_open_when_options_unavailable():
    # No metadata options => can't verify => keep the value (never drop unverified).
    fake = Fake(records={("CSession", "s1"): {}})  # meta_fields={} => no options
    await service.update_session(fake, "s1", {"sessionType": "Anything"}, None)
    _, _, payload = fake.updates[0]
    assert payload["sessionType"] == "Anything"


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
    # phase-one common detail tabs (same for every domain)
    tabs = data["detailTabs"]
    assert [t["key"] for t in tabs] == [
        "overview", "details", "sessions", "communications", "documents",
    ]
    # Overview/Details/Sessions are built; Communications/Documents are placeholders
    assert next(t for t in tabs if t["key"] == "communications")["placeholder"] is True
    assert "placeholder" not in next(t for t in tabs if t["key"] == "details")


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

    async def fake_create(cfg, client, parent_id, changes, attendees, owner_user_id=None):
        return {"id": "s1", "parent": parent_id, "attendees": attendees,
                "owner": owner_user_id, **changes}

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
