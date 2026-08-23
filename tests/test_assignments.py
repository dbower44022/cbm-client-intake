"""Tests for the mentor assignment tool: service writes, mentor query, auth gate."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from assignments import auth, service
from core.config import Settings, get_settings
from core.espo import EspoError


class FakeClient:
    """Mock of the EspoClient slice the service uses; records get/list/update calls."""

    def __init__(self, *, mentor=None, engagement=None, contact=None, related=None,
                 lists=None, mentor_fields=None):
        # The CMentorProfile field defs this fake CRM reports. Defaults to a CRM
        # that HAS the lastClientAssignedDate stamp field built, so the suite
        # exercises the live shape; pass ``mentor_fields={}`` for a CRM without it.
        self._mentor_fields = (
            {"name": {}, "mentorStatus": {}, service.LAST_ASSIGNED_FIELD: {}}
            if mentor_fields is None else mentor_fields
        )
        self._mentor = mentor or {}
        self._engagement = engagement or {}
        self._contact = contact
        self._related = related or {"list": []}
        self._lists = lists or {}
        self.updates: list[tuple[str, str, dict]] = []
        self.creates: list[tuple[str, dict]] = []
        self.list_calls: list[tuple[str, list]] = []
        self.list_selects: list[tuple[str, str | None]] = []

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
        self.list_selects.append((entity, kwargs.get("select")))
        return self._lists.get(entity, {"total": 0, "list": []})

    async def list_related(self, entity, record_id, link, **kwargs):
        return self._related

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        return {"id": record_id, **payload}

    async def create(self, entity, payload):
        self.creates.append((entity, payload))
        return {"id": f"{entity.lower()}-new", **payload}

    async def metadata(self, key):
        if key == f"entityDefs.{service.MENTOR_PROFILE}.fields":
            return self._mentor_fields
        return {}


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

    # Contacts (primary + extra, deduped) each reassigned. Contact uses
    # assignedUsers (collaborators) since 2026-07-16 — both attributes written.
    contact_updates = {u[1]: u[2] for u in client.updates if u[0] == service.CONTACT}
    assert set(contact_updates) == {"contact-primary", "contact-extra"}
    assert all(p["assignedUserId"] == "user-99" for p in contact_updates.values())
    assert all(p["assignedUsersIds"] == ["user-99"] for p in contact_updates.values())

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


async def test_assign_merges_assigned_users_on_client_records():
    """The client profile / account re-home must MERGE into each record's
    existing assignedUsers, never overwrite — an overwrite silently revoked the
    co-mentor access the session tools stamp onto those records (add_comentor).
    The engagement's co-mentor users are folded in too, matching the engagement
    write."""

    class Client(FakeClient):
        async def get(self, entity, record_id, select=None):
            if entity == service.CLIENT_PROFILE:
                return {"id": record_id, "assignedUsersIds": ["user-co", "user-other"]}
            if entity == service.ACCOUNT:
                return {"id": record_id, "assignedUsersIds": ["user-co"]}
            return await super().get(entity, record_id, select)

        async def list_related(self, entity, record_id, link, **kwargs):
            if link == "additionalMentors":
                return {"list": [{"id": "mentor-co", "assignedUsersIds": ["user-co"]}]}
            return await super().list_related(entity, record_id, link, **kwargs)

    client = Client(
        mentor=_mentor(),
        engagement={
            "engagementStatus": "Submitted",
            "engagementClientId": "clientprofile-1",
            "clientOrganizationId": "account-1",
        },
    )
    await service.assign_engagement(client, "eng-1", "mentor-1")

    prof = [u for u in client.updates if u[0] == service.CLIENT_PROFILE][0][2]
    assert prof["assignedUsersIds"] == ["user-co", "user-other", "user-99"]
    assert prof["assignedUserId"] == "user-99"
    acct = [u for u in client.updates if u[0] == service.ACCOUNT][0][2]
    assert acct["assignedUsersIds"] == ["user-co", "user-99"]
    assert acct["assignedUserId"] == "user-99"


async def test_assign_merges_contact_assigned_users():
    """Contacts use the collaborators field too (switched 2026-07-16) — the
    re-home must merge into the contact's existing assignedUsers, preserving
    co-mentor stamps, never overwrite."""

    client = FakeClient(
        mentor=_mentor(),
        engagement={
            "engagementStatus": "Submitted",
            "primaryEngagementContactId": "contact-primary",
        },
        contact={"assignedUsersIds": ["user-co"]},
        related={"list": [{"id": "contact-primary"}]},
    )
    await service.assign_engagement(client, "eng-1", "mentor-1")

    payload = [u for u in client.updates if u[0] == service.CONTACT][0][2]
    assert payload["assignedUsersIds"] == ["user-co", "user-99"]
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


async def test_assign_posts_stream_note():
    """The assignment stamps a durable, human-readable note into the
    engagement's Espo stream — an app write is otherwise indistinguishable in
    history from a hand edit by the same user (the 2026-07-16 forensics
    lesson). The note names the mentor, the app, and the re-homing outcome."""
    client = FakeClient(
        mentor=_mentor(),
        engagement={
            "engagementStatus": "Submitted",
            "primaryEngagementContactId": "contact-primary",
            "engagementClientId": "clientprofile-1",
            "clientOrganizationId": None,  # e.g. a pre-v0.38.1 intake engagement
        },
        related={"list": [{"id": "contact-primary"}, {"id": "contact-extra"}]},
    )
    await service.assign_engagement(client, "eng-1", "mentor-1")

    notes = [p for e, p in client.creates if e == "Note"]
    assert len(notes) == 1
    n = notes[0]
    assert n["type"] == "Post"
    assert n["parentType"] == service.ENGAGEMENT and n["parentId"] == "eng-1"
    assert "Matt Mentor" in n["post"] and "Client Administration" in n["post"]
    assert "2/2 contact(s)" in n["post"]
    assert "client profile" in n["post"]
    assert "company: no link" in n["post"]


async def test_assign_note_reports_rehoming_failures():
    from core.espo import EspoError

    class FlakyClient(FakeClient):
        async def update(self, entity, record_id, payload):
            if entity == service.CONTACT:
                raise EspoError("HTTP 403 denied")
            return await super().update(entity, record_id, payload)

    client = FlakyClient(
        mentor=_mentor(),
        engagement={
            "engagementStatus": "Submitted",
            "primaryEngagementContactId": "contact-primary",
            "engagementClientId": "clientprofile-1",
            "clientOrganizationId": "account-1",
        },
        related={"list": [{"id": "contact-primary"}]},
    )
    await service.assign_engagement(client, "eng-1", "mentor-1")
    notes = [p for e, p in client.creates if e == "Note"]
    assert len(notes) == 1
    assert "0/1 contact(s)" in notes[0]["post"]
    assert "could not be re-homed" in notes[0]["post"]


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


# --- assign repair run (P1-9, reliability review 2026-07-17) ------------------


def _half_assigned_engagement(**over):
    """An engagement whose FIRST assignment died mid re-homing: the engagement
    write landed (mentor + Pending Acceptance) but the related records were
    never re-homed."""
    return dict({
        "engagementStatus": "Pending Acceptance",
        "mentorProfileId": "mentor-1",
        "mentorProfileName": "Matt Mentor",
        "primaryEngagementContactId": "contact-primary",
        "engagementClientId": "clientprofile-1",
        "clientOrganizationId": "account-1",
    }, **over)


async def test_assign_same_mentor_repairs_rehoming():
    """Stale-guard trip + stored mentor == requested mentor => a repair run:
    the idempotent re-homing re-executes and the stream note posts, instead of
    the 400 that made a half-assigned engagement unrepairable in-app."""
    client = FakeClient(
        mentor=_mentor(),
        engagement=_half_assigned_engagement(),
        related={"list": [{"id": "contact-primary"}]},
    )
    res = await service.assign_engagement(client, "eng-1", "mentor-1")

    assert res["repaired"] is True
    # The engagement record itself is NOT rewritten (its status — possibly
    # staffer-adjusted since — and assignment stand as they are).
    assert not [u for u in client.updates if u[0] == service.ENGAGEMENT]
    assert res["engagementStatus"] == "Pending Acceptance"
    # The re-homing ran.
    assert res["contactsUpdated"] == 1
    assert res["clientProfileUpdated"] is True and res["accountUpdated"] is True
    # And the stream note says this was a repair, not a fresh assignment.
    notes = [p for e, p in client.creates if e == "Note"]
    assert len(notes) == 1 and "repair" in notes[0]["post"].lower()


async def test_assign_repair_allowed_for_now_ineligible_mentor():
    """A repair finishes an assignment that already happened — the mentor
    having since paused new clients must not block completing it."""
    client = FakeClient(
        mentor=_mentor(acceptingNewClients=False),
        engagement=_half_assigned_engagement(),
        related={"list": [{"id": "contact-primary"}]},
    )
    res = await service.assign_engagement(client, "eng-1", "mentor-1")
    assert res["repaired"] is True and res["contactsUpdated"] == 1


async def test_assign_fresh_assignment_is_not_marked_repaired():
    client = FakeClient(
        mentor=_mentor(),
        engagement={
            "engagementStatus": "Submitted",
            "primaryEngagementContactId": "contact-primary",
        },
        related={"list": [{"id": "contact-primary"}]},
    )
    res = await service.assign_engagement(client, "eng-1", "mentor-1")
    assert res["repaired"] is False
    assert res["engagementStatus"] == "Pending Acceptance"


# --- the mentor-side "last assigned a new client" stamp -----------------------


def _submitted_engagement(**over):
    return dict({
        "engagementStatus": "Submitted",
        "primaryEngagementContactId": "contact-primary",
    }, **over)


def _mentor_stamps(client):
    """Every write of the stamp field, as (mentorProfileId, value)."""
    return [
        (rid, payload[service.LAST_ASSIGNED_FIELD])
        for entity, rid, payload in client.updates
        if entity == service.MENTOR_PROFILE and service.LAST_ASSIGNED_FIELD in payload
    ]


async def test_assign_stamps_the_mentors_last_client_assigned_date():
    import re

    client = FakeClient(mentor=_mentor(), engagement=_submitted_engagement())
    res = await service.assign_engagement(client, "eng-1", "mentor-1")

    stamps = _mentor_stamps(client)
    assert len(stamps) == 1
    mentor_id, value = stamps[0]
    assert mentor_id == "mentor-1"
    # EspoCRM's UTC datetime format, the same shape as engagementAssignedDate.
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value)
    assert res["mentorLastAssignedDate"] == value


async def test_assign_does_not_stamp_when_the_crm_field_is_not_built():
    """Feature-detected: inert until the CRM field exists, so the app can ship
    ahead of the CRM build."""
    client = FakeClient(
        mentor=_mentor(), engagement=_submitted_engagement(), mentor_fields={},
    )
    res = await service.assign_engagement(client, "eng-1", "mentor-1")
    assert _mentor_stamps(client) == []
    assert res["mentorLastAssignedDate"] is None
    # The assignment itself still happened.
    assert [u for u in client.updates if u[0] == service.ENGAGEMENT]


async def test_assign_repair_does_not_restamp_the_mentor():
    """A repair re-runs the re-homing for an assignment that already happened —
    it is not a new client, which is why the engagement's own date is left
    alone too."""
    client = FakeClient(
        mentor=_mentor(),
        engagement=_half_assigned_engagement(),
        related={"list": [{"id": "contact-primary"}]},
    )
    res = await service.assign_engagement(client, "eng-1", "mentor-1")
    assert res["repaired"] is True
    assert _mentor_stamps(client) == []
    assert res["mentorLastAssignedDate"] is None


async def test_stamp_is_advance_only():
    """A stored value at or after the new one is left alone — the date can
    never move backward."""
    client = FakeClient(mentor=_mentor(**{service.LAST_ASSIGNED_FIELD: "2099-01-01 00:00:00"}))
    assert await service.stamp_mentor_last_assigned(client, "mentor-1") is None
    assert _mentor_stamps(client) == []

    client = FakeClient(mentor=_mentor(**{service.LAST_ASSIGNED_FIELD: "2020-01-01 00:00:00"}))
    written = await service.stamp_mentor_last_assigned(client, "mentor-1")
    assert written and _mentor_stamps(client) == [("mentor-1", written)]


async def test_stamp_failure_never_fails_the_assignment():
    """A Client Administration role without edit on CMentorProfile must not
    lose the assignment that has already been written."""
    class Refusing(FakeClient):
        async def update(self, entity, record_id, payload):
            if entity == service.MENTOR_PROFILE:
                raise EspoError("403 Forbidden: CMentorProfile edit")
            return await super().update(entity, record_id, payload)

    client = Refusing(mentor=_mentor(), engagement=_submitted_engagement())
    res = await service.assign_engagement(client, "eng-1", "mentor-1")
    assert res["mentorLastAssignedDate"] is None
    assert res["engagementStatus"] == "Pending Acceptance"
    assert [u for u in client.updates if u[0] == service.ENGAGEMENT]


async def test_stamp_skipped_without_metadata_access():
    """The dry-run client has no ``metadata`` method — no detection, no stamp."""
    class NoMetadata(FakeClient):
        metadata = None

    client = NoMetadata(mentor=_mentor(), engagement=_submitted_engagement())
    res = await service.assign_engagement(client, "eng-1", "mentor-1")
    assert res["mentorLastAssignedDate"] is None
    assert _mentor_stamps(client) == []


async def test_reassign_stamps_the_new_mentor_only():
    """The field records GAINING a client; the outgoing mentor is untouched."""
    client = FakeClient(
        mentor=_mentor(assignedUserId="user-new", assignedUserName="Nina New"),
        engagement={
            "engagementStatus": "Active",
            "mentorProfileId": "mentor-old",
            "mentorProfileName": "Olly Old",
            "assignedUsersIds": ["user-old"],
            "primaryEngagementContactId": "contact-primary",
        },
    )
    res = await service.reassign_engagement(client, "eng-1", "mentor-new")
    stamps = _mentor_stamps(client)
    assert len(stamps) == 1 and stamps[0][0] == "mentor-new"
    assert res["mentorLastAssignedDate"] == stamps[0][1]


# --- reassign_engagement -----------------------------------------------------

class ReassignClient(FakeClient):
    """FakeClient with per-id mentor profiles, per-(entity,id) records, and the
    co-mentor + sessions links — the surface reassign_engagement touches."""

    def __init__(self, *, mentors=None, records=None, comentors=None,
                 sessions=None, **kw):
        super().__init__(**kw)
        self._mentors = mentors or {}
        self._records = records or {}
        self._comentors = comentors or []
        self._sessions = sessions or []

    async def get(self, entity, record_id, select=None):
        if entity == service.MENTOR_PROFILE and record_id in self._mentors:
            return {"id": record_id, **self._mentors[record_id]}
        if (entity, record_id) in self._records:
            return {"id": record_id, **self._records[(entity, record_id)]}
        return await super().get(entity, record_id, select)

    async def list_related(self, entity, record_id, link, **kwargs):
        if link == "additionalMentors":
            return {"list": self._comentors}
        if link == service.ENGAGEMENT_SESSIONS_LINK:
            return {"list": self._sessions}
        return await super().list_related(entity, record_id, link, **kwargs)


def _reassign_client(**overrides):
    base = dict(
        mentors={
            "mentor-old": {"name": "Sharon Rose", "assignedUserId": "user-old"},
            "mentor-new": _mentor(name="Robert Cohen", assignedUserId="user-new",
                                  assignedUserName="Robert Cohen"),
        },
        engagement={
            "name": "Acme Growth",
            "engagementStatus": "Active",
            "mentorProfileId": "mentor-old",
            "mentorProfileName": "Sharon Rose",
            "assignedUsersIds": ["user-old", "user-co"],
            "primaryEngagementContactId": "contact-primary",
            "engagementClientId": "clientprofile-1",
            "clientOrganizationId": "account-1",
        },
        related={"list": [{"id": "contact-primary"}, {"id": "contact-extra"}]},
        comentors=[{"id": "mentor-co", "assignedUsersIds": ["user-co"]}],
        records={
            ("CClientProfile", "clientprofile-1"): {"assignedUsersIds": ["user-old", "user-co"]},
            ("Account", "account-1"): {"assignedUsersIds": ["user-old"]},
            ("Contact", "contact-primary"): {"assignedUsersIds": ["user-old", "user-co"]},
        },
        sessions=[
            # Owned by the old mentor — they keep it (remove_comentor convention).
            {"id": "sess-owned", "assignedUserId": "user-old",
             "assignedUsersIds": ["user-old", "user-co"]},
            # Not owned by them — old User swapped out, new User in.
            {"id": "sess-other", "assignedUserId": "user-co",
             "assignedUsersIds": ["user-old", "user-co"]},
        ],
    )
    base.update(overrides)
    return ReassignClient(**base)


async def test_reassign_swaps_mentor_across_all_records():
    client = _reassign_client()
    res = await service.reassign_engagement(
        client, "eng-1", "mentor-new", actor="Jane Staff"
    )

    # Engagement: mentor swapped, old User out / new User in, co-mentor kept,
    # assigned date re-stamped, status NOT touched.
    eng_updates = [u for u in client.updates if u[0] == service.ENGAGEMENT]
    assert len(eng_updates) == 1
    payload = eng_updates[0][2]
    assert payload["mentorProfileId"] == "mentor-new"
    assert payload["assignedUsersIds"] == ["user-co", "user-new"]
    assert payload["assignedUserId"] == "user-new"
    assert "engagementStatus" not in payload
    import re
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
                        payload["engagementAssignedDate"])

    # Contacts move to the new mentor's user — swap-merge on the collaborators
    # field (old mentor out, co-mentor kept), both attributes written.
    contact_updates = {u[1]: u[2] for u in client.updates if u[0] == service.CONTACT}
    assert set(contact_updates) == {"contact-primary", "contact-extra"}
    assert all(p["assignedUserId"] == "user-new" for p in contact_updates.values())
    assert contact_updates["contact-primary"]["assignedUsersIds"] == ["user-co", "user-new"]
    assert contact_updates["contact-extra"]["assignedUsersIds"] == ["user-new", "user-co"]

    # Client profile + company: swap-merge (old out unless shared, new + co in).
    cp = [u[2] for u in client.updates if u[0] == "CClientProfile"][0]
    assert cp["assignedUsersIds"] == ["user-co", "user-new"]
    acc = [u[2] for u in client.updates if u[0] == "Account"][0]
    assert acc["assignedUsersIds"] == ["user-new", "user-co"]

    # Sessions: the old mentor keeps the session they personally own.
    sess = {u[1]: u[2] for u in client.updates if u[0] == service.SESSION}
    assert sess["sess-owned"]["assignedUsersIds"] == ["user-old", "user-co", "user-new"]
    assert sess["sess-other"]["assignedUsersIds"] == ["user-co", "user-new"]

    assert res["mentorName"] == "Robert Cohen"
    assert res["oldMentorName"] == "Sharon Rose"
    assert res["engagementStatus"] == "Active"  # unchanged
    assert res["contactsUpdated"] == 2
    assert res["clientProfileUpdated"] and res["accountUpdated"]
    assert res["sessionsUpdated"] == 2 and res["sessionsTotal"] == 2
    assert res["reassignmentErrors"] == []


async def test_reassign_posts_required_history_wording():
    """The engagement's stream gets Doug's exact history line:
    'Mentor X was replaced with Mentor Y on MM/DD/YYYY by user NAME.'"""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    client = _reassign_client()
    await service.reassign_engagement(client, "eng-1", "mentor-new", actor="Jane Staff")

    notes = [p for e, p in client.creates if e == "Note"]
    assert len(notes) == 1
    n = notes[0]
    assert n["type"] == "Post"
    assert n["parentType"] == service.ENGAGEMENT and n["parentId"] == "eng-1"
    today = datetime.now(ZoneInfo("America/New_York")).strftime("%m/%d/%Y")
    assert (
        f"Mentor Sharon Rose was replaced with Mentor Robert Cohen on {today} "
        "by user Jane Staff." in n["post"]
    )
    assert "2/2 contact(s)" in n["post"]
    assert "2/2 session(s)" in n["post"]


async def test_reassign_requires_an_existing_mentor():
    client = _reassign_client(
        engagement={"engagementStatus": "Submitted", "assignedUsersIds": []},
    )
    with pytest.raises(service.AssignError, match="no mentor yet"):
        await service.reassign_engagement(client, "eng-1", "mentor-new")
    assert client.updates == []


async def test_reassign_rejects_same_mentor():
    client = _reassign_client()
    with pytest.raises(service.AssignError, match="already"):
        await service.reassign_engagement(client, "eng-1", "mentor-old")
    assert client.updates == []


async def test_reassign_rejects_ineligible_new_mentor():
    client = _reassign_client(
        mentors={
            "mentor-old": {"name": "Sharon Rose", "assignedUserId": "user-old"},
            "mentor-new": _mentor(acceptingNewClients=False),
        },
    )
    with pytest.raises(service.AssignError, match="no longer eligible"):
        await service.reassign_engagement(client, "eng-1", "mentor-new")
    assert client.updates == []


async def test_reassign_reports_session_stamp_failures():
    """A session the staff user can't edit is reported, never fatal — the
    mentor change itself stands."""
    from core.espo import EspoError

    class Flaky(ReassignClient):
        async def update(self, entity, record_id, payload):
            if entity == service.SESSION and record_id == "sess-other":
                raise EspoError("HTTP 403 denied")
            return await super().update(entity, record_id, payload)

    client = _reassign_client()
    flaky = Flaky(
        mentors=client._mentors, records=client._records,
        comentors=client._comentors, sessions=client._sessions,
        engagement=client._engagement, related=client._related,
    )
    res = await service.reassign_engagement(flaky, "eng-1", "mentor-new")
    assert res["sessionsUpdated"] == 1 and res["sessionsTotal"] == 2
    errs = res["reassignmentErrors"]
    assert [e["entity"] for e in errs] == [service.SESSION]
    notes = [p for e, p in flaky.creates if e == "Note"]
    assert "could not be re-homed" in notes[0]["post"]


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
                        service.LAST_ASSIGNED_FIELD: "2026-08-01 14:00:00",
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
            # The mentor-side stamp feeds the picker's "Last Assigned" column.
            "lastClientAssigned": "2026-08-01 14:00:00",
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


async def test_mentor_select_asks_for_the_stamp_only_when_the_crm_has_it():
    """An unknown attribute in ``select`` is not something to bet the roster on,
    so the column's field is added by feature detection, not hardcoded."""
    built = FakeClient()
    await service.list_eligible_mentors(built)
    entity, select = built.list_selects[0]
    assert entity == service.MENTOR_PROFILE
    assert select.endswith("," + service.LAST_ASSIGNED_FIELD)

    unbuilt = FakeClient(mentor_fields={})
    await service.list_eligible_mentors(unbuilt)
    _, select = unbuilt.list_selects[0]
    assert service.LAST_ASSIGNED_FIELD not in select


async def test_roster_rows_carry_the_stamp_for_the_picker_column():
    client = FakeClient(
        lists={
            service.MENTOR_PROFILE: {
                "list": [
                    {"id": "m1", "name": "Stamped", "assignedUserId": "u1",
                     service.LAST_ASSIGNED_FIELD: "2026-08-01 14:00:00"},
                    # Never given a client — the column renders "—", not a zero.
                    {"id": "m2", "name": "Never", "assignedUserId": "u2"},
                ]
            }
        }
    )
    rows = {m["id"]: m for m in (await service.list_all_mentors(client))["mentors"]}
    assert rows["m1"]["lastClientAssigned"] == "2026-08-01 14:00:00"
    assert rows["m2"]["lastClientAssigned"] is None


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


async def test_list_engagements_company_column():
    """The Company column: the engagement's own link, else the client profile's.

    Intake-created engagements leave CEngagement.clientOrganization null and
    carry the Account on CClientProfile.linkedCompany only — without the
    fallback the column would be empty for exactly the rows this tool works.
    """

    class CompanyClient(FakeClient):
        def __init__(self, profiles, **kw):
            super().__init__(**kw)
            self.profiles = profiles
            self.profile_reads = []

        async def get(self, entity, record_id, select=None):
            if entity == service.CLIENT_PROFILE:
                self.profile_reads.append(record_id)
                return {"id": record_id, **self.profiles.get(record_id, {})}
            return await super().get(entity, record_id, select=select)

    client = CompanyClient(
        {"cp1": {"linkedCompanyId": "a1", "linkedCompanyName": "Rose LLC"},
         "cp3": {}},
        lists={
            service.ENGAGEMENT: {
                "list": [
                    # No own company link -> resolved through the client profile.
                    {"id": "e1", "name": "Rose", "engagementClientId": "cp1"},
                    # Own link present -> used as-is, no profile read.
                    {"id": "e2", "name": "Green", "engagementClientId": "cp2",
                     "clientOrganizationName": "Green Co"},
                    # Profile with no company of its own -> blank, not an error.
                    {"id": "e3", "name": "Blue", "engagementClientId": "cp3"},
                    # No client profile at all -> blank.
                    {"id": "e4", "name": "Gray"},
                ]
            }
        },
    )
    rows = await service.list_engagements(client, ["Submitted"])
    assert [r["companyName"] for r in rows] == ["Rose LLC", "Green Co", None, None]
    # One read per DISTINCT profile, and only for the rows that needed one.
    assert sorted(client.profile_reads) == ["cp1", "cp3"]


async def test_list_engagements_company_lookup_failure_is_not_fatal():
    """A client profile the user can't read leaves the cell blank, not a 500."""

    class ForbiddenClient(FakeClient):
        async def get(self, entity, record_id, select=None):
            if entity == service.CLIENT_PROFILE:
                raise EspoError("403 Forbidden")
            return await super().get(entity, record_id, select=select)

    client = ForbiddenClient(
        lists={service.ENGAGEMENT: {"list": [
            {"id": "e1", "name": "Rose", "engagementClientId": "cp1"},
        ]}},
    )
    rows = await service.list_engagements(client, ["Submitted"])
    assert rows[0]["companyName"] is None


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
        "companyName": None,
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


def test_engagements_default_filter_is_action_needed_set(monkeypatch):
    """No ?status= params → Submitted + Assignment Declined + Assignment Dormant."""
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()
    staff = {"userId": "u", "userName": "x", "name": "X", "isAdmin": True,
             "token": "t", "teams": [], "roles": []}
    monkeypatch.setattr("assignments.auth.current_user", lambda request: staff)
    monkeypatch.setattr("assignments.router.client_for", lambda settings, user: object())
    seen = {}

    async def fake_list(client, statuses):
        seen["statuses"] = statuses
        return []

    monkeypatch.setattr(service, "list_engagements", fake_list)
    from core.app import create_app
    from forms import info_request
    try:
        with TestClient(create_app([info_request.SPEC])) as c:
            r = c.get("/assignments/api/engagements")
        assert r.status_code == 200
        expected = ["Submitted", "Assignment Declined", "Assignment Dormant"]
        assert r.json()["selectedStatuses"] == expected
        assert seen["statuses"] == expected
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
