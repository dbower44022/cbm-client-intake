"""My Mentor Profile router + service: own-profile scoping, whitelist, photo."""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from forms import info_request
from mentorprofile import service

_USER = {"userId": "u1", "userName": "jane", "name": "Jane Mentor",
         "isAdmin": False, "token": "tok", "teams": ["Mentor Team"], "roles": []}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- service-level fake client ---

class FakeClient:
    """Canned CMentorProfile list (for own-profile resolution) + record reads."""

    def __init__(self, profiles=None, record=None, contact=None, metadata=None):
        # Rows returned by list(CMentorProfile) — the own-profile scan.
        self.profiles = profiles if profiles is not None else [
            {"id": "other", "assignedUserId": "someone-else"},
            {"id": "m1", "assignedUserId": "u1"},
        ]
        self.record = record or {
            "id": "m1", "name": "Jane Mentor", "mentorTitle": "Marketing",
            "contactRecordId": "c1", "profilePhotoId": None,
        }
        self.contact = contact or {
            "id": "c1", "firstName": "Jane", "lastName": "Mentor",
            "emailAddress": "jane@example.com", "cLinkedInProfile": "linkedin.com/in/jane",
        }
        self._metadata = metadata or {}
        self.updates = []
        self.gets = []
        self.uploads = []

    async def list(self, entity, **kwargs):
        rows = self.profiles
        offset = kwargs.get("offset", 0)
        return {"list": rows[offset:], "total": len(rows)}

    async def get(self, entity, record_id, select=None):
        self.gets.append((entity, record_id, select))
        if entity == "Contact":
            return dict(self.contact, id=record_id)
        return dict(self.record, id=record_id)

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        if entity == "Contact":
            self.contact.update(payload)
        else:
            self.record.update(payload)
        return {"id": record_id, **payload}

    async def metadata(self, key):
        return self._metadata

    async def upload_attachment(self, *, filename, content_type, data_base64,
                                related_type, field):
        self.uploads.append((filename, content_type, related_type, field))
        return "att-1"

    async def download_attachment(self, attachment_id):
        return b"jpegbytes", "image/jpeg"


# --- own-profile resolution ---

@pytest.mark.asyncio
async def test_get_own_profile_resolves_by_assigned_user():
    client = FakeClient()
    result = await service.get_own_profile(client, "u1")
    assert result["profileFound"] is True
    assert result["record"]["id"] == "m1"
    # linked Contact fields are merged into the record
    assert result["record"]["firstName"] == "Jane"
    assert result["record"]["cLinkedInProfile"] == "linkedin.com/in/jane"


@pytest.mark.asyncio
async def test_get_own_profile_matches_collaborators_shape():
    """Prod links the mentor's User via assignedUsers (collaborators)."""
    client = FakeClient(profiles=[{"id": "m2", "assignedUsersIds": ["u1"]}],
                        record={"id": "m2", "name": "Jane", "contactRecordId": None})
    result = await service.get_own_profile(client, "u1")
    assert result["profileFound"] is True
    assert result["record"]["id"] == "m2"


@pytest.mark.asyncio
async def test_get_own_profile_none_linked():
    client = FakeClient(profiles=[{"id": "other", "assignedUserId": "someone-else"}])
    result = await service.get_own_profile(client, "u1")
    assert result == {"profileFound": False}


@pytest.mark.asyncio
async def test_get_own_profile_without_contact_still_loads():
    client = FakeClient(record={"id": "m1", "name": "Jane", "contactRecordId": None})
    result = await service.get_own_profile(client, "u1")
    assert result["profileFound"] is True
    assert result["record"].get("firstName") is None


# --- update: whitelist + routing ---

@pytest.mark.asyncio
async def test_update_whitelists_and_never_trusts_client_ids():
    client = FakeClient()
    await service.update_own_profile(
        client, "u1",
        {"mentorTitle": "Strategy", "mentorStatus": "Inactive", "id": "hacked",
         "cbmEmail": "x@cbmentors.org", "duesStatus": "Waived", "mentorStartDate": "2020-01-01"},
    )
    assert len(client.updates) == 1
    entity, rid, payload = client.updates[0]
    # writes to the RESOLVED own profile, only whitelisted fields survive
    assert (entity, rid) == ("CMentorProfile", "m1")
    assert payload == {"mentorTitle": "Strategy"}


@pytest.mark.asyncio
async def test_update_routes_contact_fields_to_contact():
    client = FakeClient()
    await service.update_own_profile(
        client, "u1",
        {"mentorTitle": "Strategy", "phoneNumber": "(216) 555-1234",
         "cLinkedInProfile": "https://linkedin.com/in/jane"},
    )
    targets = {(e, r): p for e, r, p in client.updates}
    assert targets[("CMentorProfile", "m1")] == {"mentorTitle": "Strategy"}
    contact_payload = targets[("Contact", "c1")]
    assert contact_payload["phoneNumber"] == "+12165551234"  # E.164 at the boundary
    assert contact_payload["cLinkedInProfile"] == "https://linkedin.com/in/jane"


@pytest.mark.asyncio
async def test_contact_changes_without_linked_contact_fail_before_any_write():
    client = FakeClient(record={"id": "m1", "name": "Jane", "contactRecordId": None})
    with pytest.raises(service.MentorProfileError):
        await service.update_own_profile(client, "u1", {"mentorTitle": "X", "phoneNumber": "12165551234"})
    assert client.updates == []


@pytest.mark.asyncio
async def test_update_without_profile_raises():
    client = FakeClient(profiles=[])
    with pytest.raises(service.MentorProfileError):
        await service.update_own_profile(client, "u1", {"mentorTitle": "X"})


# --- enum sanitization (a drifted value never blocks the save) ---

@pytest.mark.asyncio
async def test_update_drops_drifted_multienum_member_and_warns():
    meta = {"areaOfExpertise": {"type": "multiEnum", "options": ["Marketing", "Accounting"]}}
    client = FakeClient(metadata=meta)
    result = await service.update_own_profile(
        client, "u1", {"areaOfExpertise": ["Marketing", "Gone Skill"]}
    )
    _, _, payload = client.updates[0]
    assert payload == {"areaOfExpertise": ["Marketing"]}
    assert "Gone Skill" in result["warnings"][0]


@pytest.mark.asyncio
async def test_update_enum_sanitize_fails_open():
    class NoMeta(FakeClient):
        async def metadata(self, key):
            raise EspoError("metadata unavailable")

    client = NoMeta()
    result = await service.update_own_profile(
        client, "u1", {"areaOfExpertise": ["Anything"]}
    )
    _, _, payload = client.updates[0]
    assert payload == {"areaOfExpertise": ["Anything"]}
    assert "warnings" not in result


# --- field spec / options / required ---

def test_field_spec_is_non_administrative():
    names = {f["name"] for f in service.PROFILE_FIELDS}
    for staff_only in ("mentorStatus", "mentorType", "recordStatus", "duesStatus",
                       "cbmEmail", "backgroundCheckCompleted",
                       "departureDate", "felonyConfiction", "mentorStatusNotes"):
        assert staff_only not in names
    # the photo is rendered but never part of a field save
    assert "profilePhoto" not in service.EDIT_NAMES
    assert "mentorTitle" in service.PROFILE_EDIT_NAMES
    # mentor-editable per Doug (2026-07-14): capacity + internal description
    assert "maximumClientCapacity" in service.PROFILE_EDIT_NAMES
    assert "description" in service.PROFILE_EDIT_NAMES
    # Contact-side personal details route to the Contact record
    for contact_field in ("cLinkedInProfile", "cBirthday", "cSpouseName"):
        assert contact_field in service.CONTACT_NAMES
    # "Mentoring since" is read-only context, never in the whitelist
    assert "mentorStartDate" not in service.EDIT_NAMES
    assert "mentorStartDate" in service._DETAIL_SELECT


@pytest.mark.asyncio
async def test_field_options_reads_live_enums():
    meta = {"areaOfExpertise": {"type": "multiEnum", "options": ["", "Marketing"]},
            "fluentLanguages": {"type": "multiEnum", "options": ["English"]}}
    options = await service.field_options(FakeClient(metadata=meta))
    assert options["areaOfExpertise"] == ["Marketing"]  # blanks dropped
    assert options["fluentLanguages"] == ["English"]


@pytest.mark.asyncio
async def test_field_required_reads_both_entities():
    meta = {"lastName": {"type": "varchar", "required": True},
            "mentorTitle": {"type": "varchar", "required": False}}
    required = await service.field_required(FakeClient(metadata=meta))
    assert "lastName" in required
    assert "mentorTitle" not in required


# --- feature-gated website-summary field (mentorSummary) ---

_SUMMARY_META = {"mentorSummary": {"type": "text"}}


@pytest.mark.asyncio
async def test_summary_field_gated_off_until_crm_has_it():
    client = FakeClient()  # metadata without mentorSummary
    spec = await service.field_spec_live(client)
    assert all(f["name"] != "mentorSummary" for f in spec)
    # not selected on reads…
    await service.get_own_profile(client, "u1")
    profile_gets = [g for g in client.gets if g[0] == "CMentorProfile" and g[2] and "mentorTitle" in g[2]]
    assert profile_gets and "mentorSummary" not in profile_gets[0][2]
    # …and a smuggled change is dropped, not written
    await service.update_own_profile(client, "u1", {"mentorSummary": "hi", "mentorTitle": "X"})
    _, _, payload = client.updates[0]
    assert payload == {"mentorTitle": "X"}


@pytest.mark.asyncio
async def test_summary_field_activates_when_crm_has_it():
    client = FakeClient(metadata=_SUMMARY_META)
    spec = await service.field_spec_live(client)
    assert any(f["name"] == "mentorSummary" for f in spec)
    await service.get_own_profile(client, "u1")
    profile_gets = [g for g in client.gets if g[0] == "CMentorProfile" and g[2] and "mentorTitle" in g[2]]
    assert "mentorSummary" in profile_gets[0][2]
    await service.update_own_profile(client, "u1", {"mentorSummary": "Short intro."})
    _, _, payload = client.updates[0]
    assert payload == {"mentorSummary": "Short intro."}


# --- photo ---

@pytest.mark.asyncio
async def test_set_own_photo_uploads_and_links():
    client = FakeClient()
    result = await service.set_own_photo(
        client, "u1", filename="me.jpg", content_type="image/jpeg", data_base64="aGk="
    )
    assert client.uploads == [("me.jpg", "image/jpeg", "CMentorProfile", "profilePhoto")]
    assert ("CMentorProfile", "m1", {"profilePhotoId": "att-1"}) in client.updates
    assert result == {"profilePhotoId": "att-1"}


@pytest.mark.asyncio
async def test_set_own_photo_rejects_bad_type_and_oversize():
    client = FakeClient()
    with pytest.raises(service.MentorProfileError):
        await service.set_own_photo(client, "u1", filename="a.pdf",
                                    content_type="application/pdf", data_base64="aGk=")
    big = "A" * (service.MAX_PHOTO_B64_CHARS + 1)
    with pytest.raises(service.MentorProfileError):
        await service.set_own_photo(client, "u1", filename="a.jpg",
                                    content_type="image/jpeg", data_base64=big)
    assert client.uploads == [] and client.updates == []


@pytest.mark.asyncio
async def test_get_own_photo_none_when_unset():
    client = FakeClient()
    assert await service.get_own_photo(client, "u1") is None


@pytest.mark.asyncio
async def test_get_own_photo_streams_bytes():
    client = FakeClient(record={"id": "m1", "profilePhotoId": "att-9", "contactRecordId": None})
    data, ctype = await service.get_own_photo(client, "u1")
    assert data == b"jpegbytes" and ctype == "image/jpeg"


@pytest.mark.asyncio
async def test_clear_own_photo():
    client = FakeClient()
    await service.clear_own_photo(client, "u1")
    assert ("CMentorProfile", "m1", {"profilePhotoId": None}) in client.updates


# --- router tests ---

def _app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")  # enables session + router
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


def _authed(monkeypatch, user=_USER):
    monkeypatch.setattr("mentorprofile.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr("mentorprofile.router.client_for", lambda settings, user: object())


def test_requires_auth(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/mentorprofile/api/profile").status_code == 401
        assert c.get("/mentorprofile/api/session").status_code == 401


def test_non_mentor_team_forbidden(monkeypatch):
    outsider = dict(_USER, teams=["Marketing Admin Team"], isAdmin=False)
    _authed(monkeypatch, outsider)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentorprofile/api/profile")
    assert r.status_code == 403
    assert "Mentor Team" in r.json()["detail"]


def test_admin_passes_gate(monkeypatch):
    admin = dict(_USER, teams=[], isAdmin=True)
    _authed(monkeypatch, admin)

    async def fake_get(client, user_id, settings=None):
        return {"profileFound": False}

    monkeypatch.setattr("mentorprofile.router.service.get_own_profile", fake_get)
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/mentorprofile/api/profile").json() == {"profileFound": False}


def test_profile_uses_session_user_id(monkeypatch):
    _authed(monkeypatch)
    seen = {}

    async def fake_get(client, user_id, settings=None):
        seen["user_id"] = user_id
        return {"profileFound": True, "record": {"id": "m1"}}

    monkeypatch.setattr("mentorprofile.router.service.get_own_profile", fake_get)
    with TestClient(_app(monkeypatch)) as c:
        data = c.get("/mentorprofile/api/profile").json()
    assert seen["user_id"] == "u1"  # always the session's user — never client input
    assert data["record"]["id"] == "m1"


def test_update_reports_profile_error_as_400(monkeypatch):
    _authed(monkeypatch)

    async def fake_update(client, user_id, changes, settings=None):
        raise service.MentorProfileError("Your mentor profile has no linked Contact record.")

    monkeypatch.setattr("mentorprofile.router.service.update_own_profile", fake_update)
    with TestClient(_app(monkeypatch)) as c:
        r = c.put("/mentorprofile/api/profile", json={"changes": {"phoneNumber": "1"}})
    assert r.status_code == 400
    assert "no linked Contact" in r.json()["detail"]


def test_crm_403_returns_readable_permission_message(monkeypatch):
    """A CRM permission rejection (e.g. the mentor role lacking Attachment
    create — found live 2026-07-14) surfaces as a plain-language 403, not a
    raw 502/504."""
    _authed(monkeypatch)

    async def boom(client, user_id, **kwargs):
        raise EspoError("upload attachment failed: HTTP 403 ")

    monkeypatch.setattr("mentorprofile.router.service.set_own_photo", boom)
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/mentorprofile/api/photo",
                   json={"filename": "a.jpg", "contentType": "image/jpeg", "dataBase64": "aGk="})
    assert r.status_code == 403
    assert "contact CBM staff" in r.json()["detail"]


def test_expired_token_returns_401(monkeypatch):
    _authed(monkeypatch)

    async def boom(client, user_id, settings=None):
        raise EspoError("list CMentorProfile failed: HTTP 401 Unauthorized")

    monkeypatch.setattr("mentorprofile.router.service.get_own_profile", boom)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentorprofile/api/profile")
    assert r.status_code == 401
    assert "expired" in r.json()["detail"].lower()


def test_photo_get_404_when_none(monkeypatch):
    _authed(monkeypatch)

    async def fake_photo(client, user_id):
        return None

    monkeypatch.setattr("mentorprofile.router.service.get_own_photo", fake_photo)
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/mentorprofile/api/photo").status_code == 404


def test_photo_get_streams_bytes(monkeypatch):
    _authed(monkeypatch)

    async def fake_photo(client, user_id):
        return b"jpegbytes", "image/jpeg"

    monkeypatch.setattr("mentorprofile.router.service.get_own_photo", fake_photo)
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentorprofile/api/photo")
    assert r.status_code == 200
    assert r.content == b"jpegbytes"
    assert r.headers["content-type"] == "image/jpeg"
    assert "no-store" in r.headers["cache-control"]


def test_photo_upload_roundtrip(monkeypatch):
    _authed(monkeypatch)
    seen = {}

    async def fake_set(client, user_id, *, filename, content_type, data_base64):
        seen.update(user_id=user_id, filename=filename, content_type=content_type)
        return {"profilePhotoId": "att-1"}

    monkeypatch.setattr("mentorprofile.router.service.set_own_photo", fake_set)
    payload = {"filename": "me.jpg", "contentType": "image/jpeg",
               "dataBase64": base64.b64encode(b"hi").decode()}
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/mentorprofile/api/photo", json=payload)
    assert r.json() == {"profilePhotoId": "att-1"}
    assert seen == {"user_id": "u1", "filename": "me.jpg", "content_type": "image/jpeg"}


def test_fields_endpoint(monkeypatch):
    _authed(monkeypatch)

    async def fake_opts(client):
        return {"areaOfExpertise": ["Marketing"]}

    async def fake_req(client):
        return ["lastName"]

    monkeypatch.setattr("mentorprofile.router.service.field_options", fake_opts)
    monkeypatch.setattr("mentorprofile.router.service.field_required", fake_req)
    with TestClient(_app(monkeypatch)) as c:
        data = c.get("/mentorprofile/api/fields").json()
    assert data["options"]["areaOfExpertise"] == ["Marketing"]
    assert data["required"] == ["lastName"]
    assert any(f["name"] == "mentorTitle" for f in data["fields"])


def test_frontend_served_and_alias(monkeypatch):
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/mentorprofile/")
        assert r.status_code == 200
        assert "My Mentor Profile" in r.text
        for alias in ("/myprofile", "/MentorProfile"):
            assert c.get(alias, follow_redirects=False).status_code == 307


def test_portal_lists_app_for_mentor_team(monkeypatch):
    from core.config import Settings
    from portal.router import _apps_for
    settings = Settings()
    apps = _apps_for(dict(_USER), settings)
    assert any(a["url"] == "/mentorprofile/" and a["title"] == "My Mentor Profile" for a in apps)
    outsider = dict(_USER, teams=["Marketing Admin Team"])
    apps = _apps_for(outsider, settings)
    assert all(a["url"] != "/mentorprofile/" for a in apps)


# --- own-Contact heal-on-access (2026-07-20 — the second stamp-drift class) ----


class _SystemFake:
    """Stands in for the API-key client the heal runs under."""

    def __init__(self, contact_assigned=None):
        self.contact = {"assignedUsersIds": list(contact_assigned or [])}
        self.updates = []

    async def get(self, entity, record_id, select=None):
        return dict(self.contact, id=record_id)

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, dict(payload)))
        self.contact.update(payload)
        return {"id": record_id}


def _heal_settings():
    from core.config import Settings

    return Settings(espo_dry_run=False, espo_api_key="k")


@pytest.mark.asyncio
async def test_profile_load_heals_unstamped_own_contact(monkeypatch):
    """The reported failure: a mentor's linked Contact missing their User 403s
    their own contact-field save. Opening the profile now heals it via the
    system identity BEFORE they ever hit Save."""
    from assignments import stamps as stamps_mod

    system = _SystemFake(contact_assigned=["someone-else"])
    monkeypatch.setattr(stamps_mod, "system_client", lambda settings: system)
    client = FakeClient()
    result = await service.get_own_profile(client, "u1", _heal_settings())
    assert result["profileFound"] is True
    # Merge-only: the existing user is kept, the mentor's own added.
    assert system.updates == [("Contact", "c1", {"assignedUsersIds": ["someone-else", "u1"]})]


@pytest.mark.asyncio
async def test_profile_save_heals_before_the_contact_write(monkeypatch):
    from assignments import stamps as stamps_mod

    system = _SystemFake()
    monkeypatch.setattr(stamps_mod, "system_client", lambda settings: system)
    client = FakeClient()
    await service.update_own_profile(
        client, "u1", {"phoneNumber": "216-555-0100"}, _heal_settings()
    )
    # The heal wrote through the SYSTEM client…
    assert system.updates == [("Contact", "c1", {"assignedUsersIds": ["u1"]})]
    # …and the user's own contact write then proceeded as them.
    assert ("Contact", "c1", {"phoneNumber": "+12165550100"}) in client.updates


@pytest.mark.asyncio
async def test_heal_is_noop_when_already_stamped(monkeypatch):
    from assignments import stamps as stamps_mod

    system = _SystemFake(contact_assigned=["u1"])
    monkeypatch.setattr(stamps_mod, "system_client", lambda settings: system)
    await service.get_own_profile(FakeClient(), "u1", _heal_settings())
    assert system.updates == []


@pytest.mark.asyncio
async def test_heal_failure_never_blocks_the_profile(monkeypatch):
    from assignments import stamps as stamps_mod

    class Exploding(_SystemFake):
        async def get(self, entity, record_id, select=None):
            raise RuntimeError("CRM down")

    monkeypatch.setattr(stamps_mod, "system_client", lambda settings: Exploding())
    result = await service.get_own_profile(FakeClient(), "u1", _heal_settings())
    assert result["profileFound"] is True  # the page still loads


@pytest.mark.asyncio
async def test_heal_inert_without_settings_or_in_dry_run(monkeypatch):
    from core.config import Settings
    from assignments import stamps as stamps_mod

    called = []
    monkeypatch.setattr(stamps_mod, "system_client",
                        lambda settings: called.append(1))
    await service.get_own_profile(FakeClient(), "u1")  # no settings
    await service.get_own_profile(FakeClient(), "u1", Settings(espo_dry_run=True))
    assert called == []
