"""Phase B of prds/mailing-list-and-event-sponsorship-plan.md — partners and
funders on an event, and the Events tab on their records.

What these guard, in the order a bug would bite:

* the pickers are feature-detected from the live CRM's links and never offered
  for a link that is missing or points at the wrong entity;
* a forbidden option list degrades the picker, it never shows an empty list;
* the write is a diff (relate the missing, unrelate the surplus), whitelisted
  to live links, with ONLY a foreign-record denial retried as the admin;
* the per-partner rollup counts registered / attended / became-a-client with
  the programme's conversion rule, de-duplicates clients in the totals, and
  renders an unreadable count as None (never 0);
* the tab and its endpoint exist on the partner and funder routers only, and
  the endpoint answers ``available: false`` on a CRM without the link.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.app import create_app
from core.config import get_settings
from core.espo import EspoError
from events import config as cfg
from events import reporting, service
from forms import info_request
from sessions.config import MENTOR, PARTNER, SPONSOR
from sessions.router import _detail_tabs

from tests.test_events_admin import MARKETING, build
from tests.test_events_reporting import FakeCrm as ReportingCrm, _reg
from tests.test_events_service import make_event

PARTNER_LINK, FUNDER_LINK = cfg.SPONSOR_LINKS

BOTH_LINKS = {
    "partnerProfiles": {"type": "hasMany", "entity": "CPartnerProfile",
                        "foreign": "sponsoredEvents"},
    "sponsorProfiles": {"type": "hasMany", "entity": "CSponsorProfile",
                        "foreign": "sponsoredEvents"},
}


class LinkCrm(ReportingCrm):
    """The reporting fake plus metadata and the relationship verbs."""

    def __init__(self, *, links=None, related=None, forbid_list=(), **kw):
        super().__init__(**kw)
        self.links = BOTH_LINKS if links is None else links
        # (entity, record id, link) -> [rows]
        self.related = related or {}
        self.forbid_list = set(forbid_list)
        self.relates: list[tuple] = []
        self.unrelates: list[tuple] = []
        self.deny_foreign = False
        self.deny_entity = False
        self.data.setdefault("CPartnerProfile", [])
        self.data.setdefault("CSponsorProfile", [])

    async def metadata(self, key):
        if key == f"entityDefs.{cfg.EVENT}.links":
            return self.links
        if key.startswith("entityDefs.") and ".links." in key:
            entity, link = key[len("entityDefs."):].split(".links.")
            if entity in ("CPartnerProfile", "CSponsorProfile") and link == "sponsoredEvents":
                return {"type": "hasMany", "entity": cfg.EVENT} if self.links else None
            return None
        if key.endswith(".fields"):
            return {}
        return None

    async def metadata_enum_options(self, entity, field):
        return []

    async def list(self, entity, **kw):
        if entity in self.forbid_list:
            raise EspoError(f"list {entity} failed: HTTP 403 forbidden")
        return await super().list(entity, **kw)

    async def list_related(self, entity, record_id, link, *, select=None, max_size=200):
        rows = self.related.get((entity, record_id, link), [])
        return {"total": len(rows), "list": rows[:max_size]}

    async def relate(self, entity, record_id, link, related_id):
        if self.deny_entity:
            raise EspoError("relate failed: HTTP 403 {\"message\":\"forbidden\"}")
        if self.deny_foreign:
            raise EspoError("relate failed: HTTP 403 noAccessToForeignRecord")
        self.relates.append((entity, record_id, link, related_id))
        self.related.setdefault((entity, record_id, link), []).append({"id": related_id})

    async def unrelate(self, entity, record_id, link, related_id):
        if self.deny_foreign:
            raise EspoError("unrelate failed: HTTP 403 noAccessToForeignRecord")
        self.unrelates.append((entity, record_id, link, related_id))
        rows = self.related.get((entity, record_id, link), [])
        self.related[(entity, record_id, link)] = [r for r in rows if r["id"] != related_id]

    async def get(self, entity, record_id, select=None):
        for row in self.data.get(entity, []):
            if row.get("id") == record_id:
                return row
        return None


# --- feature detection --------------------------------------------------------


async def test_live_links_are_only_those_the_crm_has_pointing_right():
    assert await service.live_sponsor_links(LinkCrm()) == cfg.SPONSOR_LINKS
    funder_only = LinkCrm(links={"sponsorProfiles": BOTH_LINKS["sponsorProfiles"]})
    assert await service.live_sponsor_links(funder_only) == (FUNDER_LINK,)
    # A link of the right name pointing at the wrong entity is NOT the link.
    wrong = LinkCrm(links={"partnerProfiles": {"type": "hasMany", "entity": "Account"}})
    assert await service.live_sponsor_links(wrong) == ()


async def test_live_links_fail_closed():
    class Broken(LinkCrm):
        async def metadata(self, key):
            raise EspoError("metadata failed: HTTP 500")
    assert await service.live_sponsor_links(Broken()) == ()
    assert await service.live_sponsor_links(object()) == ()   # no metadata reader


# --- the picker's options -----------------------------------------------------


async def test_options_are_id_and_name_in_name_order():
    crm = LinkCrm()
    crm.data["CPartnerProfile"] = [{"id": "p2", "name": "Zeta Alliance"},
                                   {"id": "p1", "name": "Alpha Chamber"},
                                   {"id": "p3", "name": None}]
    rows = await service.sponsor_options(crm, PARTNER_LINK)
    assert rows == [{"id": "p3", "name": "(unnamed)"},
                    {"id": "p1", "name": "Alpha Chamber"},
                    {"id": "p2", "name": "Zeta Alliance"}]


async def test_a_forbidden_list_degrades_to_read_only_not_empty():
    crm = LinkCrm(forbid_list=["CPartnerProfile"])
    assert await service.sponsor_options(crm, PARTNER_LINK) is None


async def test_options_page_at_two_hundred():
    crm = LinkCrm()
    crm.data["CPartnerProfile"] = [{"id": f"p{i:03}", "name": f"Partner {i:03}"} for i in range(250)]
    rows = await service.sponsor_options(crm, PARTNER_LINK)
    assert len(rows) == 250


# --- reading and writing an event's sponsors ------------------------------------


async def test_event_sponsors_reads_each_live_link_and_marks_unreadable_none():
    crm = LinkCrm(related={
        (cfg.EVENT, "ev1", "partnerProfiles"): [{"id": "p1", "name": "Alpha Chamber"}],
    })
    original = crm.list_related

    async def flaky(entity, record_id, link, **kw):
        if link == "sponsorProfiles":
            raise EspoError("list_related failed: HTTP 403")
        return await original(entity, record_id, link, **kw)
    crm.list_related = flaky
    out = await service.event_sponsors(crm, "ev1", cfg.SPONSOR_LINKS)
    assert out["partnerProfiles"] == [{"id": "p1", "name": "Alpha Chamber"}]
    assert out["sponsorProfiles"] is None


async def test_set_sponsors_is_a_diff_and_ignores_unknown_links():
    crm = LinkCrm(related={
        (cfg.EVENT, "ev1", "partnerProfiles"): [{"id": "p1"}, {"id": "p2"}],
    })
    result = await service.set_event_sponsors(
        crm, "ev1", {"partnerProfiles": ["p2", "p3"], "presenters": ["x"]},
        links=cfg.SPONSOR_LINKS,
    )
    assert crm.relates == [(cfg.EVENT, "ev1", "partnerProfiles", "p3")]
    assert crm.unrelates == [(cfg.EVENT, "ev1", "partnerProfiles", "p1")]
    assert result == {"partnerProfiles": {"added": 1, "removed": 1}}
    # Re-saving the same set writes nothing.
    crm.relates.clear(); crm.unrelates.clear()
    await service.set_event_sponsors(
        crm, "ev1", {"partnerProfiles": ["p2", "p3"]}, links=cfg.SPONSOR_LINKS)
    assert crm.relates == [] and crm.unrelates == []


async def test_set_sponsors_only_writes_live_links():
    crm = LinkCrm()
    await service.set_event_sponsors(
        crm, "ev1", {"partnerProfiles": ["p1"]}, links=(FUNDER_LINK,))
    assert crm.relates == []


async def test_a_foreign_record_denial_is_retried_as_the_admin_only():
    crm = LinkCrm()
    crm.deny_foreign = True
    admin = LinkCrm()
    calls = []

    async def factory():
        calls.append("admin")
        return admin
    await service.set_event_sponsors(
        crm, "ev1", {"partnerProfiles": ["p1"]}, links=cfg.SPONSOR_LINKS,
        admin_factory=factory)
    assert calls == ["admin"]
    assert admin.relates == [(cfg.EVENT, "ev1", "partnerProfiles", "p1")]

    # A denial on the EVENT itself is the user's real gate: never escalated.
    crm2 = LinkCrm()
    crm2.deny_entity = True
    with pytest.raises(EspoError):
        await service.set_event_sponsors(
            crm2, "ev1", {"partnerProfiles": ["p1"]}, links=cfg.SPONSOR_LINKS,
            admin_factory=factory)
    assert calls == ["admin"]

    # No admin configured: the user's own error surfaces.
    crm3 = LinkCrm()
    crm3.deny_foreign = True
    with pytest.raises(EspoError):
        await service.set_event_sponsors(
            crm3, "ev1", {"partnerProfiles": ["p1"]}, links=cfg.SPONSOR_LINKS)


# --- the staff endpoints -------------------------------------------------------


def test_fields_endpoint_offers_the_live_pickers(monkeypatch):
    crm = LinkCrm()
    crm.data["CPartnerProfile"] = [{"id": "p1", "name": "Alpha Chamber"}]
    client = build(monkeypatch, user=MARKETING, crm=crm)
    body = client.get("/events/api/fields").json()
    assert [l["name"] for l in body["links"]] == ["partnerProfiles", "sponsorProfiles"]
    assert body["links"][0]["label"] == "Partners"
    assert body["links"][0]["group"] == cfg.SPONSOR_GROUP
    assert body["links"][0]["options"] == [{"id": "p1", "name": "Alpha Chamber"}]
    assert body["links"][1]["options"] == []


def test_fields_endpoint_without_the_partner_link_offers_funders_only(monkeypatch):
    crm = LinkCrm(links={"sponsorProfiles": BOTH_LINKS["sponsorProfiles"]})
    client = build(monkeypatch, user=MARKETING, crm=crm)
    body = client.get("/events/api/fields").json()
    assert [l["name"] for l in body["links"]] == ["sponsorProfiles"]


def test_event_detail_carries_its_sponsors(monkeypatch):
    crm = LinkCrm(
        events=[make_event(id="ev1")],
        related={(cfg.EVENT, "ev1", "sponsorProfiles"): [{"id": "s1", "name": "Big Bank"}]},
    )
    client = build(monkeypatch, user=MARKETING, crm=crm)
    body = client.get("/events/api/events/ev1").json()
    assert body["sponsors"] == {"partnerProfiles": [],
                                "sponsorProfiles": [{"id": "s1", "name": "Big Bank"}]}


def test_put_sponsors_relates_and_reports(monkeypatch):
    crm = LinkCrm(events=[make_event(id="ev1")])
    client = build(monkeypatch, user=MARKETING, crm=crm)
    resp = client.put("/events/api/events/ev1/sponsors",
                      json={"links": {"partnerProfiles": ["p1", "p2"]}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["changes"] == {"partnerProfiles": {"added": 2, "removed": 0}}
    assert sorted(r["id"] for r in body["sponsors"]["partnerProfiles"]) == ["p1", "p2"]
    assert crm.relates == [(cfg.EVENT, "ev1", "partnerProfiles", "p1"),
                           (cfg.EVENT, "ev1", "partnerProfiles", "p2")]


def test_put_sponsors_names_the_missing_grant(monkeypatch):
    crm = LinkCrm(events=[make_event(id="ev1")])
    crm.deny_entity = True
    client = build(monkeypatch, user=MARKETING, crm=crm)
    resp = client.put("/events/api/events/ev1/sponsors",
                      json={"links": {"partnerProfiles": ["p1"]}})
    assert resp.status_code == 403


# --- the rollup behind the partner / funder Events tab ---------------------------


def _world():
    events = [
        make_event(id="e1", name="Spring Workshop", dateStart="2026-03-10 16:00:00",
                   status="Held"),
        make_event(id="e2", name="Summer Webinar", dateStart="2026-06-10 16:00:00",
                   status="Held"),
    ]
    regs = [
        _reg("r1", "e1", "c1"),                              # attended, later a client
        _reg("r2", "e1", "c2", status=cfg.REG_NO_SHOW),      # registered, absent
        _reg("r3", "e1", "c3", status=cfg.REG_CANCELLED),    # not a registration
        _reg("r4", "e2", "c1"),                              # same person again
        _reg("r5", "e2", "c4"),                              # attended, never a client
        _reg("r6", "e2", "c5", status=cfg.REG_REGISTERED),   # upcoming / unresolved
    ]
    engagements = [
        {"id": "g1", "primaryEngagementContactId": "c1", "createdAt": "2026-04-01 12:00:00"},  # after e1, before e2
        {"id": "g2", "primaryEngagementContactId": "c4", "createdAt": "2026-01-01 12:00:00"},  # BEFORE e2: not a conversion
    ]
    related = {("CPartnerProfile", "P1", "sponsoredEvents"): events}
    crm = LinkCrm(events=events, registrations=regs, engagements=engagements,
                  related=related)
    crm.data["CPartnerProfile"] = [{"id": "P1", "name": "Alpha Chamber"}]
    crm.data["CSponsorProfile"] = [{"id": "S1", "name": "Big Bank"}]
    return crm


async def test_rollup_counts_per_event_with_the_conversion_rule():
    out = await reporting.sponsor_rollup(_world(), "CPartnerProfile", "P1", "sponsoredEvents")
    assert out["available"] is True
    rows = {r["id"]: r for r in out["events"]}
    assert [r["id"] for r in out["events"]] == ["e2", "e1"]      # newest first
    assert rows["e1"]["registered"] == 2 and rows["e1"]["attended"] == 1
    assert rows["e1"]["clients"] == 1                             # c1's engagement postdates e1
    assert rows["e2"]["registered"] == 3 and rows["e2"]["attended"] == 2
    assert rows["e2"]["clients"] == 0   # c1's engagement predates e2; c4's predates too
    assert rows["e1"]["status"] == "Held"
    assert out["totals"] == {"events": 2, "registered": 5, "attended": 3, "clients": 1}


async def test_rollup_de_duplicates_clients_across_events():
    crm = _world()
    # Give c1 a second engagement after e2 too: still ONE client in the totals.
    crm.data["CEngagement"].append(
        {"id": "g3", "primaryEngagementContactId": "c1", "createdAt": "2026-07-01 12:00:00"})
    out = await reporting.sponsor_rollup(crm, "CPartnerProfile", "P1", "sponsoredEvents")
    rows = {r["id"]: r for r in out["events"]}
    assert rows["e1"]["clients"] == 1 and rows["e2"]["clients"] == 1
    assert out["totals"]["clients"] == 1


async def test_rollup_renders_an_unreadable_count_as_none_never_zero():
    crm = _world()
    original = crm.list

    async def no_engagements(entity, **kw):
        if entity == "CEngagement":
            raise EspoError("list CEngagement failed: HTTP 403")
        return await original(entity, **kw)
    crm.list = no_engagements
    out = await reporting.sponsor_rollup(crm, "CPartnerProfile", "P1", "sponsoredEvents")
    assert all(r["clients"] is None for r in out["events"])
    assert out["events"][0]["attended"] == 2          # registrations still counted
    assert out["totals"]["clients"] is None and out["totals"]["attended"] == 3

    crm2 = _world()
    crm2.forbid_list.add(cfg.REGISTRATION)
    out = await reporting.sponsor_rollup(crm2, "CPartnerProfile", "P1", "sponsoredEvents")
    assert all(r["registered"] is None and r["clients"] is None for r in out["events"])
    assert out["totals"] == {"events": 2, "registered": None, "attended": None, "clients": None}


async def test_rollup_with_no_events_is_empty_not_an_error():
    out = await reporting.sponsor_rollup(LinkCrm(), "CPartnerProfile", "P9", "sponsoredEvents")
    assert out == {"available": True, "events": [],
                   "totals": {"events": 0, "registered": 0, "attended": 0, "clients": 0}}


# --- the tab and the endpoint on the three domains -------------------------------


def test_events_tab_is_on_partner_and_funder_before_communications():
    for domain in (PARTNER, SPONSOR):
        keys = [t["key"] for t in _detail_tabs(domain)]
        assert "sponsoredEvents" in keys
        assert keys.index("sponsoredEvents") == keys.index("communications") - 1
    # The mentor domain keeps the OTHER events tab (the engagement rollup).
    mentor_keys = [t["key"] for t in _detail_tabs(MENTOR)]
    assert "sponsoredEvents" not in mentor_keys and "events" in mentor_keys


def _sessions_app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    get_settings.cache_clear()
    return create_app([info_request.SPEC])


_BOSS = {"userId": "u1", "userName": "boss", "name": "The Boss", "isAdmin": True, "token": "tok"}


def _as(monkeypatch, crm, system=None):
    monkeypatch.setattr("sessions.router.current_user", lambda request, key=None: _BOSS)
    monkeypatch.setattr("sessions.router.client_for", lambda settings, u: crm)
    # The counts run under the org-wide key; None (the test default, dry-run)
    # falls back to the user's client.
    monkeypatch.setattr("sessions.router._system_client", lambda settings: system)


def test_sponsored_events_endpoint_on_partner_and_funder(monkeypatch):
    _as(monkeypatch, _world())
    with TestClient(_sessions_app(monkeypatch)) as c:
        r = c.get("/partnersessions/api/records/P1/sponsoredevents")
        assert r.status_code == 200
        assert r.json()["totals"]["events"] == 2
        # The funder route exists too (a different record, so no rows).
        r = c.get("/sponsorsessions/api/records/S1/sponsoredevents")
        assert r.status_code == 200 and r.json()["events"] == []
        # Never on the mentor domain — falls through to the static mount.
        assert c.get("/mentorsessions/api/records/E1/sponsoredevents").status_code in (404, 405)


def test_counts_run_under_the_org_wide_key_after_the_user_reads_the_parent(monkeypatch):
    """The Partner Manager and Sponsor Manager roles cannot read events or
    registrations, so the rollup runs under the org-wide key — but only once
    the user's own client has read the parent record."""
    user_crm = LinkCrm()                         # can read the parent, nothing else
    user_crm.data["CPartnerProfile"] = [{"id": "P1", "name": "Alpha Chamber"}]
    user_crm.forbid_list.update({cfg.REGISTRATION, cfg.EVENT})
    _as(monkeypatch, user_crm, system=_world())
    with TestClient(_sessions_app(monkeypatch)) as c:
        body = c.get("/partnersessions/api/records/P1/sponsoredevents").json()
        assert body["totals"]["events"] == 2 and body["totals"]["attended"] == 3
        # A parent the user cannot see is a 404, whatever the org key could read.
        assert c.get("/partnersessions/api/records/P404/sponsoredevents").status_code == 404


def test_sponsored_events_endpoint_explains_a_crm_without_the_link(monkeypatch):
    crm = LinkCrm(links={})
    crm.data["CPartnerProfile"] = [{"id": "P1", "name": "Alpha Chamber"}]
    _as(monkeypatch, crm)
    with TestClient(_sessions_app(monkeypatch)) as c:
        body = c.get("/partnersessions/api/records/P1/sponsoredevents").json()
    assert body["available"] is False
    assert "sponsoredEvents" in body["reason"] and body["events"] == []


# --- the two frontends ----------------------------------------------------------


def test_editor_treats_links_as_relationships_not_fields():
    from pathlib import Path
    source = (Path(__file__).resolve().parent.parent / "events" / "frontend" / "app.js").read_text()
    assert 'if (type === "link") return;' in source       # collectForm skips them
    assert '"/sponsors"' in source                         # they go to their own endpoint
    assert "sponsorshipGroup(host, raw)" in source


def test_sessions_page_has_the_events_panel_with_the_org_token():
    from pathlib import Path
    page = (Path(__file__).resolve().parent.parent / "sessions" / "frontend" / "index.html").read_text()
    assert 'data-dpanel="sponsoredEvents"' in page
    assert "{{abbr}} event is linked" in page
