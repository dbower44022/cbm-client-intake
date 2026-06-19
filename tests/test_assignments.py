"""Tests for the mentor assignment tool: service writes, mentor query, auth gate."""

from __future__ import annotations

import pytest

from assignments import auth, service
from core.config import Settings


class FakeClient:
    """Mock of the EspoClient slice the service uses; records get/list/update calls."""

    def __init__(self, *, mentor=None, engagement=None, contact=None, related=None, lists=None):
        self._mentor = mentor or {}
        self._engagement = engagement or {}
        self._contact = contact
        self._related = related or {"list": []}
        self._lists = lists or {}
        self.updates: list[tuple[str, str, dict]] = []
        self.list_calls: list[tuple[str, list]] = []

    async def get(self, entity, record_id, select=None):
        if entity == service.MENTOR_PROFILE:
            return {"id": record_id, **self._mentor}
        if entity == service.ENGAGEMENT:
            return {"id": record_id, **self._engagement}
        if entity == service.CONTACT and self._contact is not None:
            return {"id": record_id, **self._contact}
        return {"id": record_id}

    async def list(self, entity, *, where=None, **kwargs):
        self.list_calls.append((entity, where or []))
        return self._lists.get(entity, {"total": 0, "list": []})

    async def list_related(self, entity, record_id, link, **kwargs):
        return self._related

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        return {"id": record_id, **payload}


def _mentor(**overrides):
    base = dict(
        name="Matt Mentor",
        acceptingNewClients=True,
        mentorStatus="Active",
        assignedUserId="user-99",
        assignedUserName="Matt Mentor",
    )
    base.update(overrides)
    return base


# --- assign_engagement -------------------------------------------------------

async def test_assign_sets_engagement_and_reassigns_related():
    client = FakeClient(
        mentor=_mentor(),
        engagement={
            "primaryEngagementContactId": "contact-primary",
            "engagementClientId": "clientprofile-1",
            "clientOrganizationId": "account-1",
        },
        related={"list": [{"id": "contact-primary"}, {"id": "contact-extra"}]},
    )

    res = await service.assign_engagement(client, "eng-1", "mentor-1")

    # Engagement update: status + mentor profile + assignedUsers (NOT the
    # disabled single assignedUser).
    eng_updates = [u for u in client.updates if u[0] == service.ENGAGEMENT]
    assert len(eng_updates) == 1
    _, eng_id, payload = eng_updates[0]
    assert eng_id == "eng-1"
    assert payload["engagementStatus"] == "Pending Acceptance"
    assert payload["assignedUsersIds"] == ["user-99"]
    assert "assignedUserId" not in payload
    assert payload["mentorProfileId"] == "mentor-1"

    # Contacts (primary + extra, deduped) each reassigned via single assignedUser.
    contact_updates = {u[1]: u[2] for u in client.updates if u[0] == service.CONTACT}
    assert set(contact_updates) == {"contact-primary", "contact-extra"}
    assert all(p["assignedUserId"] == "user-99" for p in contact_updates.values())

    # Client profile uses assignedUsers (assignedUser disabled); account uses single.
    assert ("CClientProfile", "clientprofile-1", {"assignedUsersIds": ["user-99"]}) in client.updates
    assert ("Account", "account-1", {"assignedUserId": "user-99"}) in client.updates

    assert res["contactsUpdated"] == 2
    assert res["clientProfileUpdated"] is True
    assert res["accountUpdated"] is True
    assert res["engagementStatus"] == "Pending Acceptance"


async def test_assign_skips_account_when_absent():
    client = FakeClient(
        mentor=_mentor(),
        engagement={
            "primaryEngagementContactId": "contact-primary",
            "engagementClientId": "clientprofile-1",
            "clientOrganizationId": None,
        },
        related={"list": [{"id": "contact-primary"}]},
    )

    res = await service.assign_engagement(client, "eng-2", "mentor-2")

    assert res["accountUpdated"] is False
    assert not [u for u in client.updates if u[0] == "Account"]
    assert res["clientProfileUpdated"] is True
    assert res["contactsUpdated"] == 1


async def test_assign_rejects_mentor_without_user():
    client = FakeClient(mentor=_mentor(assignedUserId=None))
    with pytest.raises(service.AssignError):
        await service.assign_engagement(client, "eng-3", "mentor-3")
    assert client.updates == []  # nothing written


async def test_assign_rejects_ineligible_mentor():
    client = FakeClient(mentor=_mentor(acceptingNewClients=False))
    with pytest.raises(service.AssignError):
        await service.assign_engagement(client, "eng-4", "mentor-4")
    assert client.updates == []


# --- queries -----------------------------------------------------------------

async def test_eligible_mentors_query_and_shape():
    client = FakeClient(
        lists={
            service.MENTOR_PROFILE: {
                "list": [
                    {
                        "id": "m1",
                        "name": "Tommy Tranell",
                        "assignedUserId": "u1",
                        "assignedUserName": "Tommy Tranell",
                        "availableCapacity": 4,
                    }
                ]
            }
        }
    )
    mentors = await service.list_eligible_mentors(client)
    assert mentors == [
        {"id": "m1", "name": "Tommy Tranell", "userId": "u1", "userName": "Tommy Tranell", "availableCapacity": 4}
    ]
    # The query filters acceptingNewClients + Active + has-user.
    _, where = client.list_calls[0]
    attrs = {(c["attribute"], c["type"]) for c in where}
    assert ("acceptingNewClients", "isTrue") in attrs
    assert ("mentorStatus", "equals") in attrs
    assert ("assignedUserId", "isNotNull") in attrs


async def test_list_engagements_query_and_shape():
    client = FakeClient(
        lists={
            service.ENGAGEMENT: {
                "list": [
                    {
                        "id": "e1",
                        "name": "Sharon Rose — Intake",
                        "createdAt": "2026-06-18 19:18:39",
                        "engagementStatus": "Submitted",
                        "primaryEngagementContactName": "Sharon Rose",
                        "engagementClientName": "Rose LLC",
                    }
                ]
            }
        }
    )
    rows = await service.list_engagements(client, ["Submitted", "Pending Acceptance"])
    assert rows[0] == {
        "id": "e1",
        "name": "Sharon Rose — Intake",
        "createdAt": "2026-06-18 19:18:39",
        "status": "Submitted",
        "contactName": "Sharon Rose",
        "clientName": "Rose LLC",
    }
    entity, where = client.list_calls[0]
    assert entity == service.ENGAGEMENT
    # Multi-status filter -> an `in` clause over the selected statuses.
    assert {"type": "in", "attribute": "engagementStatus",
            "value": ["Submitted", "Pending Acceptance"]} in where


# --- engagement detail -------------------------------------------------------

async def test_get_engagement_detail_shape():
    client = FakeClient(
        engagement={
            "name": "Sharon Rose — Intake",
            "engagementStatus": "Submitted",
            "createdAt": "2026-06-18 19:18:39",
            "meetingCadence": "Weekly",
            "mentoringFocusAreas": ["Accounting & Tax Services", "Marketing"],
            "mentoringNeedsDescription": "<p>I need help with my books.</p>",
            "engagementNotes": "<p>Client asked for Bob.</p>",
            "primaryEngagementContactId": "c1",
            "engagementClientName": "Rose LLC",
        },
        contact={
            "name": "Sharon Rose", "emailAddress": "sharon@example.com",
            "phoneNumber": "+12165550000", "accountName": "Rose LLC", "title": "Owner",
        },
    )
    d = await service.get_engagement_detail(client, "e1")
    assert d["status"] == "Submitted"
    assert d["contact"] == {
        "name": "Sharon Rose", "email": "sharon@example.com",
        "phone": "+12165550000", "company": "Rose LLC", "title": "Owner",
    }
    assert d["focusAreas"] == ["Accounting & Tax Services", "Marketing"]
    assert d["needs"] == "<p>I need help with my books.</p>"
    assert d["notes"] == "<p>Client asked for Bob.</p>"


async def test_get_engagement_detail_no_contact():
    client = FakeClient(engagement={"name": "X", "primaryEngagementContactId": None})
    d = await service.get_engagement_detail(client, "e2")
    assert d["contact"] is None
    assert d["focusAreas"] == []
    assert d["needs"] == ""
    assert d["notes"] == ""


async def test_get_engagement_detail_single_focus_string_coerced():
    client = FakeClient(engagement={"name": "Y", "mentoringFocusAreas": "Marketing"})
    d = await service.get_engagement_detail(client, "e3")
    assert d["focusAreas"] == ["Marketing"]


# --- auth team/role gate -----------------------------------------------------

def _settings(teams="", roles=""):
    return Settings(
        assign_allowed_teams=teams, assign_allowed_roles=roles, session_secret="x"
    )


def _app_user(monkeypatch, payload, status=200):
    class FakeResp:
        status_code = status
        def json(self):
            return payload

    async def fake_app_user(base_url, headers, timeout):
        return FakeResp()

    monkeypatch.setattr(auth, "_app_user", fake_app_user)


def _user(**overrides):
    """A fake user payload. teamsNames/rolesNames are always present (possibly
    empty) so the live User-record fallback never fires in unit tests."""
    base = {"id": "u1", "userName": "jdoe", "name": "Jane Doe",
            "isActive": True, "type": "regular",
            "teamsNames": {}, "rolesNames": {}}
    base.update(overrides)
    return base


async def test_auth_accepts_user_in_allowed_team(monkeypatch):
    _app_user(monkeypatch, {
        "token": "tok-1",
        "user": _user(teamsNames={"t1": "Client Administration Team"}),
    })
    user = await auth.authenticate(
        _settings(teams="Client Administration Team"), "jdoe", "pw"
    )
    assert user["userId"] == "u1"
    assert user["token"] == "tok-1"
    assert user["isAdmin"] is False
    assert user["teams"] == ["Client Administration Team"]


async def test_auth_accepts_user_with_allowed_role(monkeypatch):
    _app_user(monkeypatch, {
        "token": "tok-1b",
        "user": _user(rolesNames={"r1": "Staff"}),
    })
    user = await auth.authenticate(_settings(roles="Staff"), "jdoe", "pw")
    assert user["isAdmin"] is False


async def test_auth_accepts_admin_regardless_of_team_or_role(monkeypatch):
    _app_user(monkeypatch, {
        "token": "tok-2",
        "user": _user(userName="admin", name="Admin", type="admin"),
    })
    user = await auth.authenticate(
        _settings(teams="Client Administration Team"), "admin", "pw"
    )
    assert user["isAdmin"] is True


async def test_auth_rejects_regular_user_not_in_team_or_role(monkeypatch):
    _app_user(monkeypatch, {
        "token": "tok-3",
        "user": _user(userName="nobody", teamsNames={"t9": "Sales"},
                      rolesNames={"r9": "Mentors"}),
    })
    with pytest.raises(auth.AuthError):
        await auth.authenticate(
            _settings(teams="Client Administration Team", roles="Staff"), "nobody", "pw"
        )


async def test_auth_rejects_inactive_user(monkeypatch):
    _app_user(monkeypatch, {
        "token": "tok-4",
        "user": _user(userName="old", isActive=False,
                      teamsNames={"t1": "Client Administration Team"}),
    })
    with pytest.raises(auth.AuthError):
        await auth.authenticate(_settings(teams="Client Administration Team"), "old", "pw")


async def test_auth_rejects_portal_or_api_type(monkeypatch):
    _app_user(monkeypatch, {
        "token": "tok-5",
        "user": _user(userName="portal", type="portal",
                      teamsNames={"t1": "Client Administration Team"}),
    })
    with pytest.raises(auth.AuthError):
        await auth.authenticate(_settings(teams="Client Administration Team"), "portal", "pw")


async def test_auth_rejects_bad_credentials(monkeypatch):
    _app_user(monkeypatch, {"message": "unauthorized"}, status=401)
    with pytest.raises(auth.AuthError):
        await auth.authenticate(_settings(teams="Client Administration Team"), "jdoe", "wrong")
