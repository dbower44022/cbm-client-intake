"""Quick add — creating a partner / funder from the grid (Doug's request
2026-08-12).

The rules under test are the ones that make this safe to hand to staff:

* it runs the SAME three-record sequence as the public intake forms (Account →
  Contact → profile → relate), typed with the domain's discriminators;
* an existing company / contact is REUSED and only null-filled, never
  duplicated and never overwritten;
* the contact block is optional, but a nameless contact is refused;
* a drifted enum is dropped, not fatal (the non-required-enum policy);
* the routes exist only on the domains that own the feature, and only when the
  runtime flag is on.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from forms import info_request
from sessions import service
from sessions.config import MENTOR, PARTNER, SPONSOR

_USER = {
    "userId": "u1", "userName": "pat.partner", "name": "Pat Partner",
    "isAdmin": False,
    "teams": ["Partner Management Team", "Sponsor Management Team", "Mentor Team"],
    "roles": [], "token": "t",
}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class Fake:
    """Minimal SessionClient for the create path."""

    def __init__(self, *, found=None, meta=None, mentors=None, relate_error=False):
        self.found = found or {}          # (entity, attr, value) -> record
        self.meta = meta or {}
        self.mentors = mentors if mentors is not None else [
            {"id": "MP1", "name": "Pat Partner", "assignedUserId": "u1"},
            {"id": "MP2", "name": "Other Manager", "assignedUserId": "u9"},
        ]
        self.created = []                 # [(entity, payload)]
        self.updates = []                 # [(entity, id, payload)]
        self.related = []                 # [(entity, id, link, related_id)]
        self._relate_error = relate_error
        self._seq = 0

    async def find_one(self, entity, attribute, value, select="id"):
        return self.found.get((entity, attribute, value))

    async def list(self, entity, **kw):
        if entity == "CMentorProfile":
            return {"list": list(self.mentors)}
        return {"list": []}

    async def create(self, entity, payload):
        self._seq += 1
        rid = f"{entity.lower()}-{self._seq}"
        self.created.append((entity, payload))
        return {"id": rid}

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        return {"id": record_id}

    async def relate(self, entity, record_id, link, related_id):
        if self._relate_error:
            raise EspoError(f"relate failed: HTTP 403 forbidden")
        self.related.append((entity, record_id, link, related_id))

    async def metadata(self, key):
        return self.meta


class FakeApi(Fake):
    """The org-wide API client — only ever asked to create the Account."""


_PARTNER_META = {
    "partnershipStatus": {"options": ["", "Candidate", "Active", "Dormant"]},
    "partnershipType": {"options": ["", "Referral", "Programme"]},
}


def _payload(fake, entity):
    return next(p for e, p in fake.created if e == entity)


def _has(fake, entity):
    return any(e == entity for e, _ in fake.created)


# --- the field spec ---------------------------------------------------------

def test_spec_is_company_contact_profile_with_a_manager_picker():
    names = [f["name"] for f in service.create_field_spec(PARTNER)]
    assert names[:2] == ["company", "website"]
    assert "emailAddress" in names and "firstName" in names
    assert "partnershipStatus" in names and "partnerNotes" in names
    # Long-form notes come last, AFTER the manager picker — a full-height
    # rich-text editor between them pushes the picker and the Create button off
    # the bottom of the modal (found in the preview harness).
    assert names[-2:] == ["_manager", "partnerNotes"]
    assert [f["name"] for f in service.create_field_spec(SPONSOR)][-2:] == [
        "_manager", "description"
    ]
    sections = {f["name"]: f["section"] for f in service.create_field_spec(PARTNER)}
    assert sections["company"] == "company"
    assert sections["emailAddress"] == "contact"
    assert sections["name"] == "profile"


def test_mentor_domain_has_no_create_spec():
    """A client engagement arrives through intake and is assigned in Client
    Administration — there is no "type a new one in" step to add."""
    assert MENTOR.create_spec is None
    assert service.create_field_spec(MENTOR) == []


def test_funder_spec_uses_the_funder_words_and_its_own_notes_field():
    spec = {f["name"]: f for f in service.create_field_spec(SPONSOR)}
    assert spec["name"]["label"] == "Funder name"
    # CSponsorProfile.description IS the funder notes field, and it's longtext.
    assert spec["description"]["type"] == "text"
    assert spec["_manager"]["label"] == "Funder Manager"
    assert "partnershipStatus" not in spec


@pytest.mark.asyncio
async def test_enum_options_come_from_live_crm_metadata():
    fake = Fake(meta=_PARTNER_META)
    opts = await service.create_field_options(PARTNER, fake)
    assert opts["partnershipStatus"] == ["Candidate", "Active", "Dormant"]
    assert "" not in opts["partnershipType"]


@pytest.mark.asyncio
async def test_manager_options_default_to_the_callers_own_profile():
    fake = Fake()
    res = await service.manager_options(PARTNER, fake, "u1")
    assert res["defaultManagerId"] == "MP1"
    assert {m["id"] for m in res["managers"]} == {"MP1", "MP2"}


@pytest.mark.asyncio
async def test_manager_options_degrade_to_empty_when_unreadable():
    """The sponsor team's role may not read CMentorProfile at all — that must
    leave a blank picker, not a broken form (the manager is optional)."""
    class NoMentors(Fake):
        async def list(self, entity, **kw):
            raise EspoError("list CMentorProfile failed: HTTP 403 forbidden")

    res = await service.manager_options(SPONSOR, NoMentors(), "u1")
    assert res == {"managers": [], "defaultManagerId": None}


# --- the create -------------------------------------------------------------

@pytest.mark.asyncio
async def test_creates_account_contact_profile_and_links_them():
    fake, api = Fake(meta=_PARTNER_META), FakeApi()
    res = await service.create_record(
        PARTNER, fake, api,
        {
            "company": "Acme Supply Co.", "website": "acme.com",
            "firstName": "Dana", "lastName": "Reyes",
            "emailAddress": "dana@acme.com", "phoneNumber": "216-555-0134",
            "title": "Director",
            "name": "Acme Supply Co.", "partnershipStatus": "Candidate",
            "partnershipType": "Referral", "_manager": "MP1",
        },
        user_id="u1",
    )
    # The Account is created through the API client (the staff role may not
    # hold Account create — the resolve_company precedent).
    account = _payload(api, "Account")
    assert account["name"] == "Acme Supply Co."
    assert account["cCompanyType"] == ["Partner"]
    assert account["website"] == "https://acme.com"   # bare domain normalized
    assert not _has(fake, "Account")

    contact = _payload(fake, "Contact")
    assert contact["cContactType"] == ["Partner"]
    assert contact["accountId"] == "account-1"
    assert contact["phoneNumber"] == "+12165550134"   # E.164
    assert contact["title"] == "Director"

    profile = _payload(fake, "CPartnerProfile")
    assert profile["name"] == "Acme Supply Co."
    assert profile["partnerCompanyId"] == "account-1"
    assert profile["primaryPartnercontactId"] == "contact-1"
    assert profile["partnerManagerId"] == "MP1"
    assert profile["partnershipStatus"] == "Candidate"
    assert profile["assignedUsersIds"] == ["u1"]      # owner-stamped

    # The contact joins the profile's Contacts hasMany, as intake does.
    assert fake.related == [("CPartnerProfile", res["id"], "contacts", "contact-1")]
    assert res["accountCreated"] is True and res["contactCreated"] is True


@pytest.mark.asyncio
async def test_existing_company_is_reused_and_gains_the_type():
    """A company CBM already knows as a Client becoming a Partner must gain the
    type — cCompanyType is the discriminator the whole CRM filters on — but
    never lose what it already is."""
    fake = Fake(
        meta=_PARTNER_META,
        found={("Account", "name", "Acme Supply Co."):
               {"id": "A-OLD", "name": "Acme Supply Co.", "cCompanyType": ["Client"]}},
    )
    api = FakeApi()
    res = await service.create_record(
        PARTNER, fake, api, {"company": "Acme Supply Co.", "name": "Acme"}, user_id="u1",
    )
    assert not api.created                       # nothing new created
    assert fake.updates == [("Account", "A-OLD", {"cCompanyType": ["Client", "Partner"]})]
    assert _payload(fake, "CPartnerProfile")["partnerCompanyId"] == "A-OLD"
    assert res["accountCreated"] is False


@pytest.mark.asyncio
async def test_existing_contact_is_null_filled_never_overwritten():
    fake = Fake(
        meta=_PARTNER_META,
        found={("Contact", "emailAddress", "dana@acme.com"):
               {"id": "C-OLD", "firstName": "Dana", "lastName": "", "title": "VP"}},
    )
    await service.create_record(
        PARTNER, fake, FakeApi(),
        {"company": "Acme", "firstName": "D.", "lastName": "Reyes",
         "emailAddress": "dana@acme.com", "title": "Director"},
        user_id="u1",
    )
    assert not _has(fake, "Contact")
    # lastName was empty -> filled; firstName and title were set -> untouched.
    assert fake.updates == [("Contact", "C-OLD", {"lastName": "Reyes"})]
    assert _payload(fake, "CPartnerProfile")["primaryPartnercontactId"] == "C-OLD"


@pytest.mark.asyncio
async def test_contact_block_is_optional():
    fake = Fake(meta=_PARTNER_META)
    res = await service.create_record(
        PARTNER, fake, FakeApi(), {"company": "Acme", "name": "Acme"}, user_id="u1",
    )
    assert not _has(fake, "Contact")
    assert "primaryPartnercontactId" not in _payload(fake, "CPartnerProfile")
    assert fake.related == []
    assert res["contactId"] is None


@pytest.mark.asyncio
async def test_a_nameless_contact_is_refused_before_anything_is_written():
    fake = Fake(meta=_PARTNER_META)
    with pytest.raises(service.SessionError, match="first or last name"):
        await service.create_record(
            PARTNER, fake, FakeApi(),
            {"company": "Acme", "emailAddress": "dana@acme.com"}, user_id="u1",
        )
    assert not _has(fake, "CPartnerProfile")


@pytest.mark.asyncio
async def test_company_name_is_required():
    fake = Fake(meta=_PARTNER_META)
    with pytest.raises(service.SessionError, match="company name"):
        await service.create_record(PARTNER, fake, FakeApi(), {"name": "Acme"}, user_id="u1")
    assert not fake.created


@pytest.mark.asyncio
async def test_record_name_defaults_to_the_company():
    fake = Fake(meta=_PARTNER_META)
    await service.create_record(PARTNER, fake, FakeApi(), {"company": "Acme"}, user_id="u1")
    assert _payload(fake, "CPartnerProfile")["name"] == "Acme"


@pytest.mark.asyncio
async def test_a_drifted_enum_is_dropped_not_fatal():
    """The non-required-enum policy: one value the CRM no longer offers must
    not 400 the whole new partner."""
    fake = Fake(meta=_PARTNER_META)
    await service.create_record(
        PARTNER, fake, FakeApi(),
        {"company": "Acme", "partnershipStatus": "Candidate",
         "partnershipType": "Retired Option"},
        user_id="u1",
    )
    profile = _payload(fake, "CPartnerProfile")
    assert profile["partnershipStatus"] == "Candidate"
    assert "partnershipType" not in profile


@pytest.mark.asyncio
async def test_unknown_fields_are_dropped():
    """The spec is the whitelist — the POST can't be used to set arbitrary
    fields on the profile."""
    fake = Fake(meta=_PARTNER_META)
    await service.create_record(
        PARTNER, fake, FakeApi(),
        {"company": "Acme", "partnershipValue": ["Money"], "teamsIds": ["T-EVIL"]},
        user_id="u1",
    )
    profile = _payload(fake, "CPartnerProfile")
    assert "partnershipValue" not in profile
    assert "teamsIds" not in profile  # no team resolved in this fake


@pytest.mark.asyncio
async def test_a_failed_contact_link_does_not_fail_the_create():
    fake = Fake(meta=_PARTNER_META, relate_error=True)
    res = await service.create_record(
        PARTNER, fake, FakeApi(),
        {"company": "Acme", "firstName": "Dana", "emailAddress": "d@acme.com"},
        user_id="u1",
    )
    assert res["id"] and res["contactLinked"] is False


@pytest.mark.asyncio
async def test_funder_create_uses_the_sponsor_entity_and_links():
    fake, api = Fake(), FakeApi()
    res = await service.create_record(
        SPONSOR, fake, api,
        {"company": "Key Bank", "firstName": "Jo", "lastName": "Lee",
         "emailAddress": "jo@key.com", "description": "Warm intro from the board."},
        user_id="u1",
    )
    assert _payload(api, "Account")["cCompanyType"] == ["Sponsor"]
    assert _payload(fake, "Contact")["cContactType"] == ["Sponsor"]
    profile = _payload(fake, "CSponsorProfile")
    assert profile["sponsorCompanyId"] == "account-1"
    assert profile["sponsorContactId"] == "contact-1"
    assert profile["description"] == "Warm intro from the board."
    assert fake.related == [("CSponsorProfile", res["id"], "sponsorContacts", "contact-1")]


# --- the endpoints ----------------------------------------------------------

def _app(monkeypatch, quick_add: bool):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("RECORD_QUICK_ADD", "true" if quick_add else "false")
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


def _as(monkeypatch, fake=None):
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: _USER)
    client = fake or Fake(meta=_PARTNER_META)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, user: client)
    monkeypatch.setattr("sessions.router._api_client", lambda settings: FakeApi(), raising=False)
    return client


def test_session_config_advertises_the_button(monkeypatch):
    _as(monkeypatch)
    with TestClient(_app(monkeypatch, quick_add=True)) as c:
        partner = c.get("/partnersessions/api/session").json()
        funder = c.get("/sponsorsessions/api/session").json()
        mentor = c.get("/mentorsessions/api/session").json()
    assert partner["createRecord"]["label"] == "+ Add partner"
    assert funder["createRecord"]["label"] == "+ Add funder"
    assert mentor["createRecord"] is None


def test_button_is_absent_when_the_flag_is_off(monkeypatch):
    _as(monkeypatch)
    with TestClient(_app(monkeypatch, quick_add=False)) as c:
        assert c.get("/partnersessions/api/session").json()["createRecord"] is None


def test_endpoints_503_when_the_flag_is_off(monkeypatch):
    _as(monkeypatch)
    with TestClient(_app(monkeypatch, quick_add=False)) as c:
        r = c.post("/partnersessions/api/records", json={"changes": {"company": "X"}})
        assert r.status_code == 503
        assert c.get("/partnersessions/api/createfields").status_code == 503


def test_the_mentor_router_never_registers_the_routes(monkeypatch):
    """Gated at registration by the domain's create spec (the contributions
    precedent), so the route doesn't exist at all — not merely refuse."""
    _as(monkeypatch)
    with TestClient(_app(monkeypatch, quick_add=True)) as c:
        assert c.post("/mentorsessions/api/records", json={"changes": {}}).status_code == 405
        assert c.get("/mentorsessions/api/createfields").status_code == 404


def test_createfields_endpoint_returns_spec_options_and_managers(monkeypatch):
    _as(monkeypatch)
    with TestClient(_app(monkeypatch, quick_add=True)) as c:
        body = c.get("/partnersessions/api/createfields").json()
    assert body["title"] == "Add a partner"
    assert body["defaultManagerId"] == "MP1"
    assert body["options"]["partnershipStatus"] == ["Candidate", "Active", "Dormant"]


def test_create_endpoint_returns_the_new_record(monkeypatch):
    fake = _as(monkeypatch)
    with TestClient(_app(monkeypatch, quick_add=True)) as c:
        r = c.post("/partnersessions/api/records", json={"changes": {
            "company": "Acme Supply Co.", "firstName": "Dana", "lastName": "Reyes",
        }})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Acme Supply Co." and body["id"]
    assert _has(fake, "CPartnerProfile")


def test_create_endpoint_reports_a_bad_request_readably(monkeypatch):
    _as(monkeypatch)
    with TestClient(_app(monkeypatch, quick_add=True)) as c:
        r = c.post("/partnersessions/api/records", json={"changes": {"name": "Acme"}})
    assert r.status_code == 400
    assert "company name" in r.json()["detail"]
