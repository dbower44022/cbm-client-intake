"""Lead enrichment phase 1 — the free pass and the fit score.

prds/lead-enrichment/build-plan-phase-1.md § 5. The CRM fake refuses a page
above 200 exactly as EspoCRM does (a 403, not a truncation).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import httpx
import pytest

from core.config import Settings
from core.espo import EspoError
from enrichment import findability, fit, geo, sweep
from enrichment.terms import Segments, build_segments, build_terms, core_name

TERMS = build_terms()
AREA = geo.parse_service_area("OH:Cuyahoga|OH:Lake")


def ctx(**kw) -> fit.ScoreContext:
    base = dict(area=AREA, terms=TERMS, today=date(2026, 10, 20))
    base.update(kw)
    return fit.ScoreContext(**base)


def lead(**kw) -> dict[str, Any]:
    base = {"id": "L1", "businessName": "Smith Bakery LLC", "mailingAddressStreet": "123 Main St",
            "mailingAddressPostalCode": "44113", "mailingAddressState": "OH",
            "website": "", "email": "", "leadStatus": "Unqualified", "sideExit": None}
    base.update(kw)
    return base


# --- geo ---------------------------------------------------------------------------------

def test_zip_to_county_and_split_postal_codes():
    assert ("OH", "Cuyahoga") in geo.counties_for("44113-1234")
    split = geo.counties_for("44060")
    assert {c for _, c in split} >= {"Lake", "Geauga"}
    assert geo.in_area(split, AREA) == "Lake"          # any part inside passes
    assert geo.counties_for("00000") == ()
    assert geo.counties_for("") == ()


def test_service_area_parsing_tolerates_county_word_and_separators():
    area = geo.parse_service_area("OH:Lake County; oh:cuyahoga\nbad")
    assert area == frozenset({("OH", "lake"), ("OH", "cuyahoga")})


# --- the gate ----------------------------------------------------------------------------

def test_in_area_passes_with_county():
    r = fit.score_lead(lead(), ctx())
    assert r.gate == fit.GATE_PASSED and r.county == "Cuyahoga"
    assert any("inside the service area" in x for x in r.reasons)


def test_out_of_area_scores_zero():
    r = fit.score_lead(lead(mailingAddressPostalCode="45402"), ctx())   # Dayton
    assert r.gate == fit.GATE_OUT and r.score == 0 and r.county == "Montgomery"


def test_unknown_postal_code_is_location_unknown_and_still_scored():
    r = fit.score_lead(lead(mailingAddressPostalCode=""), ctx())
    assert r.gate == fit.GATE_UNKNOWN and r.score > 0


def test_agent_address_is_location_unknown():
    row = {"agent_name": "Northwest Registered Agent LLC", "agent_street": "123 Main St"}
    r = fit.score_lead(lead(importRow=json.dumps(row)), ctx())
    assert r.gate == fit.GATE_UNKNOWN
    assert any("registered agent" in x for x in r.reasons)


def test_no_service_area_skips_the_gate():
    r = fit.score_lead(lead(mailingAddressPostalCode="45402"), ctx(area=frozenset()))
    assert r.gate == fit.GATE_PASSED
    assert r.reasons[0].startswith("No service area is set")


# --- the signals -------------------------------------------------------------------------

def test_trade_name_beats_holding_name():
    trade = fit.score_lead(lead(businessName="Smith Plumbing LLC"), ctx())
    hold = fit.score_lead(lead(businessName="Smith Holdings LLC"), ctx())
    assert trade.operating > hold.operating
    assert hold.operating <= 20


def test_recent_filing_raises_and_old_filing_lowers():
    new = fit.score_lead(lead(importRow=json.dumps({"effective_date": "2026-08-01"})), ctx())
    old = fit.score_lead(lead(importRow=json.dumps({"effective_date": "2015-01-01"})), ctx())
    assert new.operating > old.operating


def test_serial_filer_deduction_and_its_absence_is_said():
    row = json.dumps({"associates": "Jane Doe; Ann Lee"})
    plain = fit.score_lead(lead(importRow=row), ctx())
    serial = fit.score_lead(lead(importRow=row), ctx(serial_counts={"jane doe": 5}))
    assert plain.operating - serial.operating == 30
    none = fit.score_lead(lead(importRow=json.dumps({"x": 1})), ctx())
    assert any("no associates" in x for x in none.reasons)


def test_segment_is_fifty_until_the_list_exists():
    assert fit.score_lead(lead(), ctx()).segment == 50
    segs = build_segments({"favoured": ["bakery"], "excluded": ["cannabis"]})
    assert fit.score_lead(lead(), ctx(segments=segs)).segment == 85
    assert fit.score_lead(lead(businessName="Green Cannabis LLC"), ctx(segments=segs)).segment == 10
    assert fit.score_lead(lead(industry="Retail"), ctx(segments=segs)).segment in (50, 85)


def test_findability_counts_email_and_website():
    assert fit.score_lead(lead(), ctx()).findability == 0
    assert fit.score_lead(lead(email="a@b.com"), ctx()).findability == 50
    assert fit.score_lead(lead(email="a@b.com", website="https://x.com"), ctx()).findability == 100


def test_verified_web_check_only_offers_a_website_for_an_empty_field():
    web = fit.WebCheck("https://smithbakery.com", True, "the name and the street address appear")
    r = fit.score_lead(lead(), ctx(), web)
    assert r.verified_website == "https://smithbakery.com" and r.findability == 50
    kept = fit.score_lead(lead(website="https://other.com"), ctx(), web)
    assert kept.verified_website == ""
    assert any("the stored one was kept" in x for x in kept.reasons)


def test_weights_and_version():
    assert fit.parse_weights("2,1,1") == (2.0, 1.0, 1.0)
    assert fit.parse_weights("x") == (1.0, 1.0, 1.0)
    assert fit.parse_weights("0,0,0") == (1.0, 1.0, 1.0)
    a, b = ctx().version, ctx(weights=(2.0, 1.0, 1.0)).version
    assert a != b and a.startswith(fit.RULE_VERSION + ".") and len(a) <= 20
    assert ctx().version == a                       # stable


# --- the web check -----------------------------------------------------------------------

def test_candidates_strip_the_legal_suffix():
    assert core_name("Smith Bakery, L.L.C.", TERMS) == ["smith", "bakery"]
    assert findability.candidates("Smith Bakery LLC", TERMS) == [
        "smithbakery.com", "smith-bakery.com", "smithbakery.net"]
    assert findability.candidates("AB LLC", TERMS) == []


def _web(pages: dict[str, str]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = pages.get(request.url.host)
        if body is None:
            raise httpx.ConnectError("no such host", request=request)
        if body == "TIMEOUT":
            raise httpx.ReadTimeout("slow", request=request)
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_name_and_street_verifies():
    http = _web({"smithbakery.com": "<h1>Smith Bakery</h1><p>Visit us at 123 Main Street</p>"})
    r = await findability.check(lead(), TERMS, http, agent=False)
    assert r.verified and r.website == "https://smithbakery.com"
    assert "street address" in r.evidence


async def test_name_only_does_not_verify():
    http = _web({"smithbakery.com": "<h1>Smith Bakery</h1><p>Dubai, UAE</p>"})
    assert not (await findability.check(lead(), TERMS, http, agent=False)).verified


async def test_agent_address_never_counts_but_an_associate_does():
    page = "<h1>Smith Bakery</h1>123 Main Street. Owner Jane Doe."
    http = _web({"smithbakery.com": page})
    assert not (await findability.check(lead(), TERMS, http, agent=True)).verified
    row = json.dumps({"associates": "Jane Doe"})
    r = await findability.check(lead(importRow=row), TERMS, _web({"smithbakery.com": page}), agent=True)
    assert r.verified and "associate jane doe" in r.evidence


async def test_timeout_and_missing_hosts_are_unverified():
    http = _web({"smithbakery.com": "TIMEOUT"})
    assert not (await findability.check(lead(), TERMS, http, agent=False)).verified


# --- the sweep ---------------------------------------------------------------------------

class FakeCrm:
    def __init__(self, leads, *, fields=True):
        self.leads = {l["id"]: dict(l) for l in leads}
        self.fields = fields
        self.updates: list[tuple[str, dict]] = []
        self.fail_ids: set[str] = set()

    async def metadata(self, key):
        if key == "entityDefs.CProspect.fields":
            base = {k: {} for k in ("name", "website", "email")}
            if self.fields:
                base.update({f: {} for f in sweep.FIT_FIELDS})
            return base
        return None

    def _match(self, row, where):
        for c in where or []:
            t = c["type"]
            if t == "in" and row.get(c["attribute"]) not in c["value"]:
                return False
            if t == "isNull" and row.get(c["attribute"]) not in (None, ""):
                return False
            if t == "isNotNull" and row.get(c["attribute"]) in (None, ""):
                return False
            if t == "or" and not any(self._match(row, [s]) for s in c["value"]):
                return False
            if t == "notEquals" and (row.get(c["attribute"]) in (None, "")
                                     or row.get(c["attribute"]) == c["value"]):
                return False
        return True

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0,
                   order_by=None, order=None):
        if max_size > 200:
            raise EspoError("Max size should not exceed 200. Use offset and limit.")
        rows = [r for r in self.leads.values() if self._match(r, where)]
        return {"total": len(rows), "list": [dict(r) for r in rows[offset:offset + max_size]]}

    async def update(self, entity, rid, payload):
        if rid in self.fail_ids:
            raise EspoError("refused")
        self.updates.append((rid, payload))
        self.leads[rid].update(payload)
        return self.leads[rid]


def settings(**kw) -> Settings:
    base = dict(espo_dry_run=False, espo_api_key="k", enrichment_free_pass=True,
                chapter_counties="OH:Cuyahoga|OH:Lake")
    base.update(kw)
    return Settings(**base)


@pytest.fixture(autouse=True)
def _reset_caches():
    sweep._failed.clear()
    sweep._serial_cache.update(at=0.0, counts={})


async def test_sweep_scores_open_leads_only_and_never_touches_status():
    crm = FakeCrm([lead(id="A"), lead(id="B", leadStatus="Converted"),
                   lead(id="C", sideExit="Duplicate"), lead(id="D", leadStatus="Qualified")])
    totals = await sweep.run_pass(settings(), crm)
    assert totals["scored"] == 2 and {r for r, _ in crm.updates} == {"A", "D"}
    for _, p in crm.updates:
        assert "leadStatus" not in p and "website" not in p
        assert p["fitGate"] == "Passed" and p["fitRuleVersion"].startswith("1.")


async def test_sweep_rescores_on_a_rule_change_and_not_otherwise():
    crm = FakeCrm([lead(id="A")])
    await sweep.run_pass(settings(), crm)
    assert len(crm.updates) == 1
    await sweep.run_pass(settings(), crm)
    assert len(crm.updates) == 1                       # nothing due
    await sweep.run_pass(settings(fit_weights="2,1,1"), crm)
    assert len(crm.updates) == 2                       # new version, rescored


async def test_sweep_writes_a_verified_website_only_into_an_empty_field(monkeypatch):
    async def fake_check(l, terms, http, *, agent):
        return fit.WebCheck("https://found.com", True, "the name and the postal code appear")
    monkeypatch.setattr(findability, "check", fake_check)
    crm = FakeCrm([lead(id="A"), lead(id="B", website="https://mine.com")])
    totals = await sweep.run_pass(settings(enrichment_web_checks=True), crm)
    by = dict(crm.updates)
    assert by["A"]["website"] == "https://found.com"
    assert "website" not in by["B"]
    assert totals["websites"] == 1


async def test_out_of_area_leads_spend_no_web_request(monkeypatch):
    called = []

    async def fake_check(*a, **k):
        called.append(1)
        return fit.WebCheck()
    monkeypatch.setattr(findability, "check", fake_check)
    crm = FakeCrm([lead(id="A", mailingAddressPostalCode="45402")])
    totals = await sweep.run_pass(settings(enrichment_web_checks=True), crm)
    assert called == [] and totals["out_of_area"] == 1


async def test_sweep_is_inert_without_the_fields():
    crm = FakeCrm([lead(id="A")], fields=False)
    assert (await sweep.run_pass(settings(), crm))["scored"] == 0
    assert crm.updates == []


async def test_a_failing_lead_is_skipped_for_an_hour():
    crm = FakeCrm([lead(id="A"), lead(id="B")])
    crm.fail_ids = {"A"}
    t1 = await sweep.run_pass(settings(), crm, now=1000.0)
    assert t1["failed"] == 1 and t1["scored"] == 1
    t2 = await sweep.run_pass(settings(), crm, now=1100.0)
    assert t2["failed"] == 0 and t2["scored"] == 0


async def test_switch_off_does_nothing():
    crm = FakeCrm([lead(id="A")])
    assert await sweep.run_fit_sweep(settings(enrichment_free_pass=False), client=crm) == {}
    assert crm.updates == []


async def test_batch_never_asks_for_more_than_200():
    crm = FakeCrm([lead(id=f"L{i}") for i in range(5)])
    totals = await sweep.run_pass(settings(enrichment_batch=999), crm)
    assert totals["scored"] == 5


async def test_serial_counts_read_every_import_row():
    rows = [lead(id=f"S{i}", importRow=json.dumps({"associates": "Jane Doe"})) for i in range(4)]
    crm = FakeCrm(rows + [lead(id="X")])
    counts = await sweep.serial_counts(crm, now=10.0)
    assert counts == {"jane doe": 4}
    await sweep.run_pass(settings(), crm)
    reasons = [p["fitReasons"] for _, p in crm.updates if _ .startswith("S")]
    assert all("serial filer" in r for r in reasons)


async def test_operations_plan_text_is_stable_and_clockless(monkeypatch):
    crm = FakeCrm([lead(id="A"), lead(id="B", mailingAddressPostalCode="45402")])
    monkeypatch.setattr(sweep, "_client", lambda s: crm)
    a = await sweep.job_dry_run(settings())
    b = await sweep.job_dry_run(settings())
    assert a == b and "Out of area" in a and "Rule version" in a
    assert crm.updates == []
    # Scoring a batch in between (the worker) must not move the plan.
    await sweep.run_pass(settings(), crm, limit=1)
    assert await sweep.job_dry_run(settings()) == a
    crm.updates.clear()
    done = await sweep.job_apply(settings())
    assert done.startswith("1 leads scored: 1 out of area")


def test_segments_empty_by_default():
    assert Segments().empty and build_segments(None).empty
