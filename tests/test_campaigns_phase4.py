"""Prospect marketing Phase 4: the funnel, the campaign's dashboard, and
Opportunity on attendance (build plan § 6)."""

from __future__ import annotations

import asyncio

from campaigns import attribution, reporting
from campaigns import config as cfg
from core.config import Settings
from tests.test_campaigns import FakeCrm


def run(coro):
    return asyncio.run(coro)


class _Crm(FakeCrm):
    """FakeCrm plus the stage field on Contact, with the lead model's options (rung_available)."""

    async def metadata(self, key):
        if key == "entityDefs.Contact.fields":
            return {"cFunnelStage": {"type": "enum", "options": ["Prospect", "Engaged", "Opportunity"]}}
        if key.startswith("entityDefs.Contact.fields.cFunnelStage") or key == "entityDefs.Contact.fields.cFunnelStage":
            return {"type": "enum"}
        return await super().metadata(key)


def test_the_funnel_counts_each_position_once():
    crm = FakeCrm()
    crm.add(cfg.PROSPECT, {"leadStatus": "Qualified"})
    crm.add(cfg.PROSPECT, {"leadStatus": "Unqualified"})
    crm.add(cfg.PROSPECT, {"leadStatus": "Qualified", "sideExit": "Stale"})           # no longer worked
    crm.add(cfg.PROSPECT, {"leadStatus": "Disqualified"})                               # never counted
    crm.add(cfg.PROSPECT, {"leadStatus": "Converted", "promotedCompanyId": "a1"})      # counted as its company
    crm.add("Account", {"id": "a1", "cCompanyType": ["Prospect"], "cFunnelStage": "Prospect"})
    crm.add("Account", {"id": "a2", "cCompanyType": ["Client"], "cFunnelStage": "Prospect"})   # not a prospect
    crm.add("Contact", {"cContactType": ["Prospect"], "cFunnelStage": "Prospect", "accountId": "a1"})   # under its company
    crm.add("Contact", {"cContactType": ["Prospect"], "cFunnelStage": "Engaged"})
    crm.add("CEngagement", {"engagementStatus": "Submitted"})
    crm.add("CEngagement", {"engagementStatus": "Active"})
    crm.add("CEngagement", {"engagementStatus": "Completed"})
    rows = {r["rung"]: r for r in run(reporting.funnel(crm))}
    assert [r for r in rows] == ["Unqualified", "Qualified", "Prospect", "Engaged", "Opportunity", "Candidate", "Client"]
    assert rows["Unqualified"]["count"] == 1 and rows["Qualified"]["count"] == 1
    assert rows["Prospect"]["count"] == 1 and rows["Engaged"]["count"] == 1 and rows["Opportunity"]["count"] == 0
    assert rows["Candidate"]["count"] == 1 and rows["Client"]["count"] == 1
    assert rows["Qualified"]["band"] == "Lead" and rows["Engaged"]["band"] == "Prospect" and rows["Client"]["band"] == "Client"


def test_campaign_results_count_the_records_carrying_it():
    crm = FakeCrm()
    for st in ("Submitted", "Active", "Declined"):
        crm.add("CEngagement", {"outreachCampaignId": "camp", "engagementStatus": st})
    crm.add("CEngagement", {"outreachCampaignId": "other", "engagementStatus": "Active"})
    crm.add("CEventRegistration", {"outreachCampaignId": "camp", "attendanceStatus": "Attended"})
    crm.add("CEventRegistration", {"outreachCampaignId": "camp", "attendanceStatus": "Registered"})
    crm.add("CInformationRequest", {"outreachCampaignId": "camp"})
    crm.add("CPartnerProfile", {"outreachCampaignId": "camp"})
    assert run(reporting.campaign_results(crm, "camp")) == {
        "candidates": 1, "clients": 1, "registered": 2, "attended": 1,
        "informationRequests": 1, "partners": 1, "funders": 0}


def test_the_campaign_dashboard_is_registered_and_scoped():
    import analytics  # noqa: F401
    from analytics.registry import MetricContext, RecordRef, get_metric, get_page
    page = get_page("record-campaign")
    assert page.scope == "COutreachCampaign" and len(page.panels) == 10
    # Ruling 46's three counts lead the dashboard.
    assert [p.metric_key for p in page.panels[:3]] == ["campaign_responded", "campaign_converted", "campaign_became"]
    assert get_page("campaigns").panels[0].metric_key == "prospect_funnel"
    crm = FakeCrm()
    crm.add("CEngagement", {"outreachCampaignId": "camp", "engagementStatus": "Active"})
    ctx = MetricContext(settings=Settings(_env_file=None), espo=crm,
                        record=RecordRef(entity="COutreachCampaign", record_id="camp", value="camp"))
    assert run(get_metric("campaign_clients").compute(ctx)).data["value"] == 1
    off = run(get_metric("campaign_clients").compute(MetricContext(settings=None, espo=crm)))
    assert off.error


def test_attendance_moves_a_prospect_to_opportunity_and_never_a_client():
    crm = _Crm()
    crm.add("Contact", {"id": "c-p", "cContactType": ["Prospect"], "cFunnelStage": "Engaged"})
    crm.add("Contact", {"id": "c-c", "cContactType": ["Client"], "cFunnelStage": None})
    crm.add("CEventRegistration", {"id": "r1", "contactId": "c-p", "attendanceStatus": "Attended"})
    crm.add("CEventRegistration", {"id": "r2", "contactId": "c-c", "attendanceStatus": "Attended"})
    crm.add("CEventRegistration", {"id": "r3", "contactId": "c-p", "attendanceStatus": "No Show"})
    assert run(attribution.opportunity_on_attendance(crm, "r1")) == "Opportunity"
    assert crm.rows["Contact"]["c-p"]["cFunnelStage"] == "Opportunity"
    assert run(attribution.opportunity_on_attendance(crm, "r2")) is None          # ruling 37
    assert run(attribution.opportunity_on_attendance(crm, "r3")) is None


def test_campaign_writes_split_the_applications_stamps_from_the_persons_change():
    """Ruling 40: the eight app-owned campaign fields go through the API client
    (the Marketing Admin Role may not edit them); the status as the user."""
    from campaigns import service
    user, api = FakeCrm(), FakeCrm()
    camp = user.add(cfg.CAMPAIGN, {"name": "X", "campaignStatus": "Draft"})
    api.rows = user.rows
    out = run(service.stamp_campaign(user, api, camp["id"], {
        "campaignStatus": "Awaiting sign-off", "selectionRule": "{}", "selectionSummary": "s",
        "signedOffByName": "Mark", "estimatedCostCurrency": "USD"}))
    assert user.updated == [(cfg.CAMPAIGN, camp["id"], {"campaignStatus": "Awaiting sign-off"})]
    assert api.updated == [(cfg.CAMPAIGN, camp["id"], {"selectionRule": "{}", "selectionSummary": "s",
                                                       "signedOffByName": "Mark", "estimatedCostCurrency": "USD"})]
    assert out["campaignStatus"] == "Awaiting sign-off" and out["selectionSummary"] == "s"


def test_the_applier_changes_a_field_parameter_and_reads_it_back():
    import importlib.util, json, pathlib
    plan = json.loads(pathlib.Path("scripts/plans/coutreach-campaign-app-fields.json").read_text())
    assert [f["name"] for f in plan["fieldParams"]] == [
        "selectionRule", "selectionSummary", "pieceCount", "estimatedCost",
        "signedOffByName", "signedOffAt", "runStartedAt", "runCompletedAt"]
    assert all(f["params"] == {"readOnly": False} for f in plan["fieldParams"])
    from scripts.migrate_outreach_roles import APP_OWNED_CAMPAIGN_FIELDS
    assert set(APP_OWNED_CAMPAIGN_FIELDS) == {f["name"] for f in plan["fieldParams"]}
    assert set(APP_OWNED_CAMPAIGN_FIELDS) <= cfg.CAMPAIGN_APP_FIELDS
