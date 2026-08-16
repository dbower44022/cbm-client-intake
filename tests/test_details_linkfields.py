"""Curated link-field pickers in the Details tab + the always-shown Overview
fact (Doug's 2026-07-22 report: the Referring partner rail item vanished on
unlinked engagements, and the app had no way to SET the link — the values on
record had been set in the EspoCRM UI)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from forms import info_request
from sessions import details, service
from sessions.config import MENTOR, PARTNER, SPONSOR

# --- _field_spec: the curated link picker ----------------------------------

_ENG_META = {
    "name": {"type": "varchar"},
    "engagementStatus": {"type": "enum", "options": ["Active", "Submitted"]},
    "referringPartner": {"type": "link"},
}


def test_field_spec_appends_link_picker_when_crm_has_the_link():
    spec = details._field_spec(_ENG_META, "CEngagement")
    link = [f for f in spec if f["type"] == "linkselect"]
    assert link == [{
        "name": "referringPartnerId", "label": "Referring partner",
        "type": "linkselect", "editable": True,
        "linkEntity": "CPartnerProfile", "nameAttr": "referringPartnerName",
    }]


_PARTNER_META = {
    "name": {"type": "varchar"},
    "partnershipStatus": {"type": "enum", "options": ["Active", "Prospect"]},
    "partnerManager": {"type": "link"},
}


def test_field_spec_appends_partner_manager_picker():
    """Doug's 2026-08-13 report: the partner's manager showed in the grid but
    could not be changed anywhere in the app."""
    spec = details._field_spec(_PARTNER_META, "CPartnerProfile")
    link = [f for f in spec if f["type"] == "linkselect"]
    assert link == [{
        "name": "partnerManagerId", "label": "Partner manager",
        "type": "linkselect", "editable": True,
        "linkEntity": "CMentorProfile", "nameAttr": "partnerManagerName",
    }]
    sel = details._select_for(spec, _PARTNER_META).split(",")
    assert "partnerManagerId" in sel and "partnerManagerName" in sel


def test_partner_manager_write_path():
    spec = {f["name"]: f for f in details._field_spec(_PARTNER_META, "CPartnerProfile")}
    assert details._clean_changes(spec, {"partnerManagerId": "M9"}) == {"partnerManagerId": "M9"}
    assert details._clean_changes(spec, {"partnerManagerId": ""}) == {"partnerManagerId": None}


_SPONSOR_META = {
    "name": {"type": "varchar"},
    "lastContacted": {"type": "date"},
    "cBMSponsorManager": {"type": "link"},
}


def test_field_spec_appends_funder_manager_picker():
    """The funder half of the same gap. The CRM field is ``cBMSponsorManager``;
    the label follows the domain's display wording ("Funder"), not the entity."""
    spec = details._field_spec(_SPONSOR_META, "CSponsorProfile")
    link = [f for f in spec if f["type"] == "linkselect"]
    assert link == [{
        "name": "cBMSponsorManagerId", "label": "Funder manager",
        "type": "linkselect", "editable": True,
        "linkEntity": "CMentorProfile", "nameAttr": "cBMSponsorManagerName",
    }]
    sel = details._select_for(spec, _SPONSOR_META).split(",")
    assert "cBMSponsorManagerId" in sel and "cBMSponsorManagerName" in sel


def test_funder_manager_write_path():
    spec = {f["name"]: f for f in details._field_spec(_SPONSOR_META, "CSponsorProfile")}
    assert details._clean_changes(spec, {"cBMSponsorManagerId": "M9"}) == {"cBMSponsorManagerId": "M9"}
    assert details._clean_changes(spec, {"cBMSponsorManagerId": ""}) == {"cBMSponsorManagerId": None}


# --- the Company picker (Doug 2026-08-16) ------------------------------------
# A partner/funder whose company link is empty had no repair path in the app at
# all: nothing set it, and the Details tab omits the Company card without an id.

_PARTNER_FULL_META = dict(_PARTNER_META, partnerCompany={"type": "link"})
_SPONSOR_FULL_META = dict(_SPONSOR_META, sponsorCompany={"type": "link"})


def test_field_spec_appends_partner_company_picker_and_marks_it_creatable():
    spec = details._field_spec(_PARTNER_FULL_META, "CPartnerProfile")
    link = [f for f in spec if f["type"] == "linkselect"]
    assert link[0] == {
        "name": "partnerCompanyId", "label": "Company",
        "type": "linkselect", "editable": True,
        "linkEntity": "Account", "nameAttr": "partnerCompanyName",
        # picking is not enough — a company the CRM has never held is created here
        "creatable": True,
    }
    # the manager picker still rides alongside it, and is NOT creatable
    assert link[1]["name"] == "partnerManagerId" and "creatable" not in link[1]
    sel = details._select_for(spec, _PARTNER_FULL_META).split(",")
    assert "partnerCompanyId" in sel and "partnerCompanyName" in sel


def test_field_spec_appends_funder_company_picker():
    spec = details._field_spec(_SPONSOR_FULL_META, "CSponsorProfile")
    link = [f for f in spec if f["type"] == "linkselect"]
    assert link[0] == {
        "name": "sponsorCompanyId", "label": "Company",
        "type": "linkselect", "editable": True,
        "linkEntity": "Account", "nameAttr": "sponsorCompanyName",
        "creatable": True,
    }
    assert link[1]["name"] == "cBMSponsorManagerId"


def test_company_write_path():
    for meta, entity, attr in (
        (_PARTNER_FULL_META, "CPartnerProfile", "partnerCompanyId"),
        (_SPONSOR_FULL_META, "CSponsorProfile", "sponsorCompanyId"),
    ):
        spec = {f["name"]: f for f in details._field_spec(meta, entity)}
        assert details._clean_changes(spec, {attr: "A9"}) == {attr: "A9"}
        assert details._clean_changes(spec, {attr: ""}) == {attr: None}


def test_field_spec_omits_link_picker_when_crm_lacks_the_link():
    meta = {k: v for k, v in _ENG_META.items() if k != "referringPartner"}
    spec = details._field_spec(meta, "CEngagement")
    assert not any(f["type"] == "linkselect" for f in spec)
    # and no other entity gets it at all
    assert not any(f["type"] == "linkselect" for f in details._field_spec(_ENG_META, "Account"))


def test_select_includes_link_id_and_name():
    spec = details._field_spec(_ENG_META, "CEngagement")
    sel = details._select_for(spec, _ENG_META)
    assert "referringPartnerId" in sel.split(",")
    assert "referringPartnerName" in sel.split(",")


def test_section_carries_value_name_for_link_fields():
    spec = details._field_spec(_ENG_META, "CEngagement")
    rec = {"id": "E1", "name": "Eng", "engagementStatus": "Active",
           "referringPartnerId": "P1", "referringPartnerName": "Glide"}
    sec = details._section("Engagement", "CEngagement", rec, spec, True)
    f = next(x for x in sec["fields"] if x["name"] == "referringPartnerId")
    assert f["value"] == "P1" and f["valueName"] == "Glide"
    assert sec["values"]["referringPartnerName"] == "Glide"


# --- _clean_changes: the write path -----------------------------------------

def test_clean_changes_passes_link_id_and_clears_on_empty():
    spec = {f["name"]: f for f in details._field_spec(_ENG_META, "CEngagement")}
    assert details._clean_changes(spec, {"referringPartnerId": "P9"}) == {"referringPartnerId": "P9"}
    # the select's blank option ("") clears the link as an explicit null
    assert details._clean_changes(spec, {"referringPartnerId": ""}) == {"referringPartnerId": None}
    # anything not in the spec still drops (whitelist unchanged)
    assert details._clean_changes(spec, {"mentorProfileId": "HIJACK"}) == {}


# --- build_details: the option list -----------------------------------------

class _Fake:
    def __init__(self, *, partners=None, forbid_partner_list=False):
        self._partners = partners or []
        self._forbid = forbid_partner_list
        self.meta = {"CEngagement": _ENG_META, "Contact": {"firstName": {"type": "varchar"}},
                     "Account": {"name": {"type": "varchar"}},
                     "CClientProfile": {"industrySector": {"type": "enum", "options": []}}}

    async def metadata(self, key):
        entity = key.split(".")[1]
        return self.meta.get(entity, {})

    async def get(self, entity, record_id, select=None):
        return {"id": record_id, "name": "Rec " + record_id}

    async def list(self, entity, **kw):
        if entity == "CPartnerProfile":
            if self._forbid:
                raise EspoError("list CPartnerProfile failed: HTTP 403 forbidden")
            return {"list": self._partners}
        return {"list": []}

    async def list_related(self, entity, record_id, link, **kw):
        return {"list": []}

    async def app_user(self):
        return {"acl": {"table": {}}}


@pytest.mark.asyncio
async def test_build_details_attaches_link_options():
    fake = _Fake(partners=[{"id": "P1", "name": "Glide"}, {"id": "P2", "name": "COSE"}])
    res = await details.build_details(MENTOR, fake, "E1", user_id="u1")
    assert res["linkOptions"]["CPartnerProfile"] == [
        {"id": "P1", "name": "Glide"}, {"id": "P2", "name": "COSE"},
    ]


@pytest.mark.asyncio
async def test_build_details_link_options_best_effort_on_403():
    fake = _Fake(forbid_partner_list=True)
    res = await details.build_details(MENTOR, fake, "E1", user_id="u1")
    assert "linkOptions" not in res  # picker degrades read-only; tab still loads


# --- create_company: the picker's "+ New company" ----------------------------
# Three of the four company-less records on prod (2026-08-16) had no Account to
# pick, so the picker has to be able to make one — on the intake orchestrators'
# find-or-create terms, never a blind create.


class _CoFake:
    """Client for the create-company path: find_one + the type-merge update."""

    def __init__(self, existing=None):
        self._existing = existing
        self.updates = []

    async def find_one(self, entity, attribute, value, select="id"):
        return self._existing

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        return {"id": record_id}


class _CoApi:
    """The intake API client — holds Account create where gate roles don't."""

    def __init__(self):
        self.created = []

    async def create(self, entity, payload):
        self.created.append((entity, payload))
        return {"id": "acct-new"}


@pytest.mark.asyncio
async def test_create_company_creates_typed_account_via_api_client():
    client, api = _CoFake(), _CoApi()
    res = await details.create_company(PARTNER, client, api, " Buckeye Community Bank ", "buckeye.com")
    assert res == {"id": "acct-new", "name": "Buckeye Community Bank", "created": True}
    entity, payload = api.created[0]
    assert entity == "Account"
    assert payload["name"] == "Buckeye Community Bank"
    # the discriminator the whole CRM filters on, and a usable url field
    assert payload["cCompanyType"] == ["Partner"]
    assert payload["website"] == "https://buckeye.com"


@pytest.mark.asyncio
async def test_create_company_reuses_a_same_named_account_and_merges_the_type():
    client = _CoFake(existing={"id": "A1", "name": "Key Bank", "cCompanyType": ["Client"]})
    api = _CoApi()
    res = await details.create_company(SPONSOR, client, api, "Key Bank")
    assert res == {"id": "A1", "name": "Key Bank", "created": False}
    assert not api.created  # never duplicates a company CBM already knows
    # merge-only: the existing type survives, the domain's is added
    assert client.updates == [("Account", "A1", {"cCompanyType": ["Client", "Sponsor"]})]


@pytest.mark.asyncio
async def test_create_company_requires_a_name():
    with pytest.raises(service.SessionError):
        await details.create_company(PARTNER, _CoFake(), _CoApi(), "   ")


# --- the create-company route ------------------------------------------------

_ROUTE_USER = {
    "userId": "u1", "userName": "pat.partner", "name": "Pat Partner", "isAdmin": False,
    "teams": ["Partner Management Team", "Sponsor Management Team", "Mentor Team"],
    "roles": [], "token": "t",
}


def _route_app(monkeypatch, client):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    # Deliberately OFF: this is a repair path for records that already exist, so
    # it must not ride on the quick-add flag the way the Add button does.
    monkeypatch.setenv("RECORD_QUICK_ADD", "false")
    get_settings.cache_clear()
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: _ROUTE_USER)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, user: client)
    monkeypatch.setattr("sessions.router._api_client", lambda settings: _CoApi(), raising=False)
    return create_app([info_request.SPEC])


@pytest.mark.parametrize("slug", ["partnersessions", "sponsorsessions"])
def test_create_company_route_creates_and_returns_the_company(monkeypatch, slug):
    with TestClient(_route_app(monkeypatch, _CoFake())) as c:
        r = c.post(f"/{slug}/api/records/P1/company", json={"name": "The Villages- Sheffield"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "The Villages- Sheffield" and body["created"] is True
    assert body["id"]  # the picker selects this id; the panel's Save links it


def test_create_company_route_rejects_a_blank_name(monkeypatch):
    with TestClient(_route_app(monkeypatch, _CoFake())) as c:
        r = c.post("/partnersessions/api/records/P1/company", json={"name": "  "})
    assert r.status_code == 400


def test_the_mentor_router_never_registers_the_company_route(monkeypatch):
    """Gated at registration by ``company_link_editable`` — an engagement's
    company is resolved through the client profile, so the route doesn't exist
    there at all (the contributions / primary-contact precedent). Unregistered
    POSTs surface as 405, not 404: the path falls through to the domain's static
    frontend mount, which serves GET (the quick-add precedent)."""
    with TestClient(_route_app(monkeypatch, _CoFake())) as c:
        r = c.post("/mentorsessions/api/records/E1/company", json={"name": "X"})
    assert r.status_code == 405


# --- Overview: the always-shown fact ----------------------------------------

def test_overview_referring_partner_always_renders():
    # Linked: value + partner pop-up link.
    parent = {"engagementStatus": "Active", "referringPartnerName": "Glide",
              "referringPartnerId": "P1"}
    items = {i["label"]: i for i in service._overview_items(MENTOR, parent)}
    rp = items["Referring partner"]
    assert rp["value"] == "Glide"
    assert rp["link"] == {"entity": "CPartnerProfile", "id": "P1"}
    # Unlinked: the slot still renders (value None -> "—"), with no link.
    bare = {i["label"]: i for i in service._overview_items(MENTOR, {"engagementStatus": "Active"})}
    rp2 = bare["Referring partner"]
    assert rp2["value"] is None and "link" not in rp2
    # Other empty facts still drop (the always flag is per-item).
    assert "Meeting cadence" not in bare


# --- Overview: a missing company reads as a gap, not a value -----------------

def test_overview_company_renders_a_dash_when_nothing_is_linked():
    """Doug's 2026-08-13 report opened with "the Company value is '(details)'".
    It was a link to the record itself dressed up as a value; an unlinked
    company must read as the empty fact it is."""
    from sessions.config import PARTNER as _P
    items = {i["label"]: i for i in service._overview_items(
        _P, {"id": "P1", "partnershipStatus": "Candidate"})}
    company = items["Company"]           # the slot stays (always=True)
    assert company["value"] is None      # renders "—"
    assert "link" not in company         # no pop-up of the record you're on


def test_overview_company_still_links_when_a_company_is_linked():
    from sessions.config import PARTNER as _P
    items = {i["label"]: i for i in service._overview_items(_P, {
        "id": "P1", "partnerCompanyId": "A1", "partnerCompanyName": "Global Cleveland",
    })}
    company = items["Company"]
    assert company["value"] == "Global Cleveland"
    assert company["link"]["aggregate"] == [
        {"entity": "Account", "id": "A1"}, {"entity": "CPartnerProfile", "id": "P1"},
    ]


# --- Details strip: an unset picker must still advertise itself --------------
# The Details summary strip omits empty fields on purpose (density), but a link
# picker is the ONLY signpost to the control behind Edit — so an unset one used
# to vanish, and the partner with no company (exactly the record the picker was
# built to repair) showed nothing about Company anywhere in view mode. Doug's
# report, 2026-08-16: "the ability to select or create a company that is related
# to the partner seems to be missing." Browser code, so the guard is on source.

_APP_JS = (
    __import__("pathlib").Path(__file__).resolve().parent.parent
    / "sessions" / "frontend" / "app.js"
).read_text()


def test_strip_renders_a_dash_for_an_unset_link_picker():
    assert 'add(STRIP_LABELS[f.name] || f.label, f.valueName ? String(f.valueName) : "—");' in _APP_JS
    # The old guard dropped the cell entirely — it must not come back.
    assert "if (f.valueName) add(STRIP_LABELS[f.name] || f.label, String(f.valueName));" not in _APP_JS


def test_company_leads_the_partner_and_funder_strip():
    """It identifies the organisation, so it sorts ahead of the dates — the same
    reason it leads the edit form."""
    order = _APP_JS.split("var STRIP_ORDER = [", 1)[1].split("];", 1)[0]
    for name in ("partnerCompanyId", "sponsorCompanyId"):
        assert name in order, name
    assert order.index("partnerCompanyId") < order.index("partnershipStatus")
