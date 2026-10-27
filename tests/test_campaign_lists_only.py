"""Lists only and the ready-made lists (build plan § 7e.9 second half,
§ 7e.12 Draft 9; ruling 99; step M8).

Each ready-made list must select what its kind's old rule selected: the list's
members resolved through ``audience.resolve_targets`` are compared with the
kind's ``select_targets`` over the same fake CRM.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from campaigns import audience, calls, email as email_kind, postcard, ready_made, sms
from campaigns import config as cfg
from campaigns import strip as strip_mod
from core.config import Settings
from tests.test_campaigns import FakeStore
from tests.test_campaign_lists import FakeListStore, ListCrm, _client, _contact, _lead, cat_for, run

SETTINGS = Settings(campaign_lists=True)


class SysStore(FakeListStore, FakeStore):
    """The fake list store (it carries the ready-made half) plus the links."""

    def __init__(self):
        FakeListStore.__init__(self)
        FakeStore.__init__(self)


class World(ListCrm):
    """Leads, contacts and engagements for every kind's selection."""

    CONTACT_FIELDS = {**ListCrm.CONTACT_FIELDS,
                      "cContactType": {"type": "multiEnum",
                                       "options": ["Client", "Mentor", "Partner", "Sponsor", "Prospect"]},
                      "cFunnelStage": {"type": "enum", "options": ["", *cfg.STAGES]}}


def _world():
    crm = World()
    old = (datetime.now(timezone.utc) - timedelta(days=500)).strftime("%Y-%m-%d")
    recent = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    # Leads.
    _lead(crm, "Acme", leadStatus=cfg.LEAD_QUALIFIED, phone="2165550101")
    _lead(crm, "Bolt", leadStatus=cfg.LEAD_UNQUALIFIED, phone="2165550102")
    _lead(crm, "Gone", leadStatus=cfg.LEAD_QUALIFIED, sideExit="Duplicate", phone="2165550103")
    _lead(crm, "Done", leadStatus=cfg.LEAD_DISQUALIFIED, phone="2165550104")
    _lead(crm, "Nowhere", leadStatus=cfg.LEAD_QUALIFIED, addressStatus="Dead", phone="")
    _lead(crm, "Half", leadStatus=cfg.LEAD_UNQUALIFIED, mailingAddressStreet="", phone="2165550105")
    # Contacts typed Prospect at each stage, with and without consent.
    _contact(crm, "Pat Prospect", cFunnelStage=cfg.STAGE_PROSPECT, cSmsOptIn=True, phoneNumber="+12165550201")
    _contact(crm, "Eve Engaged", cFunnelStage=cfg.STAGE_ENGAGED, cSmsOptIn=False, phoneNumber="+12165550202")
    _contact(crm, "Opal Opportunity", cFunnelStage=cfg.STAGE_OPPORTUNITY, cSmsOptIn=True,
             phoneNumber="+12165550203")
    _contact(crm, "Quiet Engaged", cFunnelStage=cfg.STAGE_ENGAGED, cMarketingOptIn=False, phoneNumber="+12165550204")
    _contact(crm, "Dee Nocall", cFunnelStage=cfg.STAGE_ENGAGED, doNotCall=True, phoneNumber="+12165550205")
    _contact(crm, "Also Client", cContactType=["Prospect", "Client"], cFunnelStage=cfg.STAGE_ENGAGED,
             cSmsOptIn=True, phoneNumber="+12165550206")
    _contact(crm, "No Stage", cSmsOptIn=True, phoneNumber="+12165550207")
    # Clients: one dormant, one with an open engagement, one recently closed.
    sleepy = _contact(crm, "Sam Sleepy", cContactType=["Client"])
    busy = _contact(crm, "Bea Busy", cContactType=["Client"])
    fresh = _contact(crm, "Fay Fresh", cContactType=["Client"])
    crm.add("CEngagement", {"name": "E1", "engagementStatus": "Completed", "closeDate": old,
                            "primaryEngagementContactId": sleepy["id"]})
    crm.add("CEngagement", {"name": "E2", "engagementStatus": "Completed", "closeDate": old,
                            "primaryEngagementContactId": busy["id"]})
    crm.add("CEngagement", {"name": "E3", "engagementStatus": "Active",
                            "primaryEngagementContactId": busy["id"]})
    crm.add("CEngagement", {"name": "E4", "engagementStatus": "Completed", "closeDate": recent,
                            "primaryEngagementContactId": fresh["id"]})
    return crm


async def _via_list(crm, list_id, kind):
    d = ready_made.BY_ID[list_id]
    cat = await audience.catalogue(crm, SETTINGS)
    result = await audience.run_recipe(crm, audience.normalise_recipe(d["recipe"]), cat)
    resolved = await audience.resolve_targets(crm, kind, result["keys"])
    return {t["key"] for t in resolved["targets"]}


@pytest.mark.parametrize("list_id,kind,select", [
    (ready_made.ID_POSTCARD, cfg.KIND_POSTCARD, lambda c: postcard.select_targets(c, postcard.DEFAULT_RULE)),
    (ready_made.ID_EMAIL, cfg.KIND_EMAIL,
     lambda c: email_kind.select_targets(c, {"stages": [cfg.STAGE_ENGAGED, cfg.STAGE_OPPORTUNITY]})),
    (ready_made.ID_SMS, cfg.KIND_SMS, lambda c: sms.select_targets(c, sms.DEFAULT_RULE)),
    (ready_made.ID_CALL, cfg.KIND_CALL,
     lambda c: calls.select_targets(c, {"statuses": list(cfg.LEAD_OPEN_STATUSES), "stages": list(cfg.STAGES)})),
    (ready_made.ID_DORMANT, cfg.KIND_EMAIL,
     lambda c: email_kind.select_targets(c, {"stages": [], "dormantDays": 365})),
])
def test_each_ready_made_list_selects_what_its_kinds_rule_selected(list_id, kind, select):
    crm = _world()
    want = {t["key"] for t in run(select(crm))}
    got = run(_via_list(crm, list_id, kind))
    assert want, "the fake world must give the rule someone to select"
    assert got == want


def test_the_consent_checks_still_hold_through_a_list():
    crm = _world()
    names = {r["id"]: r["name"] for r in crm.rows[cfg.CONTACT].values()}
    texted = {names[k.split(":")[1]] for k in run(_via_list(crm, ready_made.ID_SMS, cfg.KIND_SMS))}
    assert texted == {"Pat Prospect", "Opal Opportunity"}           # no tick, no text; a client is left out
    emailed = {names[k.split(":")[1]] for k in run(_via_list(crm, ready_made.ID_EMAIL, cfg.KIND_EMAIL))}
    assert "Quiet Engaged" not in emailed and "Also Client" not in emailed
    called = run(_via_list(crm, ready_made.ID_CALL, cfg.KIND_CALL))
    assert not any(names.get(k.split(":")[1]) == "Dee Nocall" for k in called)
    dormant = {names[k.split(":")[1]] for k in run(_via_list(crm, ready_made.ID_DORMANT, cfg.KIND_EMAIL))}
    assert dormant == {"Sam Sleepy"}


def test_the_dormant_list_describes_itself_in_words():
    cat = cat_for(World())
    words = audience.describe_recipe(audience.normalise_recipe(ready_made.BY_ID[ready_made.ID_DORMANT]["recipe"]), cat)
    assert words["include"] == ["Clients whose engagements are all closed, the latest more than 365 days ago."]
    assert audience.check_recipe(audience.normalise_recipe(ready_made.BY_ID[ready_made.ID_DORMANT]["recipe"]), cat) == []


def test_every_ready_made_recipe_passes_the_recipe_check():
    cat = cat_for(World())
    for d in ready_made.LISTS:
        assert audience.check_recipe(audience.normalise_recipe(d["recipe"]), cat) == [], d["name"]


def test_ensure_is_idempotent_and_leaves_an_existing_row_alone():
    store = SysStore()
    assert run(ready_made.ensure(store)) == 5
    store.lists[ready_made.ID_SMS]["notes"] = "kept"
    assert run(ready_made.ensure(store)) == 0
    assert store.lists[ready_made.ID_SMS]["notes"] == "kept"
    del store.lists[ready_made.ID_CALL]
    assert run(ready_made.ensure(store)) == 1
    assert all(store.lists[d["id"]]["system"] for d in ready_made.LISTS)


def test_the_migration_carries_the_same_five_lists():
    path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0039_ready_made_lists.py"
    spec = importlib.util.spec_from_file_location("m0039", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    frozen = {i: (n, notes, r) for i, n, notes, r in mod.LISTS}
    assert set(frozen) == set(ready_made.BY_ID)
    for d in ready_made.LISTS:
        name, notes, recipe = frozen[d["id"]]
        assert (name, notes) == (d["name"], d["notes"])
        assert json.loads(json.dumps(recipe)) == json.loads(json.dumps(d["recipe"])), d["name"]


# --- the API: the refusals and Copy ---------------------------------------------------------

API = "/campaigns/api/lists"


def test_a_ready_made_list_cannot_be_deleted_renamed_changed_retired_or_excluded_from(monkeypatch):
    crm, store = _world(), SysStore()
    client = _client(monkeypatch, crm, store)
    lists = client.get(API).json()["lists"]
    by_id = {l["id"]: l for l in lists}
    assert set(ready_made.BY_ID) <= set(by_id) and by_id[ready_made.ID_SMS]["system"] is True
    lid = ready_made.ID_SMS
    resp = client.delete(f"{API}/{lid}")
    assert resp.status_code == 400 and "ready-made" in resp.json()["detail"] and "deleted" in resp.json()["detail"]
    resp = client.put(f"{API}/{lid}", json={"name": "Mine now", "kind": "dynamic",
                                            "recipe": ready_made.BY_ID[lid]["recipe"]})
    assert resp.status_code == 400 and "renamed" in resp.json()["detail"]
    resp = client.put(f"{API}/{lid}", json={"name": store.lists[lid]["name"], "kind": "static"})
    assert resp.status_code == 400 and "ready-made" in resp.json()["detail"]
    resp = client.post(f"{API}/{lid}/retire")
    assert resp.status_code == 400 and "retired" in resp.json()["detail"]
    resp = client.post(f"{API}/{lid}/exclude", json={"key": "contact:x", "newName": "Off"})
    assert resp.status_code == 400 and "ready-made" in resp.json()["detail"]
    assert store.lists[lid]["name"] == "Prospects with text consent" and store.lists[lid]["status"] == "active"


def test_copy_of_a_ready_made_list_is_an_ordinary_static_list(monkeypatch):
    crm, store = _world(), SysStore()
    client = _client(monkeypatch, crm, store)
    client.get(API)
    resp = client.post(f"{API}/{ready_made.ID_DORMANT}/copy", json={"name": "Dormant on 27 Oct"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["members"] == 1 and body["list"]["kind"] == "static" and body["list"]["system"] is False
    new_id = body["list"]["id"]
    assert client.delete(f"{API}/{new_id}").status_code == 200


def test_a_list_of_our_own_may_not_carry_a_built_in_selection(monkeypatch):
    crm, store = _world(), SysStore()
    client = _client(monkeypatch, crm, store)
    resp = client.post(API, json={"name": "Sneaky", "kind": "dynamic",
                                  "recipe": ready_made.BY_ID[ready_made.ID_DORMANT]["recipe"]})
    assert resp.status_code == 400 and "ready-made selection" in resp.json()["detail"]


# --- the build: lists only -------------------------------------------------------------------

def _only(monkeypatch, crm, store, on="true"):
    monkeypatch.setenv("CAMPAIGN_LISTS_ONLY", on)
    return _client(monkeypatch, crm, store)


def _camp(crm, **kw):
    return crm.add(cfg.CAMPAIGN, {"name": "Autumn", "campaignKind": cfg.KIND_POSTCARD,
                                  "campaignStatus": cfg.STATUS_DRAFT, **kw})


def test_a_campaign_with_no_list_is_refused_at_build_in_words(monkeypatch):
    crm, store = _world(), SysStore()
    client = _only(monkeypatch, crm, store)
    camp = _camp(crm)
    resp = client.post(f"/campaigns/api/campaigns/{camp['id']}/build", json={})
    assert resp.status_code == 400 and "Choose a list first" in resp.json()["detail"]
    page = client.get(f"/campaigns/api/campaigns/{camp['id']}").json()
    assert page["listsOnly"] is True
    assert page["strip"]["current"] == "Draft" and "choose a list" in page["strip"]["next"]


def test_a_rule_payload_is_refused_with_the_switch_on_and_accepted_with_it_off(monkeypatch):
    crm, store = _world(), SysStore()
    client = _only(monkeypatch, crm, store)
    camp = _camp(crm)
    resp = client.post(f"/campaigns/api/campaigns/{camp['id']}/build", json={"rule": postcard.DEFAULT_RULE})
    assert resp.status_code == 400 and "send to lists" in resp.json()["detail"]
    client = _only(monkeypatch, crm, store, on="false")
    resp = client.post(f"/campaigns/api/campaigns/{camp['id']}/build", json={"rule": postcard.DEFAULT_RULE})
    assert resp.status_code == 200, resp.text
    assert client.get(f"/campaigns/api/campaigns/{camp['id']}").json()["strip"] is None


def test_a_campaign_with_a_list_builds_from_it(monkeypatch):
    crm, store = _world(), SysStore()
    client = _only(monkeypatch, crm, store)
    client.get(API)
    camp = _camp(crm)
    assert client.put(f"/campaigns/api/campaigns/{camp['id']}/audience",
                      json={"listId": ready_made.ID_POSTCARD}).status_code == 200
    resp = client.post(f"/campaigns/api/campaigns/{camp['id']}/build", json={})
    assert resp.status_code == 200, resp.text
    want = {t["key"] for t in run(postcard.select_targets(crm, postcard.DEFAULT_RULE))}
    assert resp.json()["pieces"] == len(want)
    page = client.get(f"/campaigns/api/campaigns/{camp['id']}").json()
    assert page["strip"]["current"] == "Ready" and "sign off" in page["strip"]["next"]


def test_a_campaign_built_by_a_rule_is_given_its_kinds_ready_made_list(monkeypatch):
    crm, store = _world(), SysStore()
    client = _only(monkeypatch, crm, store)
    camp = _camp(crm, campaignStatus=cfg.STATUS_AWAITING, selectionRule=json.dumps(postcard.DEFAULT_RULE))
    never = _camp(crm, name="Never built")
    page = client.get(f"/campaigns/api/campaigns/{camp['id']}").json()
    assert store.audiences[camp["id"]]["list_id"] == ready_made.ID_POSTCARD
    assert "All leads for postcards" not in page["strip"]["next"] or page["strip"]["current"] == "Ready"
    client.get(f"/campaigns/api/campaigns/{never['id']}")
    assert never["id"] not in store.audiences                    # never built by a rule: chooses its own
    resp = client.post(f"/campaigns/api/campaigns/{camp['id']}/build", json={})
    assert resp.status_code == 200, resp.text


def test_session_says_whether_lists_only_is_on(monkeypatch):
    crm, store = _world(), SysStore()
    assert _only(monkeypatch, crm, store).get("/campaigns/api/session").json()["listsOnlyOn"] is True
    assert _only(monkeypatch, crm, store, on="false").get("/campaigns/api/session").json()["listsOnlyOn"] is False


# --- the strip (ruling 100) ----------------------------------------------------------------------

@pytest.mark.parametrize("kind", [cfg.KIND_POSTCARD, cfg.KIND_EMAIL, cfg.KIND_SMS, cfg.KIND_CALL])
def test_the_strip_maps_each_status(kind):
    def at(status, **kw):
        return strip_mod.strip({"campaignKind": kind, "campaignStatus": status}, **kw)
    assert at(cfg.STATUS_DRAFT)["current"] == "Draft" and "choose a list" in at(cfg.STATUS_DRAFT)["next"]
    assert "build the list" in at(cfg.STATUS_DRAFT, list_name="L")["next"]
    assert at(cfg.STATUS_AWAITING, list_name="L")["current"] == "Ready"
    assert at(cfg.STATUS_SIGNED_OFF, list_name="L")["current"] == "Signed off"
    assert at(cfg.STATUS_RUNNING, list_name="L")["current"] == "Sent"
    assert at(cfg.STATUS_COMPLETE, list_name="L")["current"] == "Results"
    cancelled = at(cfg.STATUS_CANCELLED, list_name="L")
    assert cancelled["current"] is None and cancelled["cancelled"] is True
    for s in (cfg.STATUS_DRAFT, cfg.STATUS_AWAITING, cfg.STATUS_SIGNED_OFF, cfg.STATUS_RUNNING, cfg.STATUS_COMPLETE):
        assert at(s, list_name="L")["stages"] == ["Draft", "Ready", "Signed off", "Sent", "Results"]


def test_the_strip_names_missing_content_and_the_email_pick():
    sms_draft = strip_mod.strip({"campaignKind": cfg.KIND_SMS, "campaignStatus": cfg.STATUS_DRAFT},
                                list_name="L", content_problem="Write the text message first (the campaign's form, Text message).")
    assert sms_draft["next"] == ("Next: write the text message first — press Edit to change it "
                                 "(Audience and content).")
    email = strip_mod.strip({"campaignKind": cfg.KIND_EMAIL, "campaignStatus": cfg.STATUS_SIGNED_OFF},
                            list_name="Opted-in prospects (Engaged and later)")
    assert "Constant Contact" in email["next"] and "Opted-in prospects" in email["next"]
    assert strip_mod.strip({"campaignKind": cfg.KIND_SOCIAL, "campaignStatus": cfg.STATUS_DRAFT}) is None


# --- the grid (ruling 101) ---------------------------------------------------------------------

def test_the_grid_fills_partners_funders_events_and_stage_on_every_row(monkeypatch):
    crm, store = _world(), SysStore()
    partner = crm.add(cfg.PARTNER_PROFILE, {"name": "Northgate Chamber"})
    event = crm.add(cfg.EVENT, {"name": "Hiring Your First Employee"})
    ids = [_camp(crm, name=f"C{i:02d}", campaignStatus=cfg.STATUS_RUNNING if i % 2 else cfg.STATUS_DRAFT,
                 pieceCount=i)["id"] for i in range(70)]
    crm.related[(cfg.CAMPAIGN, ids[65], cfg.LINK_PARTNERS)] = {partner["id"]}
    crm.related[(cfg.CAMPAIGN, ids[65], cfg.LINK_EVENTS)] = {event["id"]}
    on = {c["id"]: c for c in _only(monkeypatch, crm, store).get("/campaigns/api/campaigns").json()["campaigns"]}
    row = on[ids[65]]
    assert [p["name"] for p in row["partners"]] == ["Northgate Chamber"]      # past the old 60-row cutoff
    assert [e["name"] for e in row["events"]] == ["Hiring Your First Employee"]
    assert row["stage"] == "Sent" and row["reached"] == 65
    assert on[ids[64]]["stage"] == "Draft" and on[ids[64]]["partners"] == []
    off = {c["id"]: c for c in _only(monkeypatch, crm, store, on="false").get("/campaigns/api/campaigns").json()["campaigns"]}
    assert off[ids[65]]["partners"] is None and "stage" not in off[ids[65]]   # switch off: as before
