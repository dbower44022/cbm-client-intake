"""Mentor Admin router + service: auth gating, list/detail/update, whitelist."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from forms import info_request
from mentoradmin import service

_USER = {"userId": "u1", "userName": "boss", "name": "Mentor Boss", "isAdmin": True, "token": "tok"}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- service-level fake client ---

class FakeClient:
    """Captures get/update calls and returns canned records."""

    def __init__(self, record=None, metadata=None):
        self.record = record or {"id": "m1", "name": "Jane Mentor", "mentorStatus": "Active"}
        self._metadata = metadata or {}
        self.updates = []
        self.gets = []

    async def get(self, entity, record_id, select=None):
        self.gets.append((entity, record_id, select))
        return dict(self.record, id=record_id)

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        self.record.update(payload)
        return dict(self.record, id=record_id)

    async def metadata(self, key):
        return self._metadata


# --- service tests ---

@pytest.mark.asyncio
async def test_update_mentor_whitelists_fields():
    client = FakeClient()
    await service.update_mentor(
        client, "m1",
        {"mentorStatus": "Inactive", "id": "hacked", "totalMentoringHours": 999, "name": "New Name"},
    )
    assert len(client.updates) == 1
    _, rid, payload = client.updates[0]
    assert rid == "m1"
    # only whitelisted editable fields survive
    assert payload == {"mentorStatus": "Inactive", "name": "New Name"}
    assert "id" not in payload and "totalMentoringHours" not in payload


@pytest.mark.asyncio
async def test_update_mentor_no_editable_changes_skips_update():
    client = FakeClient()
    await service.update_mentor(client, "m1", {"totalMentoringHours": 5, "id": "x"})
    assert client.updates == []  # nothing whitelisted -> no write
    assert client.gets  # still re-reads the record


def test_field_spec_layout():
    """Lock the requested detail-form layout."""
    by = {f["name"]: f for f in service.EDITABLE_FIELDS}
    # how-did-you-hear is a dropdown mirroring the mentor intake form
    assert by["howDidYouHearAboutCBM"]["type"] == "enum"
    assert by["howDidYouHearAboutCBM"]["options"] == service.HOW_HEARD_OPTIONS
    # start date moved to Status; Dates tab renamed Departure (no more "Dates")
    assert by["mentorStartDate"]["group"] == "Status"
    assert by["departureDate"]["group"] == "Departure"
    assert by["departureReason"]["group"] == "Departure"
    assert not any(f["group"] == "Dates" for f in service.EDITABLE_FIELDS)
    # Compliance: checkboxes on the top row, dates on the bottom
    comp = [f for f in service.EDITABLE_FIELDS if f["group"] == "Compliance"]
    assert all(f["row"] == "checks" for f in comp if f["type"] == "bool")
    assert all(f["row"] == "dates" for f in comp if f["type"] == "date")


@pytest.mark.asyncio
async def test_get_mentor_selects_contact_info_foreign_fields():
    """The read-only summary card needs the Contact-mirrored foreign fields."""
    client = FakeClient()
    await service.get_mentor(client, "m1")
    _, _, select = client.gets[0]
    cols = select.split(",")
    for f in ("personalEmail", "contactPhone", "contactStreet", "contactCity", "postalCode"):
        assert f in cols
    # these stay read-only — never in the editable whitelist
    assert not (service.EDITABLE_NAMES & {"personalEmail", "contactPhone", "postalCode"})


@pytest.mark.asyncio
async def test_field_options_reads_live_enums():
    meta = {
        "mentorStatus": {"type": "enum", "options": ["Active", "Inactive"]},
        "mentoringFocusAreas": {"type": "multiEnum", "options": ["Finance", "Marketing"]},
        "name": {"type": "varchar"},  # not an enum -> excluded
    }
    client = FakeClient(metadata=meta)
    opts = await service.field_options(client)
    assert opts["mentorStatus"] == ["Active", "Inactive"]
    assert opts["mentoringFocusAreas"] == ["Finance", "Marketing"]
    assert "name" not in opts


# --- data-structure completeness ---

class CompletenessClient:
    """Returns a Contact with a given assignedUserId (for the Active checks)."""
    def __init__(self, contact_user=None):
        self.contact_user = contact_user

    async def get(self, entity, record_id, select=None):
        return {"id": record_id, "assignedUserId": self.contact_user}


def _complete_rec(**over):
    rec = {
        "contactRecordId": "c1", "assignedUserId": "u1", "mentorStatus": "Active",
        "backgroundCheckCompleted": True, "ethicsAgreementAccepted": True,
        "trainingCompleted": True, "termsAccepted": True,
    }
    rec.update(over)
    return rec


@pytest.mark.asyncio
async def test_completeness_complete_active():
    r = await service.check_completeness(CompletenessClient(contact_user="u1"), _complete_rec())
    assert r == {"status": "Complete", "issues": []}


@pytest.mark.asyncio
async def test_completeness_missing_signoff_flag():
    r = await service.check_completeness(CompletenessClient("u1"), _complete_rec(trainingCompleted=False))
    assert r["status"] == "Incomplete" and any("training" in i for i in r["issues"])


@pytest.mark.asyncio
async def test_completeness_no_contact_record():
    r = await service.check_completeness(CompletenessClient(), _complete_rec(contactRecordId=None, mentorStatus="Candidate"))
    assert r["status"] == "Incomplete" and any("Contact" in i for i in r["issues"])


@pytest.mark.asyncio
async def test_completeness_active_requires_user_on_member_and_contact():
    # member has no user
    r = await service.check_completeness(CompletenessClient("u1"), _complete_rec(assignedUserId=None))
    assert r["status"] == "Incomplete" and any("no User assigned to the mentor" in i for i in r["issues"])
    # contact assigned to a different user
    r2 = await service.check_completeness(CompletenessClient("uX"), _complete_rec())
    assert r2["status"] == "Incomplete" and any("different User" in i for i in r2["issues"])
    # contact has no user
    r3 = await service.check_completeness(CompletenessClient(None), _complete_rec())
    assert r3["status"] == "Incomplete" and any("no User assigned to the Contact" in i for i in r3["issues"])


@pytest.mark.asyncio
async def test_completeness_non_active_ignores_user_links():
    # Not Active -> user/contact-user not required; flags + contact still are.
    r = await service.check_completeness(CompletenessClient(), _complete_rec(mentorStatus="Candidate", assignedUserId=None))
    assert r == {"status": "Complete", "issues": []}


# --- approval -> user provisioning ---

class ProvisionClient:
    """Captures get/update/create/find_one/list for the approval flow."""

    def __init__(self, *, profile=None, contact=None, team={"id": "team1", "name": "Mentor Team"},
                 existing_users=frozenset()):
        self.profile = profile or {
            "id": "m1", "name": "Jane Doe", "mentorStatus": "Candidate",
            "assignedUserId": None, "cbmEmail": "", "contactRecordId": "c1",
        }
        self.contact = contact or {"id": "c1", "firstName": "Jane", "lastName": "Doe"}
        self.team = team
        self.existing_users = existing_users
        self.created = []
        self.updates = []

    async def get(self, entity, record_id, select=None):
        if entity == "Contact":
            return dict(self.contact)
        return dict(self.profile, id=record_id)

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        self.profile.update(payload)
        return dict(self.profile, id=record_id)

    async def create(self, entity, payload):
        self.created.append((entity, payload))
        return {"id": "user-new"}

    async def find_one(self, entity, attribute, value, select="id"):
        if entity == "Team":
            return self.team
        if entity == "User":
            return {"id": "u-x"} if value in self.existing_users else None
        return None

    async def list(self, entity, **kwargs):
        return {"list": [self.team] if (entity == "Team" and self.team) else []}


def _link_update(c):
    return next(u[2] for u in c.updates if u[2].get("assignedUserId"))


def _afactory(c):
    """An async factory that yields the given fake client (mirrors the router)."""
    async def f():
        return c
    return f


def test_cbm_email_for():
    assert service.cbm_email_for("Mary Jane", "O'Brien") == "maryjane.obrien@cbmentors.org"
    assert service.cbm_email_for("", "") == "mentor@cbmentors.org"


@pytest.mark.asyncio
async def test_approval_provisions_user():
    c = ProvisionClient()
    result = await service.update_mentor(c, "m1", {"mentorStatus": "Approved"}, team_name="Mentor Team", admin_client_factory=_afactory(c))
    assert len(c.created) == 1
    entity, payload = c.created[0]
    assert entity == "User"
    assert payload["userName"] == "jane.doe@cbmentors.org"
    assert payload["emailAddress"] == "jane.doe@cbmentors.org"
    assert payload["type"] == "regular" and payload["isActive"] is True
    assert payload["teamsIds"] == ["team1"] and payload["defaultTeamId"] == "team1"
    assert payload["sendAccessInfo"] is True
    link = _link_update(c)
    assert link["assignedUserId"] == "user-new"
    assert link["cbmEmail"] == "jane.doe@cbmentors.org"  # backfilled (was blank)
    assert result["provision"] == {
        "ok": True, "userId": "user-new", "userName": "jane.doe@cbmentors.org",
        "email": "jane.doe@cbmentors.org", "team": "Mentor Team",
    }


@pytest.mark.asyncio
async def test_no_admin_client_means_no_provisioning():
    """Without a privileged client, approval never tries to create a user."""
    c = ProvisionClient()
    res = await service.update_mentor(c, "m1", {"mentorStatus": "Approved"}, team_name="Mentor Team")
    assert c.created == [] and "provision" not in res


@pytest.mark.asyncio
async def test_approval_skips_when_user_already_linked():
    c = ProvisionClient(profile={"id": "m1", "name": "Jane Doe", "mentorStatus": "Candidate",
                                 "assignedUserId": "u9", "cbmEmail": "", "contactRecordId": "c1"})
    res = await service.update_mentor(c, "m1", {"mentorStatus": "Approved"}, team_name="Mentor Team", admin_client_factory=_afactory(c))
    assert c.created == [] and "provision" not in res


@pytest.mark.asyncio
async def test_non_approval_change_does_not_provision():
    c = ProvisionClient()
    await service.update_mentor(c, "m1", {"mentorStatus": "Active"}, team_name="Mentor Team", admin_client_factory=_afactory(c))
    assert c.created == []


@pytest.mark.asyncio
async def test_already_approved_without_user_provisions_on_resave():
    # Recovery: a mentor left Approved by a failed prior attempt (no user) gets
    # provisioned on the next save even if this save re-sends the same status.
    c = ProvisionClient(profile={"id": "m1", "name": "Jane Doe", "mentorStatus": "Approved",
                                 "assignedUserId": None, "cbmEmail": "", "contactRecordId": "c1"})
    res = await service.update_mentor(c, "m1", {"mentorStatus": "Approved"}, team_name="Mentor Team", admin_client_factory=_afactory(c))
    assert len(c.created) == 1 and res["provision"]["ok"] is True


@pytest.mark.asyncio
async def test_already_approved_provisions_on_unrelated_field_save():
    # Recovery via a non-status edit (the real-world case): mentor already
    # Approved, no user, save only changes cbmEmail -> still provisions.
    c = ProvisionClient(profile={"id": "m1", "name": "Jane Doe", "mentorStatus": "Approved",
                                 "assignedUserId": None, "cbmEmail": "", "contactRecordId": "c1"})
    res = await service.update_mentor(c, "m1", {"description": "note"}, team_name="Mentor Team", admin_client_factory=_afactory(c))
    assert len(c.created) == 1 and res["provision"]["ok"] is True


@pytest.mark.asyncio
async def test_username_collision_appends_suffix():
    c = ProvisionClient(existing_users={"jane.doe@cbmentors.org"})
    await service.update_mentor(c, "m1", {"mentorStatus": "Approved"}, team_name="Mentor Team", admin_client_factory=_afactory(c))
    assert c.created[0][1]["userName"] == "jane.doe2@cbmentors.org"


@pytest.mark.asyncio
async def test_existing_cbm_email_reused_and_not_backfilled():
    c = ProvisionClient(profile={"id": "m1", "name": "Jane Doe", "mentorStatus": "Candidate",
                                 "assignedUserId": None, "cbmEmail": "jdoe@cbmentors.org", "contactRecordId": "c1"})
    await service.update_mentor(c, "m1", {"mentorStatus": "Approved"}, team_name="Mentor Team", admin_client_factory=_afactory(c))
    assert c.created[0][1]["userName"] == "jdoe@cbmentors.org"
    assert "cbmEmail" not in _link_update(c)


@pytest.mark.asyncio
async def test_team_not_found_reports_error_without_failing_save():
    c = ProvisionClient(team=None)
    res = await service.update_mentor(c, "m1", {"mentorStatus": "Approved"}, team_name="Mentor Team", admin_client_factory=_afactory(c))
    assert c.created == []  # never reached user creation
    assert res["provision"]["ok"] is False
    assert "not found" in res["provision"]["error"].lower()


@pytest.mark.asyncio
async def test_admin_login_failure_is_captured_and_status_still_saved():
    """A failed service-admin login surfaces as a provision error, not a 500."""
    c = ProvisionClient()

    async def bad_factory():
        raise RuntimeError("Service account credentials were rejected.")

    res = await service.update_mentor(
        c, "m1", {"mentorStatus": "Approved"}, team_name="Mentor Team",
        admin_client_factory=bad_factory,
    )
    assert c.created == []
    # the status write still happened (not rolled back)
    assert any(u[2].get("mentorStatus") == "Approved" for u in c.updates)
    assert res["provision"]["ok"] is False
    assert "rejected" in res["provision"]["error"].lower()


# --- router tests ---

def _app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")  # enables session + router
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


def _authed(monkeypatch):
    monkeypatch.setattr("mentoradmin.router.current_user", lambda request, key=None: _USER)
    monkeypatch.setattr("mentoradmin.router.client_for", lambda settings, user: object())


def test_requires_auth(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/mentoradmin/api/mentors").status_code == 401
        assert c.get("/mentoradmin/api/session").status_code == 401


def test_lists_mentors(monkeypatch):
    _authed(monkeypatch)

    async def fake_list(client):
        return [{"id": "m1", "name": "Jane", "status": "Active"}]

    monkeypatch.setattr("mentoradmin.router.assign_service.list_all_mentors", fake_list)
    with TestClient(_app(monkeypatch)) as c:
        data = c.get("/mentoradmin/api/mentors").json()
    assert data["mentors"][0]["name"] == "Jane"


def test_fields_endpoint_returns_spec_and_options(monkeypatch):
    _authed(monkeypatch)

    async def fake_opts(client):
        return {"mentorStatus": ["Active", "Inactive"]}

    monkeypatch.setattr("mentoradmin.router.service.field_options", fake_opts)
    with TestClient(_app(monkeypatch)) as c:
        data = c.get("/mentoradmin/api/fields").json()
    assert data["options"]["mentorStatus"] == ["Active", "Inactive"]
    assert any(f["name"] == "mentorStatus" for f in data["fields"])


def test_get_and_update_mentor(monkeypatch):
    _authed(monkeypatch)

    async def fake_get(client, mentor_id):
        return {"id": mentor_id, "name": "Jane", "mentorStatus": "Active"}

    async def fake_update(client, mentor_id, changes, **kwargs):
        return {"id": mentor_id, "name": "Jane", **changes}

    monkeypatch.setattr("mentoradmin.router.service.get_mentor", fake_get)
    monkeypatch.setattr("mentoradmin.router.service.update_mentor", fake_update)
    with TestClient(_app(monkeypatch)) as c:
        got = c.get("/mentoradmin/api/mentors/m1").json()
        r = c.put("/mentoradmin/api/mentors/m1", json={"changes": {"mentorStatus": "Inactive"}})
    assert got["mentorStatus"] == "Active"
    # the router attaches a completeness summary to both responses
    assert got["completeness"]["status"] in ("Complete", "Incomplete")
    assert r.json()["mentorStatus"] == "Inactive"
    assert "completeness" in r.json()


def test_expired_token_returns_401(monkeypatch):
    _authed(monkeypatch)

    async def boom(client):
        raise EspoError("list CMentorProfile failed: HTTP 401 Unauthorized")

    monkeypatch.setattr("mentoradmin.router.assign_service.list_all_mentors", boom)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentoradmin/api/mentors")
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


def test_other_crm_error_returns_502(monkeypatch):
    _authed(monkeypatch)

    async def boom(client):
        raise EspoError("list CMentorProfile failed: HTTP 500 Server Error")

    monkeypatch.setattr("mentoradmin.router.assign_service.list_all_mentors", boom)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentoradmin/api/mentors")
    assert r.status_code == 502


def test_login_gated_to_mentor_admin_team(monkeypatch):
    """Login passes the Mentor Administration Team as the allowed team."""
    captured = {}

    async def fake_auth(settings, username, password, *, allowed_teams=None, allowed_roles=None):
        captured["teams"] = allowed_teams
        captured["roles"] = allowed_roles
        return _USER

    monkeypatch.setattr("mentoradmin.router.authenticate", fake_auth)
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/mentoradmin/api/login", json={"username": "boss", "password": "pw"})
    assert r.status_code == 200
    assert captured["teams"] == ["Mentor Administration Team"]
    assert captured["roles"] == []
