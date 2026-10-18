"""Campaign Management, Phase 3 (prds/prospect-marketing/build-plan.md § 7):
the list import, the review, the call kind, the Stale sweep and the two
Analytics reads.

The boundaries tested: the list door enters Unverified and still promotes; each
review action applies only where the rules say and never writes a side exit
over another; the call selection's six terms; the Calls screen's gate is the
campaign's teams (ruling 36) and the touch is written as the caller while the
rung and the exit are the API client's; the Stale sweep's window and its
deterministic plan; the reporting numbers the record page and Analytics share.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from campaigns import calls, imports, reporting, review, service, stale
from campaigns import config as cfg
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


# --- 1. the list import (§ 2.3) ---------------------------------------------------------------

LIST_CSV = (
    "business_name,mailing_street,mailing_city,mailing_state,mailing_zip,email,website,phone\n"
    "Phone Shop,1 Main St,Cleveland,OH,44113,,,216-555-0101\n"
    "Mail Shop,2 Main St,Cleveland,OH,44113,owner@mail-shop.example,,\n"
    "Web Shop,3 Main St,Cleveland,OH,44113,,webshop.example,\n"
)


def test_list_import_enters_unverified_and_still_promotes_identity():
    crm, store = FakeCrm(), FakeStore()
    plan = run(imports.plan_import(crm, store, text=LIST_CSV, name="Chamber list", door=cfg.DOOR_LIST,
                                   qualified_by="", list_source="Lorain Chamber"))
    assert plan["counts"]["create"] == 3
    run(imports.apply_import(crm, crm, store, run(store.get_batch(plan["batchId"])), user_name="Mark"))
    prospects = list(crm.rows[cfg.PROSPECT].values())
    assert {p["funnelStage"] for p in prospects} == {"Unverified"}
    assert {p["entryStage"] for p in prospects} == {"Unverified"}
    assert {p["entryDoor"] for p in prospects} == {"List"}
    assert all(p["importBatch"].startswith("Lorain Chamber — ") for p in prospects)
    assert not any(p.get("qualifiedBy") for p in prospects)          # the review stamps it
    # Identity is separate from fit: the email and the website still promote.
    contact, = crm.rows["Contact"].values()
    company, = crm.rows["Account"].values()
    assert contact["cContactType"] == ["Prospect"] and contact["cFunnelStage"] == "Unverified"
    assert company["cCompanyType"] == ["Prospect"] and company["cEntryStage"] == "Unverified"


# --- 2. the review (§ 2.3, § 3.8; rulings 18, 29) -------------------------------------------------

def _p(**kw):
    return {"id": "p1", "name": "Acme", "businessName": "Acme", "funnelStage": "Unverified",
            "entryStage": "Unverified", "sideExit": None, **kw}


def test_qualify_moves_unverified_to_qualified_and_stamps_the_reviewer():
    user, api = review.plan_action(_p(), review.ACTION_QUALIFY, reviewer="Mark Marketing", note="Called them")
    assert user["funnelStage"] == "Qualified" and user["qualifiedBy"] == "Mark Marketing"
    assert user["qualifiedAt"] and user["stageChangedAt"] == user["qualifiedAt"]
    assert "Called them" in user["description"] and api == {}
    with pytest.raises(service.CampaignError):
        review.plan_action(_p(funnelStage="Qualified"), review.ACTION_QUALIFY, reviewer="M")


def test_unqualified_needs_a_note_and_names_the_reviewer():
    with pytest.raises(service.CampaignError) as exc:
        review.plan_action(_p(), review.ACTION_UNQUALIFY, reviewer="Mark", note="  ")
    assert "required" in str(exc.value)
    user, _ = review.plan_action(_p(), review.ACTION_UNQUALIFY, reviewer="Mark", note="A franchise")
    assert user["sideExit"] == "Unqualified" and user["sideExitNote"] == "A franchise — reviewed by Mark"
    assert "funnelStage" not in user                                  # Unverified stays the rung (ruling 29)


@pytest.mark.parametrize("action", [review.ACTION_QUALIFY, review.ACTION_UNQUALIFY, review.ACTION_DO_NOT_CONTACT])
def test_no_side_exit_is_written_over_another(action):
    with pytest.raises(service.CampaignError) as exc:
        review.plan_action(_p(sideExit="Stale"), action, reviewer="Mark", note="x")
    assert "Stale" in str(exc.value)


def test_do_not_contact_applies_to_any_rung():
    user, _ = review.plan_action(_p(funnelStage="Lead"), review.ACTION_DO_NOT_CONTACT, reviewer="Mark")
    assert user["sideExit"] == "Do Not Contact" and "Mark" in user["sideExitNote"]


def test_not_the_same_company_clears_already_known_and_its_link_under_the_api_client():
    crm, api = FakeCrm(), FakeCrm()
    p = crm.add(cfg.PROSPECT, _p(id="p9", funnelStage="Qualified", entryStage="Qualified",
                                 sideExit="Already known", sideExitNote="Matched Acme Inc by website at import.",
                                 alreadyKnownCompanyId="acc-1", alreadyKnownCompanyName="Acme Inc"))
    out = run(review.apply_action(crm, api, p, review.ACTION_NOT_SAME_COMPANY, reviewer="Mark", note="Different owner"))
    assert crm.updated[-1][2]["sideExit"] is None and "Acme Inc" in crm.updated[-1][2]["description"]
    assert api.updated == [(cfg.PROSPECT, "p9", {"alreadyKnownCompanyId": None})]
    assert "alreadyKnownCompanyId" in out["written"]
    with pytest.raises(service.CampaignError):
        review.plan_action(_p(sideExit="Stale"), review.ACTION_NOT_SAME_COMPANY, reviewer="Mark")


def test_review_route_writes_and_refuses_with_a_readable_400(monkeypatch):
    crm = FakeCrm()
    crm.add(cfg.PROSPECT, _p(id="p1"))
    client = build(monkeypatch, user=MARKETING, crm=crm, store=FakeStore())
    ok = client.post("/campaigns/api/prospects/p1/review", json={"action": "qualify", "note": ""})
    assert ok.status_code == 200 and crm.rows[cfg.PROSPECT]["p1"]["funnelStage"] == "Qualified"
    again = client.post("/campaigns/api/prospects/p1/review", json={"action": "unqualify", "note": "no"})
    assert again.status_code == 400 and "Unverified" in again.json()["detail"]
    assert client.post("/campaigns/api/prospects/p1/review", json={"action": "delete"}).status_code == 400


# --- 3. the call kind (§ 3.4; ruling 36) -------------------------------------------------------------

def _seed_callable(crm):
    crm.add(cfg.PROSPECT, {"id": "p-phone", "businessName": "Phone Shop", "funnelStage": "Qualified", "phone": "216-555-0101"})
    crm.add(cfg.PROSPECT, {"id": "p-nophone", "businessName": "No Phone", "funnelStage": "Qualified"})
    crm.add(cfg.PROSPECT, {"id": "p-unverified", "businessName": "Unreviewed", "funnelStage": "Unverified", "phone": "1"})
    crm.add(cfg.PROSPECT, {"id": "p-exit", "businessName": "Gone", "funnelStage": "Qualified", "phone": "2", "sideExit": "Do Not Contact"})
    crm.add(cfg.PROSPECT, {"id": "p-declined", "businessName": "Said no", "funnelStage": "Qualified", "phone": "3"})
    crm.add(cfg.TOUCH, {"channel": "Call", "touchStatus": "Done", "outcome": "Declined", "prospectId": "p-declined"})
    crm.add("Contact", {"id": "c-ok", "name": "Pat Prospect", "cContactType": ["Prospect"], "cFunnelStage": "Qualified",
                        "phoneNumber": "216-555-0102", "doNotCall": False, "phoneNumberIsOptedOut": False})
    crm.add("Contact", {"id": "c-dnc", "name": "Dee", "cContactType": ["Prospect"], "cFunnelStage": "Qualified",
                        "phoneNumber": "4", "doNotCall": True})
    crm.add("Contact", {"id": "c-out", "name": "Otto", "cContactType": ["Prospect"], "cFunnelStage": "Qualified",
                        "phoneNumber": "5", "phoneNumberIsOptedOut": True})
    crm.add("Contact", {"id": "c-client", "name": "Cli", "cContactType": ["Client"], "cFunnelStage": "Qualified", "phoneNumber": "6"})
    # A promoted record is its Contact: one row, the Contact's number, the record's as fallback.
    crm.add("Contact", {"id": "c-promoted", "name": "Promo Person", "cContactType": ["Prospect"], "cFunnelStage": "Qualified"})
    crm.add(cfg.PROSPECT, {"id": "p-promoted", "businessName": "Promo Co", "funnelStage": "Qualified",
                           "phone": "216-555-0103", "promotedContactId": "c-promoted"})
    # A Contact whose prospect record left the ladder left with it.
    crm.add("Contact", {"id": "c-left", "name": "Left", "cContactType": ["Prospect"], "cFunnelStage": "Qualified", "phoneNumber": "7"})
    crm.add(cfg.PROSPECT, {"id": "p-left", "businessName": "Left Co", "funnelStage": "Lead",
                           "sideExit": "Do Not Contact", "promotedContactId": "c-left"})


def test_call_selection_applies_every_term():
    crm = FakeCrm()
    _seed_callable(crm)
    targets = run(calls.select_targets(crm, {"stages": ["Qualified"]}))
    got = {(t["key"], t["phone"]) for t in targets}
    assert got == {("prospect:p-phone", "216-555-0101"), ("contact:c-ok", "216-555-0102"),
                   ("contact:c-promoted", "216-555-0103")}
    # Unverified is never callable, whatever the rule asks.
    assert calls.normalise_rule({"stages": ["Unverified"]}) == {"stages": ["Qualified"]}


def test_call_build_and_sign_off_start_the_list_without_a_piece_count():
    crm = FakeCrm()
    _seed_callable(crm)
    camp = crm.add(cfg.CAMPAIGN, {"name": "Chamber calls", "campaignKind": "Call", "campaignStatus": "Draft"})
    built = run(calls.build_list(crm, crm, camp, {"stages": ["Qualified"]}))
    assert built["pieces"] == 3 and built["created"] == 3
    camp = crm.rows[cfg.CAMPAIGN][camp["id"]]
    assert camp["campaignStatus"] == "Awaiting sign-off" and "phone" in camp["selectionSummary"]
    assert {t["channel"] for t in crm.rows[cfg.TOUCH].values() if t.get("outreachCampaignId") == camp["id"]} == {"Call"}
    signed = run(calls.sign_off(crm, crm, camp, user_name="Mark"))
    assert signed["campaignStatus"] == "Running" and signed["signedOffByName"] == "Mark"
    assert "pieceCount" not in signed
    with pytest.raises(service.CampaignError):
        run(calls.build_list(crm, crm, signed, None))                   # running: no rebuild


def _running_call_campaign(crm, *, teams=None):
    camp = crm.add(cfg.CAMPAIGN, {"name": "Chamber calls", "campaignKind": "Call", "campaignStatus": "Running",
                                  "description": "<p>Offer a free first session.</p>",
                                  "teamsNames": teams or {}})
    crm.add(cfg.PROSPECT, {"id": "p1", "businessName": "Phone Shop", "funnelStage": "Qualified", "phone": "216-555-0101"})
    crm.add(cfg.PROSPECT, {"id": "p2", "businessName": "Two Shop", "funnelStage": "Qualified", "phone": "216-555-0102"})
    crm.add(cfg.PROSPECT, {"id": "p3", "businessName": "Three Shop", "funnelStage": "Qualified", "phone": "216-555-0103"})
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
    # No answer + Call again: Done, and a fresh Planned row for the same record.
    r1 = run(calls.record_outcome(api, user, MENTOR, "t1", outcome="No answer", notes="voicemail",
                                  call_again=True, settings=settings))
    t1 = api.rows[cfg.TOUCH]["t1"]
    assert t1["touchStatus"] == "Done" and t1["outcome"] == "No answer" and t1["callNotes"] == "voicemail"
    assert t1["calledPhone"] == "216-555-0101" and t1["stageAtTouch"] == "Qualified"
    assert ("COutreachTouch", "t1") == user.updated[0][:2]                       # the caller's write
    assert "planned again" in r1["consequences"]
    fresh = [t for t in api.rows[cfg.TOUCH].values() if t.get("prospectId") == "p1" and t["touchStatus"] == "Planned"]
    assert len(fresh) == 1
    # Interested: the record moves to Lead, under the API client.
    run(calls.record_outcome(api, user, MENTOR, "t2", outcome="Interested", notes="", call_again=False, settings=settings))
    assert api.rows[cfg.PROSPECT]["p2"]["funnelStage"] == "Lead"
    assert any(e == cfg.PROSPECT and i == "p2" for e, i, _ in api.updated)
    # Declined: Done, and the record leaves by Declined.
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


def test_outcome_refusals():
    api = FakeCrm()
    _running_call_campaign(api, teams={"t-m": "Mentor Team"})
    s = _settings()
    with pytest.raises(PermissionError):
        run(calls.record_outcome(api, api, OUTSIDER, "t1", outcome="No answer", notes="", call_again=False, settings=s))
    with pytest.raises(service.CampaignError):
        run(calls.record_outcome(api, api, MENTOR, "t1", outcome="Interested", notes="", call_again=True, settings=s))
    with pytest.raises(service.CampaignError):
        run(calls.record_outcome(api, api, MENTOR, "t1", outcome="Maybe", notes="", call_again=False, settings=s))
    assert api.rows[cfg.TOUCH]["t1"]["touchStatus"] == "Planned"               # nothing written


def test_declined_never_overwrites_another_side_exit():
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
    assert client.get("/campaigns/api/session").status_code == 403      # the tile stays the Marketing Admin Team's
    import campaigns.router as router_mod
    monkeypatch.setattr(router_mod, "_api_client", lambda settings, request: crm)
    rows = client.get("/campaigns/api/calls").json()["rows"]
    assert len(rows) == 3
    done = client.post("/campaigns/api/calls/t1/outcome", json={"outcome": "Interested"})
    assert done.status_code == 200 and crm.rows[cfg.PROSPECT]["p1"]["funnelStage"] == "Lead"
    assert client.post("/campaigns/api/calls/t1/outcome", json={"outcome": "Interested"}).status_code == 400


def test_the_call_kind_is_offered_only_with_the_switch(monkeypatch):
    crm = FakeCrm()
    with pytest.raises(service.CampaignError):
        run(service.create_campaign(crm, {"name": "Calls", "campaignKind": "Call"}, user_id="u-1"))
    made = run(service.create_campaign(crm, {"name": "Calls", "campaignKind": "Call"}, user_id="u-1", calls_on=True))
    assert made["campaignKind"] == "Call" and made["campaignStatus"] == "Draft"
    assert service.manual_moves({"campaignKind": "Call", "campaignStatus": "Running"}) == ("Complete", "Cancelled")


# --- 4. the Stale sweep (§ 1.2, § 6) --------------------------------------------------------------

def test_stale_plan_reads_the_window_and_skips_active_records():
    crm = FakeCrm()
    now = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
    old = _crm_time(now - timedelta(days=200))
    recent = _crm_time(now - timedelta(days=10))
    crm.add(cfg.PROSPECT, {"id": "old", "name": "Old", "funnelStage": "Qualified", "stageChangedAt": old, "createdAt": old})
    crm.add(cfg.PROSPECT, {"id": "old-unv", "name": "Old U", "funnelStage": "Unverified", "createdAt": old})
    crm.add(cfg.PROSPECT, {"id": "fresh", "name": "Fresh", "funnelStage": "Qualified", "stageChangedAt": recent, "createdAt": old})
    crm.add(cfg.PROSPECT, {"id": "touched", "name": "Touched", "funnelStage": "Qualified", "createdAt": old})
    crm.add(cfg.TOUCH, {"prospectId": "touched", "touchStatus": "Sent", "sentAt": recent})
    crm.add(cfg.PROSPECT, {"id": "planned", "name": "Planned", "funnelStage": "Qualified", "createdAt": old})
    crm.add(cfg.TOUCH, {"prospectId": "planned", "touchStatus": "Planned", "plannedAt": old})
    crm.add(cfg.PROSPECT, {"id": "lead", "name": "Lead", "funnelStage": "Lead", "createdAt": old})
    crm.add(cfg.PROSPECT, {"id": "exited", "name": "Exited", "funnelStage": "Qualified", "sideExit": "Declined", "createdAt": old})
    plan = run(stale.plan_stale(crm, 180, now=now))
    assert sorted(r["id"] for r in plan) == ["old", "old-unv"]
    # PROSPECT_STALE_DAYS=0 (the live check): every untouched record at the two rungs.
    zero = run(stale.plan_stale(crm, 0, now=now))
    assert sorted(r["id"] for r in zero) == ["fresh", "old", "old-unv", "touched"]
    text = stale.plan_text(plan, 180)
    assert "2 would leave by Stale" in text and text == stale.plan_text(run(stale.plan_stale(crm, 180, now=now)), 180)


def test_stale_apply_never_overwrites_and_rereads_each_record():
    crm = FakeCrm()
    crm.add(cfg.PROSPECT, {"id": "a", "funnelStage": "Qualified"})
    crm.add(cfg.PROSPECT, {"id": "b", "funnelStage": "Qualified", "sideExit": "Do Not Contact"})
    crm.add(cfg.PROSPECT, {"id": "c", "funnelStage": "Lead"})
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
    crm.add(cfg.PROSPECT, {"id": "a", "funnelStage": "Qualified", "createdAt": "2020-01-01 00:00:00"})
    out = run(stale.run_stale_sweep(_settings(), client=crm))
    assert out["stale"] == 0 and crm.updated == []
    on = run(stale.run_stale_sweep(_settings(campaigns_enabled=True), client=crm))
    assert on["stale"] == 1


# --- 5. the reporting numbers and the Analytics reads (§ 6 items 2 and 3) --------------------------

def test_touches_by_campaign_matches_the_record_pages_summary():
    crm = FakeCrm()
    a = crm.add(cfg.CAMPAIGN, {"name": "Cards", "campaignKind": "Postcard", "campaignStatus": "Complete"})
    b = crm.add(cfg.CAMPAIGN, {"name": "Calls", "campaignKind": "Call", "campaignStatus": "Running"})
    crm.add(cfg.CAMPAIGN, {"name": "Social", "campaignKind": "Social media", "campaignStatus": "Running"})
    crm.add(cfg.TOUCH, {"outreachCampaignId": a["id"], "touchStatus": "Delivered", "stageAtTouch": "Qualified", "scanCount": 1})
    crm.add(cfg.TOUCH, {"outreachCampaignId": a["id"], "touchStatus": "Returned", "stageAtTouch": "Qualified"})
    crm.add(cfg.TOUCH, {"outreachCampaignId": b["id"], "touchStatus": "Done", "outcome": "Interested", "stageAtTouch": "Lead"})
    crm.add(cfg.TOUCH, {"outreachCampaignId": b["id"], "touchStatus": "Planned"})
    data = {r["name"]: r for r in run(reporting.touches_by_campaign(crm))}
    assert set(data) == {"Cards", "Calls"}                                   # social media selects nobody
    assert data["Cards"]["delivered"] == 1 and data["Cards"]["returned"] == 1 and data["Cards"]["scanned"] == 1
    assert data["Cards"]["stageAtTouch"] == {"Qualified": 2} and data["Cards"]["responded"] is None
    assert data["Calls"]["Interested"] == 1 and data["Calls"]["planned"] == 1 and data["Calls"]["done"] == 1
    touches = run(service.campaign_touches(crm, a["id"]))
    assert {k: data["Cards"][k] for k in service.touch_summary(touches)} == service.touch_summary(touches)


def test_entry_rung_by_door_counts_each_door_and_the_warm_lead_contacts():
    crm = FakeCrm()
    crm.add(cfg.PROSPECT, {"entryDoor": "State filing", "entryStage": "Qualified"})
    crm.add(cfg.PROSPECT, {"entryDoor": "State filing", "entryStage": "Qualified"})
    crm.add(cfg.PROSPECT, {"entryDoor": "List", "entryStage": "Unverified"})
    crm.add("Contact", {"cEntryStage": "Warm Lead"})
    crm.add("Contact", {"cEntryStage": "Qualified"})
    rows = {r["door"]: r for r in run(reporting.entry_rung_by_door(crm))}
    assert rows["State filing"]["Qualified"] == 2 and rows["State filing"]["total"] == 2
    assert rows["List"]["Unverified"] == 1
    assert rows[reporting.DOOR_INFO_OR_REGISTRATION]["Warm Lead"] == 1
    assert rows[reporting.DOOR_INFO_OR_REGISTRATION]["total"] == 1


def test_the_campaigns_analytics_page_and_its_metrics_are_registered():
    import analytics  # noqa: F401 — registers
    from analytics.registry import MetricContext, get_metric, get_page
    page = get_page("campaigns")
    assert page is not None and [p.metric_key for p in page.panels] == ["campaign_touches", "prospect_entry_rungs"]
    crm = FakeCrm()
    crm.add(cfg.PROSPECT, {"entryDoor": "List", "entryStage": "Unverified"})
    result = run(get_metric("prospect_entry_rungs").compute(MetricContext(settings=_settings(), espo=crm)))
    assert result.error is None and result.data["rows"][1]["Unverified"] == 1
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
    crm.add(cfg.PROSPECT, {"id": "p-phone", "businessName": "Phone Shop", "funnelStage": "Qualified", "phone": "1"})
    camp = crm.add(cfg.CAMPAIGN, {"name": "Calls", "campaignKind": "Call", "campaignStatus": "Draft", "teamsIds": ["t-m"]})
    run(calls.build_list(crm, crm, camp, None))
    touch, = [t for t in crm.rows[cfg.TOUCH].values()]
    assert touch["teamsIds"] == ["t-m"]
