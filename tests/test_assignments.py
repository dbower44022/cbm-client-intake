"""Tests for the mentor assignment tool: service writes, mentor query, auth gate."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from assignments import auth, service
from core.config import Settings, get_settings


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
            "engagementStatus": "Submitted",
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
    # The assignment stamps engagementAssignedDate (feeds the Assigned-last-30
    # metric) in EspoCRM's UTC datetime format.
    import re
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", payload["engagementAssignedDate"])

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


async def test_assign_preserves_comentor_users():
    """Reassigning a mentor must not strip co-mentors out of assignedUsers —
    their engagement-list visibility (Mentor Role read=own) rides on it."""

    class Client(FakeClient):
        async def list_related(self, entity, record_id, link, **kwargs):
            if link == "additionalMentors":
                return {"list": [
                    {"id": "mentor-co", "assignedUsersIds": ["user-co"]},
                    {"id": "mentor-unlinked", "assignedUsersIds": []},
                ]}
            return await super().list_related(entity, record_id, link, **kwargs)

    client = Client(mentor=_mentor(), engagement={"engagementStatus": "Submitted"})
    await service.assign_engagement(client, "eng-1", "mentor-1")

    payload = [u for u in client.updates if u[0] == service.ENGAGEMENT][0][2]
    assert payload["assignedUsersIds"] == ["user-99", "user-co"]
    assert payload["assignedUserId"] == "user-99"


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
            "engagementStatus": "Submitted",
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
            "engagementStatus": "Submitted",
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
    client = FakeClient(
        mentor=_mentor(assignedUserId=None),
        engagement={"engagementStatus": "Submitted"},
    )
    with pytest.raises(service.AssignError):
        await service.assign_engagement(client, "eng-3", "mentor-3")
    assert client.updates == []  # nothing written


async def test_assign_rejects_ineligible_mentor():
    client = FakeClient(
        mentor=_mentor(acceptingNewClients=False),
        engagement={"engagementStatus": "Submitted"},
    )
    with pytest.raises(service.AssignError):
        await service.assign_engagement(client, "eng-4", "mentor-4")
    assert client.updates == []


async def test_assign_rejects_already_assigned_engagement():
    """A stale grid (second browser/tab) must not overwrite a saved assignment:
    the engagement is re-read before any write, and an existing mentorProfile
    rejects the whole call naming the current mentor."""
    client = FakeClient(
        mentor=_mentor(),
        engagement={
            "engagementStatus": "Pending Acceptance",
            "mentorProfileId": "mentor-first",
            "mentorProfileName": "First Mentor",
        },
    )
    with pytest.raises(service.AssignError, match="First Mentor"):
        await service.assign_engagement(client, "eng-5", "mentor-second")
    assert client.updates == []  # nothing written, first assignment intact


async def test_assign_rejects_non_submitted_engagement():
    """Unassigned but no longer Submitted (e.g. a staffer parked it On-Hold
    between the grid load and the Assign click) — also rejected, message names
    the current status."""
    client = FakeClient(
        mentor=_mentor(),
        engagement={"engagementStatus": "On-Hold"},
    )
    with pytest.raises(service.AssignError, match="On-Hold"):
        await service.assign_engagement(client, "eng-6", "mentor-1")
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
                        "maximumClientCapacity": 5,
                        "yearsOfExperience": 10,
                        "mentorType": "Mentor",
                        "mentorStatus": "Active",
                        "acceptingNewClients": True,
                        "cbmEmail": "tommy.tranell@cbmentors.org",
                        "industrySector": "Manufacturing",
                        "industryExperience": ["Manufacturing", "Retail Trade"],
                        "mentoringFocusAreas": ["Agriculture"],
                        "areaOfExpertise": ["Lean"],
                    },
                    # Userless row: must be dropped in Python (the query no longer
                    # filters on assignedUserId — prod forbids it in `where`).
                    {"id": "m2", "name": "No User", "assignedUserId": None,
                     "mentorStatus": "Active", "acceptingNewClients": True},
                ]
            },
            # One active engagement for m1 → activeClients 1, available 5-1=4.
            service.ENGAGEMENT: {
                "list": [{"mentorProfileId": "m1", "engagementStatus": "Active"}]
            },
        }
    )
    res = await service.list_eligible_mentors(client)
    assert res["metricsAvailable"] is True
    assert res["mentors"] == [
        {
            "id": "m1", "name": "Tommy Tranell", "createdAt": None, "userId": "u1", "userName": "Tommy Tranell",
            "activeClients": 1, "assignedLast30": 0, "lifetimeClients": 1,
            "availableCapacity": 4, "maxCapacity": 5,
            "yearsOfExperience": 10, "mentorType": "Mentor", "status": "Active",
            "acceptingNewClients": True, "recordStatus": None,
            "cbmEmail": "tommy.tranell@cbmentors.org", "industrySector": "Manufacturing",
            "industryExperience": ["Manufacturing", "Retail Trade"],
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
    mentors = (await service.list_eligible_mentors(client))["mentors"]
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
    rows = (await service.list_all_mentors(client))["mentors"]
    assert [r["status"] for r in rows] == ["Candidate"]
    assert rows[0]["acceptingNewClients"] is False
    # No eligibility where-clause — the review list spans all statuses.
    _, where = client.list_calls[0]
    assert where == []


async def test_mentor_type_options_in_roster_envelope():
    """The roster envelope carries the CRM's full mentorType enum (blanks
    dropped) so the grid filters can offer types no current mentor has."""

    class MetaClient(FakeClient):
        async def metadata_enum_options(self, entity, field):
            assert (entity, field) == (service.MENTOR_PROFILE, "mentorType")
            return ["", "Mentor", "Co-Mentor Only", "Presenter", "Volunteer", "Other"]

    res = await service.list_all_mentors(MetaClient())
    assert res["mentorTypeOptions"] == [
        "Mentor", "Co-Mentor Only", "Presenter", "Volunteer", "Other"
    ]


async def test_mentor_type_options_empty_without_metadata_access():
    # FakeClient has no metadata_enum_options — the envelope still serves, with
    # [] so the frontend falls back to the values found in the rows.
    res = await service.list_all_mentors(FakeClient())
    assert res["mentorTypeOptions"] == []


# --- mentor engagement metrics -------------------------------------------------

def _eng(mentor_id, status, assigned=None):
    return {"mentorProfileId": mentor_id, "engagementStatus": status,
            "engagementAssignedDate": assigned}


async def test_mentor_engagement_metrics_grouping_and_windows():
    from datetime import datetime, timedelta, timezone

    recent = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
    old = (datetime.now(timezone.utc) - timedelta(days=45)).strftime("%Y-%m-%d %H:%M:%S")
    client = FakeClient(lists={service.ENGAGEMENT: {"list": [
        _eng("m1", "Active", recent),            # active + assigned last 30
        _eng("m1", "Assigned", old),             # active, too old for last-30
        _eng("m1", "Pending Acceptance", None),  # active, no date -> not last-30
        _eng("m1", "Completed", recent),         # lifetime only (not an active status)
        _eng("m2", "Declined", None),            # lifetime only
        _eng(None, "Active", recent),            # unlinked -> counts toward nobody
    ]}})
    metrics = await service.mentor_engagement_metrics(client)
    assert metrics == {
        "m1": {"activeClients": 3, "assignedLast30": 1, "lifetimeClients": 4},
        "m2": {"activeClients": 0, "assignedLast30": 0, "lifetimeClients": 1},
    }


async def test_mentor_engagement_metrics_paginates():
    """A roster with more engagements than one page walks every page via offset."""

    class PagedClient(FakeClient):
        async def list(self, entity, *, where=None, offset=0, max_size=200, **kw):
            self.list_calls.append((entity, offset))
            rows = [_eng("m1", "Active")] * 450
            return {"list": rows[offset:offset + max_size]}

    client = PagedClient()
    metrics = await service.mentor_engagement_metrics(client)
    assert metrics["m1"]["activeClients"] == 450
    assert metrics["m1"]["lifetimeClients"] == 450
    assert [offset for _, offset in client.list_calls] == [0, 200, 400]


async def test_metrics_failure_leaves_roster_with_blank_counts():
    """No CEngagement read grant -> the roster still loads; metrics are None and
    the envelope says so (the UI shows blanks, not zeros)."""
    from core.espo import EspoError

    class NoEngClient(FakeClient):
        async def list(self, entity, **kwargs):
            if entity == service.ENGAGEMENT:
                raise EspoError("list CEngagement failed: HTTP 403 forbidden")
            return await super().list(entity, **kwargs)

    client = NoEngClient(lists={service.MENTOR_PROFILE: {"list": [
        {"id": "m1", "name": "Jane", "maximumClientCapacity": 5, "mentorStatus": "Active"},
    ]}})
    res = await service.list_all_mentors(client)
    assert res["metricsAvailable"] is False
    row = res["mentors"][0]
    assert row["activeClients"] is None
    assert row["assignedLast30"] is None
    assert row["lifetimeClients"] is None
    assert row["availableCapacity"] is None
    assert row["maxCapacity"] == 5  # the stored field still shows


async def test_available_capacity_unlimited_and_blank_semantics():
    client = FakeClient(lists={
        service.MENTOR_PROFILE: {"list": [
            {"id": "m1", "name": "Unlimited", "maximumClientCapacity": -1},
            {"id": "m2", "name": "NoMax"},
        ]},
        service.ENGAGEMENT: {"list": [_eng("m1", "Active")]},
    })
    rows = (await service.list_all_mentors(client))["mentors"]
    by_id = {r["id"]: r for r in rows}
    assert by_id["m1"]["availableCapacity"] == -1    # -1 = unlimited, passed through
    assert by_id["m2"]["availableCapacity"] is None  # no max -> not computable
    assert by_id["m2"]["activeClients"] == 0         # metrics known, just zero


def test_parse_espo_datetime():
    from datetime import timezone

    dt = service._parse_espo_datetime("2026-06-19 12:30:00")
    assert dt.tzinfo == timezone.utc and dt.hour == 12
    assert service._parse_espo_datetime(None) is None
    assert service._parse_espo_datetime("not-a-date") is None


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
                    },
                    {
                        "id": "e2",
                        "name": "Al Green — Intake",
                        "createdAt": "2026-06-17 10:00:00",
                        "engagementStatus": "Pending Acceptance",
                        "primaryEngagementContactName": "Al Green",
                        "engagementClientName": "Green Co",
                        "mentorProfileId": "mp9",
                        "mentorProfileName": "Pat Mentor",
                        "engagementAssignedDate": "2026-06-17 12:30:00",
                        "description": "Prefers evening calls.",
                    },
                ]
            }
        }
    )
    rows = await service.list_engagements(client, ["Submitted", "Pending Acceptance"])
    # Unassigned engagement -> no mentor (the row renders the picker).
    assert rows[0] == {
        "id": "e1",
        "name": "Sharon Rose — Intake",
        "createdAt": "2026-06-18 19:18:39",
        "status": "Submitted",
        "contactName": "Sharon Rose",
        "clientName": "Rose LLC",
        "mentorId": None,
        "mentorName": None,
        "assignedDate": None,
        "notes": "",
    }
    # Assigned engagement -> mentor surfaced (the row shows the name, no picker).
    assert rows[1]["mentorId"] == "mp9" and rows[1]["mentorName"] == "Pat Mentor"
    # When the assignment happened (the grid's Assigned Date column).
    assert rows[1]["assignedDate"] == "2026-06-17 12:30:00"
    # Internal process notes come from CEngagement.description (Notes column).
    assert rows[1]["notes"] == "Prefers evening calls."
    entity, where = client.list_calls[0]
    assert entity == service.ENGAGEMENT
    # Multi-status filter -> an `in` clause over the selected statuses.
    assert {"type": "in", "attribute": "engagementStatus",
            "value": ["Submitted", "Pending Acceptance"]} in where


async def test_update_engagement_notes_writes_description():
    client = FakeClient()
    res = await service.update_engagement_notes(client, "e1", "Call back next week.")
    assert client.updates == [
        (service.ENGAGEMENT, "e1", {"description": "Call back next week."})
    ]
    assert res == {"engagementId": "e1", "notes": "Call back next week."}
    # Empty string clears the notes (a legitimate save, not a no-op).
    await service.update_engagement_notes(client, "e1", "")
    assert client.updates[-1] == (service.ENGAGEMENT, "e1", {"description": ""})


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
            "description": "Called 7/14 — left voicemail.",
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
    # The grid's internal process notes (description) surface in the popup too.
    assert d["internalNotes"] == "Called 7/14 — left voicemail."


async def test_get_engagement_detail_no_contact():
    client = FakeClient(engagement={"name": "X", "primaryEngagementContactId": None})
    d = await service.get_engagement_detail(client, "e2")
    assert d["contact"] is None
    assert d["focusAreas"] == []
    assert d["needs"] == ""
    assert d["notes"] == ""
    assert d["internalNotes"] == ""


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


async def test_auth_ungated_accepts_any_active_internal_user(monkeypatch):
    """The portal signs in any active internal user (gate=False); team checks
    happen per request in each staff app instead."""
    _app_user(monkeypatch, {
        "token": "tok-6",
        "user": _user(userName="mentor", teamsNames={"t9": "Mentor Team"}),
    })
    user = await auth.authenticate(
        _settings(teams="Client Administration Team"), "mentor", "pw", gate=False
    )
    assert user["teams"] == ["Mentor Team"]


async def test_auth_ungated_still_rejects_inactive_and_portal_types(monkeypatch):
    _app_user(monkeypatch, {"token": "t", "user": _user(isActive=False)})
    with pytest.raises(auth.AuthError):
        await auth.authenticate(_settings(), "x", "pw", gate=False)
    _app_user(monkeypatch, {"token": "t", "user": _user(type="portal")})
    with pytest.raises(auth.AuthError):
        await auth.authenticate(_settings(), "x", "pw", gate=False)


def test_is_member_team_role_and_admin():
    assert auth.is_member({"isAdmin": True}, ["Team A"])
    assert auth.is_member({"teams": ["Team A"]}, ["Team A"])
    assert auth.is_member({"roles": ["Role R"]}, [], ["Role R"])
    assert not auth.is_member({"teams": ["Other"]}, ["Team A"])
    assert not auth.is_member({}, ["Team A"])


def test_request_gate_rejects_wrong_team_with_team_name(monkeypatch):
    """A signed-in user outside ASSIGN_ALLOWED_TEAMS gets a 403 naming the team."""
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ASSIGN_ALLOWED_TEAMS", "Client Administration Team")
    get_settings.cache_clear()
    outsider = {"userId": "u", "userName": "x", "name": "X", "isAdmin": False,
                "token": "t", "teams": ["Mentor Team"], "roles": []}
    monkeypatch.setattr("assignments.auth.current_user", lambda request: outsider)
    from core.app import create_app
    from forms import info_request
    try:
        with TestClient(create_app([info_request.SPEC])) as c:
            r = c.get("/assignments/api/engagements")
        assert r.status_code == 403
        assert "Client Administration Team" in r.json()["detail"]
    finally:
        get_settings.cache_clear()  # don't leak the patched env into other tests


# --- refresh_membership (portal session restore re-reads CRM teams) ----------

class _RefreshClient:
    def __init__(self, rec=None, exc=None):
        self.rec, self.exc = rec, exc

    async def get(self, entity, record_id, select=None):
        assert entity == "User" and record_id == "u1"
        if self.exc:
            raise self.exc
        return self.rec


def _patch_refresh_client(monkeypatch, client):
    class FakeEspo:
        @staticmethod
        def for_user_token(base_url, user_name, token, timeout):
            return client

    monkeypatch.setattr(auth, "EspoClient", FakeEspo)


_SESSION_USER = {"userId": "u1", "userName": "jdoe", "name": "J", "token": "tok",
                 "isAdmin": False, "teams": ["Old Team"], "roles": []}


async def test_refresh_membership_updates_teams_roles_and_admin(monkeypatch):
    _patch_refresh_client(monkeypatch, _RefreshClient(rec={
        "type": "admin",
        "teamsNames": {"t1": "Mentor Administration Team",
                       "t2": "Client Administration Team"},
        "rolesNames": {"r1": "Staff"},
    }))
    user = await auth.refresh_membership(_settings(), dict(_SESSION_USER))
    assert sorted(user["teams"]) == ["Client Administration Team", "Mentor Administration Team"]
    assert user["roles"] == ["Staff"]
    assert user["isAdmin"] is True


async def test_refresh_membership_keeps_cache_when_fields_absent(monkeypatch):
    # a field the CRM didn't serialize is NOT treated as "no teams"
    _patch_refresh_client(monkeypatch, _RefreshClient(rec={}))
    user = await auth.refresh_membership(_settings(), dict(_SESSION_USER))
    assert user["teams"] == ["Old Team"] and user["isAdmin"] is False


async def test_refresh_membership_keeps_cache_on_crm_error(monkeypatch):
    from core.espo import EspoError

    _patch_refresh_client(monkeypatch, _RefreshClient(exc=EspoError("get failed: HTTP 500 boom")))
    user = await auth.refresh_membership(_settings(), dict(_SESSION_USER))
    assert user["teams"] == ["Old Team"]  # a blip never wipes entitlements


async def test_refresh_membership_expired_token_raises(monkeypatch):
    from core.espo import EspoError

    _patch_refresh_client(monkeypatch, _RefreshClient(exc=EspoError("get failed: HTTP 401 Unauthorized")))
    with pytest.raises(auth.AuthError):
        await auth.refresh_membership(_settings(), dict(_SESSION_USER))
