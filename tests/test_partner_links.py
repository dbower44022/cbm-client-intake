"""Partner and funder associations — prds/partner-association-plan.md (Doug's
rulings 10-28-26), stop 2: the one module that writes them, and its callers.

The rule: a tie is held by the company when there is one, else the person or
the lead, and moves to the company once it exists; a second partner or funder
is a second association; the same tie is never written twice; nothing is ever
deleted; attendance (not registration) at a partner's or funder's event
creates one; a CRM without the entity is left exactly as before.
"""

from __future__ import annotations

import asyncio

from core import partner_links as pl
from tests.test_campaigns import FakeCrm


def run(coro):
    return asyncio.run(coro)


class AssocCrm(FakeCrm):
    def __init__(self, *, with_assoc: bool = True, with_reg_company: bool = True):
        super().__init__()
        self.with_assoc = with_assoc
        self.with_reg_company = with_reg_company

    async def metadata(self, key):
        if key == f"entityDefs.{pl.ENTITY}.fields":
            return {"reason": {"type": "enum"}, "associatedAt": {"type": "datetime"}} if self.with_assoc else None
        if key == "entityDefs.CEventRegistration.links":
            return {"registrationCompany": {"type": "belongsTo"}} if self.with_reg_company else {}
        if key == "entityDefs.CProspect.links":
            return {"referredByPartner": {"type": "belongsTo"}}
        return await super().metadata(key)

    async def list_related(self, entity, record_id, link, *, select=None, max_size=200):
        ids = self.related.get((entity, record_id, link), set())
        foreign = {pl.EVENT_PARTNERS: pl.PARTNER, pl.EVENT_FUNDERS: pl.FUNDER,
                   "referringPartners": pl.PARTNER}.get(link, "")
        rows = [self.rows.get(foreign, {}).get(i, {"id": i}) for i in sorted(ids)]
        return {"total": len(rows), "list": rows}

    def assocs(self):
        return list(self.rows.get(pl.ENTITY, {}).values())


def _setup(crm):
    lib = crm.add(pl.PARTNER, {"name": "Lakewood Library"})
    bank = crm.add(pl.PARTNER, {"name": "Shore Bank"})
    fund = crm.add(pl.FUNDER, {"name": "Adler Foundation"})
    bakery = crm.add("Account", {"name": "Moreno Bakery"})
    alicia = crm.add("Contact", {"name": "Alicia Moreno", "accountId": bakery["id"]})
    return lib, bank, fund, bakery, alicia


def test_a_tie_is_held_by_the_company_and_written_once():
    crm = AssocCrm()
    lib, _bank, _f, bakery, alicia = _setup(crm)
    a = run(pl.associate(crm, reason=pl.REASON_REFERRED_TO, partner_id=lib["id"], company_id=bakery["id"],
                         contact_id=alicia["id"]))
    b = run(pl.associate(crm, reason=pl.REASON_REFERRED_TO, partner_id=lib["id"], company_id=bakery["id"]))
    assert a and a == b and len(crm.assocs()) == 1
    row = crm.assocs()[0]
    assert row["companyId"] == bakery["id"] and row["contactId"] == alicia["id"]
    assert row["name"] == "Lakewood Library — Referred to CBM"


def test_a_second_partner_or_a_funder_is_a_second_association():
    crm = AssocCrm()
    lib, bank, fund, bakery, _a = _setup(crm)
    run(pl.associate(crm, reason=pl.REASON_REFERRED_TO, partner_id=lib["id"], company_id=bakery["id"]))
    run(pl.associate(crm, reason=pl.REASON_REFERRED_TO, partner_id=bank["id"], company_id=bakery["id"]))
    run(pl.associate(crm, reason=pl.REASON_REFERRED_TO, funder_id=fund["id"], company_id=bakery["id"]))
    assert len(crm.assocs()) == 3
    assert sum(1 for r in crm.assocs() if r.get("sponsorProfileId") == fund["id"]) == 1


def test_bad_calls_and_a_crm_without_the_entity_write_nothing():
    crm = AssocCrm(with_assoc=False)
    lib, _b, fund, bakery, _a = _setup(crm)
    assert run(pl.associate(crm, reason=pl.REASON_REFERRED_TO, partner_id=lib["id"], company_id=bakery["id"])) is None
    ok = AssocCrm()
    lib, _b, fund, bakery, _a = _setup(ok)
    assert run(pl.associate(ok, reason="Something else", partner_id=lib["id"], company_id=bakery["id"])) is None
    assert run(pl.associate(ok, reason=pl.REASON_REFERRED_TO, partner_id=lib["id"], funder_id=fund["id"],
                            company_id=bakery["id"])) is None
    assert run(pl.associate(ok, reason=pl.REASON_REFERRED_TO, partner_id=lib["id"])) is None
    assert crm.assocs() == [] and ok.assocs() == []


def test_a_tie_on_a_person_moves_to_their_company_and_is_never_removed():
    crm = AssocCrm()
    lib, _b, _f, _bakery, _a = _setup(crm)
    sam = crm.add("Contact", {"name": "Sam Startup"})
    run(pl.associate(crm, reason=pl.REASON_REFERRED_TO, partner_id=lib["id"], contact_id=sam["id"]))
    assert crm.assocs()[0].get("companyId") in (None, "")
    newco = crm.add("Account", {"name": "Sam's New Co"})
    crm.rows["Contact"][sam["id"]]["accountId"] = newco["id"]
    summary = run(pl.run_transfer_pass(crm))
    assert summary["moved"] == 1 and crm.assocs()[0]["companyId"] == newco["id"]
    # Sam leaves the company: the company keeps the tie.
    crm.rows["Contact"][sam["id"]]["accountId"] = None
    run(pl.run_transfer_pass(crm))
    assert crm.assocs()[0]["companyId"] == newco["id"] and len(crm.assocs()) == 1


def test_conversion_carries_the_leads_partner_and_its_ties_to_the_company():
    crm = AssocCrm()
    lib, bank, _f, bakery, alicia = _setup(crm)
    lead = crm.add("CProspect", {"name": "Moreno Bakery", "referredByPartnerId": lib["id"]})
    run(pl.associate(crm, reason=pl.REASON_REFERRED_TO, partner_id=bank["id"], lead_id=lead["id"]))
    run(pl.on_conversion(crm, lead, company_id=bakery["id"], contact_id=alicia["id"]))
    by_partner = {r["partnerProfileId"]: r for r in crm.assocs()}
    assert set(by_partner) == {lib["id"], bank["id"]}
    assert all(r["companyId"] == bakery["id"] for r in by_partner.values())
    assert by_partner[bank["id"]]["contactId"] == alicia["id"]


def test_attendance_at_a_partners_and_funders_event_associates_the_company_registered_from():
    crm = AssocCrm()
    lib, _b, fund, bakery, alicia = _setup(crm)
    ev = crm.add("CEvent", {"name": "Spring Clinic"})
    crm.related[("CEvent", ev["id"], pl.EVENT_PARTNERS)] = {lib["id"]}
    crm.related[("CEvent", ev["id"], pl.EVENT_FUNDERS)] = {fund["id"]}
    reg = crm.add("CEventRegistration", {"contactId": alicia["id"], "eventId": ev["id"],
                                         "attendanceStatus": "Registered"})
    assert run(pl.stamp_registration_company(crm, reg["id"], alicia["id"])) == bakery["id"]
    # She leaves the bakery before the event: the registration remembers it.
    crm.rows["Contact"][alicia["id"]]["accountId"] = None
    assert run(pl.on_attendance(crm, reg["id"])) == 0, "registered is not attended"
    crm.rows["CEventRegistration"][reg["id"]]["attendanceStatus"] = "Attended"
    assert run(pl.on_attendance(crm, reg["id"])) == 2
    assert {(r.get("partnerProfileId"), r.get("sponsorProfileId"), r["companyId"], r["eventId"], r["reason"])
            for r in crm.assocs()} == {(lib["id"], None, bakery["id"], ev["id"], pl.REASON_ATTENDED),
                                       (None, fund["id"], bakery["id"], ev["id"], pl.REASON_ATTENDED)}
    assert run(pl.on_attendance(crm, reg["id"])) == 2 and len(crm.assocs()) == 2, "never twice"


def test_a_registration_company_waits_for_the_crm_field():
    crm = AssocCrm(with_reg_company=False)
    _l, _b, _f, _bakery, alicia = _setup(crm)
    reg = crm.add("CEventRegistration", {"contactId": alicia["id"]})
    assert run(pl.stamp_registration_company(crm, reg["id"], alicia["id"])) is None
    assert "registrationCompanyId" not in crm.rows["CEventRegistration"][reg["id"]]


def test_intake_and_a_mentors_referral():
    crm = AssocCrm()
    lib, bank, _f, bakery, alicia = _setup(crm)
    eng = crm.add("CEngagement", {"clientOrganizationId": bakery["id"], "primaryEngagementContactId": alicia["id"]})
    assert run(pl.on_intake(crm, partner_ids=[lib["id"], lib["id"]], company_id=bakery["id"],
                            contact_id=alicia["id"], engagement_id=eng["id"])) == 1
    assert run(pl.on_mentor_referral(crm, partner_id=bank["id"], engagement=eng))
    reasons = {(r["partnerProfileId"], r["reason"]) for r in crm.assocs()}
    assert reasons == {(lib["id"], pl.REASON_REFERRED_TO), (bank["id"], pl.REASON_REFERRED_BY)}
    assert all(r["engagementId"] == eng["id"] for r in crm.assocs())


def test_the_backfill_plans_what_the_records_imply_and_applying_twice_writes_once():
    crm = AssocCrm()
    lib, bank, fund, bakery, alicia = _setup(crm)
    crm.add("CProspect", {"name": "Lead Co", "referredByPartnerId": lib["id"], "promotedCompanyId": bakery["id"]})
    eng = crm.add("CEngagement", {"referringPartnerId": bank["id"], "clientOrganizationId": bakery["id"],
                                  "primaryEngagementContactId": alicia["id"]})
    crm.related[("CEngagement", eng["id"], "referringPartners")] = {bank["id"]}
    ev = crm.add("CEvent", {"name": "Spring Clinic"})
    crm.related[("CEvent", ev["id"], pl.EVENT_FUNDERS)] = {fund["id"]}
    crm.add("CEventRegistration", {"contactId": alicia["id"], "eventId": ev["id"], "attendanceStatus": "Attended"})
    crm.add("CEventRegistration", {"contactId": alicia["id"], "eventId": ev["id"], "attendanceStatus": "No-show"})
    plan = run(pl.plan_backfill(crm))
    assert len(plan) == 3
    text = pl.plan_text(plan)
    assert text == pl.plan_text(list(reversed(plan))), "the fingerprint text is order-free"
    run(pl.apply_backfill(crm, plan))
    run(pl.apply_backfill(crm, plan))
    assert len(crm.assocs()) == 3


def test_the_operations_job_is_registered_and_mutating():
    from setup.jobs import JOBS
    job = next(j for j in JOBS if j.key == "partner_associations")
    assert job.mutating and job.dry_run and job.apply
