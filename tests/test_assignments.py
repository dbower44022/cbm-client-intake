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
    # Both assignment attributes are written; EspoCRM keeps whichever the instance
    # has (collaborators on crm-test, single assignedUser on prod).
    assert payload["assignedUsersIds"] == ["user-99"]
    assert payload["assignedUserId"] == "user-99"
    assert payload["mentorProfileId"] == "mentor-1"

    # Contacts (primary + extra, deduped) each reassigned via single assignedUser.
    contact_updates = {u[1]: u[2] for u in client.updates if u[0] == service.CONTACT}
    assert set(contact_updates) == {"contact-primary", "contact-extra"}
    assert all(p["assignedUserId"] == "user-99" for p in contact_updates.values())

    # Client profile AND account get both assignment attributes — both have
    # assignedUser disabled on prod (collaborators field), so writing only the
    # single attribute would silently no-op there.
    assert ("CClientProfile", "clientprofile-1",
            {"assignedUsersIds": ["user-99"], "assignedUserId": "user-99"}) in client.updates
    assert ("Account", "account-1",
            {"assignedUsersIds": ["user-99"], "assignedUserId": "user-99"}) in client.updates

    assert res["contactsUpdated"] == 2
    assert res["clientProfileUpdated"] is True
    assert res["accountUpdated"] is True
    assert res["engagementStatus"] == "Pending Acceptance"


async def test_assign_reports_partial_reassignment_failures():
    """A CRM failure re-homing a related record is captured + reported, not
    raised — the core assignment (engagement → Pending Acceptance) still stands."""
    from core.espo import EspoError

    class FlakyClient(FakeClient):
        async def update(self, entity, record_id, payload):
            if entity == service.CONTACT and record_id == "contact-extra":
                raise EspoError("update Contact/contact-extra failed: HTTP 403 denied")
            return await super().update(entity, record_id, payload)

    client = FlakyClient(
        mentor=_mentor(),
        engagement={
            "primaryEngagementContactId": "contact-primary",
            "engagementClientId": "clientprofile-1",
            "clientOrganizationId": "account-1",
        },
        related={"list": [{"id": "contact-primary"}, {"id": "contact-extra"}]},
    )

    res = await service.assign_engagement(client, "eng-1", "mentor-1")

    # The engagement itself was assigned despite the downstream failure.
    assert res["engagementStatus"] == "Pending Acceptance"
    # One contact succeeded, one failed and is reported (the rest still re-homed).
    assert res["contactsUpdated"] == 1
    assert res["contactsTotal"] == 2
    assert res["clientProfileUpdated"] is True
    assert res["accountUpdated"] is True
    assert len(res["reassignmentErrors"]) == 1
    assert res["reassignmentErrors"][0]["entity"] == service.CONTACT
    assert res["reassignmentErrors"][0]["id"] == "contact-extra"


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
                        "currentActiveClients": 2,
                        "maximumClientCapacity": 5,
                        "yearsOfExperience": 10,
                        "mentorType": "Mentor",
                        "mentorStatus": "Active",
                        "acceptingNewClients": True,
                        "industrySector": "Manufacturing",
                        "mentoringFocusAreas": ["Agriculture"],
                        "areaOfExpertise": ["Lean"],
                    },
                    # Userless row: must be dropped in Python (the query no longer
                    # filters on assignedUserId — prod forbids it in `where`).
                    {"id": "m2", "name": "No User", "assignedUserId": None,
                     "mentorStatus": "Active", "acceptingNewClients": True},
                ]
            }
        }
    )
    mentors = await service.list_eligible_mentors(client)
    assert mentors == [
        {
            "id": "m1", "name": "Tommy Tranell", "createdAt": None, "userId": "u1", "userName": "Tommy Tranell",
            "availableCapacity": 4, "assignedClients": 2, "maxCapacity": 5,
            "yearsOfExperience": 10, "mentorType": "Mentor", "status": "Active",
            "acceptingNewClients": True, "recordStatus": None, "industrySector": "Manufacturing",
            "focusAreas": ["Agriculture"], "expertise": ["Lean"],
        }
    ]
    # The query filters acceptingNewClients + Active; the has-user filter is done
    # in Python, NOT in `where` — prod EspoCRM forbids filtering CMentorProfile by
    # assignedUserId ("Forbidden attribute 'assignedUserId' in where" → 400).
    _, where = client.list_calls[0]
    attrs = {(c["attribute"], c["type"]) for c in where}
    assert ("acceptingNewClients", "isTrue") in attrs
    assert ("mentorStatus", "equals") in attrs
    assert ("assignedUserId", "isNotNull") not in attrs


def test_assigned_user_id_reads_either_field_shape():
    # Single assignedUser (crm-test) and multi-user assignedUsers (prod) both resolve.
    assert service.assigned_user_id({"assignedUserId": "u1"}) == "u1"
    assert service.assigned_user_id({"assignedUsersIds": ["u2"]}) == "u2"
    assert service.assigned_user_id({"assignedUsersIds": []}) is None
    assert service.assigned_user_id({}) is None
    assert service.assigned_user_name(
        {"assignedUsersIds": ["u2"], "assignedUsersNames": {"u2": "Pat Smith"}}
    ) == "Pat Smith"


@pytest.mark.asyncio
async def test_eligible_mentor_with_only_collaborators_field_is_included():
    """A prod mentor whose User is on assignedUsers (assignedUser disabled) must
    still resolve a userId and appear in the dropdown."""
    client = FakeClient(lists={service.MENTOR_PROFILE: {"list": [
        {"id": "m1", "name": "Collab Mentor", "assignedUserId": None,
         "assignedUsersIds": ["u7"], "assignedUsersNames": {"u7": "Collab Mentor"},
         "mentorStatus": "Active", "acceptingNewClients": True},
    ]}})
    mentors = await service.list_eligible_mentors(client)
    assert len(mentors) == 1
    assert mentors[0]["userId"] == "u7"
    assert mentors[0]["userName"] == "Collab Mentor"


async def test_list_all_mentors_has_no_where_filter():
    client = FakeClient(
        lists={
            service.MENTOR_PROFILE: {
                "list": [
                    {"id": "m1", "name": "Cand", "mentorStatus": "Candidate",
                     "acceptingNewClients": False},
                ]
            }
        }
    )
    rows = await service.list_all_mentors(client)
    assert [r["status"] for r in rows] == ["Candidate"]
    assert rows[0]["acceptingNewClients"] is False
    # No eligibility where-clause — the review list spans all statuses.
    _, where = client.list_calls[0]
    assert where == []


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


async def test_requested_mentor_absent_is_none():
    client = FakeClient(engagement={"name": "Y"})
    d = await service.get_engagement_detail(client, "e1")
    assert d["requestedMentor"] is None


async def test_requested_mentor_uses_inline_name_without_extra_read():
    client = FakeClient(engagement={
        "name": "Y", "requestedMentorId": "m1", "requestedMentorName": "Bob Mentor",
    })
    d = await service.get_engagement_detail(client, "e1")
    assert d["requestedMentor"] == {"id": "m1", "name": "Bob Mentor"}
    # No CMentorProfile read needed when the name accessor is present.
    assert not any(u for u in client.list_calls if u[0] == service.MENTOR_PROFILE)


async def test_requested_mentor_resolves_name_via_profile_read():
    client = FakeClient(
        engagement={"name": "Y", "requestedMentorId": "m1"},  # no inline name
        mentor={"name": "Bob Mentor"},
    )
    d = await service.get_engagement_detail(client, "e1")
    assert d["requestedMentor"] == {"id": "m1", "name": "Bob Mentor"}


async def test_requested_mentor_orphaned_link_resolves_to_no_name():
    from core.espo import EspoError

    class OrphanClient(FakeClient):
        async def get(self, entity, record_id, select=None):
            if entity == service.MENTOR_PROFILE:
                raise EspoError("get CMentorProfile/m1 failed: HTTP 404 Not Found")
            return await super().get(entity, record_id, select=select)

    client = OrphanClient(engagement={"name": "Y", "requestedMentorId": "m1"})
    d = await service.get_engagement_detail(client, "e1")
    assert d["requestedMentor"] == {"id": "m1", "name": None}


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
