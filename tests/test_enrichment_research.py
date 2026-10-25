"""Lead enrichment phase 2 — the AI research pass started by staff.

prds/lead-enrichment/build-plan-phase-2.md § 5. The model, the CRM and the
run store are fakes; the CRM fake refuses a page above 200 as EspoCRM does.
"""

from __future__ import annotations

import json
from types import SimpleNamespace as NS
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient

from core.config import Settings, get_settings
from core.espo import EspoError
from enrichment import research, runs


# --- fakes ------------------------------------------------------------------------------------

def usage(inp=20000, out=1500, searches=3):
    return NS(input_tokens=inp, output_tokens=out, cache_creation_input_tokens=0, cache_read_input_tokens=0,
              server_tool_use=NS(web_search_requests=searches))


def report_block(**raw):
    base = {"business_found": True, "candidates": [], "people": [], "summary": "", "summary_sources": []}
    base.update(raw)
    return NS(type="tool_use", name="report_findings", input=base, id="tu1",
              model_dump=lambda **k: {"type": "tool_use", "name": "report_findings", "input": base, "id": "tu1"})


def text_block(t="searching"):
    return NS(type="text", text=t, model_dump=lambda **k: {"type": "text", "text": t})


class FakeAI:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[dict] = []
        outer = self

        class _M:
            async def create(self_inner, **kw):
                outer.calls.append(kw)
                return outer.responses.pop(0)
        self.messages = _M()
        self.beta = NS(messages=_M())


def resp(content, stop="tool_use", model="claude-opus-5-5", use=None):
    return NS(content=content, stop_reason=stop, model=model, usage=use or usage())


class FakeCrm:
    def __init__(self):
        self.rows: dict[str, dict[str, dict]] = {"CProspect": {}, "Account": {}, "Contact": {},
                                                 "CEnrichmentFinding": {}, "CEngagement": {}, "CClientProfile": {}}
        self.n = 0
        self.has_findings = True

    async def metadata(self, key):
        if key == "entityDefs.CEnrichmentFinding.links":
            return {"prospect": {}, "company": {}} if self.has_findings else None
        if key == "entityDefs.CProspect.fields":
            return {"name": {}, "website": {}, "industry": {}}
        if key.endswith(".fields.industry"):
            return {"options": ["", "Food & Beverage", "Construction"]}
        return None

    async def get(self, entity, rid, select=None):
        row = self.rows[entity].get(rid)
        if row is None:
            raise EspoError(f"get {entity}/{rid} failed: HTTP 404")
        return dict(row)

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0, order_by=None, order=None):
        assert max_size <= 200, "the CRM refuses a page over 200"
        rows = list(self.rows[entity].values())
        for c in where or []:
            rows = [r for r in rows if r.get(c["attribute"]) == c["value"]]
        return {"total": len(rows), "list": [dict(r) for r in rows[offset:offset + max_size]]}

    async def create(self, entity, payload):
        self.n += 1
        rid = f"{entity[:3].lower()}{self.n:05d}"
        self.rows[entity][rid] = {"id": rid, **payload}
        return dict(self.rows[entity][rid])

    async def update(self, entity, rid, payload):
        self.rows[entity][rid].update(payload)
        return dict(self.rows[entity][rid])


class FakeStore:
    def __init__(self, avg=None, spent=0.0, queued=0):
        self.avg, self.spent, self.queued = avg, spent, queued
        self.runs: dict[str, dict] = {}
        self.items: list[dict] = []
        self.finished: list[tuple] = []

    async def average_item_cost(self, last=50):
        return self.avg

    async def month_spend(self, now=None):
        return self.spent

    async def queued_items(self):
        return self.queued + sum(1 for i in self.items if i["status"] in ("queued", "running"))

    async def create_run(self, *, tier, target_type, target_ids, estimate, model, started_by):
        rid = f"run{len(self.runs) + 1}"
        self.runs[rid] = {"id": rid, "target_type": target_type, "model": model}
        for t in target_ids:
            self.items.append({"run_id": rid, "target_id": t, "status": "queued",
                               "target_type": target_type, "model": model})
        return self.runs[rid]

    async def claim(self, limit, now=None):
        out = [i for i in self.items if i["status"] == "queued"][:limit]
        for i in out:
            i["status"] = "running"
        return [dict(i) for i in out]

    async def finish_item(self, run_id, target_id, *, ok, cost, findings, detail, error):
        for i in self.items:
            if i["run_id"] == run_id and i["target_id"] == target_id:
                i["status"] = "done" if ok else "failed"
        self.finished.append((target_id, ok, cost, findings, error))


def settings(**kw) -> Settings:
    base = dict(espo_dry_run=False, espo_api_key="k", enrichment_ai=True, anthropic_api_key="sk",
                database_url="postgresql://x/y", enrichment_monthly_budget=50.0)
    base.update(kw)
    return Settings(**base)


def lead_row(crm, **kw):
    row = {"name": "Smith Bakery LLC", "businessName": "Smith Bakery LLC", "mailingAddressStreet": "123 Main St",
           "mailingAddressCity": "Cleveland", "mailingAddressState": "OH", "mailingAddressPostalCode": "44113",
           "website": "", "email": "owner@private.example", "phone": "2165550100", "importRow": None}
    row.update(kw)
    return crm.create.__self__ and _put(crm, "CProspect", row)


def _put(crm, entity, row):
    crm.n += 1
    rid = row.get("id") or f"{entity[:3].lower()}{crm.n:05d}"
    crm.rows[entity][rid] = {"id": rid, **row}
    return rid


# --- ruling E12, counted by the application ----------------------------------------------------

def test_confidence_counts_two_facts_and_the_agent_exclusion():
    c = research.confidence
    assert c(["name", "street_address"], agent_address=False) == research.VERIFIED
    assert c(["name", "postal_code"], agent_address=False) == research.VERIFIED
    assert c(["name", "associate"], agent_address=True) == research.VERIFIED
    assert c(["name", "street_address"], agent_address=True) == research.UNVERIFIED   # E12 exclusion
    assert c(["name", "city"], agent_address=False) == research.LIKELY
    assert c(["name"], agent_address=False) == research.UNVERIFIED
    assert c(["street_address", "postal_code"], agent_address=False) == research.UNVERIFIED  # no name


def test_usage_cost_is_tokens_at_the_models_price_plus_searches():
    cost, n = research.usage_cost(usage(1_000_000, 100_000, 4), "claude-opus-5-5")
    assert n == 4 and cost == pytest.approx(4.0 + 2.0 + 0.04)


def test_the_request_carries_only_what_E7_allows():
    s = research.Subject(name="Smith Bakery LLC", street="123 Main St", city="Cleveland", postal="44113",
                         associates=["Jane Doe"])
    text = s.prompt()
    assert "Smith Bakery" in text and "Jane Doe" in text
    assert "@" not in text and "216" not in text


# --- the engine ------------------------------------------------------------------------------

async def test_research_reads_the_report_and_overrules_an_overclaim():
    ai = FakeAI([resp([text_block(), report_block(
        candidates=[{"kind": "website", "value": "https://smithbakery.com", "source_url": "https://smithbakery.com",
                     "facts_seen": ["name", "street_address"]},
                    {"kind": "email", "value": "hi@smith.example", "source_url": "https://x", "facts_seen": ["name"]},
                    {"kind": "industry", "value": "Not An Option", "source_url": "https://x", "facts_seen": ["name", "postal_code"]}],
        people=[{"name": "Jane Doe", "title": "Owner", "email": "", "source_url": "https://y", "facts_seen": ["name", "city"]}],
        summary="A bakery.", summary_sources=["https://smithbakery.com"])])])
    subject = research.Subject(name="Smith Bakery LLC", industry_options=["Food & Beverage"])
    res = await research.research(ai, subject, model="claude-opus-5-5", max_searches=5, fallback=True, record_cap=1.0)
    assert res.ok and res.found
    conf = {c.kind: c.confidence for c in res.candidates}
    assert conf == {"website": "Verified", "email": "Unverified"}       # bad industry option dropped
    assert res.people[0].confidence == "Likely"
    assert res.cost > 0 and res.searches == 3
    call = ai.calls[0]
    assert call["fallbacks"] == "default" and research.FALLBACK_BETA in call["betas"]
    assert call["tool_choice"] == {"type": "auto"}
    assert {t["name"] for t in call["tools"]} == {"web_search", "web_fetch", "report_findings"}


async def test_pause_turn_resumes_without_a_user_message():
    ai = FakeAI([resp([text_block()], stop="pause_turn"), resp([report_block(business_found=False)])])
    res = await research.research(ai, research.Subject(name="X Co"), model="claude-opus-5-5",
                                  max_searches=5, fallback=False, record_cap=1.0)
    assert res.ok and not res.found
    assert ai.calls[1]["messages"][-1]["role"] == "assistant"


async def test_a_refusal_and_a_missing_report_are_failed_records():
    ai = FakeAI([resp([], stop="refusal")])
    res = await research.research(ai, research.Subject(name="X Co"), model="m", max_searches=1, fallback=False, record_cap=1)
    assert not res.ok and "declined" in res.error
    ai = FakeAI([resp([text_block()], stop="end_turn"), resp([text_block()], stop="end_turn")])
    res = await research.research(ai, research.Subject(name="X Co"), model="m", max_searches=1, fallback=False, record_cap=1)
    assert not res.ok and "without reporting" in res.error
    assert ai.calls[1]["messages"][-1] == {"role": "user", "content": "Call report_findings now with what you found."}


async def test_the_per_business_cap_stops_a_runaway():
    ai = FakeAI([resp([text_block()], stop="pause_turn", use=usage(500_000, 10_000, 5))])
    res = await research.research(ai, research.Subject(name="X Co"), model="claude-opus-5-5",
                                  max_searches=5, fallback=False, record_cap=1.0)
    assert not res.ok and "over the $1.00 limit" in res.error


# --- landing (design § 6) --------------------------------------------------------------------

def _result(*cands, people=(), summary=""):
    r = research.Result(ok=True, found=True, summary=summary, summary_sources=["https://s"] if summary else [])
    for kind, value, conf in cands:
        r.candidates.append(research.Candidate(kind, value, "https://src", ["name", "street_address"], conf))
    for name in people:
        r.people.append(research.Person(name, "Owner", "", "https://p", ["name", "associate"], "Verified"))
    return r


async def test_a_verified_website_fills_an_empty_lead_field_and_nothing_else_is_written():
    crm = FakeCrm()
    lid = _put(crm, "CProspect", {"businessName": "Smith Bakery LLC", "website": "", "email": "keep@x.example",
                                  "phone": ""})
    record = await crm.get("CProspect", lid)
    counts = await runs.land(crm, _result(("website", "https://smithbakery.com", "Verified"),
                                          ("email", "new@smith.example", "Verified"),
                                          ("phone", "216 555 0199", "Likely"),
                                          ("email", "junk@x", "Unverified"),
                                          people=["Jane Doe"], summary="A bakery."),
                             target_type="lead", record=record, run_id="r1", lead_has_industry=True)
    lead = crm.rows["CProspect"][lid]
    assert lead["website"] == "https://smithbakery.com"           # E14
    assert lead["email"] == "keep@x.example"                      # never over a value
    assert lead["leadStatus"] if "leadStatus" in lead else True
    found = list(crm.rows["CEnrichmentFinding"].values())
    statuses = {(f.get("targetField") or f["kind"]): f["findingStatus"] for f in found}
    assert statuses["website"] == "Applied" and statuses["email"] == "Proposed" and statuses["phone"] == "Proposed"
    assert counts["applied"] == 1 and counts["skipped"] == 1       # the Unverified email
    assert all(f["name"] for f in found)                            # the CRM requires a name
    again = await runs.land(crm, _result(("phone", "216 555 0199", "Likely"), people=["Jane Doe"]),
                            target_type="lead", record=lead, run_id="r2")
    assert again["created"] == 0                                    # never the same finding twice


@pytest.mark.parametrize("field,held,proposed,same", [
    ("website", "https://greatlakesbrewing.com", "https://www.greatlakesbrewing.com", True),
    ("website", "greatlakesbrewing.com", "HTTP://GreatLakesBrewing.com/", True),
    ("website", "https://acme.com/a", "https://acme.com/b", False),
    ("emailAddress", "Info@Acme.com", "info@acme.com", True),
    ("phone", "(216) 555-0199", "216.555.0199", True),
    ("phoneNumber", "+1 216 555 0199", "2165550199", True),
    ("phone", "2165550199", "2165550100", False),
    ("industry", "Food & Beverage", "food & beverage", True),
    ("website", "", "", False),
])
def test_same_value_is_what_a_person_would_call_the_same(field, held, proposed, same):
    assert runs.same_value(field, held, proposed) is same


async def test_a_held_website_with_www_makes_no_finding():
    crm = FakeCrm()
    lid = _put(crm, "CProspect", {"businessName": "Great Lakes Brewing Company",
                                  "website": "https://greatlakesbrewing.com", "email": "", "phone": "(216) 771-4404"})
    counts = await runs.land(crm, _result(("website", "https://www.greatlakesbrewing.com", "Verified"),
                                          ("phone", "216-771-4404", "Verified")),
                             target_type="lead", record=await crm.get("CProspect", lid), run_id="r1")
    assert counts == {"created": 0, "applied": 0, "skipped": 2}
    assert crm.rows["CEnrichmentFinding"] == {}


async def test_accepting_a_value_the_record_already_holds_closes_it_and_writes_nothing():
    crm = FakeCrm()
    cid, fid = await _client_finding(crm, kind="Field value", targetField="website",
                                     proposedValue="https://www.smithbakery.com")
    crm.rows["Account"][cid]["website"] = "https://smithbakery.com"
    out = await runs.decide(crm, fid, "Accepted", actor="Cara Client", target_type="company", target_id=cid)
    assert out["status"] == "Accepted" and out["note"] == "the record already holds this"
    assert crm.rows["Account"][cid]["website"] == "https://smithbakery.com"
    assert crm.rows["CEnrichmentFinding"][fid]["findingStatus"] == "Accepted"


async def test_nothing_on_a_client_is_written_without_a_person():
    crm = FakeCrm()
    cid = _put(crm, "Account", {"name": "Smith Bakery LLC", "website": ""})
    await runs.land(crm, _result(("website", "https://smithbakery.com", "Verified")), target_type="company",
                    record=await crm.get("Account", cid), run_id="r1")
    assert crm.rows["Account"][cid]["website"] == ""
    assert [f["findingStatus"] for f in crm.rows["CEnrichmentFinding"].values()] == ["Proposed"]


# --- Accept and Reject -----------------------------------------------------------------------

async def _client_finding(crm, **kw):
    cid = _put(crm, "Account", {"name": "Smith Bakery LLC", "website": "", "assignedUsersIds": ["u9"], "teamsIds": ["t1"]})
    fid = _put(crm, "CEnrichmentFinding", {"companyId": cid, "findingStatus": "Proposed", **kw})
    return cid, fid


async def test_accepting_a_field_fills_it_only_when_empty():
    crm = FakeCrm()
    cid, fid = await _client_finding(crm, kind="Field value", targetField="website", proposedValue="https://s.com")
    out = await runs.decide(crm, fid, "Accepted", actor="Cara Client", target_type="company", target_id=cid)
    assert crm.rows["Account"][cid]["website"] == "https://s.com" and out["status"] == "Accepted"
    assert crm.rows["CEnrichmentFinding"][fid]["decidedBy"] == "Cara Client"
    cid2, fid2 = await _client_finding(crm, kind="Field value", targetField="website", proposedValue="https://t.com")
    crm.rows["Account"][cid2]["website"] = "https://mine.com"
    with pytest.raises(runs.EnrichmentError, match="never replaces"):
        await runs.decide(crm, fid2, "Accepted", actor="x", target_type="company", target_id=cid2)
    with pytest.raises(runs.EnrichmentError, match="Already accepted"):
        await runs.decide(crm, fid, "Rejected", actor="x", target_type="company", target_id=cid)


async def test_accepting_a_person_on_a_client_creates_a_contact_never_opted_in():
    crm = FakeCrm()
    cid, fid = await _client_finding(crm, kind="Person", personName="Jane Q Doe", personTitle="Owner",
                                     personEmail="jane@smith.example", sourceUrl="https://s")
    await runs.decide(crm, fid, "Accepted", actor="Cara", target_type="company", target_id=cid)
    contact = next(iter(crm.rows["Contact"].values()))
    assert contact["lastName"] == "Doe" and contact["firstName"] == "Jane Q" and contact["accountId"] == cid
    assert contact["assignedUsersIds"] == ["u9"] and contact["teamsIds"] == ["t1"]
    assert "cMarketingOptIn" not in contact and "ruling E10" in contact["description"]
    cid2, fid2 = await _client_finding(crm, kind="Person", personName="Jim Roe", personEmail="jane@smith.example")
    crm.rows["Contact"][next(iter(crm.rows["Contact"]))]["emailAddress"] = "jane@smith.example"
    with pytest.raises(runs.EnrichmentError, match="already belongs"):
        await runs.decide(crm, fid2, "Accepted", actor="x", target_type="company", target_id=cid2)


async def test_accepting_a_person_on_a_lead_fills_its_empty_person_fields_and_makes_no_contact():
    """Ruling 121: the person goes into the lead's own firstName / lastName /
    email where they are empty; ruling 43 stands — no Contact is created."""
    crm = FakeCrm()
    lid = _put(crm, "CProspect", {"businessName": "S", "firstName": "", "lastName": "", "email": "", "phone": ""})
    fid = _put(crm, "CEnrichmentFinding", {"prospectId": lid, "kind": "Person", "personName": "Jane Q Doe",
                                           "personEmail": "jane@s.example", "findingStatus": "Proposed"})
    out = await runs.decide(crm, fid, "Accepted", actor="Mark", target_type="lead", target_id=lid)
    lead = crm.rows["CProspect"][lid]
    assert (lead["firstName"], lead["lastName"], lead["email"]) == ("Jane Q", "Doe", "jane@s.example")
    assert out["status"] == "Accepted" and "lastName set to Doe" in out["note"]
    assert crm.rows["Contact"] == {} and crm.rows["CEnrichmentFinding"][fid]["decidedBy"] == "Mark"
    # A field the lead already holds is never replaced; the rest still fill.
    lid2 = _put(crm, "CProspect", {"businessName": "T", "firstName": "", "lastName": "", "email": "kept@t.example"})
    fid2 = _put(crm, "CEnrichmentFinding", {"prospectId": lid2, "kind": "Person", "personName": "Roe",
                                            "personEmail": "roe@t.example", "findingStatus": "Proposed"})
    out2 = await runs.decide(crm, fid2, "Accepted", actor="Mark", target_type="lead", target_id=lid2)
    assert crm.rows["CProspect"][lid2]["email"] == "kept@t.example" and crm.rows["CProspect"][lid2]["lastName"] == "Roe"
    assert out2["note"] == "lastName set to Roe"


async def test_accepting_a_person_the_lead_already_holds_closes_it_and_writes_nothing():
    crm = FakeCrm()
    lid = _put(crm, "CProspect", {"businessName": "S", "firstName": "Jane", "lastName": "Doe", "email": "jane@s.example"})
    fid = _put(crm, "CEnrichmentFinding", {"prospectId": lid, "kind": "Person", "personName": "Jane Doe",
                                           "personEmail": "jane@s.example", "findingStatus": "Proposed"})
    before = dict(crm.rows["CProspect"][lid])
    out = await runs.decide(crm, fid, "Accepted", actor="Mark", target_type="lead", target_id=lid)
    assert out["note"] == "the lead already holds this person" and crm.rows["CProspect"][lid] == before
    assert crm.rows["CEnrichmentFinding"][fid]["findingStatus"] == "Accepted"


async def test_a_summary_can_only_be_rejected_and_a_finding_belongs_to_one_lead():
    crm = FakeCrm()
    lid = _put(crm, "CProspect", {"businessName": "S"})
    fid = _put(crm, "CEnrichmentFinding", {"prospectId": lid, "kind": "Summary", "summary": "A shop.",
                                           "findingStatus": "Proposed"})
    with pytest.raises(runs.EnrichmentError, match="nothing to accept"):
        await runs.decide(crm, fid, "Accepted", actor="x", target_type="lead", target_id=lid)
    out = await runs.decide(crm, fid, "Rejected", actor="x", target_type="lead", target_id=lid)
    assert out["status"] == "Rejected"
    other = _put(crm, "CProspect", {"businessName": "T"})
    with pytest.raises(runs.EnrichmentError, match="does not belong"):
        await runs.decide(crm, fid, "Rejected", actor="x", target_type="lead", target_id=other)


def test_suggestions_map_the_newest_proposed_findings_onto_the_row_boxes():
    """Build plan § 7e.6: one value per box, newest first; a Person's name
    split first / last, its email only when no email finding came first;
    decided findings and summaries ignored; the ids used are returned."""
    rows = [
        {"id": "f1", "kind": "Field value", "targetField": "email", "proposedValue": "new@s.example", "findingStatus": "Proposed"},
        {"id": "f2", "kind": "Field value", "targetField": "email", "proposedValue": "old@s.example", "findingStatus": "Proposed"},
        {"id": "f3", "kind": "Field value", "targetField": "phone", "proposedValue": "216 555 0100", "findingStatus": "Rejected"},
        {"id": "f4", "kind": "Person", "personName": "Jane Q Doe", "personEmail": "jane@s.example", "findingStatus": "Proposed"},
        {"id": "f5", "kind": "Field value", "targetField": "website", "proposedValue": "https://s.example", "findingStatus": "Applied"},
        {"id": "f6", "kind": "Summary", "summary": "A shop.", "findingStatus": "Proposed"},
        {"id": "f7", "kind": "Person", "personName": "Second Person", "findingStatus": "Proposed"},
    ]
    out = runs.suggestions(rows)
    assert out == {"website": "", "email": "new@s.example", "phone": "", "firstName": "Jane Q", "lastName": "Doe",
                   "findingIds": ["f1", "f4"]}
    assert runs.suggestions([]) == {"website": "", "email": "", "phone": "", "firstName": "", "lastName": "", "findingIds": []}
    assert runs.split_name("Cher") == ("", "Cher") and runs.split_name("  ") == ("", "")


async def test_close_findings_marks_proposed_ones_accepted_and_names_the_rest():
    crm = FakeCrm()
    lid = _put(crm, "CProspect", {"businessName": "S", "email": ""})
    mine = _put(crm, "CEnrichmentFinding", {"prospectId": lid, "kind": "Field value", "targetField": "email",
                                            "proposedValue": "x@s.example", "findingStatus": "Proposed"})
    done = _put(crm, "CEnrichmentFinding", {"prospectId": lid, "kind": "Person", "personName": "Z",
                                            "findingStatus": "Rejected", "decidedBy": "Pat"})
    other = _put(crm, "CEnrichmentFinding", {"prospectId": "lead-other", "kind": "Person", "personName": "Y",
                                             "findingStatus": "Proposed"})
    out = await runs.close_findings(crm, [mine, done, other, "bad id!", mine], target_id=lid, actor="Mark")
    assert [c["id"] for c in out["closed"]] == [mine]
    assert [(s["id"], s["why"][:12]) for s in out["skipped"]] == [(done, "Already reje"), (other, "That finding"), ("bad id!", "Not a findin")]
    f = crm.rows["CEnrichmentFinding"][mine]
    assert f["findingStatus"] == "Accepted" and f["decidedBy"] == "Mark" and f["decidedAt"]
    assert crm.rows["CProspect"][lid]["email"] == ""          # closing never writes the value


# --- starting a run under the budget (E8, E9) --------------------------------------------------

async def test_a_run_past_the_budget_is_refused_with_the_amounts():
    store = FakeStore(avg=0.25, spent=49.0)
    with pytest.raises(runs.EnrichmentError, match=r"\$1.00 of this month's \$50.00 is left"):
        await runs.start_run(store, settings(), target_type="lead", target_ids=[f"lead{i:04d}" for i in range(10)],
                             started_by="Mark")
    out = await runs.start_run(store, settings(), target_type="lead", target_ids=["lead0001", "lead0001", "bad id!"],
                               started_by="Mark")
    assert out["records"] == 1 and out["estimate"] == 0.25


async def test_a_run_is_refused_when_off_too_big_or_its_estimate_grew():
    with pytest.raises(runs.EnrichmentError, match="switched off"):
        await runs.start_run(FakeStore(), settings(enrichment_ai=False), target_type="lead", target_ids=["lead0001"], started_by="m")
    with pytest.raises(runs.EnrichmentError, match="at most 2"):
        await runs.start_run(FakeStore(), settings(enrichment_ai_max_records=2), target_type="lead",
                             target_ids=["lead0001", "lead0002", "lead0003"], started_by="m")
    with pytest.raises(runs.EnrichmentError, match="changed"):
        await runs.start_run(FakeStore(avg=0.5), settings(), target_type="lead", target_ids=["lead0001"],
                             started_by="m", confirm_estimate=0.2)
    est = await runs.estimate(FakeStore(), settings(), 3)
    assert est["perRecord"] == runs.DEFAULT_RECORD_COST and not est["measured"]


# --- the worker -----------------------------------------------------------------------------

async def test_the_worker_researches_the_queue_and_lands_findings():
    crm = FakeCrm()
    lid = _put(crm, "CProspect", {"businessName": "Smith Bakery LLC", "mailingAddressStreet": "123 Main St",
                                  "mailingAddressPostalCode": "44113", "website": "", "email": "private@x.example"})
    store = FakeStore()
    await runs.start_run(store, settings(), target_type="lead", target_ids=[lid], started_by="m")
    ai = FakeAI([resp([report_block(candidates=[{"kind": "website", "value": "https://smithbakery.com",
                                                 "source_url": "https://smithbakery.com",
                                                 "facts_seen": ["name", "postal_code"]}])])])
    taken = await runs.run_research_cycle(settings(), store, client=crm, ai=ai)
    assert taken == 1 and store.finished[0][1] is True and store.finished[0][3] == 1
    assert crm.rows["CProspect"][lid]["website"] == "https://smithbakery.com"
    assert "private@x.example" not in json.dumps(ai.calls[0]["messages"])     # E7


async def test_the_worker_does_nothing_when_off_or_without_the_entity():
    crm, store = FakeCrm(), FakeStore()
    await runs.start_run(store, settings(), target_type="lead", target_ids=["lead0001"], started_by="m")
    assert await runs.run_research_cycle(settings(enrichment_ai=False), store, client=crm, ai=FakeAI([])) == 0
    crm.has_findings = False
    assert await runs.run_research_cycle(settings(), store, client=crm, ai=FakeAI([])) == 0


async def test_a_lead_without_a_business_name_fails_cleanly():
    crm = FakeCrm()
    lid = _put(crm, "CProspect", {"businessName": "", "firstName": "Pat"})
    out = await runs.research_item(settings(), crm, FakeAI([]), {"target_type": "lead", "target_id": lid, "run_id": "r"})
    assert not out["ok"] and "business name" in out["error"]


# --- the endpoints' gates (E19) --------------------------------------------------------------

MARKETING = {"userName": "mark", "name": "Mark Marketing", "id": "u-1", "isAdmin": False, "token": "t",
             "teams": ["Marketing Admin Team"]}
CLIENT_ADMIN = {"userName": "cara", "name": "Cara Client", "id": "u-2", "isAdmin": False, "token": "t",
                "teams": ["Client Administration Team"]}


def build(monkeypatch, user, crm):
    from core.app import create_app
    from forms import ALL_SPECS
    monkeypatch.setenv("CAMPAIGNS_ENABLED", "true")
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ESPO_DRY_RUN", "true")
    get_settings.cache_clear()
    app = create_app(ALL_SPECS)
    import enrichment.router as r
    monkeypatch.setattr(r, "current_user", lambda request: user)
    monkeypatch.setattr(r.runs, "api_client", lambda s: crm)
    return TestClient(app)


def test_a_client_panel_is_client_administration_only(monkeypatch):
    crm = FakeCrm()
    cid = _put(crm, "Account", {"name": "Smith Bakery LLC"})
    eid = _put(crm, "CEngagement", {"clientOrganizationId": None, "engagementClientId": "prof1"})
    crm.rows["CClientProfile"]["prof1"] = {"id": "prof1", "linkedCompanyId": cid, "linkedCompanyName": "Smith Bakery LLC"}
    resp = build(monkeypatch, MARKETING, crm).get(f"/enrichment/api/engagement/{eid}")
    assert resp.status_code == 403 and "Client Administration" in resp.json()["detail"]
    resp = build(monkeypatch, CLIENT_ADMIN, crm).get(f"/enrichment/api/engagement/{eid}")
    assert resp.status_code == 200 and resp.json()["company"]["id"] == cid


def test_a_lead_panel_is_campaign_management_only(monkeypatch):
    crm = FakeCrm()
    lid = _put(crm, "CProspect", {"businessName": "S"})
    assert build(monkeypatch, CLIENT_ADMIN, crm).get(f"/enrichment/api/lead/{lid}").status_code == 403
    body = build(monkeypatch, MARKETING, crm).get(f"/enrichment/api/lead/{lid}").json()
    assert body["available"] is True and body["findings"] == []
    get_settings.cache_clear()
