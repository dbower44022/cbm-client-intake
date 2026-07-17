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


# --- enum sanitization on save (a drifted value never blocks the save) ---

_HOW_HEARD_META = {"howDidYouHearAboutCBM": {"type": "enum", "options": ["Online Search", "Other"]}}


@pytest.mark.asyncio
async def test_update_mentor_drops_drifted_enum_and_warns():
    """A value the live CRM enum no longer offers is dropped (logged + a
    plain-language warning returned); the REST of the save still happens."""
    client = FakeClient(metadata=_HOW_HEARD_META)
    result = await service.update_mentor(
        client, "m1", {"howDidYouHearAboutCBM": "Online search", "name": "New Name"}
    )
    assert len(client.updates) == 1
    _, _, payload = client.updates[0]
    assert payload == {"name": "New Name"}  # the drifted enum never reaches the CRM
    assert len(result["warnings"]) == 1
    assert "How they heard about CBM" in result["warnings"][0]
    assert "Online search" in result["warnings"][0]


@pytest.mark.asyncio
async def test_update_mentor_multienum_keeps_valid_members():
    meta = {"industryExperience": {"type": "multiEnum", "options": ["Education", "Retail"]}}
    client = FakeClient(metadata=meta)
    result = await service.update_mentor(
        client, "m1", {"industryExperience": ["Education", "Gone Industry"]}
    )
    _, _, payload = client.updates[0]
    assert payload == {"industryExperience": ["Education"]}
    assert "Gone Industry" in result["warnings"][0]


@pytest.mark.asyncio
async def test_update_mentor_only_drifted_change_still_saves_cleanly():
    """If the only change was the drifted value, nothing is written but the
    save still succeeds with the warning (no 4xx/5xx to the user)."""
    client = FakeClient(metadata=_HOW_HEARD_META)
    result = await service.update_mentor(client, "m1", {"howDidYouHearAboutCBM": "SBA"})
    assert client.updates == []
    assert result["warnings"]


@pytest.mark.asyncio
async def test_update_mentor_enum_sanitize_fails_open():
    """Options unavailable => keep the value (never drop what can't be verified)."""

    class NoMeta(FakeClient):
        async def metadata(self, key):
            raise EspoError("metadata failed: HTTP 500")

    client = NoMeta()
    result = await service.update_mentor(client, "m1", {"howDidYouHearAboutCBM": "Other"})
    _, _, payload = client.updates[0]
    assert payload == {"howDidYouHearAboutCBM": "Other"}
    assert "warnings" not in result


def test_field_spec_layout():
    """Lock the requested detail-form layout."""
    by = {f["name"]: f for f in service.EDITABLE_FIELDS}
    # how-did-you-hear is a live-options enum (the CRM field is a real enum
    # now — a static list here drifted and 400'd a prod save 2026-07-11)
    assert by["howDidYouHearAboutCBM"]["type"] == "enum"
    assert "options" not in by["howDidYouHearAboutCBM"]
    assert "howDidYouHearAboutCBM" in service._ENUM_FIELDS
    # start date moved to Status; Dates tab renamed Departure (no more "Dates")
    assert by["mentorStartDate"]["group"] == "Status"
    assert by["departureDate"]["group"] == "Departure"
    assert by["departureReason"]["group"] == "Departure"
    assert not any(f["group"] == "Dates" for f in service.EDITABLE_FIELDS)
    # Status: status/type share a row, pause window on the line beneath them
    assert by["mentorStatus"]["row"] == "statustype" and by["mentorType"]["row"] == "statustype"
    assert by["mentorPauseStartDate"]["group"] == "Status" and by["mentorPauseStartDate"]["row"] == "pause"
    assert by["mentorPauseEndDate"]["group"] == "Status" and by["mentorPauseEndDate"]["row"] == "pause"
    # Expertise carries industry experience, not the (removed) focus areas / sector
    assert by["industryExperience"]["group"] == "Expertise"
    assert "mentoringFocusAreas" not in by
    assert "industrySector" not in by
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


# --- Contact tab: view + edit the linked Contact's info from the detail form ---

def test_contact_tab_field_spec():
    contact = [f for f in service.EDITABLE_FIELDS if f.get("entity") == service.CONTACT_ENTITY]
    assert {f["name"] for f in contact} == {
        "firstName", "lastName", "emailAddress", "phoneNumber",
        "addressStreet", "addressCity", "addressState", "addressPostalCode",
        "cLinkedInProfile",
    }
    # LinkedIn is Contact-backed but deliberately shown on the Profile tab.
    assert all(f["group"] == "Contact" for f in contact if f["name"] != "cLinkedInProfile")
    by = {f["name"]: f for f in contact}
    assert by["cLinkedInProfile"]["group"] == "Profile"
    # Contact fields never leak into the CMentorProfile select/update whitelist,
    # but they ARE editable (accepted by the update endpoint).
    assert not (service.PROFILE_EDIT_NAMES & service.CONTACT_NAMES)
    assert service.CONTACT_NAMES <= service.EDITABLE_NAMES


class ContactClient(FakeClient):
    """A fake whose Contact record is distinct from the mentor profile."""

    def __init__(self, record=None, contact=None):
        super().__init__(record=record)
        self.contact = contact or {}

    async def get(self, entity, record_id, select=None):
        self.gets.append((entity, record_id, select))
        if entity == "Contact":
            return dict(self.contact, id=record_id)
        return dict(self.record, id=record_id)


@pytest.mark.asyncio
async def test_get_mentor_merges_linked_contact_fields():
    client = ContactClient(
        record={"id": "m1", "name": "Jane Mentor", "contactRecordId": "c1"},
        contact={"firstName": "Jane", "lastName": "Doe", "emailAddress": "jane@example.com",
                 "phoneNumber": "+12165551234", "addressCity": "Cleveland"},
    )
    rec = await service.get_mentor(client, "m1")
    assert rec["firstName"] == "Jane" and rec["lastName"] == "Doe"
    assert rec["emailAddress"] == "jane@example.com"
    assert rec["addressCity"] == "Cleveland"
    assert rec["addressStreet"] is None  # unset Contact fields render blank
    contact_get = [g for g in client.gets if g[0] == "Contact"][0]
    assert set(contact_get[2].split(",")) == service.CONTACT_NAMES


@pytest.mark.asyncio
async def test_get_mentor_without_contact_still_loads():
    client = FakeClient()  # record has no contactRecordId
    rec = await service.get_mentor(client, "m1")
    assert not [g for g in client.gets if g[0] == "Contact"]
    assert "firstName" not in rec


@pytest.mark.asyncio
async def test_update_mentor_routes_contact_fields_to_contact():
    client = ContactClient(record={"id": "m1", "name": "Jane", "contactRecordId": "c1"})
    await service.update_mentor(client, "m1", {
        "firstName": "Janet", "addressCity": "Cleveland",
        "phoneNumber": "(216) 555-1234",  # normalized to E.164 at the CRM boundary
        "mentorStatusNotes": "x",
    })
    profile_updates = [u for u in client.updates if u[0] == service.MENTOR_PROFILE]
    contact_updates = [u for u in client.updates if u[0] == "Contact"]
    assert profile_updates[0][2] == {"mentorStatusNotes": "x"}
    assert contact_updates[0] == ("Contact", "c1", {
        "firstName": "Janet", "addressCity": "Cleveland", "phoneNumber": "+12165551234",
    })


@pytest.mark.asyncio
async def test_contact_changes_without_linked_contact_fail_before_any_write():
    client = FakeClient()  # no contactRecordId
    with pytest.raises(service.MentorAdminError, match="no linked Contact"):
        await service.update_mentor(client, "m1", {"phoneNumber": "2165551234", "name": "New"})
    assert client.updates == []  # nothing half-saved — not even the profile part


@pytest.mark.asyncio
async def test_get_mentor_attaches_app_computed_client_counts():
    """The detail card shows the SAME counts as the roster grid — computed from
    CEngagement, not the CRM's buggy currentActiveClients/availableCapacity."""

    class Client(FakeClient):
        async def list(self, entity, **kwargs):
            assert entity == "CEngagement"
            return {"list": [
                {"mentorProfileId": "m1", "engagementStatus": "Active"},
                {"mentorProfileId": "m1", "engagementStatus": "Completed"},
                {"mentorProfileId": "other", "engagementStatus": "Active"},
            ]}

    client = Client(record={"id": "m1", "name": "Jane", "maximumClientCapacity": 5})
    rec = await service.get_mentor(client, "m1")
    assert rec["clientCounts"] == {
        "activeClients": 1, "assignedLast30": 0, "lifetimeClients": 2,
        "availableCapacity": 4, "maxCapacity": 5,
    }
    # The CRM-computed fields are no longer selected.
    _, _, select = client.gets[0]
    cols = select.split(",")
    assert "currentActiveClients" not in cols and "availableCapacity" not in cols


@pytest.mark.asyncio
async def test_get_mentor_counts_blank_when_engagements_unreadable():
    class Client(FakeClient):
        async def list(self, entity, **kwargs):
            raise EspoError("list CEngagement failed: HTTP 403 forbidden")

    client = Client(record={"id": "m1", "maximumClientCapacity": 3})
    rec = await service.get_mentor(client, "m1")
    cc = rec["clientCounts"]
    assert cc["activeClients"] is None and cc["lifetimeClients"] is None
    assert cc["availableCapacity"] is None
    assert cc["maxCapacity"] == 3  # the stored field still shows


@pytest.mark.asyncio
async def test_field_options_reads_live_enums():
    meta = {
        "mentorStatus": {"type": "enum", "options": ["Active", "Inactive"]},
        "industryExperience": {"type": "multiEnum", "options": ["Finance", "Marketing"]},
        "name": {"type": "varchar"},  # not an enum -> excluded
    }
    client = FakeClient(metadata=meta)
    opts = await service.field_options(client)
    assert opts["mentorStatus"] == ["Active", "Inactive"]
    assert opts["industryExperience"] == ["Finance", "Marketing"]
    assert "name" not in opts


# --- data-structure completeness ---

class CompletenessClient:
    """Returns a Contact with a given assignedUserId / assignedUsersIds
    (for the Active checks). Contact uses the collaborators field since
    2026-07-16, so the check must accept either shape."""
    def __init__(self, contact_user=None, contact_multi=None):
        self.contact_user = contact_user
        self.contact_multi = contact_multi or []

    async def get(self, entity, record_id, select=None):
        return {"id": record_id, "assignedUserId": self.contact_user,
                "assignedUsersIds": self.contact_multi}


def _complete_rec(**over):
    # NB: background check is deliberately NOT set here — it is optional, so a rec
    # without it must still be Complete.
    rec = {
        "contactRecordId": "c1", "assignedUserId": "u1", "mentorStatus": "Active",
        "cbmEmail": "jane.doe@cbmentors.org",
        "ethicsAgreementAccepted": True,
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
async def test_completeness_accepts_contact_collaborators_shape():
    """Contact was switched to Multiple Assigned Users (2026-07-16): the single
    assignedUserId reads null even when the contact is assigned. Membership in
    assignedUsersIds must count — this was the 'every mentor reads Incomplete:
    no User assigned to the Contact' regression."""
    # mentor's user only in the multi list (possibly alongside a co-mentor)
    r = await service.check_completeness(
        CompletenessClient(None, contact_multi=["u-co", "u1"]), _complete_rec())
    assert r == {"status": "Complete", "issues": []}
    # multi list populated but the mentor's user is not in it
    r2 = await service.check_completeness(
        CompletenessClient(None, contact_multi=["u-other"]), _complete_rec())
    assert r2["status"] == "Incomplete" and any("different User" in i for i in r2["issues"])


@pytest.mark.asyncio
async def test_completeness_contact_read_failure_reports_once():
    """An unreadable Contact reports the read failure — not a bogus
    'no User assigned to the Contact' on top of it."""
    class Failing:
        async def get(self, entity, record_id, select=None):
            raise RuntimeError("403 denied")

    r = await service.check_completeness(Failing(), _complete_rec())
    assert r["status"] == "Incomplete"
    assert any("could not read the Contact" in i for i in r["issues"])
    assert not any("no User assigned to the Contact" in i for i in r["issues"])


@pytest.mark.asyncio
async def test_completeness_active_requires_cbm_email():
    r = await service.check_completeness(CompletenessClient("u1"), _complete_rec(cbmEmail=""))
    assert r["status"] == "Incomplete" and any("CBM email" in i for i in r["issues"])


@pytest.mark.asyncio
async def test_completeness_ignores_public_profile():
    # publicProfile is not part of completeness: on, with no About/expertise, a
    # record with the required flags is still Complete.
    r = await service.check_completeness(CompletenessClient("u1"), _complete_rec(
        publicProfile=True, aboutMentor="<p></p>", areaOfExpertise=[]))
    assert r == {"status": "Complete", "issues": []}


@pytest.mark.asyncio
async def test_completeness_background_check_optional():
    # Background check false (or absent) must NOT make a record Incomplete.
    r = await service.check_completeness(CompletenessClient("u1"), _complete_rec(
        backgroundCheckCompleted=False))
    assert r == {"status": "Complete", "issues": []}
    joined = " ".join(r["issues"])
    assert "background check" not in joined


@pytest.mark.asyncio
async def test_completeness_non_active_ignores_user_links():
    # Not Active -> user/contact-user not required; flags + contact still are.
    r = await service.check_completeness(CompletenessClient(), _complete_rec(mentorStatus="Candidate", assignedUserId=None))
    assert r == {"status": "Complete", "issues": []}


class _RecordStatusClient:
    def __init__(self):
        self.updates = []

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        return {"id": record_id}


@pytest.mark.asyncio
async def test_sync_record_status_writes_on_change():
    c = _RecordStatusClient()
    out = await service.sync_record_status(c, "m1", {"recordStatus": "Incomplete"}, "Complete")
    assert out == "Complete"
    assert c.updates == [("CMentorProfile", "m1", {"recordStatus": "Complete"})]


@pytest.mark.asyncio
async def test_sync_record_status_noop_when_unchanged():
    c = _RecordStatusClient()
    out = await service.sync_record_status(c, "m1", {"recordStatus": "Complete"}, "Complete")
    assert out == "Complete" and c.updates == []


@pytest.mark.asyncio
async def test_sync_record_status_preserves_manual_duplicate():
    c = _RecordStatusClient()
    out = await service.sync_record_status(c, "m1", {"recordStatus": "Duplicate"}, "Incomplete")
    assert out == "Duplicate" and c.updates == []


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
    # Write BOTH the single and collaborators link so it persists on prod
    # (CMentorProfile.assignedUser is disabled there — assignedUsers is used).
    assert link["assignedUsersIds"] == ["user-new"]
    assert link["cbmEmail"] == "jane.doe@cbmentors.org"  # backfilled (was blank)
    assert result["provision"] == {
        "ok": True, "userId": "user-new", "userName": "jane.doe@cbmentors.org",
        "email": "jane.doe@cbmentors.org", "team": "Mentor Team", "reused": False,
    }


@pytest.mark.asyncio
async def test_provision_reuses_existing_login_no_duplicate():
    """A mentor whose cbmEmail is already set and whose CBM User already exists
    must be LINKED to that User — never get a duplicate (jane.doe2@…) created."""
    c = ProvisionClient(
        profile={"id": "m1", "name": "Jane Doe", "mentorStatus": "Candidate",
                 "assignedUserId": None, "cbmEmail": "jane.doe@cbmentors.org",
                 "contactRecordId": "c1"},
        existing_users={"jane.doe@cbmentors.org"},
    )
    result = await service.update_mentor(
        c, "m1", {"mentorStatus": "Active"},
        team_name="Mentor Team", admin_client_factory=_afactory(c),
    )
    assert c.created == []                      # no new User created
    link = _link_update(c)
    assert link["assignedUserId"] == "u-x"      # the EXISTING user
    assert link["assignedUsersIds"] == ["u-x"]  # both fields, for prod
    assert result["provision"]["reused"] is True
    assert result["provision"]["userId"] == "u-x"


@pytest.mark.asyncio
async def test_no_admin_client_means_no_provisioning():
    """Without a privileged client, approval never tries to create a user — but
    it reports that provisioning is disabled so the UI can say so."""
    c = ProvisionClient()
    res = await service.update_mentor(c, "m1", {"mentorStatus": "Approved"}, team_name="Mentor Team")
    assert c.created == []
    assert res["provision"] == {
        "ok": False, "disabled": True,
        "error": "mentor login provisioning is disabled on this server",
    }


@pytest.mark.asyncio
async def test_approval_skips_when_user_already_linked():
    c = ProvisionClient(profile={"id": "m1", "name": "Jane Doe", "mentorStatus": "Candidate",
                                 "assignedUserId": "u9", "cbmEmail": "", "contactRecordId": "c1"})
    res = await service.update_mentor(c, "m1", {"mentorStatus": "Approved"}, team_name="Mentor Team", admin_client_factory=_afactory(c))
    assert c.created == [] and "provision" not in res


@pytest.mark.asyncio
async def test_non_provisioning_status_does_not_provision():
    # A status that isn't Approved or Active never provisions.
    c = ProvisionClient()
    await service.update_mentor(c, "m1", {"mentorStatus": "Inactive"}, team_name="Mentor Team", admin_client_factory=_afactory(c))
    assert c.created == []


@pytest.mark.asyncio
async def test_active_without_user_provisions():
    # Set straight to Active (skipping Approved) with no user -> provisions.
    c = ProvisionClient()
    res = await service.update_mentor(c, "m1", {"mentorStatus": "Active"}, team_name="Mentor Team", admin_client_factory=_afactory(c))
    assert len(c.created) == 1 and res["provision"]["ok"] is True


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


# --- Google Workspace mailbox gate + creation ---

class FakeDirectory:
    """A stand-in for core.google_directory.GoogleDirectory. ``status`` is the
    mailbox state; after a create_user() call it flips to EXISTS (so polling
    succeeds), unless ``create_error`` is set or ``stays_missing`` is True."""

    def __init__(self, status, *, create_error=None, stays_missing=False):
        self._status = status
        self.create_error = create_error
        self.stays_missing = stays_missing
        self.created = []

    async def mailbox_status(self, email):
        return self._status

    async def create_user(self, primary_email, first, last, *, recovery_email, temp_password):
        from core.google_directory import GoogleDirectoryError
        if self.create_error:
            raise GoogleDirectoryError(self.create_error)
        self.created.append({"email": primary_email, "recovery": recovery_email, "password": temp_password})
        if not self.stays_missing:
            from core.google_directory import MailboxStatus
            self._status = MailboxStatus.EXISTS


async def _drain(gen):
    return [ev async for ev in gen]


@pytest.mark.asyncio
async def test_missing_mailbox_blocks_when_create_disabled():
    # Inline update_mentor never creates; a missing mailbox still blocks.
    from core.google_directory import MailboxStatus
    c = ProvisionClient()
    res = await service.update_mentor(
        c, "m1", {"mentorStatus": "Approved"}, team_name="Mentor Team",
        admin_client_factory=_afactory(c), directory=FakeDirectory(MailboxStatus.MISSING),
    )
    assert c.created == []  # the EspoCRM User is NOT created
    assert res["provision"]["ok"] is False
    assert "does not exist" in res["provision"]["error"].lower()


@pytest.mark.asyncio
async def test_existing_mailbox_allows_provisioning():
    from core.google_directory import MailboxStatus
    c = ProvisionClient()
    res = await service.update_mentor(
        c, "m1", {"mentorStatus": "Approved"}, team_name="Mentor Team",
        admin_client_factory=_afactory(c), directory=FakeDirectory(MailboxStatus.EXISTS),
    )
    assert len(c.created) == 1 and res["provision"]["ok"] is True


@pytest.mark.asyncio
async def test_unknown_mailbox_fails_open():
    # An inconclusive check must NOT block — a Google outage can't freeze approvals.
    from core.google_directory import MailboxStatus
    c = ProvisionClient()
    res = await service.update_mentor(
        c, "m1", {"mentorStatus": "Approved"}, team_name="Mentor Team",
        admin_client_factory=_afactory(c), directory=FakeDirectory(MailboxStatus.UNKNOWN),
    )
    assert len(c.created) == 1 and res["provision"]["ok"] is True


# --- streaming provisioning generator (the live status window) ---

async def _noop_sleep(_seconds):
    return None


@pytest.mark.asyncio
async def test_steps_existing_mailbox_sequence():
    from core.google_directory import MailboxStatus
    c = ProvisionClient()
    events = await _drain(service.provision_mentor_user_steps(
        c, c, "m1", team_name="Mentor Team",
        directory=FakeDirectory(MailboxStatus.EXISTS), create_mailbox=True, sleep=_noop_sleep,
    ))
    steps = [(e["step"], e["status"]) for e in events]
    assert ("mailbox", "done") in steps
    assert ("login", "done") in steps
    assert events[-1]["step"] == "done"
    assert events[-1]["result"]["userName"] == "jane.doe@cbmentors.org"
    assert len(c.created) == 1  # EspoCRM User created


@pytest.mark.asyncio
async def test_steps_missing_creates_then_provisions():
    from core.google_directory import MailboxStatus
    c = ProvisionClient(contact={"id": "c1", "firstName": "Jane", "lastName": "Doe",
                                 "emailAddress": "jane.personal@example.com"})
    d = FakeDirectory(MailboxStatus.MISSING)
    events = await _drain(service.provision_mentor_user_steps(
        c, c, "m1", team_name="Mentor Team",
        directory=d, create_mailbox=True, poll_seconds=1, poll_timeout=5, sleep=_noop_sleep,
    ))
    # the mailbox was created with the personal email as recovery
    assert d.created and d.created[0]["recovery"] == "jane.personal@example.com"
    assert d.created[0]["email"] == "jane.doe@cbmentors.org"
    # provisioning completed; the final result advertises the new mailbox + temp pw
    final = events[-1]
    assert final["step"] == "done"
    assert final["result"]["mailboxCreated"] is True
    assert final["result"]["tempPassword"]
    assert len(c.created) == 1


@pytest.mark.asyncio
async def test_steps_create_failure_stops_before_espo_user():
    from core.google_directory import MailboxStatus
    c = ProvisionClient()
    d = FakeDirectory(MailboxStatus.MISSING, create_error="license exhausted")
    events = await _drain(service.provision_mentor_user_steps(
        c, c, "m1", team_name="Mentor Team",
        directory=d, create_mailbox=True, sleep=_noop_sleep,
    ))
    assert events[-1]["status"] == "error"
    assert "license exhausted" in events[-1]["message"]
    assert c.created == []  # never reached EspoCRM User creation


@pytest.mark.asyncio
async def test_steps_created_but_not_active_reports_pending():
    from core.google_directory import MailboxStatus
    c = ProvisionClient()
    d = FakeDirectory(MailboxStatus.MISSING, stays_missing=True)  # never becomes active
    events = await _drain(service.provision_mentor_user_steps(
        c, c, "m1", team_name="Mentor Team",
        directory=d, create_mailbox=True, poll_seconds=1, poll_timeout=3, sleep=_noop_sleep,
    ))
    assert d.created  # the create was attempted
    assert events[-1]["status"] == "error"
    assert "not active yet" in events[-1]["message"]
    assert events[-1].get("mailboxCreated") is True
    assert c.created == []  # login deferred to a later save


def test_google_directory_disabled_without_config():
    from core.google_directory import GoogleDirectory

    class S:
        google_directory_check = False
        google_service_account_json = ""
        google_delegated_admin = ""
        request_timeout_seconds = 20

    assert GoogleDirectory.from_settings(S()) is None


def test_google_directory_bad_json_disables():
    from core.google_directory import GoogleDirectory

    class S:
        google_directory_check = True
        google_service_account_json = "not-json"
        google_delegated_admin = "admin@cbmentors.org"
        request_timeout_seconds = 20

    assert GoogleDirectory.from_settings(S()) is None


@pytest.mark.asyncio
async def test_google_directory_unknown_when_no_token(monkeypatch):
    from core.google_directory import GoogleDirectory, MailboxStatus
    gd = GoogleDirectory({"x": 1}, "admin@cbmentors.org")

    async def no_token():
        return None

    monkeypatch.setattr(gd, "_access_token", no_token)
    assert await gd.mailbox_status("x@cbmentors.org") is MailboxStatus.UNKNOWN


@pytest.mark.asyncio
async def test_google_directory_maps_status_codes(monkeypatch):
    import httpx
    from core.google_directory import GoogleDirectory, MailboxStatus
    gd = GoogleDirectory({"x": 1}, "admin@cbmentors.org")

    async def tok():
        return "tok"

    monkeypatch.setattr(gd, "_access_token", tok)

    def handler(request):
        return httpx.Response(200 if "exists" in str(request.url) else 404)

    real = httpx.AsyncClient

    def fake_client(*a, **k):
        k["transport"] = httpx.MockTransport(handler)
        return real(*a, **k)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    assert await gd.mailbox_status("exists@cbmentors.org") is MailboxStatus.EXISTS
    assert await gd.mailbox_status("missing@cbmentors.org") is MailboxStatus.MISSING


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


# --- user-link reconciliation on save ---

@pytest.mark.asyncio
async def test_save_assigns_member_user_to_contact():
    # member has a User, Contact doesn't -> saving assigns it to the Contact.
    c = ProvisionClient(profile={"id": "m1", "name": "Jane", "mentorStatus": "Active",
                                 "assignedUserId": "u1", "cbmEmail": "", "contactRecordId": "c1"})
    await service.update_mentor(c, "m1", {"mentorStatusNotes": "x"})
    contact_updates = [u for u in c.updates if u[0] == "Contact"]
    assert contact_updates and contact_updates[-1][2]["assignedUserId"] == "u1"


@pytest.mark.asyncio
async def test_save_reconcile_noop_when_already_aligned():
    c = ProvisionClient(
        profile={"id": "m1", "name": "Jane", "mentorStatus": "Active",
                 "assignedUserId": "u1", "cbmEmail": "", "contactRecordId": "c1"},
        contact={"id": "c1", "firstName": "Jane", "lastName": "Doe", "assignedUserId": "u1"},
    )
    await service.update_mentor(c, "m1", {"mentorStatusNotes": "x"})
    assert not [u for u in c.updates if u[0] == "Contact"]


@pytest.mark.asyncio
async def test_save_reconcile_merges_into_contact_collaborators():
    """The Contact write must carry BOTH shapes (its single assignedUser is
    disabled since the 2026-07-16 Multiple-Assigned-Users switch) and MERGE
    into the existing list — a co-mentor stamped on the contact keeps access."""
    c = ProvisionClient(
        profile={"id": "m1", "name": "Jane", "mentorStatus": "Active",
                 "assignedUserId": "u1", "cbmEmail": "", "contactRecordId": "c1"},
        contact={"id": "c1", "firstName": "Jane", "lastName": "Doe",
                 "assignedUserId": None, "assignedUsersIds": ["u-co"]},
    )
    await service.update_mentor(c, "m1", {"mentorStatusNotes": "x"})
    contact_updates = [u for u in c.updates if u[0] == "Contact"]
    assert contact_updates
    payload = contact_updates[-1][2]
    assert payload["assignedUserId"] == "u1"
    assert payload["assignedUsersIds"] == ["u-co", "u1"]


@pytest.mark.asyncio
async def test_save_reconcile_noop_when_user_in_contact_collaborators():
    # The mentor's user already in the contact's assignedUsers -> nothing to do.
    c = ProvisionClient(
        profile={"id": "m1", "name": "Jane", "mentorStatus": "Active",
                 "assignedUserId": "u1", "cbmEmail": "", "contactRecordId": "c1"},
        contact={"id": "c1", "firstName": "Jane", "lastName": "Doe",
                 "assignedUserId": None, "assignedUsersIds": ["u-co", "u1"]},
    )
    await service.update_mentor(c, "m1", {"mentorStatusNotes": "x"})
    assert not [u for u in c.updates if u[0] == "Contact"]


@pytest.mark.asyncio
async def test_save_reconcile_noop_when_no_user_anywhere():
    c = ProvisionClient(profile={"id": "m1", "name": "Jane", "mentorStatus": "Active",
                                 "assignedUserId": None, "cbmEmail": "", "contactRecordId": "c1"})
    await service.update_mentor(c, "m1", {"mentorStatusNotes": "x"})
    assert not [u for u in c.updates if u[0] == "Contact"]


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
        return {"mentors": [{"id": "m1", "name": "Jane", "status": "Active"}],
                "metricsAvailable": True}

    monkeypatch.setattr("mentoradmin.router.assign_service.list_all_mentors", fake_list)
    with TestClient(_app(monkeypatch)) as c:
        data = c.get("/mentoradmin/api/mentors").json()
    assert data["mentors"][0]["name"] == "Jane"
    assert data["metricsAvailable"] is True


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


def test_update_reports_mentor_admin_error_as_400(monkeypatch):
    """A save rejected by the service (e.g. contact info on a mentor with no
    linked Contact) surfaces its exact message, not a generic 500/502."""
    _authed(monkeypatch)

    async def fake_update(client, mentor_id, changes, **kwargs):
        raise service.MentorAdminError("This mentor has no linked Contact record, so contact information can't be saved.")

    monkeypatch.setattr("mentoradmin.router.service.update_mentor", fake_update)
    with TestClient(_app(monkeypatch)) as c:
        r = c.put("/mentoradmin/api/mentors/m1", json={"changes": {"phoneNumber": "2165551234"}})
    assert r.status_code == 400
    assert "no linked Contact" in r.json()["detail"]


def test_expired_token_returns_401(monkeypatch):
    _authed(monkeypatch)

    async def boom(client):
        raise EspoError("list CMentorProfile failed: HTTP 401 Unauthorized")

    monkeypatch.setattr("mentoradmin.router.assign_service.list_all_mentors", boom)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentoradmin/api/mentors")
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


def test_crm_validation_rejection_returns_readable_400(monkeypatch):
    """An EspoCRM validationFailure (e.g. an enum value the CRM no longer
    accepts, if one slips past sanitization) comes back as a readable 400
    naming the field — never a raw 502/504 (the Allen Ingram prod failure)."""
    _authed(monkeypatch)

    async def fake_update(client, mentor_id, changes, **kwargs):
        raise EspoError(
            'update CMentorProfile/m1 failed: HTTP 400 {"messageTranslation":'
            '{"label":"validationFailure","scope":null,"data":'
            '{"field":"howDidYouHearAboutCBM","type":"valid"}}}'
        )

    monkeypatch.setattr("mentoradmin.router.service.update_mentor", fake_update)
    with TestClient(_app(monkeypatch)) as c:
        r = c.put("/mentoradmin/api/mentors/m1", json={"changes": {"howDidYouHearAboutCBM": "SBA"}})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "How Did You Hear About CBM" in detail
    assert "does not accept" in detail
    assert "502" not in detail and "messageTranslation" not in detail


def test_other_crm_error_returns_502(monkeypatch):
    _authed(monkeypatch)

    async def boom(client):
        raise EspoError("list CMentorProfile failed: HTTP 500 Server Error")

    monkeypatch.setattr("mentoradmin.router.assign_service.list_all_mentors", boom)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentoradmin/api/mentors")
    assert r.status_code == 502


def test_request_gate_rejects_wrong_team_with_team_name(monkeypatch):
    """Sign-in is shared (portal); THIS app's team is enforced per request —
    a signed-in user outside the Mentor Administration Team gets a 403 that
    names the required team."""
    outsider = dict(_USER, isAdmin=False, teams=["Client Administration Team"], roles=[])
    monkeypatch.setattr("mentoradmin.router.current_user", lambda request, key=None: outsider)
    monkeypatch.setattr("mentoradmin.router.client_for", lambda settings, user: object())
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentoradmin/api/mentors")
    assert r.status_code == 403
    assert "Mentor Administration Team" in r.json()["detail"]


def test_request_gate_passes_team_member(monkeypatch):
    member = dict(_USER, isAdmin=False, teams=["Mentor Administration Team"], roles=[])
    monkeypatch.setattr("mentoradmin.router.current_user", lambda request, key=None: member)
    monkeypatch.setattr("mentoradmin.router.client_for", lambda settings, user: object())

    async def fake_list(client):
        return {"mentors": [], "metricsAvailable": True}

    monkeypatch.setattr("mentoradmin.router.assign_service.list_all_mentors", fake_list)
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/mentoradmin/api/mentors").status_code == 200


def _authed_nonadmin(monkeypatch):
    user = dict(_USER, isAdmin=False)
    monkeypatch.setattr("mentoradmin.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("mentoradmin.router.client_for", lambda settings, user: object())


def test_setup_get_requires_admin(monkeypatch):
    _authed_nonadmin(monkeypatch)
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/mentoradmin/api/setup/google").status_code == 403


def test_setup_get_reports_unavailable_without_db(monkeypatch):
    # No DATABASE_URL/APP_ENCRYPTION_KEY in the test env -> the in-app store is off.
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch)) as c:
        data = c.get("/mentoradmin/api/setup/google").json()
    assert data["available"] is False


def test_setup_put_requires_admin(monkeypatch):
    _authed_nonadmin(monkeypatch)
    with TestClient(_app(monkeypatch)) as c:
        r = c.put("/mentoradmin/api/setup/google", json={"delegated_admin": "a@b.org"})
    assert r.status_code == 403


def test_provision_stream_reports_disabled(monkeypatch):
    # With provisioning unconfigured, the SSE stream emits a clear error event
    # rather than touching the CRM.
    _authed(monkeypatch)
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/mentoradmin/api/mentors/m1/provision")
    assert r.status_code == 200
    assert "turned off" in r.text.lower()


def test_provision_stream_requires_auth(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        assert c.post("/mentoradmin/api/mentors/m1/provision").status_code == 401


# --- "Update Mentor Status" verification sweep ---

class VerifyClient:
    """Roster of mentors + a User table, for the status-check sweep."""

    def __init__(self, mentors, users=None, contact_user=None):
        # mentors: list of full CMentorProfile records (dicts with id).
        self.mentors = {m["id"]: dict(m) for m in mentors}
        self.users = users or {}
        self.contact_user = contact_user
        self.updates = []

    async def list(self, entity, **kwargs):
        assert entity == "CMentorProfile"
        return {"list": [{"id": m["id"], "name": m.get("name")} for m in self.mentors.values()]}

    async def get(self, entity, record_id, select=None):
        if entity == "CMentorProfile":
            return dict(self.mentors[record_id])
        if entity == "User":
            if record_id in self.users:
                return dict(self.users[record_id])
            raise EspoError(f"GET User/{record_id} -> 404 Not Found")
        if entity == "Contact":
            return {"id": record_id, "assignedUserId": self.contact_user}
        raise AssertionError(f"unexpected get {entity}")

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        if entity == "CMentorProfile":
            self.mentors[record_id].update(payload)
        return {"id": record_id}


class VerifyDirectory:
    """mailbox_status keyed by email; anything else -> MISSING."""

    def __init__(self, existing=()):
        self.existing = set(existing)
        self.checked = []

    async def mailbox_status(self, email):
        from core.google_directory import MailboxStatus
        self.checked.append(email)
        return MailboxStatus.EXISTS if email in self.existing else MailboxStatus.MISSING


def _mentor(id, name, *, user=None, cbm=None, status="Active", record="Complete"):
    return {
        "id": id, "name": name, "mentorStatus": status, "recordStatus": record,
        "assignedUserId": user, "cbmEmail": cbm, "contactRecordId": None,
        "ethicsAgreementAccepted": True, "trainingCompleted": True, "termsAccepted": True,
    }


@pytest.mark.asyncio
async def test_verify_sweep_reports_user_and_mailbox():
    client = VerifyClient(
        mentors=[
            _mentor("m1", "Has Everything", user="u9", cbm="a.b@cbmentors.org"),
            _mentor("m2", "No User", user=None, cbm="c.d@cbmentors.org"),
            _mentor("m3", "Dangling User", user="gone", cbm=None),
        ],
        users={"u9": {"id": "u9", "userName": "a.b@cbmentors.org", "isActive": True}},
    )
    directory = VerifyDirectory(existing={"a.b@cbmentors.org"})
    rows = await service.verify_all_mentor_statuses(client, directory=directory)
    by = {r["id"]: r for r in rows}

    assert by["m1"]["user"]["exists"] is True and by["m1"]["user"]["active"] is True
    assert by["m1"]["mailbox"]["status"] == "exists"

    assert by["m2"]["user"] == {"linked": False, "exists": False, "detail": "no login User linked"}
    assert by["m2"]["mailbox"]["status"] == "missing"

    assert by["m3"]["user"]["linked"] is True and by["m3"]["user"]["exists"] is False
    assert by["m3"]["mailbox"]["status"] == "no-email"
    # only mentors with a CBM email hit the directory
    assert sorted(directory.checked) == ["a.b@cbmentors.org", "c.d@cbmentors.org"]


@pytest.mark.asyncio
async def test_verify_sweep_without_directory_reports_unavailable():
    client = VerifyClient(
        mentors=[_mentor("m1", "Jane", user=None, cbm="j@cbmentors.org")],
    )
    rows = await service.verify_all_mentor_statuses(client, directory=None)
    assert rows[0]["mailbox"]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_verify_sweep_resyncs_record_status():
    # Stored recordStatus says Complete but the sign-offs are missing ->
    # the sweep recomputes Incomplete and persists it.
    m = _mentor("m1", "Stale", user=None, cbm=None, status="Candidate", record="Complete")
    m["ethicsAgreementAccepted"] = False
    m["contactRecordId"] = None
    client = VerifyClient(mentors=[m])
    rows = await service.verify_all_mentor_statuses(client)
    assert rows[0]["recordStatus"] == "Incomplete"
    assert ("CMentorProfile", "m1", {"recordStatus": "Incomplete"}) in client.updates


@pytest.mark.asyncio
async def test_verify_sweep_heals_contact_user_link():
    """The sweep reconciles the member<->Contact User links (best-effort) so
    'Update Mentor Status' FIXES a roster whose Contacts lost their effective
    assignment (the 2026-07-16 Multiple-Assigned-Users switch) — writing both
    shapes, since Contact's single assignedUser is now disabled."""
    m = _mentor("m1", "Jane", user="u9", cbm="jane.d@cbmentors.org")
    m["contactRecordId"] = "c1"
    client = VerifyClient(
        mentors=[m],
        users={"u9": {"id": "u9", "userName": "jane.d@cbmentors.org", "isActive": True}},
    )
    await service.verify_all_mentor_statuses(client)
    contact_updates = [u for u in client.updates if u[0] == "Contact"]
    assert contact_updates == [
        ("Contact", "c1", {"assignedUserId": "u9", "assignedUsersIds": ["u9"]})
    ]


def test_status_check_endpoint_requires_auth(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        assert c.post("/mentoradmin/api/mentors/status-check").status_code == 401


def test_status_check_endpoint_returns_rows(monkeypatch):
    _authed(monkeypatch)

    async def fake_verify(client, *, user_client=None, directory=None):
        return [{"id": "m1", "name": "Jane", "user": {"exists": True},
                 "mailbox": {"status": "unavailable"}}]

    monkeypatch.setattr("mentoradmin.router.service.verify_all_mentor_statuses", fake_verify)
    with TestClient(_app(monkeypatch)) as c:
        resp = c.post("/mentoradmin/api/mentors/status-check")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mailboxCheckEnabled"] is False
        assert data["mentors"][0]["id"] == "m1"
