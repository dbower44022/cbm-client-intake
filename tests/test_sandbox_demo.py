"""The sandbox's demo campaigns: the outreach seeder and the nightly link restore.

What a test can prove here is the shape — the restore puts back exactly the
fixed links, never twice, never for a campaign the CRM lacks, never anywhere
but crm-test; the seeder makes the campaigns the restore names, is idempotent,
and drops what the CRM does not carry. The live result is the re-baseline's.
"""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
from datetime import datetime, timezone

import pytest

from campaigns import config as cfg
from campaigns import sandbox_demo as demo
from campaigns.tokens import ALPHABET
from core.config import Settings

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _seeder():
    path = ROOT / "scripts" / "sandbox" / "seed_outreach_data.py"
    spec = importlib.util.spec_from_file_location("seed_outreach_data", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_outreach_data"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class FakeCrm:
    def __init__(self, fields: dict[str, dict] | None = None, links: dict[str, dict] | None = None):
        self.rows: dict[str, dict[str, dict]] = {}
        self.fields = fields or {}
        self.links_meta = links or {}
        self.related: dict[tuple[str, str, str], set[str]] = {}
        self.creates: list[tuple[str, dict]] = []
        self.updates: list[tuple[str, str, dict]] = []
        self._n = 0

    def add(self, entity: str, **row) -> dict:
        self._n += 1
        row.setdefault("id", f"{entity.lower()}-{self._n}")
        self.rows.setdefault(entity, {})[row["id"]] = row
        return row

    async def metadata(self, key: str):
        parts = key.split(".")
        if parts[0] == "entityDefs" and parts[2] == "fields":
            return self.fields.get(parts[1])
        if parts[0] == "entityDefs" and parts[2] == "links":
            return self.links_meta.get(parts[1])
        return None

    async def list(self, entity, select="", where=None, max_size=200, offset=0, **_):
        rows = list(self.rows.get(entity, {}).values())
        for clause in where or []:
            rows = [r for r in rows if r.get(clause["attribute"]) == clause["value"]]
        return {"list": rows[offset:offset + max_size], "total": len(rows)}

    async def find_one(self, entity, attribute, value, select="id"):
        rows = (await self.list(entity, where=[{"attribute": attribute, "value": value}]))["list"]
        return rows[0] if rows else None

    async def get(self, entity, record_id, select=""):
        return dict(self.rows.get(entity, {}).get(record_id) or {})

    async def create(self, entity, payload):
        self.creates.append((entity, dict(payload)))
        return self.add(entity, **payload)

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, dict(payload)))
        self.rows[entity][record_id].update(payload)

    async def list_related(self, entity, record_id, link, select="id", max_size=200):
        return {"list": [{"id": i} for i in self.related.get((entity, record_id, link), set())]}

    async def relate(self, entity, record_id, link, foreign_id):
        self.related.setdefault((entity, record_id, link), set()).add(foreign_id)


class FakeStore:
    def __init__(self):
        self.links: dict[str, dict] = {}

    async def get_link_by_token(self, token):
        return self.links.get(token)

    async def create_link(self, **row):
        self.links[row["token"]] = row
        return row


# --- the fixed list ---------------------------------------------------------------------

def test_every_demo_link_names_a_campaign_the_seeder_creates():
    seeded = {c["name"] for c in _seeder().CAMPAIGNS}
    assert set(demo.DEMO_CAMPAIGNS) == seeded
    assert {l.campaign for l in demo.DEMO_LINKS} <= seeded


def test_codes_are_valid_and_unique():
    tokens = [l.token for l in demo.DEMO_LINKS]
    assert len(tokens) == len(set(tokens))
    assert all(len(t) == 8 and set(t) <= set(ALPHABET) for t in tokens)
    scans = demo.DEMO_SCAN_TOKENS
    assert len(scans) == len(set(scans))
    assert all(len(t) == 12 and set(t) <= set(ALPHABET) for t in scans)


def test_the_postcard_has_one_card_per_scan_code():
    postcard = [t for t in _seeder().TOUCHES if t[0] == demo.POSTCARD_DONE]
    assert len(postcard) == len(demo.DEMO_SCAN_TOKENS)


def test_the_event_link_names_an_event_the_seeder_relates():
    events = {e for c in _seeder().CAMPAIGNS for e in c["events"]}
    assert demo.EMAIL_EVENT in events


# --- the restore ------------------------------------------------------------------------

def _crm_with_campaigns(*, skip: str = ""):
    crm = FakeCrm()
    for name in demo.DEMO_CAMPAIGNS:
        if name != skip:
            crm.add(cfg.CAMPAIGN, name=name)
    crm.add(cfg.EVENT, id="ev-1", name=demo.EMAIL_EVENT, slug="marketing-on-a-shoestring")
    return crm


def test_restore_creates_each_fixed_link_once():
    crm, store = _crm_with_campaigns(), FakeStore()
    first = asyncio.run(demo.restore_demo_links(store, crm))
    assert first == {"created": len(demo.DEMO_LINKS), "present": 0, "skipped": 0}
    assert set(store.links) == {l.token for l in demo.DEMO_LINKS}
    landing = store.links["sbxcard2"]
    assert landing["destination_kind"] == cfg.DEST_LANDING
    assert landing["campaign_id"] == crm.rows[cfg.CAMPAIGN][next(
        i for i, r in crm.rows[cfg.CAMPAIGN].items() if r["name"] == demo.POSTCARD_DONE)]["id"]
    event = store.links["sbxevnt7"]
    assert (event["destination_target"], event["destination_slug"]) == ("ev-1", "marketing-on-a-shoestring")
    second = asyncio.run(demo.restore_demo_links(store, crm))
    assert second == {"created": 0, "present": len(demo.DEMO_LINKS), "skipped": 0}


def test_restore_leaves_a_present_link_exactly_as_it_is():
    crm, store = _crm_with_campaigns(), FakeStore()
    store.links["sbxcard2"] = {"token": "sbxcard2", "state": cfg.LINK_RETIRED}
    asyncio.run(demo.restore_demo_links(store, crm))
    assert store.links["sbxcard2"] == {"token": "sbxcard2", "state": cfg.LINK_RETIRED}


def test_a_missing_campaign_is_skipped_not_failed():
    crm, store = _crm_with_campaigns(skip=demo.SOCIAL), FakeStore()
    totals = asyncio.run(demo.restore_demo_links(store, crm))
    social = sum(1 for l in demo.DEMO_LINKS if l.campaign == demo.SOCIAL)
    assert totals["skipped"] == social
    text = demo.plan_text(asyncio.run(demo.plan_demo_links(FakeStore(), crm)))
    assert "the CRM holds no campaign of that name" in text


def test_refused_anywhere_but_the_sandbox():
    prod = Settings(espo_base_url="https://crm.clevelandbusinessmentors.org", espo_api_key="k",
                    espo_dry_run=False, sandbox_nightly_reset=True)
    with pytest.raises(Exception):
        asyncio.run(demo.job_dry_run(prod))
    # The worker's call never raises.
    assert asyncio.run(demo.run_after_reset(prod)) == {"created": 0, "present": 0, "skipped": 0}


def test_the_operations_job_is_registered():
    from setup.jobs import JOBS

    job = next(j for j in JOBS if j.key == "sandbox_demo_links")
    assert job.mutating and job.dry_run and job.apply


def test_the_reset_still_empties_the_links_table():
    from core.sandbox_reset import RESET_TABLES

    assert "campaign_link" in RESET_TABLES


# --- the seeder -------------------------------------------------------------------------

def _seed_crm():
    seed = _seeder()
    fields = {
        cfg.PROSPECT: {k: {"type": "varchar"} for k in (
            "name", "businessName", "firstName", "lastName", "mailingAddressStreet", "mailingAddressCity",
            "mailingAddressState", "mailingAddressPostalCode", "mailingAddressCountry", "website", "email",
            "phone", "externalReference", "importBatch", "qualifiedBy", "qualifiedAt", "sideExitAt",
            "sideExitNote", "description", "leadStatusChangedAt", "addressDeadAt",
            "promotedCompany", "promotedContact", "alreadyKnownCompany")},
        cfg.CAMPAIGN: {k: {"type": "varchar"} for k in (
            "name", "selectionSummary", "pieceCount", "estimatedCost", "estimatedCostCurrency",
            "signedOffByName", "signedOffAt", "runStartedAt", "runCompletedAt", "startDate", "endDate",
            "description", "teams")},   # no smsMessage: dropped, never sent
        cfg.TOUCH: {k: {"type": "varchar"} for k in (
            "name", "plannedAt", "sentAt", "deliveredAt", "returnedAt", "doneAt", "scanToken", "scanCount",
            "firstScannedAt", "mailedAddress", "vendorPieceId", "vendorStatus", "calledPhone", "callNotes",
            "outreachCampaign", "prospect", "teams")},
        cfg.ACCOUNT: {k: {"type": "varchar"} for k in (
            "name", "website", "billingAddressStreet", "billingAddressCity", "billingAddressState",
            "billingAddressPostalCode", "description", "cOutreachCampaign")},
        cfg.CONTACT: {k: {"type": "varchar"} for k in (
            "firstName", "lastName", "emailAddress", "phoneNumber", "description", "account",
            "cOutreachCampaign", "cSmsOptIn")},
        "CEngagement": {"outreachCampaign": {"type": "link"}},
    }
    enums = {
        cfg.PROSPECT: {"leadStatus": list(cfg.LEAD_STATUSES), "leadSource": ["State filing", "List", "Information request"],
                       "addressStatus": ["Usable", "Dead"], "sideExit": ["", "Duplicate", "Do Not Contact", "Declined", "Stale"]},
        cfg.CAMPAIGN: {"campaignKind": ["Postcard", "Email", "SMS", "Call", "Social media"],
                       "campaignStatus": ["Draft", "Running", "Complete"], "postcardSize": ["", "4x6", "6x9"],
                       "platform": ["", "LinkedIn"]},
        cfg.TOUCH: {"channel": ["Postcard", "Call"], "touchStatus": ["Planned", "Sent", "Delivered", "Returned", "Done"],
                    "outcome": ["", "Scanned", "No answer", "Interested", "Declined"],
                    "stageAtTouch": ["Unqualified", "Qualified", "Prospect", "Engaged", "Opportunity"]},
    }
    for entity, opts in enums.items():
        for name, options in opts.items():
            fields[entity][name] = {"type": "enum", "options": options}
    for entity in (cfg.ACCOUNT, cfg.CONTACT):
        fields[entity]["cFunnelStage"] = {"type": "enum", "options": list(cfg.STAGES)}
        fields[entity]["cEntryStage"] = {"type": "enum", "options": list(cfg.STAGES)}
    fields[cfg.ACCOUNT]["cCompanyType"] = {"type": "multiEnum", "options": ["Client", "Prospect"]}
    fields[cfg.CONTACT]["cContactType"] = {"type": "multiEnum", "options": ["Client", "Prospect"]}
    links = {"CEngagement": {"referringPartners": {}}, "CPartnerProfile": {"additionalManagers": {}},
             "CSponsorProfile": {"additionalManagers": {}}}
    crm = FakeCrm(fields, links)
    for team in ("Marketing Admin Team", "Mentor Team"):
        crm.add("Team", name=team)
    for partner in ("Cuyahoga Small Business Alliance", "Northgate Chamber of Commerce"):
        crm.add(cfg.PARTNER_PROFILE, name=partner)
    crm.add("CSponsorProfile", name="Harrowgate Family Trust")
    crm.add("CMentorProfile", name="Joe Mentor")
    for event in (demo.EMAIL_EVENT, "Hiring Your First Employee"):
        crm.add(cfg.EVENT, name=event)
    crm.add(cfg.ACCOUNT, name="Brightline Bakehouse")
    for engagement in ("Riverbend Cycles — Mentoring", "Salt & Sable Catering — Mentoring"):
        crm.add("CEngagement", name=engagement)
    return seed, crm


NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def test_seeder_is_idempotent_and_drops_what_the_crm_lacks():
    seed, crm = _seed_crm()
    asyncio.run(seed.run(crm, apply=True, now=NOW))
    created = len(crm.creates)
    assert created > 0
    assert not any("smsMessage" in p for e, p in crm.creates if e == cfg.CAMPAIGN)
    again = asyncio.run(seed.run(crm, apply=True, now=NOW))
    assert len(crm.creates) == created
    assert not [m for m in again.did if not m.startswith("!")]


def test_seeded_cards_carry_the_fixed_scan_codes_in_order():
    seed, crm = _seed_crm()
    asyncio.run(seed.run(crm, apply=True, now=NOW))
    cards = [p for e, p in crm.creates if e == cfg.TOUCH and p.get("channel") == cfg.KIND_POSTCARD]
    assert [c["scanToken"] for c in cards] == list(demo.DEMO_SCAN_TOKENS)
    calls = [p for e, p in crm.creates if e == cfg.TOUCH and p.get("channel") == cfg.KIND_CALL]
    assert calls and all(len(c["teamsIds"]) == 2 for c in calls)


def test_seeder_relates_partners_and_managers():
    seed, crm = _seed_crm()
    asyncio.run(seed.run(crm, apply=True, now=NOW))
    links = {k[2] for k in crm.related}
    assert {cfg.LINK_PARTNERS, cfg.LINK_EVENTS, "referringPartners", "additionalManagers"} <= links


def test_seeder_stops_on_a_crm_without_the_lead_model():
    seed, crm = _seed_crm()
    del crm.fields[cfg.PROSPECT]["leadStatus"]
    with pytest.raises(RuntimeError):
        asyncio.run(seed.run(crm, apply=False, now=NOW))


# --- the demo import template (build plan § 7e.7, M4) ------------------------------------------

class _TemplateStore(FakeStore):
    def __init__(self):
        super().__init__()
        self.templates: list[dict] = []

    async def list_templates(self): return list(self.templates)
    async def create_template(self, values, *, actor):
        row = {"id": f"t{len(self.templates) + 1}", **values, "created_by": actor}
        self.templates.append(row); return row


def test_the_demo_import_template_is_valid_and_restored_once():
    from campaigns import import_templates as tpl

    values = tpl.validate_template({
        "name": demo.DEMO_TEMPLATE["name"], "source": demo.DEMO_TEMPLATE["door"],
        "qualifiedBy": demo.DEMO_TEMPLATE["qualified_by"], "entersAt": demo.DEMO_TEMPLATE["enters_at"],
        "mapping": demo.DEMO_TEMPLATE["mapping"], "headerSignature": demo.DEMO_TEMPLATE["header_signature"]})
    assert values["mapping"] == demo.DEMO_TEMPLATE["mapping"]
    assert tpl.missing_required(values["mapping"]) == []
    # A filing's own column names are recognised at once.
    found = tpl.recognise([{"id": "x", "name": demo.DEMO_TEMPLATE["name"], "mapping": demo.DEMO_TEMPLATE["mapping"]}],
                          demo.DEMO_TEMPLATE["header_signature"])
    assert found["suggested"]["score"] == 1.0
    store = _TemplateStore()
    assert asyncio.run(demo.restore_demo_template(store)) == {"created": 1, "present": 0}
    assert asyncio.run(demo.restore_demo_template(store)) == {"created": 0, "present": 1}
    assert store.templates[0]["created_by"] == demo.CREATED_BY and len(store.templates) == 1


def test_the_template_table_resets_and_the_seeder_refuses_production():
    from core.sandbox_reset import RESET_TABLES

    assert "import_template" in RESET_TABLES
    path = ROOT / "scripts" / "sandbox" / "seed_import_templates.py"
    assert path.exists() and "--apply" in path.read_text(encoding="utf-8")
