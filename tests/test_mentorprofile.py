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
         "cbmEmail": "x@cbmentors.org", "maximumClientCapacity": 99},
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
                       "maximumClientCapacity", "cbmEmail", "backgroundCheckCompleted",
                       "departureDate", "felonyConfiction", "mentorStatusNotes"):
        assert staff_only not in names
    # the photo is rendered but never part of a field save
    assert "profilePhoto" not in service.EDIT_NAMES
    assert "mentorTitle" in service.PROFILE_EDIT_NAMES
    assert "cLinkedInProfile" in service.CONTACT_NAMES


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

    async def fake_get(client, user_id):
        return {"profileFound": False}

    monkeypatch.setattr("mentorprofile.router.service.get_own_profile", fake_get)
    with TestClient(_app(monkeypatch)) as c:
        assert c.get("/mentorprofile/api/profile").json() == {"profileFound": False}


def test_profile_uses_session_user_id(monkeypatch):
    _authed(monkeypatch)
    seen = {}

    async def fake_get(client, user_id):
        seen["user_id"] = user_id
        return {"profileFound": True, "record": {"id": "m1"}}

    monkeypatch.setattr("mentorprofile.router.service.get_own_profile", fake_get)
    with TestClient(_app(monkeypatch)) as c:
        data = c.get("/mentorprofile/api/profile").json()
    assert seen["user_id"] == "u1"  # always the session's user — never client input
    assert data["record"]["id"] == "m1"


def test_update_reports_profile_error_as_400(monkeypatch):
    _authed(monkeypatch)

    async def fake_update(client, user_id, changes):
        raise service.MentorProfileError("Your mentor profile has no linked Contact record.")

    monkeypatch.setattr("mentorprofile.router.service.update_own_profile", fake_update)
    with TestClient(_app(monkeypatch)) as c:
        r = c.put("/mentorprofile/api/profile", json={"changes": {"phoneNumber": "1"}})
    assert r.status_code == 400
    assert "no linked Contact" in r.json()["detail"]


def test_expired_token_returns_401(monkeypatch):
    _authed(monkeypatch)

    async def boom(client, user_id):
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
    assert {"title": "My Mentor Profile", "url": "/mentorprofile/"} in apps
    outsider = dict(_USER, teams=["Marketing Admin Team"])
    apps = _apps_for(outsider, settings)
    assert all(a["url"] != "/mentorprofile/" for a in apps)
