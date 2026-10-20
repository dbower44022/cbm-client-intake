"""Campaign audiences as named lists — build plan § 7c, rulings 58–68 (L1:
leads and contacts).

The boundaries: what a recipe step selects (add widens, keep narrows only its
own type, remove excludes); ruling 60 (a contacts Add names its types; "No
type"); a static list's hand ticks survive "Run again"; a dynamic list's
standing entries apply after the recipe; the send-time checks per channel and
the cbmEmail rule; the switch, the retired list and the in-use delete refusal;
a campaign naming a list sends to it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from campaigns import audience
from campaigns import config as cfg
from campaigns.audience_store import STATE_IN, STATE_OUT
from core.config import Settings
from tests.test_campaigns import MARKETING, FakeCrm, build


def run(coro):
    return asyncio.run(coro)


# --- fakes ------------------------------------------------------------------------------

class ListCrm(FakeCrm):
    """FakeCrm plus the clauses a list step produces and the fields it reads."""

    PROSPECT_FIELDS = {
        "leadStatus": {"type": "enum", "options": list(cfg.LEAD_STATUSES)},
        "leadSource": {"type": "enum", "options": ["", "State filing", "List"]},
        "industry": {"type": "enum", "options": ["", "Manufacturing", "Retail Trade"]},
        "mailingAddressPostalCode": {"type": "varchar"},
        "mailingAddressCity": {"type": "varchar"},
        "importBatch": {"type": "varchar"},
        "createdAt": {"type": "datetime"},
        "qualifiedAt": {"type": "datetime"},
        "sideExit": {"type": "enum", "options": ["", "Duplicate"]},
    }
    CONTACT_FIELDS = {
        "cContactType": {"type": "multiEnum", "options": ["Client", "Mentor", "Prospect", "Presenter"]},
        "cFunnelStage": {"type": "enum", "options": ["", "Prospect", "Engaged"]},
        "cMarketingOptIn": {"type": "bool"}, "cSmsOptIn": {"type": "bool"},
        "cHowDidYouHear": {"type": "enum", "options": [""]},
        "addressPostalCode": {"type": "varchar"}, "createdAt": {"type": "datetime"},
    }

    def __init__(self, *, with_industry: bool = True):
        super().__init__()
        self.with_industry = with_industry
        self.lists_seen: list[tuple[str, list]] = []

    async def metadata(self, key: str):
        if key == f"entityDefs.{cfg.PROSPECT}.fields":
            f = dict(self.PROSPECT_FIELDS)
            if not self.with_industry:
                f.pop("industry")
            return f
        if key == "entityDefs.Contact.fields":
            return dict(self.CONTACT_FIELDS)
        return await super().metadata(key)

    def _match(self, row, clause) -> bool:
        t, attr, val = clause.get("type"), clause.get("attribute"), clause.get("value")
        if t == "or":
            return any(self._match(row, c) for c in val)
        if t == "and":
            return all(self._match(row, c) for c in val)
        if t == "notIn":
            return row.get(attr) not in (val or [])
        if t == "notEquals":
            return row.get(attr) != val
        if t == "isTrue":
            return bool(row.get(attr))
        if t == "isFalse":
            return not row.get(attr)
        if t == "startsWith":
            return str(row.get(attr) or "").lower().startswith(str(val).lower())
        if t == "arrayAnyOf":
            return bool(set(row.get(attr) or []) & set(val))
        if t == "arrayNoneOf":
            return not (set(row.get(attr) or []) & set(val))
        if t == "arrayIsEmpty":
            return not row.get(attr)
        if t == "arrayIsNotEmpty":
            return bool(row.get(attr))
        if t == "after":
            return str(row.get(attr) or "") > str(val)
        if t == "before":
            return bool(row.get(attr)) and str(row.get(attr)) < str(val)
        return super()._match(row, clause)

    async def list(self, entity, *, where=None, select=None, max_size=50, offset=0, order_by=None, order=None):
        self.lists_seen.append((entity, where or []))
        return await super().list(entity, where=where, select=select, max_size=max_size, offset=offset,
                                  order_by=order_by, order=order)


class FakeListStore:
    """The audience half of the campaign store, in memory."""

    def __init__(self):
        self.lists: dict[str, dict] = {}
        self.versions: list[dict] = []
        self.members: dict[tuple[str, str], dict] = {}
        self.entries_: dict[tuple[str, str], dict] = {}
        self.audiences: dict[str, dict] = {}

    async def create_list(self, *, name, notes, kind, recipe, actor):
        now = datetime.now(timezone.utc)
        row = {"id": f"list-{len(self.lists) + 1}", "name": name, "notes": notes, "kind": kind,
               "status": "active", "version": 1, "recipe": recipe, "last_run_at": None, "last_run_by": None,
               "last_run": None, "created_by": actor, "created_at": now, "updated_by": actor, "updated_at": now}
        self.lists[row["id"]] = row
        self.versions.append({"list_id": row["id"], "version": 1, "kind": kind, "recipe": recipe,
                              "saved_by": actor, "saved_at": now})
        return dict(row)

    async def get_list(self, list_id):
        r = self.lists.get(list_id)
        return dict(r) if r else None

    async def all_lists(self):
        return [dict(r) for r in self.lists.values()]

    async def save_list(self, list_id, *, name, notes, kind, recipe, actor):
        r = self.lists[list_id]
        r.update(name=name, notes=notes, updated_by=actor)
        if recipe != r["recipe"] or kind != r["kind"]:
            r.update(kind=kind, recipe=recipe, version=r["version"] + 1)
            self.versions.append({"list_id": list_id, "version": r["version"], "kind": kind, "recipe": recipe,
                                  "saved_by": actor, "saved_at": datetime.now(timezone.utc)})
        return dict(r)

    async def set_list_status(self, list_id, status, actor):
        self.lists[list_id]["status"] = status
        return dict(self.lists[list_id])

    async def delete_list(self, list_id):
        self.lists.pop(list_id, None)

    async def list_versions(self, list_id):
        return [v for v in self.versions if v["list_id"] == list_id]

    async def replace_recipe_members(self, list_id, keyed_steps, *, run, actor):
        for k in [k for k, m in self.members.items() if k[0] == list_id and m["source"] == "recipe"]:
            del self.members[k]
        hand = {k[1] for k, m in self.members.items() if k[0] == list_id and m["source"] == "hand"}
        for key, step in keyed_steps.items():
            if key not in hand:
                self.members[(list_id, key)] = {"list_id": list_id, "target_key": key, "source": "recipe",
                                                "state": STATE_IN, "step": step, "added_by": actor}
        self.lists[list_id].update(last_run_at=datetime.now(timezone.utc), last_run_by=actor, last_run=run)

    async def hand_mark(self, list_id, key, state, actor):
        self.members[(list_id, key)] = {"list_id": list_id, "target_key": key, "source": "hand", "state": state,
                                        "step": None, "added_by": actor, "added_at": datetime.now(timezone.utc)}

    async def hand_clear(self, list_id, key):
        m = self.members.get((list_id, key))
        if m and m["source"] == "hand":
            del self.members[(list_id, key)]

    async def member_rows(self, list_id):
        return [dict(m) for k, m in self.members.items() if k[0] == list_id]

    async def set_entry(self, list_id, key, mode, note, actor):
        self.entries_[(list_id, key)] = {"list_id": list_id, "target_key": key, "mode": mode, "note": note,
                                         "created_by": actor, "created_at": datetime.now(timezone.utc)}

    async def remove_entry(self, list_id, key):
        self.entries_.pop((list_id, key), None)

    async def entries(self, list_id):
        return [dict(e) for k, e in self.entries_.items() if k[0] == list_id]

    async def get_campaign_audience(self, campaign_id):
        a = self.audiences.get(campaign_id)
        return dict(a) if a else None

    async def set_campaign_audience(self, campaign_id, list_id, *, include_every_contact, actor):
        if not list_id:
            self.audiences.pop(campaign_id, None)
            return
        self.audiences[campaign_id] = {"campaign_id": campaign_id, "list_id": list_id,
                                       "include_every_contact": include_every_contact, "built_version": None,
                                       "built_at": None, "build": None}

    async def record_campaign_build(self, campaign_id, *, version, build):
        self.audiences[campaign_id].update(built_version=version, built_at=datetime.now(timezone.utc), build=build)

    async def campaigns_using(self, list_id):
        return [a for a in self.audiences.values() if a["list_id"] == list_id]

    async def usage_counts(self):
        out: dict[str, int] = {}
        for a in self.audiences.values():
            out[a["list_id"]] = out.get(a["list_id"], 0) + 1
        return out


def _lead(crm, name, **kw):
    row = {"name": name, "businessName": name, "leadStatus": cfg.LEAD_QUALIFIED, "sideExit": None,
           "addressStatus": cfg.ADDRESS_USABLE, "mailingAddressStreet": "1 Main St",
           "mailingAddressCity": "Cleveland", "mailingAddressState": "OH", "mailingAddressPostalCode": "44113",
           "industry": "Manufacturing", **kw}
    return crm.add(cfg.PROSPECT, row)


def _contact(crm, name, **kw):
    row = {"name": name, "firstName": name.split()[0], "lastName": name.split()[-1],
           "cContactType": ["Prospect"], "cMarketingOptIn": True, "emailAddress": f"{name.split()[0].lower()}@x.org",
           **kw}
    return crm.add(cfg.CONTACT, row)


SETTINGS = Settings(campaign_lists=True)


def cat_for(crm):
    return run(audience.catalogue(crm, SETTINGS))


def recipe(*steps):
    return audience.normalise_recipe({"steps": list(steps)})


def step(action, type_, *conds):
    return {"action": action, "type": type_,
            "conditions": [{"field": f, "op": o, "value": v} for f, o, v in conds]}


# --- the catalogue (ruling 63) -----------------------------------------------------------

def test_catalogue_offers_configured_fields_and_flags_missing_ones():
    crm = ListCrm(with_industry=False)
    cat = cat_for(crm)
    lead_fields = [f["field"] for f in cat["lead"]["fields"]]
    assert "leadStatus" in lead_fields and "industry" not in lead_fields
    assert "industry" in cat["lead"]["missing"]          # ruling 66's field, not on this CRM yet
    ctype = next(f for f in cat["contact"]["fields"] if f["field"] == "cContactType")
    assert audience.NO_TYPE in ctype["options"]           # ruling 60's "No type"


def test_setting_overrides_the_defaults():
    s = Settings(campaign_lists=True, campaign_list_fields="lead: leadStatus; contact: cFunnelStage")
    cat = run(audience.catalogue(ListCrm(), s))
    assert [f["field"] for f in cat["lead"]["fields"]] == ["leadStatus"]
    assert [f["field"] for f in cat["contact"]["fields"]] == ["cFunnelStage"]


# --- running a recipe ----------------------------------------------------------------------

def test_add_widens_keep_narrows_remove_excludes():
    crm = ListCrm()
    a = _lead(crm, "Acme Tooling", industry="Manufacturing", mailingAddressPostalCode="44113")
    b = _lead(crm, "Bakery", industry="Retail Trade", mailingAddressPostalCode="44113")
    c = _lead(crm, "Far Mfg", industry="Manufacturing", mailingAddressPostalCode="44001")
    cat = cat_for(crm)
    r = recipe(step("add", "lead", ("mailingAddressPostalCode", "in", "44113, 44114")),
               step("add", "lead", ("industry", "in", ["Manufacturing"])),
               step("keep", "lead", ("mailingAddressPostalCode", "startsWith", "4411")),
               step("remove", "lead", ("industry", "in", ["Retail Trade"])))
    result = run(audience.run_recipe(crm, r, cat))
    assert set(result["keys"]) == {f"lead:{a['id']}"}
    assert [s["after"] for s in result["steps"]] == [2, 3, 2, 1]
    assert result["steps"][1]["added"] == 1 and result["steps"][2]["dropped"] == 1
    assert c["id"] and b["id"]


def test_keep_only_touches_its_own_type():
    crm = ListCrm()
    lead = _lead(crm, "Acme", industry="Retail Trade")
    person = _contact(crm, "Pat Doe")
    cat = cat_for(crm)
    r = recipe(step("add", "lead", ("leadStatus", "in", [cfg.LEAD_QUALIFIED])),
               step("add", "contact", ("cContactType", "anyOf", ["Prospect"])),
               step("keep", "lead", ("industry", "in", ["Manufacturing"])))
    keys = run(audience.run_recipe(crm, r, cat))["keys"]
    assert f"contact:{person['id']}" in keys and f"lead:{lead['id']}" not in keys


def test_contacts_add_must_name_types_and_no_type_works():
    crm = ListCrm()
    typed = _contact(crm, "Pat Doe")
    untyped = _contact(crm, "Una Typed", cContactType=[])
    cat = cat_for(crm)
    bad = recipe(step("add", "contact", ("cMarketingOptIn", "isTrue", None)))
    assert any("ruling 60" in p["message"] for p in audience.check_recipe(bad, cat))
    with pytest.raises(audience.AudienceError):
        run(audience.run_recipe(crm, bad, cat))
    only_untyped = recipe(step("add", "contact", ("cContactType", "anyOf", [audience.NO_TYPE])))
    keys = run(audience.run_recipe(crm, only_untyped, cat))["keys"]
    assert set(keys) == {f"contact:{untyped['id']}"} and typed["id"]


def test_a_step_over_the_cap_is_refused(monkeypatch):
    crm = ListCrm()
    for i in range(5):
        _lead(crm, f"L{i}")
    monkeypatch.setattr(audience, "STEP_CAP", 3)
    monkeypatch.setattr(audience, "_PAGE", 2)
    cat = cat_for(crm)
    with pytest.raises(audience.AudienceError, match="narrow the step"):
        run(audience._ids_matching(crm, cfg.PROSPECT, [], cap=3))
    assert cat


def test_a_field_the_crm_lost_stops_the_run_with_a_message():
    crm = ListCrm(with_industry=False)
    r = recipe(step("add", "lead", ("industry", "in", ["Manufacturing"])))
    problems = audience.check_recipe(r, cat_for(crm))
    assert problems and "no longer offered" in problems[0]["message"]


def test_hand_ticks_and_standing_entries():
    keys = {"lead:1": 1, "lead:2": 1}
    hand = [{"source": "hand", "target_key": "lead:2", "state": STATE_OUT},
            {"source": "hand", "target_key": "lead:9", "state": STATE_IN}]
    assert set(audience.apply_hand(keys, hand)) == {"lead:1", "lead:9"}
    entries = [{"target_key": "lead:1", "mode": "exclude"}, {"target_key": "contact:7", "mode": "include"}]
    assert set(audience.apply_entries(keys, entries)) == {"lead:2", "contact:7"}


def test_last_days_resolves_to_a_concrete_after():
    f = {"family": "date"}
    clause = audience.condition_where({"field": "createdAt", "op": "lastDays", "value": 30}, f,
                                      now=datetime(2026, 10, 20, tzinfo=timezone.utc))
    assert clause == {"type": "after", "attribute": "createdAt", "value": "2026-09-20 00:00:00"}


# --- recipients, per channel (§ 7c.2) and the send-time checks --------------------------

def test_postcard_skips_exits_cards_and_dead_addresses():
    crm = ListCrm()
    ok = _lead(crm, "Good Co")
    gone = _lead(crm, "Gone Co", sideExit="Duplicate")
    dead = _lead(crm, "Dead Co", addressStatus="Dead")
    carded = _lead(crm, "Carded Co")
    crm.add(cfg.TOUCH, {"channel": cfg.KIND_POSTCARD, "touchStatus": cfg.TOUCH_SENT, "prospectId": carded["id"]})
    keys = [f"lead:{x['id']}" for x in (ok, gone, dead, carded)]
    out = run(audience.resolve_targets(crm, cfg.KIND_POSTCARD, keys))
    assert [t["id"] for t in out["targets"]] == [ok["id"]]
    codes = {s["code"]: s["count"] for s in out["skipped"]}
    assert codes == {"exit": 1, "no_address": 1, "carded": 1}


def test_postcard_to_a_contact_goes_to_its_company_else_its_own_address():
    crm = ListCrm()
    acct = crm.add(cfg.ACCOUNT, {"name": "Acme", "billingAddressStreet": "9 Elm", "billingAddressCity": "Euclid",
                                 "billingAddressState": "OH", "billingAddressPostalCode": "44117"})
    at_company = _contact(crm, "Pat Doe", accountId=acct["id"])
    at_home = _contact(crm, "Una Home", addressStreet="5 Oak", addressCity="Parma", addressState="OH",
                       addressPostalCode="44129")
    out = run(audience.resolve_targets(crm, cfg.KIND_POSTCARD,
                                       [f"contact:{at_company['id']}", f"contact:{at_home['id']}"]))
    assert {(t["kind"], t["id"]) for t in out["targets"]} == {("company", acct["id"]), ("contact", at_home["id"])}


def test_email_needs_consent_and_reaches_members_at_their_cbm_email():
    crm = ListCrm()
    yes = _contact(crm, "Pat Doe")
    no = _contact(crm, "Nora No", cMarketingOptIn=False)
    mentor = _contact(crm, "Mike Mentor", cContactType=["Mentor"], emailAddress="mike@home.example")
    crm.add("CMentorProfile", {"contactRecordId": mentor["id"], "cbmEmail": "mike.mentor@cbmentors.org"})
    bare = _contact(crm, "Mo Member", cContactType=["Mentor"])
    lead_only = _lead(crm, "No Contact Yet")
    out = run(audience.resolve_targets(crm, cfg.KIND_EMAIL, [
        f"contact:{yes['id']}", f"contact:{no['id']}", f"contact:{mentor['id']}", f"contact:{bare['id']}",
        f"lead:{lead_only['id']}"]))
    emails = {t["id"]: t["email"] for t in out["targets"]}
    assert emails == {yes["id"]: "pat@x.org", mentor["id"]: "mike.mentor@cbmentors.org"}
    codes = {s["code"]: s["count"] for s in out["skipped"]}
    assert codes == {"no_consent": 1, "member_no_cbm_email": 1, "no_contact": 1}


def test_texts_need_the_text_consent_and_calls_respect_do_not_call():
    crm = ListCrm()
    texter = _contact(crm, "Tex Ter", cSmsOptIn=True, phoneNumber="+12165550100")
    silent = _contact(crm, "Sil Ent", phoneNumber="+12165550101")
    dnc = _contact(crm, "Dee Nc", phoneNumber="+12165550102", doNotCall=True)
    lead = _lead(crm, "Call Me", phone="2165550103")
    sms = run(audience.resolve_targets(crm, cfg.KIND_SMS, [f"contact:{texter['id']}", f"contact:{silent['id']}"]))
    assert [t["id"] for t in sms["targets"]] == [texter["id"]]
    call = run(audience.resolve_targets(crm, cfg.KIND_CALL, [f"contact:{dnc['id']}", f"lead:{lead['id']}",
                                                             f"contact:{silent['id']}"]))
    assert {(t["kind"], t["id"]) for t in call["targets"]} == {("prospect", lead["id"]), ("contact", silent["id"])}


def test_one_person_twice_is_one_recipient():
    crm = ListCrm()
    person = _contact(crm, "Pat Doe")
    lead = _lead(crm, "Pat's Co", promotedContactId=person["id"], leadStatus=cfg.LEAD_CONVERTED)
    out = run(audience.resolve_targets(crm, cfg.KIND_EMAIL, [f"lead:{lead['id']}", f"contact:{person['id']}"]))
    assert len(out["targets"]) == 1
    assert {s["code"]: s["count"] for s in out["skipped"]} == {"duplicate": 1}


# --- a campaign naming a list ----------------------------------------------------------------

def test_a_campaign_naming_a_list_builds_from_it():
    crm = ListCrm()
    store = FakeListStore()
    a = _lead(crm, "Acme")
    _lead(crm, "Elsewhere", mailingAddressPostalCode="90210")
    camp = crm.add(cfg.CAMPAIGN, {"name": "Downtown", "campaignKind": cfg.KIND_POSTCARD,
                                  "campaignStatus": cfg.STATUS_DRAFT})
    row = run(store.create_list(name="Downtown", notes="", kind="dynamic", actor="Mark",
                                recipe=recipe(step("add", "lead", ("mailingAddressPostalCode", "in", ["44113"])))))
    run(store.set_campaign_audience(camp["id"], row["id"], include_every_contact=False, actor="Mark"))
    chosen = run(audience.audience_for_build(crm, store, SETTINGS, camp))
    assert [t["id"] for t in chosen["targets"]] == [a["id"]]
    assert "Downtown" in chosen["summary"]
    off = run(audience.audience_for_build(crm, store, Settings(campaign_lists=False), camp))
    assert off is None


def test_a_static_list_never_run_cannot_be_sent_to():
    crm = ListCrm()
    store = FakeListStore()
    camp = crm.add(cfg.CAMPAIGN, {"name": "C", "campaignKind": cfg.KIND_EMAIL, "campaignStatus": cfg.STATUS_DRAFT})
    row = run(store.create_list(name="S", notes="", kind="static", actor="Mark",
                                recipe=recipe(step("add", "contact", ("cContactType", "anyOf", ["Prospect"])))))
    run(store.set_campaign_audience(camp["id"], row["id"], include_every_contact=False, actor="Mark"))
    with pytest.raises(audience.AudienceError, match="never been run"):
        run(audience.audience_for_build(crm, store, SETTINGS, camp))


# --- the API ------------------------------------------------------------------------------------

class Both(FakeListStore):
    """The router reads the campaign store; the lists half is all it needs here."""


def _client(monkeypatch, crm, store, lists="true"):
    monkeypatch.setenv("CAMPAIGN_LISTS", lists)
    client = build(monkeypatch, user=MARKETING, crm=crm, store=store)
    import campaigns.router as router_mod
    import campaigns.lists_router as lists_mod
    monkeypatch.setattr(router_mod, "_api_client", lambda settings, request: crm)
    monkeypatch.setattr(lists_mod, "_api_client", lambda settings, request: crm)

    async def _no_log(*a, **kw):
        return None
    monkeypatch.setattr(lists_mod, "record_action", _no_log)
    return client


def test_lists_api_is_404_while_switched_off(monkeypatch):
    client = _client(monkeypatch, ListCrm(), Both(), lists="false")
    assert client.get("/campaigns/api/lists").status_code == 404


def test_static_list_run_freeze_and_hand_tick_survives_run_again(monkeypatch):
    crm = ListCrm()
    a = _lead(crm, "Acme")
    b = _lead(crm, "Bakery")
    store = Both()
    client = _client(monkeypatch, crm, store)
    body = {"name": "Downtown", "kind": "static",
            "recipe": {"steps": [step("add", "lead", ("leadStatus", "in", [cfg.LEAD_QUALIFIED]))]}}
    created = client.post("/campaigns/api/lists", json=body).json()["list"]
    lid = created["id"]
    assert client.post(f"/campaigns/api/lists/{lid}/run").json()["run"]["total"] == 2
    assert client.post(f"/campaigns/api/lists/{lid}/mark",
                       json={"key": f"lead:{b['id']}", "state": "out"}).status_code == 200
    members = client.get(f"/campaigns/api/lists/{lid}/members").json()
    assert [m["id"] for m in members["members"]] == [a["id"]]
    again = client.post(f"/campaigns/api/lists/{lid}/run").json()["run"]
    assert again["total"] == 1                       # the hand tick survived "Run again"


def test_in_use_list_cannot_be_deleted_and_retired_cannot_be_chosen(monkeypatch):
    crm = ListCrm()
    store = Both()
    client = _client(monkeypatch, crm, store)
    camp = crm.add(cfg.CAMPAIGN, {"name": "C", "campaignKind": cfg.KIND_POSTCARD, "campaignStatus": cfg.STATUS_DRAFT})
    lid = client.post("/campaigns/api/lists", json={"name": "L", "kind": "dynamic"}).json()["list"]["id"]
    assert client.put(f"/campaigns/api/campaigns/{camp['id']}/audience", json={"listId": lid}).status_code == 200
    resp = client.delete(f"/campaigns/api/lists/{lid}")
    assert resp.status_code == 400 and "retire" in resp.json()["detail"]
    client.post(f"/campaigns/api/lists/{lid}/retire")
    other = crm.add(cfg.CAMPAIGN, {"name": "D", "campaignKind": cfg.KIND_EMAIL, "campaignStatus": cfg.STATUS_DRAFT})
    resp = client.put(f"/campaigns/api/campaigns/{other['id']}/audience", json={"listId": lid})
    assert resp.status_code == 400 and "retired" in resp.json()["detail"]


def test_saving_a_changed_recipe_is_a_new_version(monkeypatch):
    crm = ListCrm()
    store = Both()
    client = _client(monkeypatch, crm, store)
    lid = client.post("/campaigns/api/lists", json={"name": "L", "kind": "dynamic"}).json()["list"]["id"]
    same = client.put(f"/campaigns/api/lists/{lid}", json={"name": "L renamed", "kind": "dynamic"}).json()["list"]
    assert same["version"] == 1
    changed = client.put(f"/campaigns/api/lists/{lid}", json={
        "name": "L renamed", "kind": "dynamic",
        "recipe": {"steps": [step("add", "lead", ("leadStatus", "in", ["Qualified"]))]}}).json()["list"]
    assert changed["version"] == 2
