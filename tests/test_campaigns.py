"""Marketing Management, Phase 1 (prds/prospect-marketing/build-plan.md).

The boundaries: who may reach the staff API and when the switch is off; what a
link resolve does and never does (no CRM call, same 404 for every reason, a
retired link still opens and counts late); the postcard selection and the
sign-off gate; the import plan's outcomes; the landing page's scan write and the
response orchestrator's promotion rules; the dry-run vendor and the event
signature.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient

from campaigns import config as cfg
from campaigns import imports, postcard, service
from campaigns.public import destination_path
from campaigns.tokens import looks_like_token, new_link_token, new_scan_token
from core.app import create_app
from core.config import Settings, get_settings
from core.postal import (
    Address, DryRunPostalClient, PostalSignatureError, estimated_cost, sign_event,
)
from forms import ALL_SPECS
from forms.prospect_response.orchestrator import orchestrate as respond
from forms.prospect_response.schemas import ProspectResponse

MARKETING = {"userName": "mark", "name": "Mark Marketing", "userId": "u-1",
             "token": "t", "isAdmin": False, "teams": ["Marketing Admin Team"]}
OUTSIDER = {"userName": "sally", "name": "Sally Sponsor", "userId": "u-2",
            "token": "t", "isAdmin": False, "teams": ["Sponsor Management Team"]}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- fakes -------------------------------------------------------------------------------

class FakeCrm:
    """Enough of EspoClient for the campaigns code: records by entity, where
    clauses of type equals / in, metadata for the three entities, relate and
    unrelate on a campaign."""

    def __init__(self, *, with_entities: bool = True):
        self.rows: dict[str, dict[str, dict[str, Any]]] = {}
        self.created: list[tuple[str, dict]] = []
        self.updated: list[tuple[str, str, dict]] = []
        self.related: dict[tuple[str, str, str], set[str]] = {}
        self.with_entities = with_entities
        self.with_sms_field = True
        self._n = 0

    def add(self, entity: str, row: dict[str, Any]) -> dict[str, Any]:
        self._n += 1
        row = {"id": row.get("id") or f"{entity.lower()}-{self._n}", **row}
        self.rows.setdefault(entity, {})[row["id"]] = row
        return row

    async def metadata(self, key: str):
        if key.startswith("scopes."):
            entity = key.split(".", 1)[1]
            if entity in (cfg.PROSPECT, cfg.CAMPAIGN, cfg.TOUCH):
                return {"entity": True, "isCustom": True} if self.with_entities else None
            return {"entity": True}
        if key == f"entityDefs.{cfg.CAMPAIGN}.links":
            return {cfg.LINK_PARTNERS: {"type": "hasMany"}, cfg.LINK_EVENTS: {"type": "hasMany"},
                    cfg.LINK_TOUCHES: {"type": "hasMany"}} if self.with_entities else {}
        if key == f"entityDefs.{cfg.CAMPAIGN}.fields":
            return {"campaignKind": {"options": ["Postcard", "Email", "SMS", "Call", "Social media"]},
                    "platform": {"options": ["", "Meta", "YouTube"]},
                    "campaignStatus": {"options": ["Draft", "Awaiting sign-off", "Signed off", "Running", "Complete", "Cancelled"]},
                    "postcardSize": {"options": ["", "4x6", "6x9", "6x11"]},
                    **({"smsMessage": {"type": "text"}} if self.with_sms_field else {})}
        if key == f"entityDefs.{cfg.PROSPECT}.fields":
            return {"leadStatus": {"options": list(cfg.LEAD_STATUSES)}, "leadStatusChangedAt": {"type": "datetime"},
                    "leadSource": {"options": ["", "State filing", "List", "Partner file"]},
                    "sideExit": {"options": ["", "Duplicate", "Stale", "Already known"]},
                    "addressStatus": {"options": ["Usable", "Dead"]}}
        return None

    async def metadata_enum_options(self, entity, field):
        if entity == "Account" and field == "cCompanyType":
            return ["Client", "Sponsor", "Partner", "Other", "Prospect"]
        return None

    def _match(self, row, clause) -> bool:
        t, attr, val = clause.get("type"), clause.get("attribute"), clause.get("value")
        if t == "equals":
            return row.get(attr) == val
        if t == "in":
            return row.get(attr) in (val or [])
        if t == "isNull":
            return row.get(attr) in (None, "")
        if t == "isNotNull":
            return row.get(attr) not in (None, "")
        if t == "contains":
            return str(val).lower() in str(row.get(attr) or "").lower()
        return True

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0, order_by=None, order=None):
        rows = [r for r in self.rows.get(entity, {}).values() if all(self._match(r, c) for c in (where or []))]
        return {"total": len(rows), "list": rows[offset: offset + max_size]}

    async def list_related(self, entity, record_id, link, *, select=None, max_size=200):
        ids = self.related.get((entity, record_id, link), set())
        foreign = {cfg.LINK_PARTNERS: "CPartnerProfile", cfg.LINK_EVENTS: "CEvent", cfg.LINK_TOUCHES: cfg.TOUCH}.get(link, "")
        rows = [self.rows.get(foreign, {}).get(i, {"id": i, "name": i}) for i in sorted(ids)]
        return {"total": len(rows), "list": rows}

    async def get(self, entity, record_id, select=None):
        return dict(self.rows.get(entity, {}).get(record_id) or {})

    async def find_one(self, entity, attribute, value, select="id"):
        for r in self.rows.get(entity, {}).values():
            if r.get(attribute) == value:
                return r
        return None

    async def create(self, entity, payload):
        row = self.add(entity, dict(payload))
        self.created.append((entity, payload))
        return row

    async def update(self, entity, record_id, payload):
        self.rows.setdefault(entity, {}).setdefault(record_id, {"id": record_id}).update(payload)
        self.updated.append((entity, record_id, payload))
        return self.rows[entity][record_id]

    async def relate(self, entity, record_id, link, related_id):
        self.related.setdefault((entity, record_id, link), set()).add(related_id)

    async def unrelate(self, entity, record_id, link, related_id):
        self.related.setdefault((entity, record_id, link), set()).discard(related_id)


class FakeStore:
    """The campaign store, in memory."""

    def __init__(self):
        self.links: dict[str, dict] = {}
        self.visits: list[dict] = []
        self.batches: dict[str, dict] = {}
        self.rows: list[dict] = []

    async def create_link(self, **kw):
        row = {"id": f"l-{len(self.links) + 1}", "token": new_link_token(), "state": cfg.LINK_ACTIVE,
               "history": [], "retired_by": None, "retired_at": None, **kw}
        self.links[row["id"]] = row
        return row

    async def get_link(self, link_id): return self.links.get(link_id)
    async def get_link_by_token(self, token):
        return next((l for l in self.links.values() if l["token"] == token), None)
    async def list_links(self, campaign_id):
        return [l for l in self.links.values() if l["campaign_id"] == campaign_id]
    async def landing_link(self, campaign_id):
        return next((l for l in self.links.values() if l["campaign_id"] == campaign_id and l["destination_kind"] == cfg.DEST_LANDING), None)
    async def correct_destination(self, link_id, **kw):
        l = self.links[link_id]; l.update(destination_kind=kw["destination_kind"], destination_target=kw["destination_target"], destination_slug=kw["destination_slug"]); return l
    async def refresh_slug(self, link_id, slug): self.links[link_id]["destination_slug"] = slug
    async def set_state(self, link_id, state, actor): self.links[link_id]["state"] = state; return self.links[link_id]
    async def record_visit(self, link, *, address, user_agent, salt, scan_token=None):
        self.visits.append({"link_id": link["id"], "late": link["state"] == cfg.LINK_RETIRED, "scan": scan_token})
    async def visit_counts(self, ids):
        out = {i: {"visits": 0, "late": 0, "scans": 0} for i in ids}
        for v in self.visits:
            if v["link_id"] in out:
                out[v["link_id"]]["visits"] += 1; out[v["link_id"]]["late"] += int(v["late"]); out[v["link_id"]]["scans"] += int(bool(v["scan"]))
        return out
    async def submissions_by_link(self, tokens): return {t: {} for t in tokens}
    async def recent_submissions(self, campaign_id, limit=50): return []
    async def find_batch_by_file(self, sha): return None
    async def get_batch(self, batch_id): return self.batches.get(batch_id)
    async def create_batch(self, **kw):
        row = {"id": f"b-{len(self.batches) + 1}", "status": "planned", "applied_at": None, **kw}
        self.batches[row["id"]] = row; return row
    async def mark_applied(self, batch_id, result): self.batches[batch_id].update(status="applied", result=result)
    async def known_row_hashes(self, hashes): return {r["row_hash"] for r in self.rows if r["row_hash"] in set(hashes)}
    async def record_rows(self, batch_id, rows): self.rows.extend(rows)
    async def recent_batches(self, limit=25): return list(self.batches.values())


def build(monkeypatch, user=None, crm=None, store=None, enabled="true"):
    monkeypatch.setenv("CAMPAIGNS_ENABLED", enabled)
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("ESPO_DRY_RUN", "true")
    get_settings.cache_clear()
    app = create_app(ALL_SPECS)
    app.state.campaign_store = store
    import campaigns.router as router_mod
    monkeypatch.setattr(router_mod, "current_user", lambda request: user)
    if crm is not None:
        monkeypatch.setattr(router_mod, "client_for", lambda settings, u: crm)

    async def _no_log(*a, **kw):
        return None
    monkeypatch.setattr(router_mod, "record_action", _no_log)
    return TestClient(app)


# --- the gate ---------------------------------------------------------------------------------

def test_signed_out_is_401(monkeypatch):
    assert build(monkeypatch, user=None).get("/campaigns/api/session").status_code == 401


def test_wrong_team_gets_a_caller_only_session_and_every_other_door_stays_shut(monkeypatch):
    """Ruling 114: a caller from another team opens Marketing Management and
    sees the Calls tab alone. /session says so; nothing else opens."""
    client = build(monkeypatch, user=OUTSIDER)
    resp = client.get("/campaigns/api/session")
    assert resp.status_code == 200
    body = resp.json()
    assert body["callerOnly"] is True and body["callsOn"] is False
    assert body["name"] == "Sally Sponsor" and "available" not in body
    for path in ("/campaigns/api/campaigns", "/campaigns/api/fields", "/campaigns/api/prospects", "/campaigns/api/prospects/imports"):
        resp = client.get(path)
        assert resp.status_code == 403, path
        assert "Marketing Admin Team" in resp.json()["detail"]


def test_a_team_member_is_not_caller_only(monkeypatch):
    body = build(monkeypatch, user=MARKETING).get("/campaigns/api/session").json()
    assert body["callerOnly"] is False and "available" in body


def test_switch_off_is_404_per_request(monkeypatch):
    client = build(monkeypatch, user=MARKETING, enabled="false")
    assert client.get("/campaigns/api/session").status_code == 404
    assert client.get("/c/abcdefgh", follow_redirects=False).status_code == 404
    assert client.get("/api/campaigns/public/abc123").status_code == 404


def test_marketing_admin_session_reports_availability(monkeypatch):
    client = build(monkeypatch, user=MARKETING, crm=FakeCrm(), store=FakeStore())
    body = client.get("/campaigns/api/session").json()
    assert body["name"] == "Mark Marketing"
    assert body["available"] is True
    assert body["storeAvailable"] is True
    assert body["postal"]["provider"] == "dryrun"


def test_crm_without_the_entities_reads_unavailable(monkeypatch):
    client = build(monkeypatch, user=MARKETING, crm=FakeCrm(with_entities=False))
    body = client.get("/campaigns/api/session").json()
    assert body["available"] is False
    assert "CProspect" in body["reason"]


def test_portal_tile_follows_the_switch(monkeypatch):
    from portal.router import _apps_for
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    monkeypatch.setenv("CAMPAIGNS_ENABLED", "true")
    get_settings.cache_clear()
    titles = [a["title"] for a in _apps_for(MARKETING, get_settings())]
    assert "Marketing Management" in titles
    assert "Marketing Management" not in [a["title"] for a in _apps_for(OUTSIDER, get_settings())]
    monkeypatch.setenv("CAMPAIGNS_ENABLED", "false")
    get_settings.cache_clear()
    assert "Marketing Management" not in [a["title"] for a in _apps_for(MARKETING, get_settings())]


# --- links and the resolve (§ 3.7) ----------------------------------------------------------------

def test_tokens_have_no_ambiguous_glyphs():
    for _ in range(50):
        t = new_link_token()
        assert len(t) == 8 and looks_like_token(t)
        assert not set(t) & set("01OIl")
    assert len(new_scan_token()) == 12
    assert not looks_like_token("abc")
    assert not looks_like_token("has space")


def test_destination_paths_carry_campaign_and_link():
    link = {"campaign_id": "camp1", "token": "abcdefgh", "destination_kind": cfg.DEST_FORM, "destination_target": "client-intake"}
    assert destination_path(link) == "/client-intake/?campaign=camp1&link=abcdefgh"
    link["destination_kind"] = cfg.DEST_PROGRAMME
    assert destination_path(link) == "/webinars/?campaign=camp1&link=abcdefgh"
    link["destination_kind"] = cfg.DEST_EVENT; link["destination_slug"] = "oct-webinar"
    assert destination_path(link) == "/webinars/oct-webinar?campaign=camp1&link=abcdefgh"
    link["destination_slug"] = None
    assert destination_path(link) == "/webinars/?campaign=camp1&link=abcdefgh"
    link["destination_kind"] = cfg.DEST_LANDING
    assert destination_path(link) is None                      # a card's code is needed
    assert destination_path(link, scan_token="23456789abcd") == "/p/23456789abcd?link=abcdefgh"
    link["destination_kind"] = cfg.DEST_FORM; link["destination_target"] = "not-a-form"
    assert destination_path(link) is None


def test_resolve_counts_the_visit_and_redirects_302(monkeypatch):
    store = FakeStore()
    client = build(monkeypatch, user=None, store=store)
    link = asyncio.run(store.create_link(campaign_id="camp1", name="Post", destination_kind=cfg.DEST_FORM,
                                         destination_target="info-request", destination_slug=None, created_by="t"))
    resp = client.get(f"/c/{link['token']}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == f"/info-request/?campaign=camp1&link={link['token']}"
    assert resp.headers["cache-control"] == "no-store"
    assert len(store.visits) == 1 and store.visits[0]["late"] is False


def test_retired_link_still_opens_and_counts_late(monkeypatch):
    store = FakeStore()
    client = build(monkeypatch, user=None, store=store)
    link = asyncio.run(store.create_link(campaign_id="camp1", name="Post", destination_kind=cfg.DEST_PROGRAMME,
                                         destination_target=None, destination_slug=None, created_by="t"))
    asyncio.run(store.set_state(link["id"], cfg.LINK_RETIRED, "t"))
    resp = client.get(f"/c/{link['token']}", follow_redirects=False)
    assert resp.status_code == 302
    assert store.visits[0]["late"] is True


def test_unknown_malformed_and_cardless_landing_tokens_404_alike(monkeypatch):
    store = FakeStore()
    client = build(monkeypatch, user=None, store=store)
    landing = asyncio.run(store.create_link(campaign_id="camp1", name="Landing", destination_kind=cfg.DEST_LANDING,
                                            destination_target=None, destination_slug=None, created_by="t"))
    answers = {
        client.get("/c/zzzzzzzz", follow_redirects=False).json()["detail"],
        client.get("/c/bad!token", follow_redirects=False).json()["detail"],
        client.get(f"/c/{landing['token']}", follow_redirects=False).json()["detail"],
    }
    assert answers == {"Not found"}
    card = client.get(f"/c/{landing['token']}/23456789abcd", follow_redirects=False)
    assert card.status_code == 302 and card.headers["location"] == f"/p/23456789abcd?link={landing['token']}"
    assert store.visits[-1]["scan"] == "23456789abcd"
    png = client.get(f"/c/{landing['token']}/23456789abcd/qr.png")
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"
    assert png.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_staff_link_crud_and_counts(monkeypatch):
    crm = FakeCrm(); store = FakeStore()
    camp = crm.add(cfg.CAMPAIGN, {"name": "Social October", "campaignKind": "Social media", "campaignStatus": "Draft"})
    client = build(monkeypatch, user=MARKETING, crm=crm, store=store)
    made = client.post(f"/campaigns/api/campaigns/{camp['id']}/links", json={"name": "Facebook post", "kind": "form", "target": "client-intake"})
    assert made.status_code == 200
    link = made.json()["link"]
    assert made.json()["shortUrl"].endswith("/c/" + link["token"])
    bad = client.post(f"/campaigns/api/campaigns/{camp['id']}/links", json={"name": "x", "kind": "form", "target": "nope"})
    assert bad.status_code == 400
    client.get(f"/c/{link['token']}", follow_redirects=False)
    listed = client.get(f"/campaigns/api/campaigns/{camp['id']}/links").json()["links"]
    assert listed[0]["counts"]["visits"] == 1 and listed[0]["state"] == "active"
    corrected = client.put(f"/campaigns/api/campaigns/{camp['id']}/links/{link['id']}", json={"kind": "programme"})
    assert corrected.json()["link"]["destination_kind"] == "programme"
    retired = client.post(f"/campaigns/api/campaigns/{camp['id']}/links/{link['id']}/retire")
    assert retired.json()["link"]["state"] == "retired"
    qr = client.get(f"/campaigns/api/campaigns/{camp['id']}/links/{link['id']}/qr.png")
    assert qr.status_code == 200 and qr.headers["content-type"] == "image/png"


# --- campaigns (§ 3.1, § 3.6) -----------------------------------------------------------------------

def test_create_campaign_whitelists_and_refuses_unbuilt_kinds(monkeypatch):
    crm = FakeCrm()
    client = build(monkeypatch, user=MARKETING, crm=crm, store=FakeStore())
    refused = client.post("/campaigns/api/campaigns", json={"changes": {"name": "Calls", "campaignKind": "Call"}})
    assert refused.status_code == 400 and "not built yet" in refused.json()["detail"]
    nameless = client.post("/campaigns/api/campaigns", json={"changes": {"campaignKind": "Postcard"}})
    assert nameless.status_code == 400
    made = client.post("/campaigns/api/campaigns", json={
        "changes": {"name": "Filings Nov", "campaignKind": "Postcard", "platform": "Meta", "pieceCount": 99, "campaignStatus": "Running"},
        "partnerIds": ["p-1"], "eventIds": [],
    })
    assert made.status_code == 200
    created = crm.created[0][1]
    assert created["campaignStatus"] == "Draft"          # the application moves it
    assert "pieceCount" not in created                    # not in the whitelist
    assert created["platform"] is None                    # social media only
    assert created["assignedUserId"] == "u-1"
    assert crm.related[(cfg.CAMPAIGN, made.json()["campaign"]["id"], cfg.LINK_PARTNERS)] == {"p-1"}


def test_manual_status_moves_per_kind():
    social = {"campaignKind": "Social media", "campaignStatus": "Draft"}
    assert set(service.manual_moves(social)) == {"Running", "Cancelled"}
    postcard_signed = {"campaignKind": "Postcard", "campaignStatus": "Signed off"}
    assert service.manual_moves(postcard_signed) == ("Cancelled",)
    running = {"campaignKind": "Postcard", "campaignStatus": "Running"}
    assert service.manual_moves(running) == ()


def test_advance_stage_is_advance_only():
    # The stages after first contact (ruling 50): Prospect · Engaged · Opportunity.
    assert service.advance_stage("Prospect", "Engaged") == "Engaged"
    assert service.advance_stage("Engaged", "Prospect") is None
    assert service.advance_stage("Opportunity", "Engaged") is None
    assert service.advance_stage(None, "Prospect") == "Prospect"
    assert service.advance_stage("Prospect", "Client") is None    # never stored
    assert service.advance_stage("Prospect", "Qualified") is None # a lead status, not a stage


def test_address_text_round_trip():
    p = {"mailingAddressStreet": "100 Public Sq", "mailingAddressCity": "Cleveland", "mailingAddressState": "OH",
         "mailingAddressPostalCode": "44113", "mailingAddressCountry": ""}
    text = service.mailing_address_text(p)
    assert text == "100 Public Sq\nCleveland, OH 44113"
    back = service.parse_address_text(text)
    assert back == {"street": "100 Public Sq", "city": "Cleveland", "state": "OH", "postalCode": "44113", "country": ""}


# --- the postcard kind (§ 3.2) ------------------------------------------------------------------------

def _prospect(crm, name, *, stage="Qualified", exit_=None, address=True, status="Usable"):
    """A lead; ``stage`` is its lead status (the helper's old name kept)."""
    row = {"name": name, "businessName": name, "leadStatus": stage, "addressStatus": status, "sideExit": exit_}
    if address:
        row.update(mailingAddressStreet="1 Main St", mailingAddressCity="Cleveland", mailingAddressState="OH", mailingAddressPostalCode="44113")
    return crm.add(cfg.PROSPECT, row)


def test_selection_applies_rulings_10_14_15_and_44():
    crm = FakeCrm()
    a = _prospect(crm, "Acme")
    _prospect(crm, "Unqualified one", stage="Unqualified")
    _prospect(crm, "Dead address", status="Dead")
    _prospect(crm, "Duplicate", exit_="Duplicate")
    _prospect(crm, "No address", address=False)
    _prospect(crm, "Disqualified", stage="Disqualified")
    _prospect(crm, "Converted", stage="Converted")
    carded = _prospect(crm, "Carded")
    crm.add(cfg.TOUCH, {"channel": "Postcard", "touchStatus": "Sent", "prospectId": carded["id"]})
    crm.add("Account", {"name": "Prospect Co", "cCompanyType": ["Prospect"], "cFunnelStage": "Prospect",
                        "billingAddressStreet": "2 Main", "billingAddressCity": "Akron", "billingAddressState": "OH", "billingAddressPostalCode": "44308"})
    crm.add("Account", {"name": "Plain Client", "cCompanyType": ["Client"], "cFunnelStage": "Prospect",
                        "billingAddressStreet": "3 Main", "billingAddressCity": "Akron", "billingAddressState": "OH", "billingAddressPostalCode": "44308"})
    # Ruling 44: the default reaches Unqualified and Qualified leads, and no Company.
    targets = asyncio.run(postcard.select_targets(crm, None))
    assert sorted(t["name"] for t in targets) == ["Acme", "Unqualified one"]
    assert {t["stage"] for t in targets} == {"Qualified", "Unqualified"}
    # Companies typed Prospect (already contacted) only when asked for.
    with_co = asyncio.run(postcard.select_targets(crm, {"statuses": ["Qualified"], "stages": ["Prospect"]}))
    assert sorted(t["name"] for t in with_co) == ["Acme", "Prospect Co"]
    # A card already sent to a converted lead's Company counts for the lead too.
    linked = crm.add("Account", {"name": "Linked Co", "cCompanyType": ["Prospect"], "cFunnelStage": "Prospect",
                                 "billingAddressStreet": "9 Main", "billingAddressCity": "Akron", "billingAddressState": "OH", "billingAddressPostalCode": "44308"})
    crm.rows[cfg.PROSPECT][a["id"]]["promotedCompanyId"] = linked["id"]
    crm.add(cfg.TOUCH, {"channel": "Postcard", "touchStatus": "Sent", "companyId": linked["id"]})
    third = asyncio.run(postcard.select_targets(crm, {"statuses": ["Qualified"]}))
    assert sorted(t["name"] for t in third) == []
    # ...and a card to the lead counts for its Company (one card per business, ever).
    crm.add(cfg.TOUCH, {"channel": "Postcard", "touchStatus": "Sent", "prospectId": carded["id"]})
    other = crm.add("Account", {"name": "Carded Co", "cCompanyType": ["Prospect"], "cFunnelStage": "Prospect",
                                "billingAddressStreet": "8 Main", "billingAddressCity": "Akron", "billingAddressState": "OH", "billingAddressPostalCode": "44308"})
    crm.rows[cfg.PROSPECT][carded["id"]]["promotedCompanyId"] = other["id"]
    cos = asyncio.run(postcard.select_targets(crm, {"statuses": [], "stages": ["Prospect"]}))
    assert sorted(t["name"] for t in cos) == ["Prospect Co"]


def test_build_list_reconciles_planned_touches_and_moves_draft_to_awaiting():
    crm = FakeCrm()
    camp = crm.add(cfg.CAMPAIGN, {"name": "Nov cards", "campaignKind": "Postcard", "campaignStatus": "Draft"})
    a = _prospect(crm, "Acme"); b = _prospect(crm, "Beta")
    settings = Settings(_env_file=None)
    first = asyncio.run(postcard.build_list(crm, crm, camp, None, settings))
    assert first["pieces"] == 2 and first["created"] == 2
    assert crm.rows[cfg.CAMPAIGN][camp["id"]]["campaignStatus"] == "Awaiting sign-off"
    assert "Qualified" in crm.rows[cfg.CAMPAIGN][camp["id"]]["selectionSummary"]
    # Beta leaves the ladder; the rebuild cancels its Planned row and keeps Acme's.
    crm.rows[cfg.PROSPECT][b["id"]]["sideExit"] = "Stale"
    camp = crm.rows[cfg.CAMPAIGN][camp["id"]]
    second = asyncio.run(postcard.build_list(crm, crm, camp, None, settings))
    assert second == {**second, "pieces": 1, "created": 0, "kept": 1, "cancelled": 1}
    statuses = sorted(t["touchStatus"] for t in crm.rows[cfg.TOUCH].values())
    assert statuses == ["Cancelled", "Planned"]


def test_sign_off_needs_the_typed_count_and_stamps_the_campaign(monkeypatch):
    crm = FakeCrm()
    camp = crm.add(cfg.CAMPAIGN, {"name": "Nov cards", "campaignKind": "Postcard", "campaignStatus": "Awaiting sign-off"})
    for n in range(3):
        crm.add(cfg.TOUCH, {"channel": "Postcard", "touchStatus": "Planned", "outreachCampaignId": camp["id"]})
    monkeypatch.setenv("DATABASE_URL", "postgresql://x/y")
    settings = Settings(_env_file=None, database_url="postgresql://x/y", postal_provider="lob", postal_api_key="k", postal_unit_cost=0.95)
    with pytest.raises(service.CampaignError):
        asyncio.run(postcard.sign_off(crm, crm, camp, confirm="2", user_name="Mark", settings=settings))
    updated = asyncio.run(postcard.sign_off(crm, crm, camp, confirm="3", user_name="Mark", settings=settings))
    assert updated["campaignStatus"] == "Signed off"
    assert updated["pieceCount"] == 3 and updated["estimatedCost"] == 2.85 and updated["estimatedCostCurrency"] == "USD"
    assert updated["signedOffByName"] == "Mark"


def test_run_mails_each_planned_touch_once_and_completes():
    crm = FakeCrm(); store = FakeStore(); vendor = DryRunPostalClient()
    camp = crm.add(cfg.CAMPAIGN, {"name": "Nov cards", "campaignKind": "Postcard", "campaignStatus": "Signed off"})
    a = _prospect(crm, "Acme"); none = _prospect(crm, "No address", address=False)
    t1 = crm.add(cfg.TOUCH, {"channel": "Postcard", "touchStatus": "Planned", "outreachCampaignId": camp["id"], "prospectId": a["id"]})
    t2 = crm.add(cfg.TOUCH, {"channel": "Postcard", "touchStatus": "Planned", "outreachCampaignId": camp["id"], "prospectId": none["id"]})
    settings = Settings(_env_file=None, app_base_url="https://apps.example.org")
    totals = asyncio.run(postcard.run_campaign(crm, camp, vendor=vendor, store=store, settings=settings))
    assert totals == {"sent": 1, "failed": 0, "skipped": 1}
    sent = crm.rows[cfg.TOUCH][t1["id"]]
    assert sent["touchStatus"] == "Sent" and sent["vendorPieceId"] == f"dryrun-{t1['id']}"
    assert looks_like_token(sent["scanToken"]) and "Cleveland, OH 44113" in sent["mailedAddress"]
    assert sent["stageAtTouch"] == "Qualified"     # the lead's status when mailed
    assert crm.rows[cfg.TOUCH][t2["id"]]["touchStatus"] == "Cancelled"
    assert crm.rows[cfg.CAMPAIGN][camp["id"]]["campaignStatus"] == "Complete"
    link = asyncio.run(store.landing_link(camp["id"]))
    assert link is not None and vendor.created[0]["merge_variables"]["card_url"] == f"https://apps.example.org/c/{link['token']}/{sent['scanToken']}"
    assert vendor.created[0]["key"] == t1["id"]                      # the idempotency key is the touch id


def test_returned_event_kills_the_address_and_leaves_the_status():
    crm = FakeCrm()
    p = _prospect(crm, "Acme", stage="Unqualified")
    t = crm.add(cfg.TOUCH, {"touchStatus": "Sent", "vendorPieceId": "psc_1", "prospectId": p["id"]})
    result = asyncio.run(postcard.apply_event(crm, piece_id="psc_1", kind="returned", vendor_status="returned_to_sender"))
    assert result["applied"] is True
    assert crm.rows[cfg.TOUCH][t["id"]]["touchStatus"] == "Returned"
    assert crm.rows[cfg.PROSPECT][p["id"]]["addressStatus"] == "Dead"
    assert crm.rows[cfg.PROSPECT][p["id"]]["leadStatus"] == "Unqualified"
    unknown = asyncio.run(postcard.apply_event(crm, piece_id="psc_nope", kind="delivered", vendor_status="x"))
    assert unknown["applied"] is False


def test_dry_run_vendor_and_event_signature():
    vendor = DryRunPostalClient()
    with pytest.raises(Exception):
        asyncio.run(vendor.create_postcard(idempotency_key="t", to=Address(name="", line1="", city="", state="", postal_code=""),
                                           template="", size="4x6", merge_variables={}, metadata={}))
    body = json.dumps({"event": "returned", "piece_id": "dryrun-t1"}).encode()
    headers = sign_event(body, "secret")
    events = vendor.parse_events(headers=headers, body=body, secret="secret")
    assert events[0].kind == "returned" and events[0].piece_id == "dryrun-t1"
    with pytest.raises(PostalSignatureError):
        vendor.parse_events(headers=headers, body=body, secret="other")
    with pytest.raises(PostalSignatureError):
        vendor.parse_events(headers={}, body=body, secret="secret")
    assert estimated_cost(Settings(_env_file=None), 10) == 0.0
    assert estimated_cost(Settings(_env_file=None, postal_provider="lob", postal_unit_cost=1.1), 10) == 11.0


def test_webhook_refuses_without_secret_and_applies_signed_events(monkeypatch):
    crm = FakeCrm()
    client = build(monkeypatch, user=None, crm=crm, store=FakeStore())
    body = json.dumps({"event": "delivered", "piece_id": "dryrun-x"}).encode()
    assert client.post("/api/campaigns/postal/events", content=body).status_code == 404   # no secret → not mounted
    monkeypatch.setenv("POSTAL_WEBHOOK_SECRET", "s3")
    get_settings.cache_clear()
    bad = client.post("/api/campaigns/postal/events", content=body, headers=sign_event(body, "wrong"))
    assert bad.status_code == 401
    import core.app as app_mod
    crm.add(cfg.TOUCH, {"touchStatus": "Sent", "vendorPieceId": "dryrun-x"})
    client.app.state.events_client_factory = lambda: crm
    ok = client.post("/api/campaigns/postal/events", content=body, headers=sign_event(body, "s3"))
    assert ok.status_code == 200 and ok.json()["results"][0]["applied"] is True


# --- the import doors (§ 2) ----------------------------------------------------------------------------

CSV = (
    "business_name,mailing_street,mailing_city,mailing_state,mailing_zip,external_reference,website,email\n"
    "Acme Widgets,1 Main St,Cleveland,oh,44113,F-1,acme.com,\n"
    "Known Client,5 Euclid Ave,Cleveland,OH,44115,F-2,,\n"
    "Person Shop,9 Lake Rd,Cleveland,OH,44102,F-3,,owner@shop-example.com\n"
    "Acme Widgets,1 Main St,Cleveland,OH,44113,F-1,acme.com,\n"
    "No Address,,,,,F-4,,\n"
)


def test_plan_classifies_every_row_and_apply_writes_exactly_that():
    crm = FakeCrm(); store = FakeStore()
    crm.add("Account", {"name": "Known Client", "billingAddressPostalCode": "44115", "website": ""})
    plan = asyncio.run(imports.plan_import(crm, store, text=CSV, name="Filings Oct", door=cfg.SOURCE_FILING, qualified_by="Filter v1"))
    c = plan["counts"]
    assert (c["rows"], c["create"], c["alreadyKnown"], c["duplicate"], c["invalid"]) == (5, 2, 1, 1, 1)
    # Ruling 53: a filing row with a website or an email enters Qualified.
    assert c["qualified"] == 2 and c["unqualified"] == 0
    outcomes = {r["name"]: r["outcome"] for r in plan["rows"]}
    assert outcomes["Known Client"] == "already_known" and outcomes["No Address"] == "invalid"
    batch = asyncio.run(store.get_batch(plan["batchId"]))
    result = asyncio.run(imports.apply_import(crm, crm, store, batch, user_name="Mark"))
    assert (result["created"], result["duplicates"], result["qualified"], result["errors"]) == (2, 1, 2, 0)
    leads = list(crm.rows[cfg.PROSPECT].values())
    assert len(leads) == 3
    # Ruling 43: the import creates no Company and no Contact.
    assert [e for e, _p in crm.created if e in ("Account", "Contact")] == []
    # The lead is created as the user WITHOUT its company link; the link is
    # the API client's second write (found live 10-15-26).
    lead_creates = [p for e, p in crm.created if e == cfg.PROSPECT]
    assert all("alreadyKnownCompanyId" not in p for p in lead_creates)
    acme = next(p for p in leads if p["businessName"] == "Acme Widgets")
    assert acme["leadStatus"] == "Qualified" and acme["leadSource"] == "State filing" and acme["qualifiedBy"] == "Filter v1"
    assert acme["mailingAddressState"] == "OH" and not acme.get("promotedCompanyId")
    known = next(p for p in leads if p["businessName"] == "Known Client")
    assert known["sideExit"] == "Duplicate" and known["alreadyKnownCompanyId"]
    assert known["leadStatus"] == "Unqualified" and "qualifiedBy" not in known      # no website or email
    # The same file again is a no-op.
    again = asyncio.run(imports.plan_import(crm, store, text=CSV, name="Filings Oct again", door=cfg.SOURCE_FILING, qualified_by="Filter v1"))
    assert again["nothingToDo"] is True and again["counts"]["knownRow"] == 3


def test_a_matched_contact_makes_a_duplicate_never_a_converted_lead():
    crm = FakeCrm(); store = FakeStore()
    crm.add("Contact", {"name": "Owner", "emailAddress": "owner@shop-example.com", "cContactType": ["Prospect"]})
    plan = asyncio.run(imports.plan_import(crm, store, text=CSV, name="Filings", door=cfg.SOURCE_FILING, qualified_by="F"))
    batch = asyncio.run(store.get_batch(plan["batchId"]))
    asyncio.run(imports.apply_import(crm, crm, store, batch, user_name="Mark"))
    shop = next(p for p in crm.rows[cfg.PROSPECT].values() if p["businessName"] == "Person Shop")
    assert shop["sideExit"] == "Duplicate" and "Owner" in shop["sideExitNote"]
    assert not shop.get("promotedContactId")


def test_plan_names_a_missing_column_and_a_list_row_enters_unqualified():
    crm = FakeCrm(); store = FakeStore()
    with pytest.raises(service.CampaignError) as exc:
        asyncio.run(imports.plan_import(crm, store, text="name,zip\nA,1\n", name="x", door=cfg.SOURCE_FILING, qualified_by=""))
    assert "business_name" in str(exc.value)
    plan = asyncio.run(imports.plan_import(crm, store, text=CSV.splitlines()[0] + "\n" + CSV.splitlines()[1] + "\n",
                                           name="Vendor list", door=cfg.SOURCE_LIST, qualified_by="", list_source="Dun"))
    batch = asyncio.run(store.get_batch(plan["batchId"]))
    asyncio.run(imports.apply_import(crm, crm, store, batch, user_name="Mark"))
    p = next(iter(crm.rows[cfg.PROSPECT].values()))
    # Rulings 18, 53: a list row enters Unqualified even with a website.
    assert p["leadStatus"] == "Unqualified" and p["leadSource"] == "List" and p["importBatch"].startswith("Dun — ")
    assert "qualifiedBy" not in p


# --- the landing page and the response (§ 4) -------------------------------------------------------

def test_landing_scan_counts_and_changes_no_status():
    """Ruling 51: a scan alone changes no status."""
    from campaigns.landing import record_scan
    crm = FakeCrm()
    p = _prospect(crm, "Acme", stage="Unqualified")
    t = crm.add(cfg.TOUCH, {"touchStatus": "Sent", "prospectId": p["id"], "scanToken": "abcdefghjkmn", "scanCount": 0})
    out = asyncio.run(record_scan(crm, crm.rows[cfg.TOUCH][t["id"]]))
    assert out == {"written": True}
    touch = crm.rows[cfg.TOUCH][t["id"]]
    assert touch["scanCount"] == 1 and touch["outcome"] == "Scanned" and touch["firstScannedAt"]
    first = touch["firstScannedAt"]
    asyncio.run(record_scan(crm, dict(touch)))
    assert crm.rows[cfg.TOUCH][t["id"]]["scanCount"] == 2
    assert crm.rows[cfg.TOUCH][t["id"]]["firstScannedAt"] == first
    assert crm.rows[cfg.PROSPECT][p["id"]]["leadStatus"] == "Unqualified"
    assert not [u for u in crm.updated if u[0] == cfg.PROSPECT]
    planned = crm.add(cfg.TOUCH, {"touchStatus": "Planned", "prospectId": p["id"], "scanToken": "planned12345"})
    assert asyncio.run(record_scan(crm, planned)) == {"written": False, "preview": True}


def test_landing_page_is_404_until_switched_on_and_404s_unknown_tokens(monkeypatch):
    crm = FakeCrm()
    client = build(monkeypatch, user=None, crm=crm, store=FakeStore())
    assert client.get("/p/abcdefghjkmn").status_code == 404
    monkeypatch.setenv("CAMPAIGNS_LANDING_PUBLIC", "true")
    monkeypatch.setenv("ESPO_DRY_RUN", "false"); monkeypatch.setenv("ESPO_BASE_URL", "https://crm.example"); monkeypatch.setenv("ESPO_API_KEY", "k")
    get_settings.cache_clear()
    client.app.state.events_client_factory = lambda: crm
    # No store in tests, so the response delivers inline; the pipeline's own
    # client is swapped for the fake the page reads from.
    import core.app as app_mod
    monkeypatch.setattr(app_mod, "_make_client", lambda settings: crm)
    assert client.get("/p/abcdefghjkmn").json()["detail"] == "Not found"
    p = _prospect(crm, "Acme & Sons")
    crm.add(cfg.TOUCH, {"touchStatus": "Sent", "prospectId": p["id"], "prospectName": "Acme & Sons", "scanToken": "abcdefghjkmn",
                        "mailedAddress": "1 Main St\nCleveland, OH 44113", "outreachCampaignId": "camp1", "outreachCampaignName": "Nov"})
    page = client.get("/p/abcdefghjkmn?link=linktok1")
    assert page.status_code == 200
    html = page.text
    assert "Acme &amp; Sons" in html and 'value="1 Main St"' in html and 'value="44113"' in html
    assert 'data-campaign-id="camp1"' in html and 'data-link-token="linktok1"' in html
    assert "owner@" not in html                               # nothing a person's; ruling 16
    posted = client.post("/api/campaigns/landing/abcdefghjkmn", json={
        "submission_token": "tok-12345678", "action": "update", "business_name": "Acme & Sons",
        "first_name": "Ann", "email": "ann@acme-example.com", "sms_consent": True,
    })
    assert posted.status_code == 200


def test_response_converts_the_lead_to_a_company_and_its_contact_true_only():
    crm = FakeCrm()
    p = _prospect(crm, "Acme", stage="Unqualified")
    crm.add(cfg.TOUCH, {"touchStatus": "Sent", "prospectId": p["id"], "scanToken": "abcdefghjkmn", "outreachCampaignId": "camp1"})
    sub = ProspectResponse(submission_token="tok-12345678", scan_token="abcdefghjkmn", action="mentor",
                           business_name="Acme Widgets", mailing_street="2 New St", mailing_city="Cleveland", mailing_state="OH", mailing_zip="44113",
                           first_name="Ann", last_name="Lee", email="ann@acme-example.com", phone="2165550143", website="https://www.acme.com/",
                           marketing_consent=False, sms_consent=True)
    result = asyncio.run(respond(sub, crm))
    lead = crm.rows[cfg.PROSPECT][p["id"]]
    assert lead["businessName"] == "Acme Widgets" and lead["mailingAddressStreet"] == "2 New St"
    assert lead["leadStatus"] == "Converted" and lead["leadStatusChangedAt"]
    assert lead["promotedCompanyId"] == result["companyId"] and lead["promotedContactId"] == result["contactId"]
    assert result["leadConverted"] is True
    company = crm.rows["Account"][result["companyId"]]
    assert company["cCompanyType"] == ["Prospect"] and company["cOutreachCampaignId"] == "camp1"
    assert company["cFunnelStage"] == "Prospect" and company["billingAddressStreet"] == "2 New St"
    contact = crm.rows["Contact"][result["contactId"]]
    assert contact["cSmsOptIn"] is True and "cMarketingOptIn" not in contact   # true-only
    assert contact["cContactType"] == ["Prospect"] and contact["accountId"] == company["id"]
    assert contact["cFunnelStage"] == "Prospect"
    assert result["action"] == "mentor"


def test_an_email_alone_converts_a_business_lead_to_its_company_and_contact():
    """Ruling 52: the Company is made from the lead even without a website."""
    crm = FakeCrm()
    p = _prospect(crm, "Lakeview Bakery", stage="Unqualified")
    crm.add(cfg.TOUCH, {"touchStatus": "Sent", "prospectId": p["id"], "scanToken": "abcdefghjkmn"})
    sub = ProspectResponse(submission_token="tok-12345678", scan_token="abcdefghjkmn", email="jo@gmail.com", first_name="Jo")
    result = asyncio.run(respond(sub, crm))
    company = crm.rows["Account"][result["companyId"]]
    assert company["name"] == "Lakeview Bakery" and not company.get("website")
    assert company["billingAddressPostalCode"] == "44113"
    assert crm.rows["Contact"][result["contactId"]]["accountId"] == company["id"]
    # A same-named Company in another ZIP is another business; in the same ZIP it is this one.
    crm2 = FakeCrm()
    crm2.add("Account", {"name": "Lakeview Bakery", "billingAddressPostalCode": "44308"})
    same = crm2.add("Account", {"name": "Lakeview Bakery", "billingAddressPostalCode": "44113"})
    p2 = _prospect(crm2, "Lakeview Bakery", stage="Qualified")
    crm2.add(cfg.TOUCH, {"touchStatus": "Sent", "prospectId": p2["id"], "scanToken": "abcdefghjkmn"})
    r2 = asyncio.run(respond(sub, crm2))
    assert r2["companyId"] == same["id"] and r2["companyCreated"] is False


def test_a_response_converts_on_the_leads_own_website():
    """A response is first contact: a lead that already holds a website converts
    on a name alone (rulings 42-44)."""
    crm = FakeCrm()
    p = crm.add(cfg.PROSPECT, {"name": "Acme", "businessName": "Acme", "leadStatus": "Qualified", "website": "acme.com",
                                "mailingAddressPostalCode": "44113"})
    crm.add(cfg.TOUCH, {"touchStatus": "Sent", "prospectId": p["id"], "scanToken": "abcdefghjkmn"})
    sub = ProspectResponse(submission_token="tok-12345678", scan_token="abcdefghjkmn", first_name="Ann")
    result = asyncio.run(respond(sub, crm))
    assert result["leadConverted"] is True and result["companyId"] and "contactId" not in result
    assert crm.rows[cfg.PROSPECT][p["id"]]["leadStatus"] == "Converted"


def test_response_orchestrator_holds_a_same_named_company_at_another_website():
    from core.crm_upsert import CompanyConflict
    crm = FakeCrm()
    crm.add("Account", {"name": "Acme Widgets", "website": "https://acme-other.example", "cCompanyType": ["Client"]})
    p = _prospect(crm, "Acme Widgets")
    crm.add(cfg.TOUCH, {"touchStatus": "Sent", "prospectId": p["id"], "scanToken": "abcdefghjkmn"})
    sub = ProspectResponse(submission_token="tok-12345678", scan_token="abcdefghjkmn", website="acme.com")
    with pytest.raises(CompanyConflict):
        asyncio.run(respond(sub, crm))


def test_response_without_email_or_website_converts_nothing():
    crm = FakeCrm()
    p = _prospect(crm, "Acme", stage="Unqualified")
    crm.add(cfg.TOUCH, {"touchStatus": "Sent", "prospectId": p["id"], "scanToken": "abcdefghjkmn"})
    sub = ProspectResponse(submission_token="tok-12345678", scan_token="abcdefghjkmn", first_name="Ann")
    result = asyncio.run(respond(sub, crm))
    assert "contactId" not in result and "companyId" not in result
    assert not crm.rows.get("Contact") and not crm.rows.get("Account")
    assert crm.rows[cfg.PROSPECT][p["id"]]["leadStatus"] == "Unqualified"


# --- the hidden fields and the SMS tick on every door ------------------------------------------------

def test_every_submission_model_carries_the_campaign_fields_and_sms_tick():
    from forms import SPECS_BY_SLUG
    for slug, spec in SPECS_BY_SLUG.items():
        fields = spec.submission_model.model_fields
        assert {"campaign_id", "campaign_link", "prospect_id"} <= set(fields), slug
        if slug not in ("info-email",):
            assert "sms_consent" in fields or slug == "info-request", slug


@pytest.mark.parametrize("form", ["client_intake", "volunteer", "info_request", "partner", "sponsor"])
def test_every_public_form_carries_the_hidden_fields_and_the_sms_tick(form):
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "forms" / form / "frontend"
    html = (root / "index.html").read_text()
    js = (root / "app.js").read_text()
    for field in ("campaign_id", "campaign_link", "prospect_id"):
        assert f'id="{field}"' in html, (form, field)
        assert field in js, (form, field)
    assert 'id="campaign_banner"' in html
    assert "/shared/campaign-link.js" in html
    assert 'id="sms_consent"' in html and "sms_consent" in js, form


@pytest.mark.parametrize("sheet", ["campaigns/frontend/styles.css", "campaigns/landing_frontend/landing.css"])
def test_hidden_attribute_beats_every_display_rule(sheet):
    """A panel set to display: grid renders THROUGH the hidden attribute unless the
    sheet says otherwise — the blocked view and the "not available" view both
    showed on a working record page on 10-15-26."""
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / sheet).read_text()
    assert "[hidden] { display: none !important; }" in css


def test_a_partial_apply_resumes_without_doubling_records():
    """One row 403s on the first apply (the live case): the rows that landed are
    recorded, so a re-plan knows them; a re-apply finishes the batch without a
    second lead for any row."""
    crm = FakeCrm(); store = FakeStore()
    plan = asyncio.run(imports.plan_import(crm, store, text=CSV, name="Filings Oct", door=cfg.SOURCE_FILING, qualified_by="Filter v1"))
    batch = asyncio.run(store.get_batch(plan["batchId"]))
    real_create = crm.create
    state = {"failed": False}

    async def flaky_create(entity, payload):
        if entity == cfg.PROSPECT and payload.get("businessName") == "Acme Widgets" and not state["failed"]:
            state["failed"] = True
            from core.espo import EspoError
            raise EspoError("create CProspect failed: HTTP 403 [No foreign record access]")
        return await real_create(entity, payload)
    crm.create = flaky_create
    first = asyncio.run(imports.apply_import(crm, crm, store, batch, user_name="Mark"))
    assert first["errors"] == 1 and first["created"] == 2      # Known Client is a create here: no such Account
    assert asyncio.run(store.get_batch(batch["id"]))["status"] == "planned"
    again = asyncio.run(imports.plan_import(crm, store, text=CSV, name="Filings Oct 2", door=cfg.SOURCE_FILING, qualified_by="Filter v1"))
    assert again["counts"]["knownRow"] == 2 and again["counts"]["create"] == 1 and again["nothingToDo"] is False
    batch2 = asyncio.run(store.get_batch(again["batchId"]))
    second = asyncio.run(imports.apply_import(crm, crm, store, batch2, user_name="Mark"))
    assert second["created"] == 1
    names = sorted(p["businessName"] for p in crm.rows[cfg.PROSPECT].values())
    assert names == ["Acme Widgets", "Known Client", "Person Shop"]


def test_imports_list_route_is_not_shadowed_by_the_record_route(monkeypatch):
    client = build(monkeypatch, user=MARKETING, crm=FakeCrm(), store=FakeStore())
    resp = client.get("/campaigns/api/prospects/imports")
    assert resp.status_code == 200 and resp.json() == {"batches": []}


# --- ruling 57: a campaign names its funders, like its partners -------------------------------

class FunderCrm(FakeCrm):
    def __init__(self, *, with_link: bool = True):
        super().__init__()
        self.with_link = with_link

    async def metadata(self, key: str):
        out = await super().metadata(key)
        if key == f"entityDefs.{cfg.CAMPAIGN}.links" and self.with_link:
            out = {**out, cfg.LINK_FUNDERS: {"type": "hasMany"}}
        return out


def test_funders_picker_and_relate_when_the_crm_has_the_link(monkeypatch):
    crm = FunderCrm()
    crm.add(cfg.SPONSOR_PROFILE, {"id": "f1", "name": "Harrowgate Family Trust"})
    client = build(monkeypatch, user=MARKETING, crm=crm)
    f = client.get("/campaigns/api/fields").json()
    assert f["fundersAvailable"] is True and [o["name"] for o in f["funderOptions"]] == ["Harrowgate Family Trust"]
    res = client.post("/campaigns/api/campaigns", json={"changes": {"name": "Funded card", "campaignKind": "Postcard"},
                                                       "funderIds": ["f1"]})
    assert res.status_code == 200, res.text
    cid = res.json()["campaign"]["id"]
    assert crm.related.get((cfg.CAMPAIGN, cid, cfg.LINK_FUNDERS)) == {"f1"}
    rec = client.get(f"/campaigns/api/campaigns/{cid}").json()
    assert [x["id"] for x in rec["funders"]] == ["f1"]


def test_without_the_link_there_is_no_picker_and_funders_are_ignored(monkeypatch):
    crm = FunderCrm(with_link=False)
    client = build(monkeypatch, user=MARKETING, crm=crm)
    f = client.get("/campaigns/api/fields").json()
    assert f["fundersAvailable"] is False and f["funderOptions"] is None
    res = client.post("/campaigns/api/campaigns", json={"changes": {"name": "Plain card", "campaignKind": "Postcard"},
                                                       "funderIds": ["f1"]})
    assert res.status_code == 200
    cid = res.json()["campaign"]["id"]
    assert (cfg.CAMPAIGN, cid, cfg.LINK_FUNDERS) not in crm.related
    assert client.get(f"/campaigns/api/campaigns/{cid}").json()["funders"] is None


def test_the_funder_record_has_a_campaigns_tab():
    from sessions.config import DOMAINS
    sponsor = next(d for d in DOMAINS.values() if d.parent_entity == "CSponsorProfile")
    partner = next(d for d in DOMAINS.values() if d.parent_entity == "CPartnerProfile")
    assert sponsor.sponsored_campaigns_link == partner.sponsored_campaigns_link == "sponsoredCampaigns"


# --- the owner (ruling 76) ---------------------------------------------------------------

class TeamCrm(FakeCrm):
    """FakeCrm plus a Team with its users link."""

    def __init__(self):
        super().__init__()
        self.add("Team", {"id": "team-m", "name": "Marketing Admin Team"})
        self.team_users = [
            {"id": "u-1", "name": "Mark Marketing", "isActive": True, "type": "regular"},
            {"id": "u-3", "name": "Alice Admin", "isActive": True, "type": "admin"},
            {"id": "u-4", "name": "Gone Person", "isActive": False, "type": "regular"},
            {"id": "u-5", "name": "API Robot", "isActive": True, "type": "api"},
        ]

    async def list_related(self, entity, record_id, link, *, select=None, max_size=200):
        if entity == "Team" and link == "users":
            rows = self.team_users if record_id == "team-m" else []
            return {"total": len(rows), "list": rows}
        return await super().list_related(entity, record_id, link, select=select, max_size=max_size)


def _owned_campaign(crm):
    return crm.add(cfg.CAMPAIGN, {"name": "Nov card", "campaignKind": "Postcard", "campaignStatus": "Draft",
                                  "assignedUserId": "u-1", "assignedUserName": "Mark Marketing"})


def test_owner_options_are_the_teams_active_people(monkeypatch):
    client = build(monkeypatch, user=MARKETING, crm=TeamCrm())
    res = client.get("/campaigns/api/owner-options")
    assert res.status_code == 200, res.text
    assert [o["name"] for o in res.json()["options"]] == ["Alice Admin", "Mark Marketing"]


def test_a_team_member_hands_the_campaign_to_another(monkeypatch):
    crm = TeamCrm()
    row = _owned_campaign(crm)
    client = build(monkeypatch, user=MARKETING, crm=crm)
    res = client.put(f"/campaigns/api/campaigns/{row['id']}/owner", json={"userId": "u-3"})
    assert res.status_code == 200, res.text
    assert res.json()["changed"] is True
    assert crm.updated[-1] == (cfg.CAMPAIGN, row["id"], {"assignedUserId": "u-3"})


def test_the_same_owner_writes_nothing(monkeypatch):
    crm = TeamCrm()
    row = _owned_campaign(crm)
    client = build(monkeypatch, user=MARKETING, crm=crm)
    res = client.put(f"/campaigns/api/campaigns/{row['id']}/owner", json={"userId": "u-1"})
    assert res.status_code == 200 and res.json()["changed"] is False
    assert crm.updated == []


@pytest.mark.parametrize("user_id", ["u-4", "u-5", "u-99", ""])
def test_an_inactive_outside_or_missing_owner_is_refused(monkeypatch, user_id):
    crm = TeamCrm()
    row = _owned_campaign(crm)
    client = build(monkeypatch, user=MARKETING, crm=crm)
    res = client.put(f"/campaigns/api/campaigns/{row['id']}/owner", json={"userId": user_id})
    assert res.status_code == 400
    assert crm.updated == []


def test_a_crm_refusal_names_the_denial(monkeypatch):
    from core.espo import EspoError

    class Refusing(TeamCrm):
        async def update(self, entity, record_id, payload):
            raise EspoError("update OutreachCampaign failed: HTTP 403 Forbidden")

    crm = Refusing()
    row = _owned_campaign(crm)
    client = build(monkeypatch, user=MARKETING, crm=crm)
    res = client.put(f"/campaigns/api/campaigns/{row['id']}/owner", json={"userId": "u-3"})
    assert res.status_code == 403
    assert res.json()["detail"].startswith("Could not change the campaign's owner: your CRM role")


def test_the_general_save_cannot_change_the_owner(monkeypatch):
    crm = TeamCrm()
    row = _owned_campaign(crm)
    client = build(monkeypatch, user=MARKETING, crm=crm)
    res = client.put(f"/campaigns/api/campaigns/{row['id']}", json={"changes": {"assignedUserId": "u-3"}})
    assert res.status_code == 200
    assert all("assignedUserId" not in p for _, _, p in crm.updated)


def test_an_outsider_cannot_change_the_owner(monkeypatch):
    crm = TeamCrm()
    row = _owned_campaign(crm)
    client = build(monkeypatch, user=OUTSIDER, crm=crm)
    assert client.put(f"/campaigns/api/campaigns/{row['id']}/owner", json={"userId": "u-3"}).status_code == 403
