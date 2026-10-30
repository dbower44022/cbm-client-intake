"""Who attended a partner's or funder's events, by company.

prds/partner-attendance-report-plan.md — decision 3 (Doug, 10-28-26):
attendance is reported by company, the person as optional detail, and
someone who did not attend is never reported.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from events import config as cfg
from events import reporting
from tests.test_event_sponsorship import LinkCrm, _as, _sessions_app
from tests.test_events_reporting import _reg
from tests.test_events_service import make_event

ROOT = Path(__file__).resolve().parent.parent


class AttCrm(LinkCrm):
    def __init__(self, *, reg_company=True, **kw):
        super().__init__(**kw)
        self.reg_company = reg_company
        self.selects: list[str] = []

    async def metadata(self, key):
        if key == "entityDefs.CEventRegistration.links":
            return {"registrationCompany": {"type": "belongsTo"}} if self.reg_company else {}
        return await super().metadata(key)

    async def list(self, entity, **kw):
        if entity == cfg.REGISTRATION:
            self.selects.append(kw.get("select") or "")
        return await super().list(entity, **kw)


def _world(reg_company=True):
    events = [
        make_event(id="e1", name="Pricing for Profit", dateStart="2026-03-10 16:00:00"),
        make_event(id="e2", name="Cash Flow Basics", dateStart="2026-06-10 16:00:00"),
        make_event(id="e3", name="Empty Session", dateStart="2026-07-10 16:00:00"),
    ]
    regs = [
        # Ann registered under Brightline; her contact has moved on since.
        _reg("r1", "e1", "c1", firstName="Ann", lastName="Ames",
             registrationCompanyId="a1", registrationCompanyName="Brightline Bakehouse"),
        # Bo has no registration company: the contact's company now.
        _reg("r2", "e1", "c2", firstName="Bo", lastName="Berg"),
        # Never reported: not attended.
        _reg("r3", "e1", "c3", status=cfg.REG_NO_SHOW, firstName="No", lastName="Show"),
        _reg("r4", "e2", "c4", status=cfg.REG_REGISTERED, firstName="Reg", lastName="Only"),
        # Ann again at e2 — one person, still one name.
        _reg("r5", "e2", "c1", firstName="Ann", lastName="Ames",
             registrationCompanyId="a1", registrationCompanyName="Brightline Bakehouse"),
        # No company anywhere, no name on the registration: the contact's name.
        _reg("r6", "e2", "c5"),
        # No contact at all: the email.
        _reg("r7", "e2", None, email="walkin@example.org"),
    ]
    related = {("CPartnerProfile", "P1", "sponsoredEvents"): events}
    crm = AttCrm(events=events, registrations=regs, related=related, reg_company=reg_company)
    crm.data["Contact"] = [
        {"id": "c1", "name": "Ann Ames", "accountId": "a9", "accountName": "Zed Corp"},
        {"id": "c2", "name": "Bo Berg", "accountId": "a2", "accountName": "Acme Tools"},
        {"id": "c5", "name": "Cy Cole", "accountId": None, "accountName": None},
    ]
    crm.data["CPartnerProfile"] = [{"id": "P1", "name": "Alpha Chamber"}]
    return crm


def _call(crm, event_id=None):
    return reporting.sponsor_attendance(crm, "CPartnerProfile", "P1", "sponsoredEvents",
                                        event_id=event_id)


async def test_all_events_by_company_attended_only_no_company_last():
    out = await _call(_world())
    assert [r["company"] for r in out["rows"]] == [
        "Acme Tools", "Brightline Bakehouse", reporting.NO_COMPANY]
    rows = {r["company"]: r for r in out["rows"]}
    # The registration's company beats the contact's company now (Zed Corp).
    assert rows["Brightline Bakehouse"]["companyId"] == "a1"
    assert rows["Brightline Bakehouse"]["attended"] == 1
    assert rows["Brightline Bakehouse"]["names"] == ["Ann Ames"]          # deduplicated
    assert rows["Brightline Bakehouse"]["events"] == ["Pricing for Profit", "Cash Flow Basics"]
    assert rows["Acme Tools"]["names"] == ["Bo Berg"]                      # contact fallback
    none = rows[reporting.NO_COMPANY]
    assert none["companyId"] is None and none["attended"] == 2
    assert none["names"] == ["Cy Cole", "walkin@example.org"]
    names = [n for r in out["rows"] for n in r["names"]]
    assert "No Show" not in names and "Reg Only" not in names
    assert "Zed Corp" not in rows
    assert out["companies"] == 2 and out["people"] == 4
    assert [e["id"] for e in out["events"]] == ["e1", "e2", "e3"]          # oldest first
    assert set(out["events"][0]) == {"id", "title", "dateLabel", "startsAtUtc"}


async def test_one_event_filter():
    out = await _call(_world(), "e1")
    assert [e["id"] for e in out["events"]] == ["e1"]
    assert [r["company"] for r in out["rows"]] == ["Acme Tools", "Brightline Bakehouse"]
    assert out["people"] == 2


async def test_an_event_with_nobody_attended_is_empty():
    out = await _call(_world(), "e3")
    assert out["rows"] == [] and out["companies"] == 0 and out["people"] == 0


async def test_an_event_not_linked_is_not_found():
    with pytest.raises(reporting.EventNotLinked):
        await _call(_world(), "elsewhere")


async def test_without_the_registration_company_link_the_contact_company_is_used():
    crm = _world(reg_company=False)
    out = await _call(crm)
    assert all("registrationCompany" not in s for s in crm.selects)
    # (The fake still returns the snapshot keys; the select is what the CRM is asked.)
    crm2 = _world(reg_company=True)
    await _call(crm2)
    assert all("registrationCompanyId,registrationCompanyName" in s for s in crm2.selects)
    assert out["rows"]


# --- the route --------------------------------------------------------------


def test_route_gate_and_404(monkeypatch):
    user_crm = LinkCrm()
    user_crm.data["CPartnerProfile"] = [{"id": "P1", "name": "Alpha Chamber"}]
    user_crm.data["CSponsorProfile"] = [{"id": "S1", "name": "Big Bank"}]
    user_crm.forbid_list.update({cfg.REGISTRATION, cfg.EVENT})
    _as(monkeypatch, user_crm, system=_world())
    with TestClient(_sessions_app(monkeypatch)) as c:
        body = c.get("/partnersessions/api/records/P1/sponsoredevents/attendance").json()
        assert body["companies"] == 2 and body["people"] == 4
        one = c.get("/partnersessions/api/records/P1/sponsoredevents/attendance?event=e1")
        assert one.status_code == 200 and one.json()["people"] == 2
        r = c.get("/partnersessions/api/records/P1/sponsoredevents/attendance?event=nope")
        assert r.status_code == 404 and "not one of this partner's events" in r.json()["detail"]
        # A parent the user cannot read is a 404, whatever the org key could read.
        assert c.get("/partnersessions/api/records/P404/sponsoredevents/attendance").status_code == 404
        # Funder Management has the same route (no events linked to S1).
        f = c.get("/sponsorsessions/api/records/S1/sponsoredevents/attendance")
        assert f.status_code == 200 and f.json()["rows"] == [] and f.json()["events"] == []
        assert c.get("/mentorsessions/api/records/E1/sponsoredevents/attendance").status_code in (404, 405)


def test_route_explains_a_crm_without_the_link(monkeypatch):
    crm = LinkCrm(links={})
    crm.data["CPartnerProfile"] = [{"id": "P1", "name": "Alpha Chamber"}]
    _as(monkeypatch, crm)
    with TestClient(_sessions_app(monkeypatch)) as c:
        body = c.get("/partnersessions/api/records/P1/sponsoredevents/attendance").json()
    assert body["available"] is False and body["rows"] == []


# --- the page ----------------------------------------------------------------


def test_page_has_the_attendance_panel_and_buttons():
    page = (ROOT / "sessions" / "frontend" / "index.html").read_text()
    for el in ("speAttAll", "speAtt", "speAttNames", "speAttCopy", "speAttCsv",
               "speAttTable", "speAttEmpty", "speAttSummary"):
        assert f'id="{el}"' in page
    assert "Nobody was marked as attended at this event." in page
    # The actions column has no heading text and never sorts.
    assert re.search(r'<th data-sortable="false" scope="col"><span class="sx__sr">', page)


def test_script_builds_copy_and_csv_in_the_browser():
    js = (ROOT / "sessions" / "frontend" / "app.js").read_text()
    body = js.split("// --- Who attended, by company", 1)[1].split("// --- Campaigns tab", 1)[0]
    assert "/sponsoredevents/attendance" in body
    assert "new Blob(" in body and "URL.createObjectURL" in body and ".download = " in body
    assert "navigator.clipboard" in body and "fallbackCopy(" in body
    assert 'fitGrid("speAttTable"' in body and 'gridOrder("speAttTable"' in body
    assert "busyOver(panel" in body
    assert "disabled" not in body
    assert "openAttendance(r.id)" in js
