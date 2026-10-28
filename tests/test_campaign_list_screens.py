"""The Lists tab redesigned — build plan § 7e.14, rulings 129–132 (M11), stop 1.

The server half: every list's counts stored and kept current (ruling 131) —
``audience.count_list``, *Refresh*, the nightly pass; the preview's *Who this
change moves*; the View page's member filters, reach and extra columns; the
switch on the session.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

from campaigns import audience, list_counts
from campaigns import config as cfg
from core.config import Settings
from core.settings_registry import BY_KEY
from tests.test_campaign_lists import (
    API, QUALIFIED, Both, ListCrm, _client, _contact, _lead, _new, match,
)


def run(coro):
    return asyncio.run(coro)


def _people(crm):
    """One person per reach: email and text and postcard, a card only, nobody."""
    everywhere = _contact(crm, "Pat Doe", cSmsOptIn=True, phoneNumber="+12165550100",
                          addressStreet="5 Oak", addressCity="Parma", addressState="OH",
                          addressPostalCode="44129")
    card_only = _lead(crm, "Card Only")
    nobody = _contact(crm, "Quiet Person", cMarketingOptIn=False, emailAddress="")
    return everywhere, card_only, nobody


# --- count_list: the stored numbers and each member's reach ---------------------------

def test_count_list_counts_each_channel_and_who_reaches_nobody():
    crm = ListCrm()
    everywhere, card_only, nobody = _people(crm)
    keys = [f"contact:{everywhere['id']}", f"lead:{card_only['id']}", f"contact:{nobody['id']}"]
    out = run(audience.count_list(crm, keys))
    assert out["counts"] == {"people": 3, "email": 1, "text": 1, "postcard": 2, "notReachable": 1}
    assert out["reach"] == {keys[0]: "etp", keys[1]: "p", keys[2]: ""}


def test_a_member_whose_person_another_member_took_is_still_reached():
    crm = ListCrm()
    pat = _contact(crm, "Pat Doe")
    lead = _lead(crm, "Pat's Shop", promotedContactId=pat["id"])
    keys = [f"contact:{pat['id']}", f"lead:{lead['id']}"]
    resolved = run(audience.resolve_targets(crm, cfg.KIND_EMAIL, keys))
    assert len(resolved["targets"]) == 1
    assert resolved["reachedMembers"] == set(keys)


# --- Refresh and the nightly pass -----------------------------------------------------

def test_refresh_runs_a_dynamic_list_and_stores_its_counts(monkeypatch):
    crm = ListCrm()
    _lead(crm, "Acme")
    _lead(crm, "Bakery")
    store = Both()
    client = _client(monkeypatch, crm, store)
    lid = _new(client, "Qualified leads", "dynamic", include=[QUALIFIED])
    before = next(r for r in client.get(API).json()["lists"] if r["id"] == lid)
    assert before["counts"] is None and before["countedAt"] is None
    out = client.post(f"{API}/{lid}/refresh")
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["run"]["total"] == 2 and body["counts"]["people"] == 2 and body["counts"]["postcard"] == 2
    after = next(r for r in client.get(API).json()["lists"] if r["id"] == lid)
    assert after["counts"]["people"] == 2 and after["countedAt"]


def test_refresh_counts_a_static_list_without_running_it(monkeypatch):
    crm = ListCrm()
    pat = _contact(crm, "Pat Doe")
    store = Both()
    client = _client(monkeypatch, crm, store)
    sid = _new(client, "Picked", "static")
    assert client.post(f"{API}/{sid}/add-people", json={"keys": [f"contact:{pat['id']}"]}).status_code == 200
    body = client.post(f"{API}/{sid}/refresh").json()
    assert body["run"] is None and body["counts"] == {"people": 1, "email": 1, "text": 0, "postcard": 0,
                                                      "notReachable": 0}


def test_a_retired_list_is_not_refreshed(monkeypatch):
    crm = ListCrm()
    store = Both()
    client = _client(monkeypatch, crm, store)
    lid = _new(client, "Old", "dynamic", include=[QUALIFIED])
    assert client.post(f"{API}/{lid}/retire").status_code == 200
    resp = client.post(f"{API}/{lid}/refresh")
    assert resp.status_code == 400 and "retired" in resp.json()["detail"]


def test_the_nightly_pass_counts_every_active_list_and_skips_retired_ones():
    crm = ListCrm()
    _lead(crm, "Acme")
    store = Both()
    dyn = run(store.create_list(name="A dynamic", notes="", kind="dynamic",
                                recipe={"include": [QUALIFIED], "exclude": []}, actor="t"))
    sta = run(store.create_list(name="B static", notes="", kind="static",
                                recipe={"include": [], "exclude": []}, actor="t"))
    old = run(store.create_list(name="C retired", notes="", kind="dynamic",
                                recipe={"include": [QUALIFIED], "exclude": []}, actor="t"))
    run(store.set_list_status(old["id"], "retired", "t"))
    summary = run(list_counts.run_pass(Settings(campaigns_enabled=True, campaign_lists=True),
                                       store=store, client=crm))
    assert (summary["lists"], summary["counted"], summary["failed"]) == (2, 2, [])
    assert store.lists[dyn["id"]]["counts"]["people"] == 1
    assert store.lists[dyn["id"]]["last_run_by"] == list_counts.PASS_ACTOR
    assert store.lists[sta["id"]]["counts"]["people"] == 0
    assert "counts" not in store.lists[old["id"]] or store.lists[old["id"]].get("counts") is None


def test_the_nightly_pass_goes_on_past_a_list_that_fails():
    crm = ListCrm()
    store = Both()
    bad = run(store.create_list(name="A bad", notes="", kind="dynamic",
                                recipe={"include": [match("lead", ("noSuchField", "in", ["x"]))], "exclude": []},
                                actor="t"))
    good = run(store.create_list(name="B good", notes="", kind="static",
                                 recipe={"include": [], "exclude": []}, actor="t"))
    summary = run(list_counts.run_pass(Settings(campaigns_enabled=True, campaign_lists=True),
                                       store=store, client=crm))
    assert summary["counted"] == 1 and summary["failed"] == ["A bad"]
    assert store.lists[good["id"]]["counts"]["people"] == 0
    assert store.lists[bad["id"]].get("counts") is None


def test_the_nightly_pass_does_nothing_while_lists_are_off():
    summary = run(list_counts.run_pass(Settings(campaigns_enabled=True, campaign_lists=False),
                                       store=Both(), client=ListCrm()))
    assert summary["lists"] == 0


# --- the preview's difference ---------------------------------------------------------

def test_the_preview_names_who_comes_on_and_who_drops_off(monkeypatch):
    crm = ListCrm()
    acme = _lead(crm, "Acme", industry="Manufacturing")
    bakery = _lead(crm, "Bakery", industry="Retail Trade")
    client = _client(monkeypatch, crm, Both())
    lid = _new(client, "Mfg", "dynamic", include=[match("lead", ("industry", "in", ["Manufacturing"]))])
    never = client.post(f"{API}/preview", json={"listId": lid, "recipe": {"include": [QUALIFIED]}}).json()
    assert never["diff"] is None
    client.post(f"{API}/{lid}/run")
    out = client.post(f"{API}/preview", json={"listId": lid, "recipe": {"include": [
        match("lead", ("industry", "in", ["Retail Trade"]))]}}).json()
    diff = out["diff"]
    assert (diff["comesOn"], diff["dropsOff"]) == (1, 1)
    assert [m["name"] for m in diff["comingOn"]] == ["Bakery"] and diff["comingOn"][0]["key"] == f"lead:{bakery['id']}"
    assert [m["name"] for m in diff["droppingOff"]] == ["Acme"] and diff["droppingOff"][0]["key"] == f"lead:{acme['id']}"


# --- the View page's members ----------------------------------------------------------

def test_members_carry_their_reach_and_filter_by_channel(monkeypatch):
    crm = ListCrm()
    everywhere, card_only, nobody = _people(crm)
    keys = [f"contact:{everywhere['id']}", f"lead:{card_only['id']}", f"contact:{nobody['id']}"]
    client = _client(monkeypatch, crm, Both())
    sid = _new(client, "Picked", "static")
    client.post(f"{API}/{sid}/add-people", json={"keys": keys})
    before = client.get(f"{API}/{sid}/members").json()
    assert before["uncounted"] == 3 and {m["reach"] for m in before["members"]} == {None}
    assert client.get(f"{API}/{sid}/members?channel=email").json()["total"] == 0
    client.post(f"{API}/{sid}/refresh")
    after = client.get(f"{API}/{sid}/members").json()
    assert after["uncounted"] == 0
    assert {m["key"]: m["reach"] for m in after["members"]} == {keys[0]: "etp", keys[1]: "p", keys[2]: ""}
    assert [m["key"] for m in client.get(f"{API}/{sid}/members?channel=postcard").json()["members"]] \
        == sorted([keys[0], keys[1]])
    assert [m["key"] for m in client.get(f"{API}/{sid}/members?channel=none").json()["members"]] == [keys[2]]
    assert client.get(f"{API}/{sid}/members?channel=fax").status_code == 400


def test_members_filter_by_the_group_that_brought_them_in(monkeypatch):
    crm = ListCrm()
    acme = _lead(crm, "Acme", industry="Manufacturing")
    bakery = _lead(crm, "Bakery", industry="Retail Trade")
    client = _client(monkeypatch, crm, Both())
    lid = _new(client, "Two groups", "dynamic", include=[
        match("lead", ("industry", "in", ["Manufacturing"])), match("lead", ("industry", "in", ["Retail Trade"]))])
    client.post(f"{API}/{lid}/run")
    first = client.get(f"{API}/{lid}/members?group=1").json()
    second = client.get(f"{API}/{lid}/members?group=2").json()
    assert [m["id"] for m in first["members"]] == [acme["id"]] and first["members"][0]["broughtInByIndex"] == 1
    assert [m["id"] for m in second["members"]] == [bakery["id"]]


def test_members_detail_adds_the_view_columns(monkeypatch):
    crm = ListCrm()
    pat = _contact(crm, "Pat Doe", phoneNumber="+12165550100", addressCity="Parma", cFunnelStage="Engaged")
    acme = _lead(crm, "Acme", email="hello@acme.test", phone="+12165550111")
    client = _client(monkeypatch, crm, Both())
    sid = _new(client, "Picked", "static")
    client.post(f"{API}/{sid}/add-people", json={"keys": [f"contact:{pat['id']}", f"lead:{acme['id']}"]})
    plain = client.get(f"{API}/{sid}/members").json()["members"]
    assert all("details" not in m for m in plain)
    rows = {m["key"]: m["details"] for m in client.get(f"{API}/{sid}/members?detail=true").json()["members"]}
    assert rows[f"contact:{pat['id']}"]["email"] == "pat@x.org"
    assert rows[f"contact:{pat['id']}"]["city"] == "Parma" and rows[f"contact:{pat['id']}"]["status"] == "Engaged"
    assert rows[f"lead:{acme['id']}"]["email"] == "hello@acme.test"
    assert rows[f"lead:{acme['id']}"]["city"] == "Cleveland"


# --- the switch -----------------------------------------------------------------------

def test_the_session_says_whether_the_new_screens_are_on(monkeypatch):
    crm = ListCrm()
    monkeypatch.setenv("CAMPAIGN_LIST_SCREENS", "true")
    client = _client(monkeypatch, crm, Both())
    assert client.get("/campaigns/api/session").json()["listScreensOn"] is True
    off = _client(monkeypatch, crm, Both(), lists="false")
    assert off.get("/campaigns/api/session").json()["listScreensOn"] is False


def test_the_settings_are_on_the_setup_page():
    keys = set(BY_KEY)
    assert {"campaign_list_screens", "campaign_list_count_seconds"} <= keys
    assert Settings().campaign_list_screens is False and Settings().campaign_list_count_seconds == 86400


def test_migration_0040_adds_the_three_columns():
    path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0040_list_stored_counts.py"
    spec = importlib.util.spec_from_file_location("m0040", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.down_revision == "0039_ready_made_lists"
    text = path.read_text()
    for col in ('"counts"', '"counted_at"', '"reach"'):
        assert text.count(col) == 2, col


# --- stops 2 to 4: the screens -------------------------------------------------------

FRONTEND = Path(__file__).resolve().parent.parent / "campaigns" / "frontend"


def test_the_view_page_is_served_with_busy_js_first_and_the_org_named(monkeypatch):
    client = _client(monkeypatch, ListCrm(), Both())
    resp = client.get("/campaigns/lists/list1/members")
    assert resp.status_code == 200
    html = resp.text
    assert '<base href="/campaigns/">' in html and "{{org}}" not in html
    scripts = html.split('<script src="')[1:]
    assert scripts[0].startswith("/shared/busy.js")
    assert "list-members.js" in html and 'name="cbm-org"' in html


def test_the_name_search_says_who_is_already_on_the_list(monkeypatch):
    crm = ListCrm()
    pat = _contact(crm, "Pat Doe")
    _contact(crm, "Pat Other")
    client = _client(monkeypatch, crm, Both())
    sid = _new(client, "Picked", "static")
    client.post(f"{API}/{sid}/add-people", json={"keys": [f"contact:{pat['id']}"]})
    rows = client.get(f"{API}/search/records?type=contact&q=Pat&listId={sid}").json()["records"]
    assert {r["name"]: r["onList"] for r in rows} == {"Pat Doe": True, "Pat Other": False}
    plain = client.get(f"{API}/search/records?type=contact&q=Pat").json()["records"]
    assert all("onList" not in r for r in plain)


def test_the_screens_never_disable_a_button_and_open_view_in_a_named_tab():
    view = (FRONTEND / "listview.js").read_text()
    members = (FRONTEND / "list-members.js").read_text()
    for js in (view, members):
        assert ".disabled = true" not in js and 'setAttribute("disabled"' not in js
    assert 'return "cbm-list-" + id;' in view and "window.open(viewUrl(id), viewTab(id))" in view
    # Preview remembers its switch per browser, and survives a blocked store.
    assert "localStorage.getItem(PREVIEW_KEY)" in view and "try { st.preview" in view


# --- the shared grid on the Lists screens (prds/shared-grid-plan.md, stop 2) ---------

def test_members_sort_on_several_keys_on_the_server(monkeypatch):
    crm = ListCrm()
    a = _lead(crm, "Bakery", industry="Manufacturing")
    b = _lead(crm, "Acme", industry="Retail Trade")
    c = _lead(crm, "Cobbler", industry="Manufacturing")
    client = _client(monkeypatch, crm, Both())
    lid = _new(client, "Two groups", "dynamic", include=[
        match("lead", ("industry", "in", ["Manufacturing"])), match("lead", ("industry", "in", ["Retail Trade"]))])
    client.post(f"{API}/{lid}/run")
    by_group_then_name_desc = client.get(f"{API}/{lid}/members?sort=broughtInBy:asc,name:desc").json()["members"]
    assert [m["id"] for m in by_group_then_name_desc] == [c["id"], a["id"], b["id"]]
    by_name = client.get(f"{API}/{lid}/members?sort=name").json()["members"]
    assert [m["id"] for m in by_name] == [b["id"], a["id"], c["id"]], "the old single-column form still works"
    refused = client.get(f"{API}/{lid}/members?sort=city:asc")
    assert refused.status_code == 400 and "cannot be sorted" in refused.json()["detail"]


def test_members_sort_reachable_first_and_uncounted_last(monkeypatch):
    crm = ListCrm()
    everywhere, card_only, nobody = _people(crm)
    keys = [f"contact:{nobody['id']}", f"lead:{card_only['id']}", f"contact:{everywhere['id']}"]
    client = _client(monkeypatch, crm, Both())
    sid = _new(client, "Picked", "static")
    client.post(f"{API}/{sid}/add-people", json={"keys": keys})
    client.post(f"{API}/{sid}/refresh")
    email_first = [m["key"] for m in client.get(f"{API}/{sid}/members?sort=reachEmail:asc,name:asc").json()["members"]]
    assert email_first[0] == f"contact:{everywhere['id']}"
    email_last = [m["key"] for m in client.get(f"{API}/{sid}/members?sort=reachEmail:desc").json()["members"]]
    assert email_last[-1] == f"contact:{everywhere['id']}"


def test_the_lists_screens_load_the_shared_grid_divider_and_spinner():
    index = (FRONTEND / "index.html").read_text()
    members = (FRONTEND / "list-members.html").read_text()
    for html in (index, members):
        assert '<script src="/shared/grid.js"></script>' in html and 'href="/shared/grid.css"' in html
        assert html.index("/shared/busy.js") < html.index("/shared/grid.js")
    assert '<script src="/shared/splitpane.js"></script>' in index and 'href="/shared/splitpane.css"' in index
    view = (FRONTEND / "listview.js").read_text()
    assert 'CBMGrid.enhance($("lv_grid")' in view and 'CBMGrid.enhance($("lv_eMemGrid")' in view
    assert 'CBMSplit.attach($("lv_listbox"), $("lv_preview")' in view
    assert "CBMBusy.loading(target, promise)" in view
    lm = (FRONTEND / "list-members.js").read_text()
    assert 'CBMGrid.enhance($("lm_grid")' in lm and "CBMBusy.loading($(\"lm_gridbox\")" in lm
