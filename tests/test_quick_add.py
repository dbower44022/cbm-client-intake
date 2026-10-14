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

    # The contact is owner-stamped like the profile (Doug's ruling 2026-10-09:
    # a role at Assignment Permission not-set refuses an unowned create, and a
    # team-read role could never see one it had made). Both spellings, the
    # new-session precedent. No team resolved in this fake, so no teamsIds.
    assert contact["assignedUserId"] == "u1"
    assert contact["assignedUsersIds"] == ["u1"]
    assert "teamsIds" not in contact

    profile = _payload(fake, "CPartnerProfile")
    assert profile["name"] == "Acme Supply Co."
    assert profile["partnerCompanyId"] == "account-1"
    assert profile["primaryPartnercontactId"] == "contact-1"
    assert profile["partnerManagerId"] == "MP1"
    assert profile["partnershipStatus"] == "Candidate"
    assert profile["assignedUsersIds"] == ["u1"]      # owner-stamped
    assert profile["assignedUserId"] == "u1"          # … in both spellings (v0.249.3)

    # The contact joins the profile's Contacts hasMany, as intake does.
    assert fake.related == [("CPartnerProfile", res["id"], "contacts", "contact-1")]
    assert res["accountCreated"] is True and res["contactCreated"] is True


@pytest.mark.asyncio
async def test_existing_company_is_reused_and_gains_the_type():
    """A company CBM already knows as a Client becoming a Partner must gain the
    type — cCompanyType is the discriminator the whole CRM filters on — but
    never lose what it already is."""
    fake = Fake(meta=_PARTNER_META)
    api = FakeApi(
        found={("Account", "name", "Acme Supply Co."):
               {"id": "A-OLD", "name": "Acme Supply Co.", "cCompanyType": ["Client"]}},
    )
    res = await service.create_record(
        PARTNER, fake, api, {"company": "Acme Supply Co.", "name": "Acme"}, user_id="u1",
    )
    assert not api.created                       # nothing new created
    assert fake.updates == []                    # the user client writes nothing here
    assert _payload(fake, "CPartnerProfile")["partnerCompanyId"] == "A-OLD"
    assert res["accountCreated"] is False
    # Both writes ride the API client: the type merge, then the owner stamp
    # (v0.249.1 — a team-read role must be able to read the company the new
    # contact links to).
    assert api.updates == [
        ("Account", "A-OLD", {"cCompanyType": ["Client", "Partner"]}),
        ("Account", "A-OLD", {"assignedUsersIds": ["u1"]}),
    ]


@pytest.mark.asyncio
async def test_same_name_different_website_is_refused_not_merged():
    """Two businesses can share a name. A same-named company whose stored
    website is a different address is a different company — the save is
    refused with the existing company named, and nothing is written (Doug's
    ruling 2026-10-07: refuse and explain, never a second same-named Account)."""
    fake = Fake(meta=_PARTNER_META)
    api = FakeApi(
        found={("Account", "name", "Acme Supply Co."):
               {"id": "A-OLD", "name": "Acme Supply Co.", "cCompanyType": ["Client"],
                "website": "https://acme-ohio.com"}},
    )
    with pytest.raises(service.SessionError) as excinfo:
        await service.create_record(
            PARTNER, fake, api,
            {"company": "Acme Supply Co.", "website": "acme.com", "name": "Acme"},
            user_id="u1",
        )
    msg = str(excinfo.value)
    assert "Acme Supply Co." in msg and "https://acme-ohio.com" in msg
    assert not api.created and not fake.created and not fake.updates and not api.updates


@pytest.mark.asyncio
async def test_same_name_same_website_in_another_form_still_matches():
    """acme.com, https://www.acme.com/ and HTTP://Acme.com are one site."""
    fake = Fake(meta=_PARTNER_META)
    api = FakeApi(
        found={("Account", "name", "Acme Supply Co."):
               {"id": "A-OLD", "name": "Acme Supply Co.", "cCompanyType": ["Partner"],
                "website": "https://www.acme.com/", "assignedUsersIds": ["u1"]}},
    )
    res = await service.create_record(
        PARTNER, fake, api,
        {"company": "Acme Supply Co.", "website": "HTTP://Acme.com", "name": "Acme"},
        user_id="u1",
    )
    assert res["accountCreated"] is False and not api.created
    # type present, website present, already owned: nothing to write
    assert fake.updates == [] and api.updates == []


@pytest.mark.asyncio
async def test_same_name_no_stored_website_matches_and_fills_it():
    fake = Fake(meta=_PARTNER_META)
    api = FakeApi(
        found={("Account", "name", "Acme Supply Co."):
               {"id": "A-OLD", "name": "Acme Supply Co.", "cCompanyType": ["Partner"],
                "assignedUsersIds": ["u1"]}},
    )
    res = await service.create_record(
        PARTNER, fake, api,
        {"company": "Acme Supply Co.", "website": "acme.com", "name": "Acme"},
        user_id="u1",
    )
    assert res["accountCreated"] is False
    assert api.updates == [("Account", "A-OLD", {"website": "https://acme.com"})]
    assert fake.updates == []


@pytest.mark.asyncio
async def test_no_website_entered_matches_by_name_as_before():
    fake = Fake(meta=_PARTNER_META)
    api = FakeApi(
        found={("Account", "name", "Acme Supply Co."):
               {"id": "A-OLD", "name": "Acme Supply Co.", "cCompanyType": ["Partner"],
                "website": "https://acme-ohio.com", "assignedUsersIds": ["u1"]}},
    )
    res = await service.create_record(
        PARTNER, fake, api, {"company": "Acme Supply Co.", "name": "Acme"}, user_id="u1",
    )
    assert res["accountCreated"] is False and fake.updates == [] and api.updates == []


@pytest.mark.asyncio
async def test_company_match_runs_under_the_api_key_so_a_team_read_user_never_duplicates():
    """The match used to run as the user. A role reading Account at *team*
    cannot see an unowned company the previous attempt created, so every
    retry made another same-named Account (three on crm-test, 2026-10-09).
    Now the API client finds it, and the reused company gains the creator and
    the domain team so the user can read it and link the contact to it."""
    settings = get_settings()
    team_name = settings.sponsor_team_name
    fake = Fake(meta=_PARTNER_META)          # the USER sees nothing by name
    api = FakeApi(found={
        ("Account", "name", "Acme Bank and Loan"):
            {"id": "A-UNOWNED", "name": "Acme Bank and Loan", "cCompanyType": ["Sponsor"],
             "teamsIds": [], "assignedUsersIds": []},
        ("Team", "name", team_name): {"id": "T-S"},
    })
    res = await service.create_record(
        SPONSOR, fake, api,
        {"company": "Acme Bank and Loan", "firstName": "Wendy", "lastName": "Kay"},
        user_id="u1",
    )
    assert res["accountCreated"] is False and not api.created
    assert api.updates == [
        ("Account", "A-UNOWNED", {"assignedUsersIds": ["u1"], "teamsIds": ["T-S"]}),
    ]
    contact = _payload(fake, "Contact")
    assert contact["accountId"] == "A-UNOWNED"
    assert contact["teamsIds"] == ["T-S"] and contact["assignedUsersIds"] == ["u1"]
    assert _payload(fake, "CSponsorProfile")["teamsIds"] == ["T-S"]


@pytest.mark.asyncio
async def test_existing_contact_is_null_filled_never_overwritten():
    fake = Fake(meta=_PARTNER_META)
    api = FakeApi(
        found={("Contact", "emailAddress", "dana@acme.com"):
               {"id": "C-OLD", "firstName": "Dana", "lastName": "", "title": "VP"}},
    )
    await service.create_record(
        PARTNER, fake, api,
        {"company": "Acme", "firstName": "D.", "lastName": "Reyes",
         "emailAddress": "dana@acme.com", "title": "Director"},
        user_id="u1",
    )
    assert not _has(fake, "Contact")
    # lastName was empty -> filled; firstName and title were set -> untouched.
    # The null-fill runs AS THE USER; the owner stamp rides the API client.
    assert fake.updates == [("Contact", "C-OLD", {"lastName": "Reyes"})]
    assert api.updates == [("Contact", "C-OLD", {"assignedUsersIds": ["u1"]})]
    assert _payload(fake, "CPartnerProfile")["primaryPartnercontactId"] == "C-OLD"


@pytest.mark.asyncio
async def test_new_contact_carries_the_domain_team_on_both_doors():
    """Partner and funder run the same code, so the stamp is the same on
    both (Doug, 2026-10-09: "they should not be different"). When the domain
    team resolves, the contact joins it exactly as the profile does — and a
    contact created WITHOUT an email (the create-outright branch) is stamped
    the same way."""
    settings = get_settings()
    for cfg, attr, entity in (
        (PARTNER, "partner_team_name", "CPartnerProfile"),
        (SPONSOR, "sponsor_team_name", "CSponsorProfile"),
    ):
        team_name = getattr(settings, attr)
        fake = Fake(meta=_PARTNER_META)
        api = FakeApi(found={("Team", "name", team_name): {"id": "T-1"}})
        await service.create_record(
            cfg, fake, api,
            {"company": "Acme", "firstName": "Dana", "lastName": "Reyes"},  # no email
            user_id="u1",
        )
        contact = _payload(fake, "Contact")
        assert contact["teamsIds"] == ["T-1"], cfg.slug
        assert contact["assignedUsersIds"] == ["u1"], cfg.slug
        assert contact["assignedUserId"] == "u1", cfg.slug
        assert _payload(fake, entity)["teamsIds"] == ["T-1"], cfg.slug
        # the company is owned the same way, under the API client
        account = _payload(api, "Account")
        assert account["teamsIds"] == ["T-1"] and account["assignedUsersIds"] == ["u1"], cfg.slug


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


# --- the Company picker (v0.254.0) ------------------------------------------
# Doug's request 2026-10-12: "a way to select a company instead of hoping to
# match the company name / website". A chosen company's id rides as
# ``companyId`` beside (or instead of) the typed name; the typed name stays
# the "+ New company" path and keeps the name-and-website rule.

class PickerApi(FakeApi):
    """The org-wide API client with a company directory: ``get`` for the
    chosen company and a paged ``list`` for the picker's options."""

    def __init__(self, companies=None, **kw):
        super().__init__(**kw)
        self.companies = companies if companies is not None else {
            "A1": {"id": "A1", "name": "Key Bank", "website": "https://keybank.com",
                   "cCompanyType": ["Partner"], "teamsIds": [], "assignedUsersIds": []},
            "A2": {"id": "A2", "name": "Key Bank", "website": None,
                   "cCompanyType": [], "teamsIds": [], "assignedUsersIds": []},
        }
        self.gets = []

    async def get(self, entity, record_id, select=None):
        self.gets.append((entity, record_id))
        rec = self.companies.get(record_id)
        if rec is None:
            raise EspoError("HTTP 404: Not Found")
        return dict(rec)

    async def list(self, entity, **kw):
        if entity == "Account":
            rows = sorted(self.companies.values(), key=lambda a: a["name"])
            off = kw.get("offset", 0); size = kw.get("max_size", 200)
            return {"list": [dict(r) for r in rows[off:off + size]], "total": len(rows)}
        return await super().list(entity, **kw)


@pytest.mark.asyncio
async def test_chosen_company_is_used_without_a_name_match_or_website_check():
    """The picker's id wins: no find_one, no website refusal even though the
    typed website differs from the stored one, the domain type merged in,
    the website left alone (null-fill only), and the record named after the
    company when no name was typed."""
    api = PickerApi()
    client = Fake(meta=_PARTNER_META)
    res = await service.create_record(
        PARTNER, client, api,
        {"companyId": "A1", "website": "https://other-site.example", "partnershipStatus": "Active"},
        user_id="u1",
    )
    assert api.gets[0] == ("Account", "A1")
    assert res["accountId"] == "A1" and res["accountCreated"] is False
    assert res["name"] == "Key Bank"
    assert not _has(api, "Account")                      # nothing created
    # The stored website is kept (null-fill only) and no type merge was
    # needed — Partner is already on it. (The owner stamps still merge.)
    touched = {}
    for e, i, p in api.updates:
        if e == "Account":
            touched.update(p)
    assert "website" not in touched and "cCompanyType" not in touched
    assert _payload(client, "CPartnerProfile")["partnerCompanyId"] == "A1"


@pytest.mark.asyncio
async def test_chosen_company_gains_the_type_and_the_website_by_null_fill():
    api = PickerApi()
    client = Fake(meta=_PARTNER_META)
    await service.create_record(
        SPONSOR, client, api, {"companyId": "A2", "website": "example.org", "name": "KB grant"},
        user_id="u1",
    )
    account_updates = [p for e, i, p in api.updates if e == "Account" and i == "A2"]
    merged = {}
    for p in account_updates:
        merged.update(p)
    assert merged.get("website") == "https://example.org"
    assert merged.get("cCompanyType") == ["Sponsor"]
    assert _payload(client, "CSponsorProfile")["sponsorCompanyId"] == "A2"


@pytest.mark.asyncio
async def test_chosen_company_that_is_gone_is_a_readable_refusal_not_a_create():
    api = PickerApi()
    client = Fake(meta=_PARTNER_META)
    with pytest.raises(service.SessionError) as exc:
        await service.create_record(PARTNER, client, api, {"companyId": "NOPE", "company": "Typed Name"},
                                    user_id="u1")
    assert "no longer in the CRM" in str(exc.value)
    assert not _has(api, "Account") and not _has(client, "CPartnerProfile")


@pytest.mark.asyncio
async def test_typed_name_without_a_choice_still_takes_the_match_path():
    api = PickerApi()
    client = Fake(meta=_PARTNER_META)
    res = await service.create_record(PARTNER, client, api, {"company": "Brand New Co"}, user_id="u1")
    assert res["accountCreated"] is True and api.gets == []
    assert _payload(api, "Account")["name"] == "Brand New Co"


@pytest.mark.asyncio
async def test_nothing_chosen_and_nothing_typed_is_refused():
    with pytest.raises(service.SessionError) as exc:
        await service.create_record(PARTNER, Fake(meta=_PARTNER_META), PickerApi(), {"website": "x.org"},
                                    user_id="u1")
    assert "pick a company" in str(exc.value)


@pytest.mark.asyncio
async def test_company_options_page_at_200_and_carry_the_website():
    companies = {f"A{i:04d}": {"id": f"A{i:04d}", "name": f"Co {i:04d}", "website": "https://w.example" if i % 2 else None}
                 for i in range(450)}
    api = PickerApi(companies=companies)
    opts = await service.quick_add_company_options(api)
    assert len(opts) == 450
    assert opts[0] == {"id": "A0000", "name": "Co 0000", "website": ""}
    assert opts[1]["website"] == "https://w.example"


def test_createcompanies_endpoint_reads_under_the_api_client(monkeypatch):
    _as(monkeypatch)
    # The router builds the org-wide client itself (dry-run in tests), so the
    # directory rides in through the dry-run client's constructor.
    monkeypatch.setattr("core.espo.DryRunEspoClient", lambda: PickerApi())
    with TestClient(_app(monkeypatch, quick_add=True)) as c:
        r = c.get("/partnersessions/api/createcompanies")
        assert r.status_code == 200
        names = [a["name"] for a in r.json()["companies"]]
        assert names == ["Key Bank", "Key Bank"]
    with TestClient(_app(monkeypatch, quick_add=False)) as c:
        assert c.get("/partnersessions/api/createcompanies").status_code == 503


def test_create_endpoint_accepts_a_chosen_company(monkeypatch):
    _as(monkeypatch)
    monkeypatch.setattr("core.espo.DryRunEspoClient", lambda: PickerApi())
    with TestClient(_app(monkeypatch, quick_add=True)) as c:
        r = c.post("/partnersessions/api/records", json={"changes": {"companyId": "A1"}})
        assert r.status_code == 200, r.text
        assert r.json()["accountId"] == "A1" and r.json()["name"] == "Key Bank"


_APP_JS = (
    __import__("pathlib").Path(__file__).resolve().parent.parent / "sessions" / "frontend" / "app.js"
).read_text()


def test_quick_add_form_carries_the_company_picker():
    assert 'f.name === "company" && qadd.companies && qadd.companies.length' in _APP_JS
    assert '{ id: "__new__", label: "+ New company…", muted: true }' in _APP_JS
    assert "if (chosen) changes.companyId = chosen.id;" in _APP_JS
    assert 'await api("/createcompanies")' in _APP_JS


# --- the inherited primary contact (v0.257.0) ---------------------------------
# Doug's request 2026-10-14: a partner made from a funder's company, with no
# contact entered, takes the funder's primary contact — and the reverse.

class SiblingApi(PickerApi):
    """The org-wide client with the other door's records on the company and
    the contacts they name."""

    def __init__(self, profiles=None, contacts=None, **kw):
        super().__init__(**kw)
        self.profiles = profiles if profiles is not None else [
            {"id": "SP-old", "name": "Old grant", "sponsorCompanyId": "A1", "sponsorContactId": None},
            {"id": "SP-new", "name": "New grant", "sponsorCompanyId": "A1", "sponsorContactId": "C-fund"},
        ]
        self.contacts = contacts if contacts is not None else {
            "C-fund": {"id": "C-fund", "name": "Fran Funder", "teamsIds": ["T-sponsor"], "assignedUsersIds": []},
        }
        self.listed = []
        self.relates = []

    async def list(self, entity, **kw):
        self.listed.append((entity, kw.get("where")))
        if entity in ("CSponsorProfile", "CPartnerProfile"):
            fk = "sponsorCompanyId" if entity == "CSponsorProfile" else "partnerCompanyId"
            acc = kw["where"][0]["value"]
            rows = [p for p in self.profiles if p.get(fk) == acc]
            rows = list(reversed(rows))  # newest first, as the real order_by would
            return {"list": rows, "total": len(rows)}
        return await super().list(entity, **kw)

    async def get(self, entity, record_id, select=None):
        if entity == "Contact":
            rec = self.contacts.get(record_id)
            if rec is None:
                raise EspoError("HTTP 404: Not Found")
            return dict(rec)
        return await super().get(entity, record_id, select)

    async def relate(self, entity, record_id, link, related_id):
        self.relates.append((entity, record_id, link, related_id))


@pytest.mark.asyncio
async def test_partner_from_a_funder_company_inherits_the_funder_primary_contact():
    api = SiblingApi()
    client = Fake(meta=_PARTNER_META)
    res = await service.create_record(PARTNER, client, api, {"companyId": "A1"}, user_id="u1")
    # The newest funder record WITH a contact wins (the older one had none).
    assert res["contactId"] == "C-fund" and res["contactInheritedFrom"] == "Funder"
    assert res["contactCreated"] is False and res["contactLinked"] is True
    assert not _has(client, "Contact") and not _has(api, "Contact")
    assert _payload(client, "CPartnerProfile")["primaryPartnercontactId"] == "C-fund"
    assert ("CPartnerProfile", "cpartnerprofile-1", "contacts", "C-fund") in client.related
    # The lookup went to the OTHER door, scoped to the company.
    assert ("CSponsorProfile", [{"type": "equals", "attribute": "sponsorCompanyId", "value": "A1"}]) in api.listed
    # The contact gained the creator and the partner team (merge-only).
    stamp = next(p for e, i, p in api.updates if e == "Contact" and i == "C-fund")
    assert "u1" in stamp.get("assignedUsersIds", [])


@pytest.mark.asyncio
async def test_funder_from_a_partner_company_inherits_the_partner_primary_contact():
    api = SiblingApi(profiles=[
        {"id": "PP1", "name": "Key Bank partnership", "partnerCompanyId": "A2", "primaryPartnercontactId": "C-part"},
    ], contacts={"C-part": {"id": "C-part", "name": "Pat", "teamsIds": [], "assignedUsersIds": []}})
    client = Fake(meta=_PARTNER_META)
    res = await service.create_record(SPONSOR, client, api, {"companyId": "A2"}, user_id="u1")
    assert res["contactId"] == "C-part" and res["contactInheritedFrom"] == "Partner"
    assert _payload(client, "CSponsorProfile")["sponsorContactId"] == "C-part"


@pytest.mark.asyncio
async def test_entered_contact_wins_over_the_inherited_one():
    api = SiblingApi()
    client = Fake(meta=_PARTNER_META)
    res = await service.create_record(
        PARTNER, client, api, {"companyId": "A1", "firstName": "Dana", "lastName": "Reyes"}, user_id="u1",
    )
    assert res["contactInheritedFrom"] is None and res["contactCreated"] is True
    assert all(e not in ("CSponsorProfile", "CPartnerProfile") for e, _ in api.listed)


@pytest.mark.asyncio
async def test_no_inheritance_without_a_chosen_company_or_a_sibling_contact():
    # Typed name (even one that matches): the form's own rule, no lookup.
    api = SiblingApi()
    res = await service.create_record(PARTNER, Fake(meta=_PARTNER_META), api, {"company": "Key Bank"}, user_id="u1")
    assert res["contactId"] is None and res["contactInheritedFrom"] is None
    # Chosen company whose other-door records name no contact: nothing.
    api = SiblingApi(profiles=[{"id": "SP1", "sponsorCompanyId": "A1", "sponsorContactId": None}])
    res = await service.create_record(PARTNER, Fake(meta=_PARTNER_META), api, {"companyId": "A1"}, user_id="u1")
    assert res["contactId"] is None and res["contactInheritedFrom"] is None


@pytest.mark.asyncio
async def test_inherited_contact_link_falls_back_to_the_org_key():
    """The user's relate may be refused on the contact side (it belongs to
    the other door's team); the org key links it instead."""
    api = SiblingApi()
    client = Fake(meta=_PARTNER_META, relate_error=True)
    res = await service.create_record(PARTNER, client, api, {"companyId": "A1"}, user_id="u1")
    assert res["contactLinked"] is True
    assert ("CPartnerProfile", "cpartnerprofile-1", "contacts", "C-fund") in api.relates


def test_quick_add_notice_names_the_inherited_contact():
    assert "Primary contact copied from the company's" in _APP_JS
