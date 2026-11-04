"""Promote this event and the event's Campaigns tab (build plan § 7e.9,
ruling 97; step M10)."""

from __future__ import annotations

import pytest

from campaigns import config as cfg
from campaigns import promote, ready_made
from core.config import Settings, get_settings
from tests.test_campaign_lists import run
from tests.test_campaign_lists_only import SysStore, World, _client
from tests.test_campaigns import MARKETING

OUTSIDE_EVENTS = {**MARKETING, "teams": ["Marketing Admin Team"]}


class PromoteCrm(World):
    """The world plus an event, its registrations and the event side of the
    campaign's ``events`` link."""

    REG_HAS_CAMPAIGN = True

    async def metadata(self, key: str):
        if key == f"entityDefs.{cfg.EVENT_REGISTRATION}.fields":
            return {"attendanceStatus": {"type": "enum"},
                    **({"outreachCampaign": {"type": "link"}} if self.REG_HAS_CAMPAIGN else {})}
        return await super().metadata(key)

    async def list_related(self, entity, record_id, link, *, select=None, max_size=200):
        if entity == cfg.EVENT and link == cfg.EVENT_CAMPAIGNS_LINK:
            ids = sorted(cid for (e, cid, l), evs in self.related.items()
                         if e == cfg.CAMPAIGN and l == cfg.LINK_EVENTS and record_id in evs)
            rows = [self.rows.get(cfg.CAMPAIGN, {}).get(i, {"id": i}) for i in ids]
            return {"total": len(rows), "list": rows}
        return await super().list_related(entity, record_id, link, select=select, max_size=max_size)


def _world():
    crm = PromoteCrm()
    crm.add(cfg.EVENT, {"id": "ev-1", "name": "Pricing for Profit", "slug": "pricing-for-profit"})
    return crm


def _on(monkeypatch, crm, store, *, promote_on="true", user=None, **env):
    monkeypatch.setenv("EVENT_PROMOTE", promote_on)
    monkeypatch.setenv("CAMPAIGNS_CALLS", "true")
    monkeypatch.setenv("CAMPAIGNS_SMS", "true")
    monkeypatch.setenv("CAMPAIGNS_EMAIL", "true")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    client = _client(monkeypatch, crm, store)
    if user is not None:
        import campaigns.router as router_mod
        monkeypatch.setattr(router_mod, "current_user", lambda request: user)
    return client


# --- the switch and the gates ----------------------------------------------------------

def test_is_on_needs_all_three_switches():
    assert promote.is_on(Settings(event_promote=True, campaigns_enabled=True, campaign_lists=True))
    assert not promote.is_on(Settings(event_promote=False, campaigns_enabled=True, campaign_lists=True))
    assert "Campaign lists" in promote.why_off(Settings(event_promote=True, campaigns_enabled=True,
                                                       campaign_lists=False))


def test_promote_is_404_in_words_while_switched_off(monkeypatch):
    client = _on(monkeypatch, _world(), SysStore(), promote_on="false")
    resp = client.get("/campaigns/api/promote/options?event=ev-1")
    assert resp.status_code == 404 and "EVENT_PROMOTE" in resp.json()["detail"]


def test_promote_needs_the_event_team_too_and_says_so(monkeypatch):
    client = _on(monkeypatch, _world(), SysStore(), EVENTS_ALLOWED_TEAMS="Event Team")
    resp = client.get("/campaigns/api/promote/options?event=ev-1")
    assert resp.status_code == 403 and "Event Team" in resp.json()["detail"]


# --- the form's options ------------------------------------------------------------------

def test_options_name_each_channel_and_preset_its_ready_made_list(monkeypatch):
    client = _on(monkeypatch, _world(), SysStore())
    body = client.get("/campaigns/api/promote/options?event=ev-1").json()
    by = {c["kind"]: c for c in body["channels"]}
    assert [c["kind"] for c in body["channels"]] == list(promote.CHANNELS)
    assert by[cfg.KIND_EMAIL]["ticked"] and by[cfg.KIND_SMS]["ticked"] and by[cfg.KIND_POSTCARD]["ticked"]
    assert by[cfg.KIND_CALL]["ticked"] is False
    assert by[cfg.KIND_SMS]["name"] == "Pricing for Profit — Text"
    assert by[cfg.KIND_POSTCARD]["listId"] == ready_made.ID_POSTCARD
    assert body["lists"][0]["system"] is True


def test_a_channel_switched_off_is_offered_unticked_with_its_reason(monkeypatch):
    client = _on(monkeypatch, _world(), SysStore(), CAMPAIGNS_SMS="false")
    by = {c["kind"]: c for c in client.get("/campaigns/api/promote/options?event=ev-1").json()["channels"]}
    assert by[cfg.KIND_SMS]["ticked"] is False and "CAMPAIGNS_SMS" in by[cfg.KIND_SMS]["refusal"]


# --- promoting ------------------------------------------------------------------------------

def _channels(*kinds):
    return [{"kind": k, "name": promote.default_name("Pricing for Profit", k), "listId": ready_made.FOR_KIND[k]}
            for k in kinds]


def test_promote_makes_one_draft_per_channel_linked_with_its_link_and_list(monkeypatch):
    crm, store = _world(), SysStore()
    client = _on(monkeypatch, crm, store)
    client.get("/campaigns/api/lists")
    resp = client.post("/campaigns/api/promote", json={"eventId": "ev-1", "channels": _channels(
        cfg.KIND_EMAIL, cfg.KIND_SMS, cfg.KIND_POSTCARD)})
    assert resp.status_code == 200, resp.text
    made = resp.json()["campaigns"]
    assert [m["kind"] for m in made] == [cfg.KIND_EMAIL, cfg.KIND_SMS, cfg.KIND_POSTCARD]
    for m in made:
        row = crm.rows[cfg.CAMPAIGN][m["id"]]
        assert row["campaignStatus"] == cfg.STATUS_DRAFT and row["assignedUserId"] == MARKETING["userId"]
        assert crm.related[(cfg.CAMPAIGN, m["id"], cfg.LINK_EVENTS)] == {"ev-1"}
        assert store.audiences[m["id"]]["list_id"] == ready_made.FOR_KIND[m["kind"]]
        links = [l for l in store.links.values() if l["campaign_id"] == m["id"]]
        assert len(links) == 1 and links[0]["destination_kind"] == cfg.DEST_EVENT
        assert links[0]["destination_target"] == "ev-1" and links[0]["destination_slug"] == "pricing-for-profit"
        assert not m["warnings"]


@pytest.mark.parametrize("channels,words", [
    ([], "Tick at least one channel"),
    ([{"kind": cfg.KIND_EMAIL, "name": "", "listId": ready_made.ID_EMAIL}], "needs a name"),
    ([{"kind": cfg.KIND_EMAIL, "name": "E", "listId": ""}], "Choose the list"),
    ([{"kind": cfg.KIND_EMAIL, "name": "E", "listId": "nope"}], "no longer exists"),
    ([{"kind": cfg.KIND_SOCIAL, "name": "S", "listId": ready_made.ID_EMAIL}], "not a channel"),
    (_channels(cfg.KIND_EMAIL) * 2, "ticked twice"),
])
def test_promote_refuses_in_words_and_makes_nothing(monkeypatch, channels, words):
    crm, store = _world(), SysStore()
    client = _on(monkeypatch, crm, store)
    client.get("/campaigns/api/lists")
    resp = client.post("/campaigns/api/promote", json={"eventId": "ev-1", "channels": channels})
    assert resp.status_code == 400 and words in resp.json()["detail"]
    assert not crm.rows.get(cfg.CAMPAIGN)


def test_promote_refuses_a_channel_switched_off_before_making_any(monkeypatch):
    crm, store = _world(), SysStore()
    client = _on(monkeypatch, crm, store, CAMPAIGNS_SMS="false")
    client.get("/campaigns/api/lists")
    resp = client.post("/campaigns/api/promote", json={"eventId": "ev-1", "channels": _channels(
        cfg.KIND_EMAIL, cfg.KIND_SMS)})
    assert resp.status_code == 400 and "Text campaigns are switched off" in resp.json()["detail"]
    assert not crm.rows.get(cfg.CAMPAIGN)


def test_promote_refuses_a_retired_list(monkeypatch):
    crm, store = _world(), SysStore()
    client = _on(monkeypatch, crm, store)
    client.get("/campaigns/api/lists")
    run(store.set_list_status(ready_made.ID_EMAIL, "retired", "test"))
    resp = client.post("/campaigns/api/promote", json={"eventId": "ev-1", "channels": _channels(cfg.KIND_EMAIL)})
    assert resp.status_code == 400 and "retired" in resp.json()["detail"]


def test_promote_answers_404_for_an_unknown_event(monkeypatch):
    client = _on(monkeypatch, _world(), SysStore())
    resp = client.post("/campaigns/api/promote", json={"eventId": "nope", "channels": _channels(cfg.KIND_EMAIL)})
    assert resp.status_code == 404


# --- the roll-up --------------------------------------------------------------------------

def _rolled():
    crm = _world()
    a = crm.add(cfg.CAMPAIGN, {"name": "A email", "campaignKind": cfg.KIND_EMAIL, "campaignStatus": "Running"})
    b = crm.add(cfg.CAMPAIGN, {"name": "B postcard", "campaignKind": cfg.KIND_POSTCARD, "campaignStatus": "Draft"})
    other = crm.add(cfg.CAMPAIGN, {"name": "Other event's", "campaignKind": cfg.KIND_SMS})
    crm.related[(cfg.CAMPAIGN, a["id"], cfg.LINK_EVENTS)] = {"ev-1"}
    crm.related[(cfg.CAMPAIGN, b["id"], cfg.LINK_EVENTS)] = {"ev-1"}
    for status in (cfg.TOUCH_DELIVERED, cfg.TOUCH_RETURNED, cfg.TOUCH_PLANNED):
        crm.add(cfg.TOUCH, {"outreachCampaignId": a["id"], "touchStatus": status, "contactName": f"P {status}"})
    reg = lambda **kw: crm.add(cfg.EVENT_REGISTRATION, {"eventId": "ev-1", **kw})
    reg(firstName="Ann", lastName="A", outreachCampaignId=a["id"], attendanceStatus="Attended")
    reg(firstName="Ben", lastName="B", outreachCampaignId=a["id"], attendanceStatus="No Show")
    reg(firstName="Cal", lastName="C", outreachCampaignId=other["id"], attendanceStatus="Attended")
    reg(firstName="Dee", lastName="D", attendanceStatus="Attended")
    reg(firstName="Eli", lastName="E")
    crm.add(cfg.EVENT_REGISTRATION, {"eventId": "ev-2", "firstName": "Far", "outreachCampaignId": a["id"]})
    return crm, a, b, other


def test_the_rollup_counts_each_campaign_the_unlinked_and_no_campaign():
    crm, a, b, other = _rolled()
    body = run(promote.rollup(crm, "ev-1"))
    rows = {r["campaignId"]: r for r in body["rows"]}
    assert rows[a["id"]] == {**rows[a["id"]], "reached": 2, "registered": 2, "attended": 1, "linked": True,
                             "channel": "Email"}
    assert rows[b["id"]]["registered"] == 0 and rows[b["id"]]["reached"] == 0 and rows[b["id"]]["linked"]
    assert rows[other["id"]]["linked"] is False and rows[other["id"]]["registered"] == 1
    assert [r["linked"] for r in body["rows"]] == [True, True, False]
    assert body["noCampaign"] == {"registered": 2, "attended": 1}
    assert body["totals"] == {"registered": 5, "attended": 3}


def test_the_rollup_without_the_credit_field_puts_everyone_under_no_campaign():
    crm, a, *_ = _rolled()
    crm.REG_HAS_CAMPAIGN = False
    body = run(promote.rollup(crm, "ev-1"))
    assert body["creditAvailable"] is False
    assert body["noCampaign"]["registered"] == 5
    assert all(r["registered"] == 0 for r in body["rows"])


@pytest.mark.parametrize("campaign,measure,names", [
    ("A", "reached", ["P Delivered", "P Returned"]),
    ("A", "registered", ["Ann A", "Ben B"]),
    ("A", "attended", ["Ann A"]),
    ("none", "registered", ["Dee D", "Eli E"]),
    ("none", "attended", ["Dee D"]),
])
def test_each_number_opens_the_people_behind_it(campaign, measure, names):
    crm, a, *_ = _rolled()
    cid = a["id"] if campaign == "A" else promote.NO_CAMPAIGN
    got = run(promote.people(crm, "ev-1", cid, measure))["people"]
    assert [p["name"] for p in got] == names


def test_people_refuses_an_unknown_measure_and_reached_without_a_campaign():
    crm, *_ = _rolled()
    with pytest.raises(promote.CampaignError):
        run(promote.people(crm, "ev-1", promote.NO_CAMPAIGN, "reached"))
    with pytest.raises(promote.CampaignError):
        run(promote.people(crm, "ev-1", "x", "clicked"))


# --- the events side ------------------------------------------------------------------------

def _events(monkeypatch, crm, on="true"):
    from tests.test_events_admin import build
    monkeypatch.setenv("CAMPAIGNS_ENABLED", "true")
    monkeypatch.setenv("CAMPAIGN_LISTS", "true")
    monkeypatch.setenv("EVENT_PROMOTE", on)
    get_settings.cache_clear()
    client = build(monkeypatch, user=MARKETING, crm=crm)
    import events.router as ev_router
    monkeypatch.setattr(ev_router, "_rollup_reader", lambda settings: crm)
    return client


def test_the_event_session_says_whether_promote_is_on(monkeypatch):
    assert _events(monkeypatch, _world()).get("/events/api/session").json()["promote"] is True
    assert _events(monkeypatch, _world(), on="false").get("/events/api/session").json()["promote"] is False


def test_the_campaigns_tab_route_counts_and_opens_people(monkeypatch):
    crm, a, *_ = _rolled()
    client = _events(monkeypatch, crm)
    body = client.get("/events/api/events/ev-1/campaigns").json()
    assert len(body["rows"]) == 3
    people = client.get(f"/events/api/events/ev-1/campaigns/people?campaign={a['id']}&measure=attended").json()
    assert [p["name"] for p in people["people"]] == ["Ann A"]
    assert client.get("/events/api/events/ev-1/campaigns/people?campaign=x&measure=clicked").status_code == 400


def test_the_campaigns_tab_route_is_404_while_off_and_for_an_unknown_event(monkeypatch):
    crm, *_ = _rolled()
    assert _events(monkeypatch, crm, on="false").get("/events/api/events/ev-1/campaigns").status_code == 404
    assert _events(monkeypatch, crm).get("/events/api/events/nope/campaigns").status_code == 404
