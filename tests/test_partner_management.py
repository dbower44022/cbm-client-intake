"""Partner & Funder Management improvements (Doug's 2026-07-24 review):

* the assigned manager on the Overview rail (it was on the grid only),
* persistent facts — a configured-but-empty slot renders "—" instead of
  vanishing (agreement date / last contacted were empty on nearly every real
  partner, which read as a missing feature),
* the company's industry as a rail fact (the profiles carry no industry),
* Sponsor → Funder wording in this app's own labels,
* the contacts table: domain title, no Role/Agreements columns, and a
  "Make primary" action for the record's primary contact.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from forms import info_request
from sessions import details, service
from sessions.config import MENTOR, PARTNER, SPONSOR

_USER = {"userId": "u1", "userName": "boss", "name": "The Boss", "isAdmin": True, "token": "tok"}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- Overview rail: the assigned manager ------------------------------------

def test_partner_overview_carries_the_partner_manager():
    parent = {"partnershipStatus": "Active", "partnerManagerName": "Milt Sierra",
              "partnerManagerId": "M9"}
    items = {i["label"]: i for i in service._overview_items(PARTNER, parent)}
    mgr = items["Partner Manager"]
    assert mgr["value"] == "Milt Sierra"
    # links to the same CMentorProfile pop-up the grid column opens
    assert mgr["link"] == {"entity": "CMentorProfile", "id": "M9"}


def test_funder_overview_carries_the_funder_manager():
    parent = {"cBMSponsorManagerName": "Brad Swimmer", "cBMSponsorManagerId": "M4"}
    items = {i["label"]: i for i in service._overview_items(SPONSOR, parent)}
    assert items["Funder Manager"]["link"] == {"entity": "CMentorProfile", "id": "M4"}


@pytest.mark.parametrize(
    "cfg, attrs",
    [(PARTNER, ("partnerManagerName", "partnerManagerId")),
     (SPONSOR, ("cBMSponsorManagerName", "cBMSponsorManagerId"))],
)
def test_manager_attrs_are_actually_selected(cfg, attrs):
    """The rail item is useless unless the detail read asks for its attributes —
    the shape of the original defect (the item simply wasn't configured, and the
    attrs weren't in the select either)."""
    selected = cfg.detail_select.split(",")
    for attr in attrs:
        assert attr in selected


# --- Overview rail: persistent facts ----------------------------------------

def test_empty_partner_facts_still_render():
    # A real crm-test partner: no agreement date, never contacted, no manager.
    items = {i["label"]: i for i in service._overview_items(PARTNER, {"name": "COSE"})}
    for label in ("Agreement date", "Last contacted", "Contact cadence",
                  "Partner Manager", "Primary contact", "Industry"):
        assert label in items, f"{label} vanished when empty"
        assert items[label]["value"] is None  # rendered as "—"
    assert "link" not in items["Partner Manager"]  # nothing to open


def test_empty_funder_facts_still_render():
    items = {i["label"]: i for i in service._overview_items(SPONSOR, {"name": "Key Bank"})}
    for label in ("Funder Manager", "Last contribution", "Last contacted", "Industry"):
        assert label in items and items[label]["value"] is None


# --- Overview rail: the company's industry ----------------------------------

class _IndustryClient:
    def __init__(self, account=None, forbid=False):
        self._account = account or {}
        self._forbid = forbid
        self.reads: list[str] = []

    async def get(self, entity, record_id, select=None):
        self.reads.append(f"{entity}/{record_id}")
        if self._forbid:
            raise EspoError("read Account failed: HTTP 403 forbidden")
        return dict(self._account, id=record_id)


@pytest.mark.asyncio
async def test_company_industry_composed_and_deduped():
    client = _IndustryClient({"industry": "Banking", "cIndustrySector": "Banking",
                              "cIndustrySubsector": "Commercial Banking"})
    parent = {"partnerCompanyId": "A1"}
    await service._fill_company_industry(PARTNER, client, parent)
    # the duplicate general industry/sector reads once
    assert parent["_companyIndustry"] == "Banking / Commercial Banking"
    assert client.reads == ["Account/A1"]


@pytest.mark.asyncio
async def test_company_industry_is_best_effort():
    # forbidden Account read -> no fact, no exception (the rail shows "—")
    parent = {"partnerCompanyId": "A1"}
    await service._fill_company_industry(PARTNER, _IndustryClient(forbid=True), parent)
    assert "_companyIndustry" not in parent

    # no company linked -> no read at all
    client = _IndustryClient({"industry": "Banking"})
    empty: dict = {}
    await service._fill_company_industry(PARTNER, client, empty)
    assert "_companyIndustry" not in empty and client.reads == []

    # the mentor domain doesn't opt in
    mentor_parent = {"clientOrganizationId": "A1"}
    await service._fill_company_industry(MENTOR, client, mentor_parent)
    assert "_companyIndustry" not in mentor_parent and client.reads == []


# --- Sponsor -> Funder wording ----------------------------------------------

def test_funder_wording_in_this_apps_labels():
    assert SPONSOR.title == "Funder Management"
    assert SPONSOR.parent_label == "Funder"
    assert SPONSOR.empty_message == "No funders found."
    assert SPONSOR.overall_notes_label == "Funder Notes"
    labels = [c.label for c in SPONSOR.list_columns]
    assert "Funder" in labels and "Funder Manager" in labels
    assert not any("Sponsor" in l for l in labels)
    assert SPONSOR.details_entities[0][0] == "Funding"


def test_backend_naming_deliberately_keeps_sponsor():
    """Doug's ruling: entity names, the route, and the CSession type value stay."""
    assert SPONSOR.slug == "sponsorsessions"
    assert SPONSOR.parent_entity == "CSponsorProfile"
    assert SPONSOR.default_session_type == "Sponsor Session"


# --- Details: the contacts card --------------------------------------------

def test_contacts_card_config_per_domain():
    assert (PARTNER.contacts_label, PARTNER.contacts_show_role,
            PARTNER.contacts_show_agreements) == ("Partner Contacts", False, False)
    assert (SPONSOR.contacts_label, SPONSOR.contacts_show_role,
            SPONSOR.contacts_show_agreements) == ("Funder Contacts", False, False)
    # the mentor domain keeps both columns — its contacts have real roles and
    # the consent bools are a client-intake concept
    assert (MENTOR.contacts_label, MENTOR.contacts_show_role,
            MENTOR.contacts_show_agreements) == ("Client Contacts", True, True)


def test_primary_settable_only_where_the_domain_owns_the_link():
    assert PARTNER.primary_contact_settable and SPONSOR.primary_contact_settable
    assert not MENTOR.primary_contact_settable  # engagement's comes from intake


def test_session_config_exposes_the_contacts_card(monkeypatch):
    _as(monkeypatch, _USER)
    with TestClient(_app(monkeypatch)) as c:
        cfg = c.get("/partnersessions/api/session").json()["contacts"]
        assert cfg == {"label": "Partner Contacts", "showRole": False,
                       "showAgreements": False, "primarySettable": True}
        mentor = c.get("/mentorsessions/api/session").json()["contacts"]
        assert mentor["label"] == "Client Contacts" and mentor["primarySettable"] is False


# --- Details: the partnership's read-only email mirror ----------------------

_PARTNER_META = {
    "name": {"type": "varchar"},
    "partnershipStatus": {"type": "enum", "options": ["Active"]},
    # EspoCRM foreign field: a read-only mirror of the primary contact's email
    "partnerEmail": {"type": "foreign", "link": "primaryPartnercontact",
                     "field": "emailAddress", "readOnly": True,
                     "view": "views/fields/foreign-email"},
}


def test_partner_email_is_labelled_and_composable():
    spec = {f["name"]: f for f in details._field_spec(_PARTNER_META, "CPartnerProfile")}
    f = spec["partnerEmail"]
    # not "Partner Email" — it's the contact's address, changed on the contact
    assert f["label"] == "Primary contact email"
    assert f["editable"] is False and f["type"] == "readonly"
    assert f["display"] == "email"  # rendered as a compose link, never bare


def test_foreign_email_never_becomes_writable():
    spec = {f["name"]: f for f in details._field_spec(_PARTNER_META, "CPartnerProfile")}
    assert details._clean_changes(spec, {"partnerEmail": "hijack@example.com"}) == {}


# --- set_primary_contact ----------------------------------------------------

class _PrimaryClient:
    """Enough CRM for the primary-contact write: the record's related contacts,
    a parent read, and an update recorder."""

    def __init__(self, contacts=(("C1", "Ann Partner"), ("C2", "Bob Partner")), current=None):
        self._contacts = contacts
        self._current = current
        self.updates: list[tuple] = []
        self.notes: list[str] = []

    async def list_related(self, entity, record_id, link, **kw):
        return {"list": [{"id": i, "name": n} for i, n in self._contacts]}

    async def get(self, entity, record_id, select=None):
        return {"id": record_id, "primaryPartnercontactId": self._current}

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        return {"id": record_id}

    async def create(self, entity, payload):  # stream note
        self.notes.append(payload.get("post", ""))
        return {"id": "note1"}


@pytest.mark.asyncio
async def test_set_primary_contact_writes_the_link_and_notes_it():
    client = _PrimaryClient()
    res = await service.set_primary_contact(PARTNER, client, "P1", "C2", actor="The Boss")
    assert res["changed"] is True and res["contactName"] == "Bob Partner"
    assert client.updates == [("CPartnerProfile", "P1", {"primaryPartnercontactId": "C2"})]
    assert client.notes and "Bob Partner" in client.notes[0] and "The Boss" in client.notes[0]


@pytest.mark.asyncio
async def test_set_primary_contact_is_a_noop_when_unchanged():
    client = _PrimaryClient(current="C1")
    res = await service.set_primary_contact(PARTNER, client, "P1", "C1")
    assert res["changed"] is False
    assert client.updates == []


@pytest.mark.asyncio
async def test_set_primary_contact_rejects_an_unrelated_contact():
    client = _PrimaryClient()
    with pytest.raises(service.SessionError, match="isn't on this record"):
        await service.set_primary_contact(PARTNER, client, "P1", "STRANGER")
    assert client.updates == []


@pytest.mark.asyncio
async def test_set_primary_contact_refused_on_the_mentor_domain():
    client = _PrimaryClient()
    with pytest.raises(service.SessionError):
        await service.set_primary_contact(MENTOR, client, "E1", "C1")
    assert client.updates == []


@pytest.mark.asyncio
async def test_funder_writes_its_own_primary_attr():
    client = _PrimaryClient()
    await service.set_primary_contact(SPONSOR, client, "S1", "C1")
    assert client.updates == [("CSponsorProfile", "S1", {"sponsorContactId": "C1"})]


# --- the endpoint -----------------------------------------------------------

def _app(monkeypatch, store=None):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()
    return create_app([info_request.SPEC], store=store)


def _as(monkeypatch, user, client=None):
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: user)
    monkeypatch.setattr(
        "sessions.router.client_for", lambda settings, u: client or _PrimaryClient()
    )


def test_primary_contact_endpoint(monkeypatch):
    _as(monkeypatch, _USER)
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/partnersessions/api/records/P1/primarycontact", json={"contactId": "C2"})
        assert r.status_code == 200 and r.json()["contactName"] == "Bob Partner"


def test_primary_contact_endpoint_not_registered_on_the_mentor_domain(monkeypatch):
    _as(monkeypatch, _USER)
    with TestClient(_app(monkeypatch)) as c:
        # falls through to the static mount — never a handled endpoint
        assert c.post(
            "/mentorsessions/api/records/E1/primarycontact", json={"contactId": "C1"}
        ).status_code in (404, 405)


# --- Referred Clients tab (partner domain only) -----------------------------

class _ReferredClient:
    """Returns the partner's referred engagements via the reverse link."""

    def __init__(self, engagements):
        self._engagements = engagements
        self.calls: list[tuple] = []

    async def list_related(self, entity, record_id, link, **kw):
        self.calls.append((entity, record_id, link))
        return {"list": list(self._engagements)}


_ENG_ROWS = [
    {"id": "E1", "name": "Acme Weight Loss", "engagementStatus": "Active",
     "engagementStartDate": "2026-01-05", "lastContactDate": "2026-07-01 09:00:00",
     "mentorProfileName": "Milt Sierra", "mentorProfileId": "M9",
     "primaryEngagementContactName": "Ann Client", "primaryEngagementContactId": "C1",
     "totalSessions": 4, "createdAt": "2026-01-05 10:00:00"},
    {"id": "E2", "name": "Beta Foods", "engagementStatus": "Submitted",
     "engagementStartDate": None, "lastContactDate": None,
     "mentorProfileName": None, "mentorProfileId": None,
     "primaryEngagementContactName": None, "primaryEngagementContactId": None,
     "totalSessions": 0, "createdAt": "2026-02-10 10:00:00"},
]


@pytest.mark.asyncio
async def test_list_referred_clients_reads_the_reverse_link():
    client = _ReferredClient(_ENG_ROWS)
    res = await service.list_referred_clients(PARTNER, client, "P1")
    # reads CPartnerProfile.engagements (reverse of CEngagement.referringPartner)
    assert client.calls == [("CPartnerProfile", "P1", "engagements")]
    rows = res["records"]
    assert [r["id"] for r in rows] == ["E2", "E1"]  # newest createdAt first
    e1 = next(r for r in rows if r["id"] == "E1")
    assert e1["name"] == "Acme Weight Loss" and e1["status"] == "Active"
    assert e1["startDate"] == "2026-01-05"
    assert e1["lastContact"] == "2026-07-01 09:00:00"  # the dedicated lastContactDate field
    assert e1["mentorName"] == "Milt Sierra" and e1["mentorId"] == "M9"
    assert e1["contactName"] == "Ann Client" and e1["contactId"] == "C1"
    assert e1["totalSessions"] == 4


@pytest.mark.asyncio
async def test_list_referred_clients_empty_without_the_link():
    # the mentor/sponsor domains don't set referred_clients_link → never reads
    client = _ReferredClient(_ENG_ROWS)
    assert await service.list_referred_clients(MENTOR, client, "E1") == {"records": []}
    assert client.calls == []


def test_referred_clients_tab_is_partner_only():
    from sessions.router import _detail_tabs
    assert "referredClients" in [t["key"] for t in _detail_tabs(PARTNER)]
    assert "referredClients" not in [t["key"] for t in _detail_tabs(MENTOR)]
    assert "referredClients" not in [t["key"] for t in _detail_tabs(SPONSOR)]


def test_referred_clients_endpoint(monkeypatch):
    _as(monkeypatch, _USER, client=_ReferredClient(_ENG_ROWS))
    with TestClient(_app(monkeypatch)) as c:
        r = c.get("/partnersessions/api/records/P1/referredclients")
        assert r.status_code == 200
        assert [row["id"] for row in r.json()["records"]] == ["E2", "E1"]


def test_referred_clients_endpoint_not_registered_on_the_mentor_domain(monkeypatch):
    _as(monkeypatch, _USER, client=_ReferredClient(_ENG_ROWS))
    with TestClient(_app(monkeypatch)) as c:
        # falls through to the static mount — never a handled endpoint
        assert c.get(
            "/mentorsessions/api/records/E1/referredclients"
        ).status_code in (404, 405)


def test_primary_contact_endpoint_rejects_a_stranger(monkeypatch):
    _as(monkeypatch, _USER)
    with TestClient(_app(monkeypatch)) as c:
        r = c.post("/partnersessions/api/records/P1/primarycontact", json={"contactId": "NOPE"})
        assert r.status_code == 400 and "isn't on this record" in r.json()["detail"]


# --- Last Contact Date auto-update (touch_last_contact) ----------------------

from datetime import datetime, timedelta, timezone  # noqa: E402


class _TouchClient:
    """Reads one field back and records updates — enough for touch_last_contact."""

    def __init__(self, current=None):
        self._current = current
        self.updates: list[tuple] = []

    async def get(self, entity, record_id, select=None):
        return {"id": record_id, select: self._current}

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, payload))
        return {"id": record_id}


def _dt(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_touch_last_contact_datetime_field_advances_from_empty():
    c = _TouchClient(current=None)
    await service.touch_last_contact(MENTOR, c, "E1", _dt("2026-07-20 14:00:00"))
    # engagement's datetime field keeps the full stamp
    assert c.updates == [("CEngagement", "E1", {"lastContactDate": "2026-07-20 14:00:00"})]


@pytest.mark.asyncio
async def test_touch_last_contact_partner_uses_the_date_field():
    c = _TouchClient(current=None)
    await service.touch_last_contact(PARTNER, c, "P1", _dt("2026-07-20 14:00:00"))
    # partner reuses `lastContacted`, a DATE field — truncated to the day
    assert c.updates == [("CPartnerProfile", "P1", {"lastContacted": "2026-07-20"})]


@pytest.mark.asyncio
async def test_touch_last_contact_is_advance_only():
    c = _TouchClient(current="2026-07-25 09:00:00")
    await service.touch_last_contact(MENTOR, c, "E1", _dt("2026-07-20 14:00:00"))  # older
    assert c.updates == []  # never regresses to an earlier contact


@pytest.mark.asyncio
async def test_touch_last_contact_same_day_is_noop_for_date_field():
    c = _TouchClient(current="2026-07-20")
    await service.touch_last_contact(PARTNER, c, "P1", _dt("2026-07-20 14:00:00"))
    assert c.updates == []  # same calendar day already recorded


@pytest.mark.asyncio
async def test_touch_last_contact_skips_a_future_date():
    future = datetime.now(timezone.utc) + timedelta(days=365)
    c = _TouchClient(current=None)
    await service.touch_last_contact(MENTOR, c, "E1", future)
    assert c.updates == []  # a future scheduled session is not a contact


@pytest.mark.asyncio
async def test_touch_last_contact_noop_without_parent_or_when():
    c = _TouchClient()
    await service.touch_last_contact(MENTOR, c, None, _dt("2026-07-20 14:00:00"))
    await service.touch_last_contact(MENTOR, c, "E1", None)
    assert c.updates == []


@pytest.mark.asyncio
async def test_touch_last_contact_swallows_crm_errors():
    class _Boom:
        async def get(self, *a, **k):
            raise EspoError("HTTP 403 forbidden")
        async def update(self, *a, **k):  # pragma: no cover - never reached
            raise AssertionError("should not update after a failed read")
    # best-effort: never raises
    await service.touch_last_contact(MENTOR, _Boom(), "E1", _dt("2026-07-20 14:00:00"))
