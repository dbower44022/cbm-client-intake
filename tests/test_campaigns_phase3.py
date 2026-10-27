"""Campaign Management, Phase 3 (prds/prospect-marketing/build-plan.md § 7),
reworked for the lead model (§ 7a; rulings 41-53): the list import, the review,
the call kind, the Stale sweep and the Analytics reads.

The boundaries tested: a list row enters Unqualified and creates no Company or
Contact; each review action applies only where the rules say (Qualify only with
a website or an email) and never writes a reason over another; the call
selection's terms; the Calls screen's gate is the campaign's teams (ruling 36),
the touch is written as the caller and the conversion, the reason and the fresh
row are the API client's; Interested converts only with an email or a website
(ruling 47); the Stale sweep's window and its deterministic plan; the three
response counts of ruling 46.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from campaigns import calls, imports, reporting, review, service, stale
from campaigns import config as cfg
from campaigns.conversion import Details
from core.config import Settings
from tests.test_campaigns import FakeCrm, FakeStore, MARKETING, OUTSIDER, build

MENTOR = {"userName": "mia", "name": "Mia Mentor", "userId": "u-3", "token": "t",
          "isAdmin": False, "teams": ["Mentor Team"]}


def run(coro):
    return asyncio.run(coro)


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def _crm_time(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


# --- 1. the list import (§ 2.3; rulings 18, 43, 53) ---------------------------------------------

LIST_CSV = (
    "business_name,mailing_street,mailing_city,mailing_state,mailing_zip,email,website,phone\n"
    "Phone Shop,1 Main St,Cleveland,OH,44113,,,216-555-0101\n"
    "Mail Shop,2 Main St,Cleveland,OH,44113,owner@mail-shop.example,,\n"
    "Web Shop,3 Main St,Cleveland,OH,44113,,webshop.example,\n"
)


def test_list_import_enters_unqualified_and_creates_no_company_or_contact():
    crm, store = FakeCrm(), FakeStore()
    plan = run(imports.plan_import(crm, store, text=LIST_CSV, name="Chamber list", door=cfg.SOURCE_LIST,
                                   qualified_by="", list_source="Lorain Chamber"))
    assert plan["counts"]["create"] == 3 and plan["counts"]["unqualified"] == 3
    run(imports.apply_import(crm, crm, store, run(store.get_batch(plan["batchId"])), user_name="Mark"))
    leads = list(crm.rows[cfg.PROSPECT].values())
    assert {p["leadStatus"] for p in leads} == {"Unqualified"}
    assert {p["leadSource"] for p in leads} == {"List"}
    assert all(p["leadStatusChangedAt"] for p in leads)
    assert all(p["importBatch"].startswith("Lorain Chamber — ") for p in leads)
    assert not any(p.get("qualifiedBy") for p in leads)          # the review stamps it
    # Ruling 43: no Company or Contact before first contact.
    assert not crm.rows.get("Contact") and not crm.rows.get("Account")


def test_a_partner_file_is_its_own_lead_source():
    crm, store = FakeCrm(), FakeStore()
    plan = run(imports.plan_import(crm, store, text=LIST_CSV, name="Partner file", door=cfg.SOURCE_PARTNER_FILE,
                                   qualified_by="", list_source="Bank"))
    run(imports.apply_import(crm, crm, store, run(store.get_batch(plan["batchId"])), user_name="Mark"))
    assert {p["leadSource"] for p in crm.rows[cfg.PROSPECT].values()} == {"Partner file"}
    with pytest.raises(service.CampaignError):
        run(imports.plan_import(crm, store, text=LIST_CSV, name="x", door="Event registration", qualified_by=""))


# --- 2. the review (§ 2.3, § 3.8; rulings 42, 50) --------------------------------------------------

def _p(**kw):
    return {"id": "p1", "name": "Acme", "businessName": "Acme", "leadStatus": "Unqualified",
            "website": "acme.example", "sideExit": None, **kw}


def test_qualify_needs_a_website_or_email_and_stamps_the_reviewer():
    user, api = review.plan_action(_p(), review.ACTION_QUALIFY, reviewer="Mark Marketing", note="Called them")
    assert user["leadStatus"] == "Qualified" and user["qualifiedBy"] == "Mark Marketing"
    assert user["qualifiedAt"] and user["leadStatusChangedAt"] == user["qualifiedAt"]
    assert "Called them" in user["description"] and api == {}
    by_email, _ = review.plan_action(_p(website=None, email="a@acme.example"), review.ACTION_QUALIFY, reviewer="M")
    assert by_email["leadStatus"] == "Qualified"
    with pytest.raises(service.CampaignError) as exc:
        review.plan_action(_p(website=None), review.ACTION_QUALIFY, reviewer="M")     # ruling 42
    assert "website or an email" in str(exc.value)
    with pytest.raises(service.CampaignError):
        review.plan_action(_p(leadStatus="Qualified"), review.ACTION_QUALIFY, reviewer="M")


def test_disqualify_needs_a_note_and_is_a_status_not_a_reason():
    with pytest.raises(service.CampaignError) as exc:
        review.plan_action(_p(), review.ACTION_DISQUALIFY, reviewer="Mark", note="  ")
    assert "required" in str(exc.value)
    user, _ = review.plan_action(_p(leadStatus="Qualified"), review.ACTION_DISQUALIFY, reviewer="Mark", note="A franchise")
    assert user["leadStatus"] == "Disqualified" and "sideExit" not in user           # ruling 50
    assert "Disqualified by Mark" in user["description"] and "A franchise" in user["description"]
    with pytest.raises(service.CampaignError):
        review.plan_action(_p(leadStatus="Converted"), review.ACTION_DISQUALIFY, reviewer="Mark", note="x")


@pytest.mark.parametrize("action", [review.ACTION_QUALIFY, review.ACTION_DISQUALIFY, review.ACTION_DO_NOT_CONTACT])
def test_no_reason_is_written_over_another(action):
    with pytest.raises(service.CampaignError) as exc:
        review.plan_action(_p(sideExit="Stale"), action, reviewer="Mark", note="x")
    assert "Stale" in str(exc.value)


def test_do_not_contact_applies_to_any_unconverted_lead():
    user, _ = review.plan_action(_p(leadStatus="Qualified"), review.ACTION_DO_NOT_CONTACT, reviewer="Mark")
    assert user["sideExit"] == "Do Not Contact" and "Mark" in user["sideExitNote"]
    with pytest.raises(service.CampaignError):
        review.plan_action(_p(leadStatus="Converted"), review.ACTION_DO_NOT_CONTACT, reviewer="Mark")


def test_not_the_same_company_clears_duplicate_and_its_link_under_the_api_client():
    crm, api = FakeCrm(), FakeCrm()
    p = crm.add(cfg.PROSPECT, _p(id="p9", leadStatus="Qualified",
                                 sideExit="Duplicate", sideExitNote="Duplicate of the company Acme Inc (matched by website at import).",
                                 alreadyKnownCompanyId="acc-1", alreadyKnownCompanyName="Acme Inc"))
    out = run(review.apply_action(crm, api, p, review.ACTION_NOT_SAME_COMPANY, reviewer="Mark", note="Different owner"))
    written = crm.updated[-1][2]
    assert written["sideExit"] is None and "Acme Inc" in written["description"] and "leadStatus" not in written
    assert api.updated == [(cfg.PROSPECT, "p9", {"alreadyKnownCompanyId": None})]
    assert "alreadyKnownCompanyId" in out["written"]
    with pytest.raises(service.CampaignError):
        review.plan_action(_p(sideExit="Stale"), review.ACTION_NOT_SAME_COMPANY, reviewer="Mark")


def test_review_route_writes_and_refuses_with_a_readable_400(monkeypatch):
    crm = FakeCrm()
    crm.add(cfg.PROSPECT, _p(id="p1"))
    client = build(monkeypatch, user=MARKETING, crm=crm, store=FakeStore())
    ok = client.post("/campaigns/api/prospects/p1/review", json={"action": "qualify", "note": ""})
    assert ok.status_code == 200 and crm.rows[cfg.PROSPECT]["p1"]["leadStatus"] == "Qualified"
    again = client.post("/campaigns/api/prospects/p1/review", json={"action": "qualify", "note": ""})
    assert again.status_code == 400 and "Unqualified" in again.json()["detail"]
    assert client.post("/campaigns/api/prospects/p1/review", json={"action": "unqualify"}).status_code == 400
    listed = client.get("/campaigns/api/prospects?status=Qualified").json()["prospects"]
    assert [p["id"] for p in listed] == ["p1"]


# --- 3. the call kind (§ 3.4; rulings 36, 44, 47, 52) -------------------------------------------------

def _seed_callable(crm):
    crm.add(cfg.PROSPECT, {"id": "p-phone", "businessName": "Phone Shop", "leadStatus": "Qualified", "phone": "216-555-0101"})
    crm.add(cfg.PROSPECT, {"id": "p-unq", "businessName": "Unreviewed", "leadStatus": "Unqualified", "phone": "216-555-0109"})
    crm.add(cfg.PROSPECT, {"id": "p-nophone", "businessName": "No Phone", "leadStatus": "Qualified"})
    crm.add(cfg.PROSPECT, {"id": "p-disq", "businessName": "Never", "leadStatus": "Disqualified", "phone": "8"})
    crm.add(cfg.PROSPECT, {"id": "p-exit", "businessName": "Gone", "leadStatus": "Qualified", "phone": "2", "sideExit": "Do Not Contact"})
    crm.add(cfg.PROSPECT, {"id": "p-declined", "businessName": "Said no", "leadStatus": "Qualified", "phone": "3"})
    crm.add(cfg.TOUCH, {"channel": "Call", "touchStatus": "Done", "outcome": "Declined", "prospectId": "p-declined"})
    crm.add("Contact", {"id": "c-ok", "name": "Pat Prospect", "cContactType": ["Prospect"], "cFunnelStage": "Prospect",
                        "phoneNumber": "216-555-0102", "doNotCall": False, "phoneNumberIsOptedOut": False})
    crm.add("Contact", {"id": "c-dnc", "name": "Dee", "cContactType": ["Prospect"], "cFunnelStage": "Prospect",
                        "phoneNumber": "4", "doNotCall": True})
    crm.add("Contact", {"id": "c-out", "name": "Otto", "cContactType": ["Prospect"], "cFunnelStage": "Prospect",
                        "phoneNumber": "5", "phoneNumberIsOptedOut": True})
    crm.add("Contact", {"id": "c-client", "name": "Cli", "cContactType": ["Client"], "cFunnelStage": "Prospect", "phoneNumber": "6"})
    # A Contact whose lead stopped being worked stopped with it.
    crm.add("Contact", {"id": "c-left", "name": "Left", "cContactType": ["Prospect"], "cFunnelStage": "Prospect", "phoneNumber": "7"})
    crm.add(cfg.PROSPECT, {"id": "p-left", "businessName": "Left Co", "leadStatus": "Converted",
                           "sideExit": "Do Not Contact", "promotedContactId": "c-left"})


def test_call_selection_applies_every_term():
    crm = FakeCrm()
    _seed_callable(crm)
    # The default (ruling 44): Unqualified and Qualified leads, no Contacts.
    targets = run(calls.select_targets(crm, None))
    assert {(t["key"], t["phone"], t["stage"]) for t in targets} == {
        ("prospect:p-phone", "216-555-0101", "Qualified"), ("prospect:p-unq", "216-555-0109", "Unqualified")}
    both = run(calls.select_targets(crm, {"statuses": ["Qualified"], "stages": ["Prospect"]}))
    assert {t["key"] for t in both} == {"prospect:p-phone", "contact:c-ok"}
    # A retired word is dropped from the rule.
    assert calls.normalise_rule({"stages": ["Unverified", "Lead"]}) == {"statuses": ["Unqualified", "Qualified"], "stages": []}


def test_call_build_and_sign_off_start_the_list_and_record_its_size():
    crm = FakeCrm()
    _seed_callable(crm)
    camp = crm.add(cfg.CAMPAIGN, {"name": "Chamber calls", "campaignKind": "Call", "campaignStatus": "Draft"})
    built = run(calls.build_list(crm, crm, camp, {"statuses": ["Qualified", "Unqualified"], "stages": ["Prospect"]}))
    assert built["pieces"] == 3 and built["created"] == 3
    camp = crm.rows[cfg.CAMPAIGN][camp["id"]]
    assert camp["campaignStatus"] == "Awaiting sign-off" and "phone" in camp["selectionSummary"]
    assert camp["selectionSummary"].startswith("Leads at Qualified or Unqualified and Contacts typed Prospect at Prospect")
    assert {t["channel"] for t in crm.rows[cfg.TOUCH].values() if t.get("outreachCampaignId") == camp["id"]} == {"Call"}
    signed = run(calls.sign_off(crm, crm, camp, user_name="Mark"))
    assert signed["campaignStatus"] == "Running" and signed["signedOffByName"] == "Mark"
    assert signed["pieceCount"] == 3                                   # the list's size (M9)
    with pytest.raises(service.CampaignError):
        run(calls.build_list(crm, crm, signed, None))                   # running: no rebuild


def _running_call_campaign(crm, *, teams=None):
    camp = crm.add(cfg.CAMPAIGN, {"name": "Chamber calls", "campaignKind": "Call", "campaignStatus": "Running",
                                  "description": "<p>Offer a free first session.</p>",
                                  "teamsNames": teams or {}})
    for n, name in ((1, "Phone Shop"), (2, "Two Shop"), (3, "Three Shop")):
        crm.add(cfg.PROSPECT, {"id": f"p{n}", "name": name, "businessName": name, "leadStatus": "Qualified",
                               "phone": f"216-555-010{n}", "mailingAddressStreet": f"{n} Main St",
                               "mailingAddressCity": "Cleveland", "mailingAddressState": "OH",
                               "mailingAddressPostalCode": "44113"})
    for n in (1, 2, 3):
        crm.add(cfg.TOUCH, {"id": f"t{n}", "name": f"Chamber calls — Shop {n}", "channel": "Call", "touchStatus": "Planned",
                            "outreachCampaignId": camp["id"], "prospectId": f"p{n}"})
    return camp


def test_calls_screen_follows_the_campaigns_teams():
    crm = FakeCrm()
    _running_call_campaign(crm, teams={"t-m": "Mentor Team"})
    settings = _settings()
    as_mentor = run(calls.call_list(crm, crm, MENTOR, settings))
    assert len(as_mentor["rows"]) == 3 and as_mentor["rows"][0]["phone"].startswith("216-555")
    assert as_mentor["rows"][0]["business"] is True and as_mentor["rows"][0]["hasEmail"] is False
    assert as_mentor["rows"][0]["email"] == "" and as_mentor["rows"][0]["website"] == ""
    assert "never contacted" in as_mentor["warning"]
    outsider = run(calls.call_list(crm, crm, OUTSIDER, settings))
    assert outsider["rows"] == [] and "Mentor Team" in outsider["message"]
    # A campaign naming no team is the Marketing Admin Team's.
    crm2 = FakeCrm()
    _running_call_campaign(crm2)
    assert run(calls.call_list(crm2, crm2, MENTOR, settings))["rows"] == []
    assert len(run(calls.call_list(crm2, crm2, MARKETING, settings))["rows"]) == 3


def test_assigned_rows_show_only_to_their_caller():
    crm = FakeCrm()
    _running_call_campaign(crm, teams={"t-m": "Mentor Team"})
    crm.rows[cfg.TOUCH]["t1"]["assignedUserId"] = "someone-else"
    rows = run(calls.call_list(crm, crm, MENTOR, _settings()))["rows"]
    assert sorted(r["touchId"] for r in rows) == ["t2", "t3"]


def test_outcomes_write_the_touch_as_the_caller_and_the_consequences_as_the_api():
    api, user = FakeCrm(), FakeCrm()
    camp = _running_call_campaign(api, teams={"t-m": "Mentor Team"})
    user.rows = api.rows                                      # one CRM, two credentials
    settings = _settings()
    # No answer + Call again: Done, and a fresh Planned row for the same lead.
    r1 = run(calls.record_outcome(api, user, MENTOR, "t1", outcome="No answer", notes="voicemail",
                                  call_again=True, settings=settings))
    t1 = api.rows[cfg.TOUCH]["t1"]
    assert t1["touchStatus"] == "Done" and t1["outcome"] == "No answer" and t1["callNotes"] == "voicemail"
    assert t1["calledPhone"] == "216-555-0101" and t1["stageAtTouch"] == "Qualified"
    assert ("COutreachTouch", "t1") == user.updated[0][:2]                       # the caller's write
    assert "planned again" in r1["consequences"]
    fresh = [t for t in api.rows[cfg.TOUCH].values() if t.get("prospectId") == "p1" and t["touchStatus"] == "Planned"]
    assert len(fresh) == 1
    # Interested with an email (ruling 47): the lead converts — a Company from
    # the lead and the Contact linked to it (ruling 52), under the API client.
    r2 = run(calls.record_outcome(api, user, MENTOR, "t2", outcome="Interested", notes="", call_again=False,
                                  settings=settings, details=Details(email="ann@two.example", first_name="Ann")))
    lead = api.rows[cfg.PROSPECT]["p2"]
    assert lead["leadStatus"] == "Converted" and "lead converted" in r2["consequences"]
    company = api.rows["Account"][lead["promotedCompanyId"]]
    contact = api.rows["Contact"][lead["promotedContactId"]]
    assert company["name"] == "Two Shop" and company["cCompanyType"] == ["Prospect"] and company["cFunnelStage"] == "Prospect"
    assert contact["accountId"] == company["id"] and contact["firstName"] == "Ann"
    assert company["cOutreachCampaignId"] == camp["id"]
    # The touch names what the call made, so Converted can be counted from it.
    t2 = api.rows[cfg.TOUCH]["t2"]
    assert t2["contactId"] == contact["id"] and t2["companyId"] == company["id"]
    assert reporting.call_conversions(api.rows[cfg.TOUCH].values()) == 1
    # Declined: Done, and the lead stops being worked by Declined.
    run(calls.record_outcome(api, user, MENTOR, "t3", outcome="Declined", notes="", call_again=False, settings=settings))
    assert api.rows[cfg.PROSPECT]["p3"]["sideExit"] == "Declined"
    # A recorded call is never recorded twice.
    with pytest.raises(service.CampaignError):
        run(calls.record_outcome(api, user, MENTOR, "t3", outcome="Interested", notes="", call_again=False, settings=settings))
    # The campaign completes only when its last Planned row is recorded.
    assert api.rows[cfg.CAMPAIGN][camp["id"]]["campaignStatus"] == "Running"
    fresh_id = fresh[0]["id"]
    run(calls.record_outcome(api, user, MENTOR, fresh_id, outcome="No answer", notes="", call_again=False, settings=settings))
    assert api.rows[cfg.CAMPAIGN][camp["id"]]["campaignStatus"] == "Complete"


def test_interested_without_an_email_or_website_keeps_the_lead_and_may_call_again():
    """Ruling 47: Interested is recorded, the lead stays a lead, the screen says
    why, and Call again is offered as for No answer."""
    api = FakeCrm()
    _running_call_campaign(api, teams={"t-m": "Mentor Team"})
    out = run(calls.record_outcome(api, api, MENTOR, "t1", outcome="Interested", notes="call back Tuesday",
                                   call_again=True, settings=_settings()))
    assert api.rows[cfg.TOUCH]["t1"]["outcome"] == "Interested"
    assert api.rows[cfg.PROSPECT]["p1"]["leadStatus"] == "Qualified"
    assert "stays a lead" in out["notConverted"] and "planned again" in out["consequences"]
    assert not api.rows.get("Account") and not api.rows.get("Contact")


def test_interested_on_a_lead_that_already_holds_a_website_converts_it():
    api = FakeCrm()
    _running_call_campaign(api, teams={"t-m": "Mentor Team"})
    api.rows[cfg.PROSPECT]["p1"]["website"] = "phoneshop.example"
    out = run(calls.record_outcome(api, api, MENTOR, "t1", outcome="Interested", notes="", call_again=True,
                                   settings=_settings()))
    assert api.rows[cfg.PROSPECT]["p1"]["leadStatus"] == "Converted"
    assert "planned again" not in out["consequences"]                 # a converted lead is not called again
    assert any("no second call" in w for w in out["warnings"])


def test_interested_with_a_conflicting_company_records_the_call_and_converts_nothing():
    api = FakeCrm()
    _running_call_campaign(api, teams={"t-m": "Mentor Team"})
    api.add("Account", {"name": "Phone Shop", "website": "other.example", "billingAddressPostalCode": "44113"})
    out = run(calls.record_outcome(api, api, MENTOR, "t1", outcome="Interested", notes="", call_again=False,
                                   settings=_settings(), details=Details(website="phoneshop.example")))
    assert api.rows[cfg.TOUCH]["t1"]["outcome"] == "Interested"
    assert api.rows[cfg.PROSPECT]["p1"]["leadStatus"] == "Qualified"
    assert "different web address" in out["notConverted"]


def test_outcome_refusals():
    api = FakeCrm()
    _running_call_campaign(api, teams={"t-m": "Mentor Team"})
    s = _settings()
    with pytest.raises(PermissionError):
        run(calls.record_outcome(api, api, OUTSIDER, "t1", outcome="No answer", notes="", call_again=False, settings=s))
    with pytest.raises(service.CampaignError):
        run(calls.record_outcome(api, api, MENTOR, "t1", outcome="Declined", notes="", call_again=True, settings=s))
    with pytest.raises(service.CampaignError):
        run(calls.record_outcome(api, api, MENTOR, "t1", outcome="Maybe", notes="", call_again=False, settings=s))
    assert api.rows[cfg.TOUCH]["t1"]["touchStatus"] == "Planned"               # nothing written


def test_declined_never_overwrites_another_reason():
    api = FakeCrm()
    _running_call_campaign(api, teams={"t-m": "Mentor Team"})
    api.rows[cfg.PROSPECT]["p1"]["sideExit"] = "Do Not Contact"
    out = run(calls.record_outcome(api, api, MENTOR, "t1", outcome="Declined", notes="", call_again=False, settings=_settings()))
    assert api.rows[cfg.PROSPECT]["p1"]["sideExit"] == "Do Not Contact"
    assert out["warnings"] and api.rows[cfg.TOUCH]["t1"]["outcome"] == "Declined"


def test_calls_routes_are_dark_until_switched_on_and_need_no_campaigns_team(monkeypatch):
    crm = FakeCrm()
    _running_call_campaign(crm, teams={"t-m": "Mentor Team"})
    off = build(monkeypatch, user=MENTOR, crm=crm, store=FakeStore())
    assert off.get("/campaigns/api/calls/session").status_code == 404
    monkeypatch.setenv("CAMPAIGNS_CALLS", "true")
    client = build(monkeypatch, user=MENTOR, crm=crm, store=FakeStore())
    assert client.get("/campaigns/api/calls/session").json()["campaignsTeam"] is False
    # Ruling 114: the page opens for the caller, on the Calls tab alone.
    body = client.get("/campaigns/api/session").json()
    assert body["callerOnly"] is True and body["callsOn"] is True
    import campaigns.router as router_mod
    monkeypatch.setattr(router_mod, "_api_client", lambda settings, request: crm)
    rows = client.get("/campaigns/api/calls").json()["rows"]
    assert len(rows) == 3
    bad = client.post("/campaigns/api/calls/t2/outcome", json={"outcome": "Interested", "email": "not-an-email"})
    assert bad.status_code == 400 and "not an email address" in bad.json()["detail"]
    done = client.post("/campaigns/api/calls/t1/outcome", json={"outcome": "Interested", "email": "pat@phone.example",
                                                                "firstName": "Pat"})
    assert done.status_code == 200 and crm.rows[cfg.PROSPECT]["p1"]["leadStatus"] == "Converted"
    assert client.post("/campaigns/api/calls/t1/outcome", json={"outcome": "Interested"}).status_code == 400


def test_the_call_kind_is_offered_only_with_the_switch(monkeypatch):
    crm = FakeCrm()
    with pytest.raises(service.CampaignError):
        run(service.create_campaign(crm, {"name": "Calls", "campaignKind": "Call"}, user_id="u-1"))
    made = run(service.create_campaign(crm, {"name": "Calls", "campaignKind": "Call"}, user_id="u-1", calls_on=True))
    assert made["campaignKind"] == "Call" and made["campaignStatus"] == "Draft"
    assert service.manual_moves({"campaignKind": "Call", "campaignStatus": "Running"}) == ("Complete", "Cancelled")


# --- 4. the Stale sweep (§ 1.2, § 6; ruling 44) -----------------------------------------------------

def test_stale_plan_reads_the_window_and_skips_active_leads():
    crm = FakeCrm()
    now = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
    old = _crm_time(now - timedelta(days=200))
    recent = _crm_time(now - timedelta(days=10))
    crm.add(cfg.PROSPECT, {"id": "old", "name": "Old", "leadStatus": "Qualified", "leadStatusChangedAt": old, "createdAt": old})
    crm.add(cfg.PROSPECT, {"id": "old-unq", "name": "Old U", "leadStatus": "Unqualified", "createdAt": old})
    crm.add(cfg.PROSPECT, {"id": "fresh", "name": "Fresh", "leadStatus": "Qualified", "leadStatusChangedAt": recent, "createdAt": old})
    crm.add(cfg.PROSPECT, {"id": "touched", "name": "Touched", "leadStatus": "Qualified", "createdAt": old})
    crm.add(cfg.TOUCH, {"prospectId": "touched", "touchStatus": "Sent", "sentAt": recent})
    # A scan changes no status (ruling 51) but is still a sign of life.
    crm.add(cfg.PROSPECT, {"id": "scanned", "name": "Scanned", "leadStatus": "Unqualified", "createdAt": old})
    crm.add(cfg.TOUCH, {"prospectId": "scanned", "touchStatus": "Delivered", "sentAt": old, "firstScannedAt": recent})
    crm.add(cfg.PROSPECT, {"id": "planned", "name": "Planned", "leadStatus": "Qualified", "createdAt": old})
    crm.add(cfg.TOUCH, {"prospectId": "planned", "touchStatus": "Planned", "plannedAt": old})
    crm.add(cfg.PROSPECT, {"id": "conv", "name": "Converted", "leadStatus": "Converted", "createdAt": old})
    crm.add(cfg.PROSPECT, {"id": "disq", "name": "Disqualified", "leadStatus": "Disqualified", "createdAt": old})
    crm.add(cfg.PROSPECT, {"id": "exited", "name": "Exited", "leadStatus": "Qualified", "sideExit": "Declined", "createdAt": old})
    plan = run(stale.plan_stale(crm, 180, now=now))
    assert sorted(r["id"] for r in plan) == ["old", "old-unq"]
    # PROSPECT_STALE_DAYS=0 (the live check): every untouched lead still being worked.
    zero = run(stale.plan_stale(crm, 0, now=now))
    assert sorted(r["id"] for r in zero) == ["fresh", "old", "old-unq", "scanned", "touched"]
    text = stale.plan_text(plan, 180)
    assert "2 would stop being worked as Stale" in text and text == stale.plan_text(run(stale.plan_stale(crm, 180, now=now)), 180)


def test_stale_apply_never_overwrites_and_rereads_each_lead():
    crm = FakeCrm()
    crm.add(cfg.PROSPECT, {"id": "a", "leadStatus": "Qualified"})
    crm.add(cfg.PROSPECT, {"id": "b", "leadStatus": "Qualified", "sideExit": "Do Not Contact"})
    crm.add(cfg.PROSPECT, {"id": "c", "leadStatus": "Converted"})
    totals = run(stale.apply_stale(crm, [{"id": "a"}, {"id": "b"}, {"id": "c"}], 180))
    assert totals == {"stale": 1, "skipped": 2, "errors": 0}
    assert crm.rows[cfg.PROSPECT]["a"]["sideExit"] == "Stale"
    assert crm.rows[cfg.PROSPECT]["b"]["sideExit"] == "Do Not Contact"


def test_stale_sweep_is_registered_as_a_dry_run_then_apply_job():
    from setup.jobs import BY_KEY
    job = BY_KEY["prospect_stale"]
    assert job.mutating and job.runnable


def test_worker_sweep_does_nothing_while_campaigns_are_off():
    crm = FakeCrm()
    crm.add(cfg.PROSPECT, {"id": "a", "leadStatus": "Unqualified", "createdAt": "2020-01-01 00:00:00"})
    out = run(stale.run_stale_sweep(_settings(), client=crm))
    assert out["stale"] == 0 and crm.updated == []
    on = run(stale.run_stale_sweep(_settings(campaigns_enabled=True), client=crm))
    assert on["stale"] == 1


# --- 5. the reporting numbers and the Analytics reads (§ 6; ruling 46) ---------------------------

def test_touches_by_campaign_matches_the_record_pages_summary():
    crm = FakeCrm()
    a = crm.add(cfg.CAMPAIGN, {"name": "Cards", "campaignKind": "Postcard", "campaignStatus": "Complete"})
    b = crm.add(cfg.CAMPAIGN, {"name": "Calls", "campaignKind": "Call", "campaignStatus": "Running"})
    crm.add(cfg.CAMPAIGN, {"name": "Social", "campaignKind": "Social media", "campaignStatus": "Running"})
    crm.add(cfg.TOUCH, {"outreachCampaignId": a["id"], "touchStatus": "Delivered", "stageAtTouch": "Qualified", "scanCount": 1})
    crm.add(cfg.TOUCH, {"outreachCampaignId": a["id"], "touchStatus": "Returned", "stageAtTouch": "Unqualified"})
    crm.add(cfg.TOUCH, {"outreachCampaignId": b["id"], "touchStatus": "Done", "outcome": "Interested", "stageAtTouch": "Qualified",
                        "prospectId": "p1", "contactId": "c1"})
    crm.add(cfg.TOUCH, {"outreachCampaignId": b["id"], "touchStatus": "Done", "outcome": "Interested", "stageAtTouch": "Prospect",
                        "contactId": "c2"})
    crm.add(cfg.TOUCH, {"outreachCampaignId": b["id"], "touchStatus": "Planned"})
    data = {r["name"]: r for r in run(reporting.touches_by_campaign(crm))}
    assert set(data) == {"Cards", "Calls"}                                   # social media selects nobody
    assert data["Cards"]["delivered"] == 1 and data["Cards"]["returned"] == 1 and data["Cards"]["scanned"] == 1
    assert data["Cards"]["stageAtTouch"] == {"Unqualified": 1, "Qualified": 1} and data["Cards"]["responded"] is None
    assert data["Calls"]["Interested"] == 2 and data["Calls"]["planned"] == 1 and data["Calls"]["done"] == 2
    # Only the call on a lead that made a Contact is a conversion.
    assert data["Calls"]["callConversions"] == 1 and data["Calls"]["became"] is None
    touches = run(service.campaign_touches(crm, a["id"]))
    assert {k: data["Cards"][k] for k in service.touch_summary(touches)} == service.touch_summary(touches)


def test_the_three_response_counts_of_ruling_46():
    rows = [
        {"id": "1", "form_slug": "prospect-response", "status": "delivered", "result": {"leadConverted": True}},
        {"id": "2", "form_slug": "client-intake", "status": "delivered",
         "result": {"engagementId": "e1", "leadId": "l1"}},
        {"id": "3", "form_slug": "info-request", "status": "delivered", "result": {"contactId": "c1"}},
        {"id": "4", "form_slug": "partner", "status": "discarded", "result": {"partnerProfileId": "pp"}},
    ]
    out = reporting.summarize_responses(rows)
    assert (out["responded"], out["converted"], out["became"]) == (3, 2, 1)


def test_leads_by_source_counts_each_source_by_status():
    crm = FakeCrm()
    crm.add(cfg.PROSPECT, {"leadSource": "State filing", "leadStatus": "Qualified"})
    crm.add(cfg.PROSPECT, {"leadSource": "State filing", "leadStatus": "Unqualified"})
    crm.add(cfg.PROSPECT, {"leadSource": "List", "leadStatus": "Unqualified"})
    crm.add(cfg.PROSPECT, {"leadSource": "Mentor request", "leadStatus": "Converted"})
    rows = {r["source"]: r for r in run(reporting.leads_by_source(crm))}
    assert rows["State filing"]["Qualified"] == 1 and rows["State filing"]["total"] == 2
    assert rows["List"]["Unqualified"] == 1
    assert rows["Mentor request"]["Converted"] == 1 and rows["Email"]["total"] == 0


def test_the_campaigns_analytics_page_and_its_metrics_are_registered():
    import analytics  # noqa: F401 — registers
    from analytics.registry import MetricContext, get_metric, get_page
    page = get_page("campaigns")
    assert page is not None and [p.metric_key for p in page.panels] == ["prospect_funnel", "campaign_touches", "prospect_entry_rungs"]
    crm = FakeCrm()
    crm.add(cfg.PROSPECT, {"leadSource": "List", "leadStatus": "Unqualified"})
    result = run(get_metric("prospect_entry_rungs").compute(MetricContext(settings=_settings(), espo=crm)))
    assert result.error is None and result.data["rows"][1]["Unqualified"] == 1
    gone = run(get_metric("campaign_touches").compute(MetricContext(settings=_settings(), espo=FakeCrm(with_entities=False))))
    assert gone.error and "CProspect" in gone.error


def test_a_call_campaign_names_its_callers_through_its_teams(monkeypatch):
    crm = FakeCrm()
    camp = crm.add(cfg.CAMPAIGN, {"name": "Calls", "campaignKind": "Call", "campaignStatus": "Draft"})
    crm.add(cfg.CAMPAIGN, {"id": "cards", "name": "Cards", "campaignKind": "Postcard", "campaignStatus": "Draft"})
    client = build(monkeypatch, user=MARKETING, crm=crm, store=FakeStore())
    ok = client.put(f"/campaigns/api/campaigns/{camp['id']}/teams", json={"teamIds": ["t-m", "t-m", ""]})
    assert ok.status_code == 200 and crm.rows[cfg.CAMPAIGN][camp["id"]]["teamsIds"] == ["t-m"]
    assert client.put("/campaigns/api/campaigns/cards/teams", json={"teamIds": ["t-m"]}).status_code == 400


def test_a_call_record_carries_its_campaigns_teams_before_the_caller_writes_it():
    """Assignment Permission *team* (the Mentor Role) refuses a save of a record
    with neither a team nor an assigned user (found on the Phase 3 pass,
    10-18-26): the API client stamps the campaign's teams first."""
    api, user = FakeCrm(), FakeCrm()
    camp = _running_call_campaign(api, teams={"t-m": "Mentor Team"})
    api.rows[cfg.CAMPAIGN][camp["id"]]["teamsIds"] = ["t-m"]
    user.rows = api.rows
    run(calls.record_outcome(api, user, MENTOR, "t1", outcome="No answer", notes="", call_again=True, settings=_settings()))
    assert ("COutreachTouch", "t1", {"teamsIds": ["t-m"]}) in api.updated
    assert api.updated.index(("COutreachTouch", "t1", {"teamsIds": ["t-m"]})) == 0   # before the caller's write
    fresh = [t for t in api.rows[cfg.TOUCH].values() if t.get("prospectId") == "p1" and t["touchStatus"] == "Planned"]
    assert fresh[0]["teamsIds"] == ["t-m"]
    # Already carrying the teams: nothing more is written.
    assert run(calls.ensure_touch_teams(api, "t1", ["t-m"])) is False


def test_build_list_stamps_new_call_records_with_the_campaigns_teams():
    crm = FakeCrm()
    crm.add(cfg.PROSPECT, {"id": "p-phone", "businessName": "Phone Shop", "leadStatus": "Qualified", "phone": "1"})
    camp = crm.add(cfg.CAMPAIGN, {"name": "Calls", "campaignKind": "Call", "campaignStatus": "Draft", "teamsIds": ["t-m"]})
    run(calls.build_list(crm, crm, camp, None))
    touch, = [t for t in crm.rows[cfg.TOUCH].values()]
    assert touch["teamsIds"] == ["t-m"]


def test_a_teams_write_refused_for_the_linked_team_is_retried_as_the_admin():
    """Found on the lead model's live pass (F1, 10-19-26): the Marketing Admin
    Role cannot read Teams, so linking one to a call campaign is refused; the
    write is retried as the admin account. Any other refusal is raised."""
    from core.espo import EspoError
    user, admin = FakeCrm(), FakeCrm()
    camp = user.add(cfg.CAMPAIGN, {"name": "Calls", "campaignKind": "Call", "campaignStatus": "Draft"})
    admin.rows = user.rows

    async def refuse(entity, record_id, payload):
        raise EspoError('update COutreachCampaign failed: HTTP 403 {"reason":"cannotRelateForbidden",'
                        '"data":{"foreignEntityType":"Team","action":"read"}}')
    user.update = refuse

    async def factory():
        return admin
    run(service.set_teams(user, camp["id"], ["t-m", "t-m"], admin_factory=factory))
    assert admin.updated == [(cfg.CAMPAIGN, camp["id"], {"teamsIds": ["t-m"]})]
    with pytest.raises(EspoError):
        run(service.set_teams(user, camp["id"], ["t-m"]))                  # no admin: raised

    async def other(entity, record_id, payload):
        raise EspoError("update COutreachCampaign failed: HTTP 403 Forbidden")
    user.update = other
    with pytest.raises(EspoError):
        run(service.set_teams(user, camp["id"], ["t-m"], admin_factory=factory))


def test_the_call_screen_offers_the_leads_own_email_and_a_cancel():
    crm = FakeCrm()
    _running_call_campaign(crm, teams={"t-m": "Mentor Team"})
    crm.rows[cfg.PROSPECT]["p1"]["email"] = "owner@phone.example"
    row = next(r for r in run(calls.call_list(crm, crm, MENTOR, _settings()))["rows"] if r["touchId"] == "t1")
    assert row["email"] == "owner@phone.example" and row["hasEmail"] is True
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "campaigns" / "frontend" / "calls.js").read_text()
    assert '["email", "Email", r.email || ""]' in js and '"Cancel"' in js
