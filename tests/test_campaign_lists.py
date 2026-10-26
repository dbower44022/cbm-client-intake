"""Campaign audiences as named lists — build plan § 7c, reshaped by § 7e.8
(rulings 58–68 and 90–98).

The boundaries: a dynamic list is Include groups minus Leave out groups, and
Leave out always wins (ruling 90); a static list is the people added by hand,
never run (91, 94); Exclude puts a person on a static exclusion list the
dynamic list leaves out (92); the kind is fixed and Copy makes a static list
(93); a contacts Include names its types, "No type" works; the send-time
checks per channel and the cbmEmail rule; the per-channel counts; the switch,
the retired list and the in-use delete refusal; a campaign naming a list
sends to it; migration 0037 converts each old step kind.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from typing import Any

import pytest

from campaigns import audience
from campaigns import config as cfg
from campaigns.audience_store import STATE_IN
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
        self.audiences: dict[str, dict] = {}

    async def create_list(self, *, name, notes, kind, recipe, actor):
        now = datetime.now(timezone.utc)
        row = {"id": f"list{len(self.lists) + 1}", "name": name, "notes": notes, "kind": kind,
               "status": "active", "version": 1, "recipe": recipe, "last_run_at": None, "last_run_by": None,
               "last_run": None, "created_by": actor, "created_at": now, "updated_by": actor, "updated_at": now,
               "needs_rebuild": False}
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
        if kind != r["kind"]:
            raise ValueError("A list's kind is fixed when it is created.")
        r.update(name=name, notes=notes, updated_by=actor, needs_rebuild=False)
        if recipe != r["recipe"]:
            r.update(recipe=recipe, version=r["version"] + 1)
            self.versions.append({"list_id": list_id, "version": r["version"], "kind": kind, "recipe": recipe,
                                  "saved_by": actor, "saved_at": datetime.now(timezone.utc)})
        return dict(r)

    async def copy_list(self, *, name, notes, keys, actor):
        row = await self.create_list(name=name, notes=notes, kind="static",
                                     recipe={"include": [], "exclude": []}, actor=actor)
        await self.hand_add_many(row["id"], keys, actor)
        return row

    async def set_list_status(self, list_id, status, actor):
        self.lists[list_id]["status"] = status
        return dict(self.lists[list_id])

    async def delete_list(self, list_id):
        self.lists.pop(list_id, None)

    async def list_versions(self, list_id):
        return [v for v in self.versions if v["list_id"] == list_id]

    async def replace_recipe_members(self, list_id, keyed_groups, *, run, actor):
        for k in [k for k in self.members if k[0] == list_id]:
            del self.members[k]
        for key, g in keyed_groups.items():
            self.members[(list_id, key)] = {"list_id": list_id, "target_key": key, "source": "recipe",
                                            "state": STATE_IN, "group_index": g or None, "added_by": actor}
        self.lists[list_id].update(last_run_at=datetime.now(timezone.utc), last_run_by=actor, last_run=run)

    async def hand_mark(self, list_id, key, state, actor):
        await self.hand_add_many(list_id, [key], actor)

    async def hand_add_many(self, list_id, keys, actor):
        added = 0
        for key in dict.fromkeys(keys):
            if (list_id, key) in self.members:
                continue
            self.members[(list_id, key)] = {"list_id": list_id, "target_key": key, "source": "hand",
                                            "state": STATE_IN, "group_index": None, "added_by": actor,
                                            "added_at": datetime.now(timezone.utc)}
            added += 1
        return added

    async def hand_clear(self, list_id, key):
        m = self.members.get((list_id, key))
        if m and m["source"] == "hand":
            del self.members[(list_id, key)]

    async def drop_member(self, list_id, key):
        self.members.pop((list_id, key), None)

    async def member_rows(self, list_id):
        return [dict(m) for k, m in self.members.items() if k[0] == list_id]

    async def member_counts(self):
        out: dict[str, int] = {}
        for (lid, _k), m in self.members.items():
            if m["state"] == STATE_IN:
                out[lid] = out.get(lid, 0) + 1
        return out

    async def get_campaign_audience(self, campaign_id):
        a = self.audiences.get(campaign_id)
        return dict(a) if a else None

    async def set_campaign_audience(self, campaign_id, list_id, *, include_every_contact, actor):
        if not list_id:
            self.audiences.pop(campaign_id, None)
            return
        self.audiences[campaign_id] = {"campaign_id": campaign_id, "list_id": list_id,
                                       "include_every_contact": include_every_contact, "built_version": None,
                                       "built_at": None, "build": None, "set_at": datetime.now(timezone.utc)}

    async def record_campaign_build(self, campaign_id, *, version, build):
        self.audiences[campaign_id].update(built_version=version, built_at=datetime.now(timezone.utc), build=build)

    async def campaigns_using(self, list_id):
        return [a for a in self.audiences.values() if a["list_id"] == list_id]

    async def usage_counts(self):
        out: dict[str, int] = {}
        for a in self.audiences.values():
            out[a["list_id"]] = out.get(a["list_id"], 0) + 1
        return out

    async def last_used(self):
        out: dict[str, Any] = {}
        for a in self.audiences.values():
            at = a.get("built_at") or a.get("set_at")
            if at and (a["list_id"] not in out or at > out[a["list_id"]]):
                out[a["list_id"]] = at
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


def recipe(include=(), exclude=()):
    return audience.normalise_recipe({"include": list(include), "exclude": list(exclude)})


def match(type_, *conds):
    return {"kind": "match", "type": type_,
            "conditions": [{"field": f, "op": o, "value": v} for f, o, v in conds]}


def of_list(list_id):
    return {"kind": "list", "listId": list_id}


def imported(type_, values):
    return {"kind": "import", "type": type_, "values": values}


QUALIFIED = match("lead", ("leadStatus", "in", [cfg.LEAD_QUALIFIED]))


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


# --- running a dynamic list: Include minus Leave out (ruling 90) -----------------------------

def test_include_groups_unite_and_leave_out_groups_subtract():
    crm = ListCrm()
    a = _lead(crm, "Acme Tooling", industry="Manufacturing", mailingAddressPostalCode="44113")
    b = _lead(crm, "Bakery", industry="Retail Trade", mailingAddressPostalCode="44113")
    c = _lead(crm, "Far Mfg", industry="Manufacturing", mailingAddressPostalCode="44001")
    cat = cat_for(crm)
    r = recipe(include=[match("lead", ("mailingAddressPostalCode", "in", "44113, 44114")),
                        match("lead", ("industry", "in", ["Manufacturing"]))],
               exclude=[match("lead", ("industry", "in", ["Retail Trade"]))])
    result = run(audience.run_recipe(crm, r, cat))
    assert set(result["keys"]) == {f"lead:{a['id']}", f"lead:{c['id']}"} and b["id"]
    assert [g["count"] for g in result["groups"]] == [2, 2, 1]
    assert (result["included"], result["leftOut"], result["total"]) == (3, 1, 2)
    # brought in by the FIRST Include group that holds the record
    assert result["keys"][f"lead:{a['id']}"] == 1 and result["keys"][f"lead:{c['id']}"] == 2
    assert [g["side"] for g in result["groups"]] == ["include", "include", "exclude"]


def test_leave_out_always_wins_whatever_the_order():
    crm = ListCrm()
    a = _lead(crm, "Acme", industry="Manufacturing")
    cat = cat_for(crm)
    everyone = match("lead", ("leadStatus", "in", [cfg.LEAD_QUALIFIED]))
    mfg = match("lead", ("industry", "in", ["Manufacturing"]))
    for include in ([everyone, mfg], [mfg, everyone]):
        out = run(audience.run_recipe(crm, recipe(include=include, exclude=[mfg]), cat))
        assert f"lead:{a['id']}" not in out["keys"] and out["total"] == 0


def test_a_leave_out_group_tests_only_the_included_records_of_its_type():
    crm = ListCrm()
    lead = _lead(crm, "Acme", industry="Retail Trade")
    person = _contact(crm, "Pat Doe")
    cat = cat_for(crm)
    r = recipe(include=[QUALIFIED, match("contact", ("cContactType", "anyOf", ["Prospect"]))],
               exclude=[match("lead", ("industry", "in", ["Retail Trade"]))])
    keys = run(audience.run_recipe(crm, r, cat))["keys"]
    assert f"contact:{person['id']}" in keys and f"lead:{lead['id']}" not in keys


def test_a_dynamic_list_needs_an_include_group():
    problems = audience.check_recipe(recipe(exclude=[QUALIFIED]), cat_for(ListCrm()))
    assert problems and "at least one Include group" in problems[0]["message"]


def test_contacts_include_must_name_types_and_no_type_works():
    crm = ListCrm()
    typed = _contact(crm, "Pat Doe")
    untyped = _contact(crm, "Una Typed", cContactType=[])
    cat = cat_for(crm)
    bad = recipe(include=[match("contact", ("cMarketingOptIn", "isTrue", None))])
    msgs = [p["message"] for p in audience.check_recipe(bad, cat)]
    assert any("must name the contact types" in m for m in msgs)
    assert not any("ruling" in m for m in msgs)               # names, never numbers, on the screen
    with pytest.raises(audience.AudienceError):
        run(audience.run_recipe(crm, bad, cat))
    blank = _contact(crm, "Bea Blank", cContactType=[""])        # how crm-test stores 14 of them
    only_untyped = recipe(include=[match("contact", ("cContactType", "anyOf", [audience.NO_TYPE]))])
    keys = run(audience.run_recipe(crm, only_untyped, cat))["keys"]
    assert set(keys) == {f"contact:{untyped['id']}", f"contact:{blank['id']}"} and typed["id"]
    # leaving contacts out by a condition reaches nobody, so it need not name types
    ok = recipe(include=[QUALIFIED], exclude=[match("contact", ("cMarketingOptIn", "isFalse", None))])
    assert audience.check_recipe(ok, cat) == []


def test_a_group_over_the_cap_is_refused(monkeypatch):
    crm = ListCrm()
    for i in range(5):
        _lead(crm, f"L{i}")
    monkeypatch.setattr(audience, "_PAGE", 2)
    with pytest.raises(audience.AudienceError, match="narrow it"):
        run(audience._ids_matching(crm, cfg.PROSPECT, [], cap=3))


def test_a_field_the_crm_lost_stops_the_run_with_a_message():
    crm = ListCrm(with_industry=False)
    r = recipe(include=[match("lead", ("industry", "in", ["Manufacturing"]))])
    problems = audience.check_recipe(r, cat_for(crm))
    assert problems and "no longer offered" in problems[0]["message"] and "Include group 1" in problems[0]["message"]


def test_last_days_resolves_to_a_concrete_after():
    f = {"family": "date"}
    clause = audience.condition_where({"field": "createdAt", "op": "lastDays", "value": 30}, f,
                                      now=datetime(2026, 10, 20, tzinfo=timezone.utc))
    assert clause == {"type": "after", "attribute": "createdAt", "value": "2026-09-20 00:00:00"}


def test_the_sentences_name_each_group():
    crm = ListCrm()
    cat = cat_for(crm)
    r = recipe(include=[QUALIFIED, imported("lead", ["a@x.example", "b@x.example"])], exclude=[of_list("L1")])
    s = audience.describe_recipe(r, cat, {"L1": "Do not invite"})
    assert s["include"] == ["Leads where Lead status is one of Qualified.", "The leads a file names (2 rows)."]
    assert s["exclude"] == ["Everyone on the list “Do not invite”."]
    typed = audience.describe_group(match("lead", ("mailingAddressPostalCode", "in", "44113,44114")), cat)
    assert typed == "Leads where Postal code is one of 44113, 44114."


def test_old_step_recipes_shape_to_empty_groups():
    assert audience.normalise_recipe({"steps": [{"action": "add"}]}) == {"include": [], "exclude": []}


# --- a static list: people added by hand, never run (rulings 91, 94) -------------------------

def test_a_static_list_is_its_hand_rows_and_needs_no_run():
    crm = ListCrm()
    store = FakeListStore()
    a = _lead(crm, "Acme")
    row = run(store.create_list(name="Picked", notes="", kind="static", recipe=audience.empty_recipe(), actor="M"))
    assert run(audience.current_members(crm, store, row, cat_for(crm)))["total"] == 0   # empty, not refused
    run(store.hand_add_many(row["id"], [f"lead:{a['id']}"], "M"))
    members = run(audience.current_members(crm, store, row, cat_for(crm)))
    assert set(members["keys"]) == {f"lead:{a['id']}"} and members["frozen"]


def test_a_campaign_can_send_to_a_static_list_never_run():
    crm = ListCrm()
    store = FakeListStore()
    person = _contact(crm, "Pat Doe")
    camp = crm.add(cfg.CAMPAIGN, {"name": "C", "campaignKind": cfg.KIND_EMAIL, "campaignStatus": cfg.STATUS_DRAFT})
    row = run(store.create_list(name="S", notes="", kind="static", actor="Mark", recipe=audience.empty_recipe()))
    run(store.hand_add_many(row["id"], [f"contact:{person['id']}"], "Mark"))
    run(store.set_campaign_audience(camp["id"], row["id"], include_every_contact=False, actor="Mark"))
    chosen = run(audience.audience_for_build(crm, store, SETTINGS, camp))
    assert [t["id"] for t in chosen["targets"]] == [person["id"]]


def test_per_channel_counts_are_each_kind_resolved():
    crm = ListCrm()
    emailable = _contact(crm, "Pat Doe", cSmsOptIn=True, phoneNumber="+12165550100",
                         addressStreet="5 Oak", addressCity="Parma", addressState="OH", addressPostalCode="44129")
    lead = _lead(crm, "Card Only")
    counts = run(audience.channel_counts(crm, [f"contact:{emailable['id']}", f"lead:{lead['id']}"]))
    assert [(c["label"], c["count"]) for c in counts] == [("Email", 1), ("Text", 1), ("Postcard", 2)]


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
                                recipe=recipe(include=[match("lead", ("mailingAddressPostalCode", "in", ["44113"]))])))
    run(store.set_campaign_audience(camp["id"], row["id"], include_every_contact=False, actor="Mark"))
    chosen = run(audience.audience_for_build(crm, store, SETTINGS, camp))
    assert [t["id"] for t in chosen["targets"]] == [a["id"]]
    assert "Downtown" in chosen["summary"]
    off = run(audience.audience_for_build(crm, store, Settings(campaign_lists=False), camp))
    assert off is None


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


API = "/campaigns/api/lists"


def _new(client, name, kind, **recipe_parts):
    body = {"name": name, "kind": kind, "recipe": {"include": recipe_parts.get("include", []),
                                                   "exclude": recipe_parts.get("exclude", [])}}
    resp = client.post(API, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()["list"]["id"]


def test_lists_api_is_404_while_switched_off(monkeypatch):
    client = _client(monkeypatch, ListCrm(), Both(), lists="false")
    assert client.get(API).status_code == 404


def test_a_dynamic_list_runs_reports_per_group_and_names_who_brought_each_member_in(monkeypatch):
    crm = ListCrm()
    a = _lead(crm, "Acme", industry="Manufacturing")
    b = _lead(crm, "Bakery", industry="Retail Trade")
    client = _client(monkeypatch, crm, Both())
    lid = _new(client, "Mfg", "dynamic", include=[match("lead", ("industry", "in", ["Manufacturing"])), QUALIFIED],
               exclude=[])
    detail = client.get(f"{API}/{lid}").json()
    assert detail["sentences"]["include"][0] == "Leads where Industry is one of Manufacturing."
    assert client.get(f"{API}/{lid}/counts").json()["neverRun"] is True
    ran = client.post(f"{API}/{lid}/run").json()["run"]
    assert [g["count"] for g in ran["groups"]] == [1, 2] and ran["total"] == 2
    members = client.get(f"{API}/{lid}/members?sort=name").json()["members"]
    by = {m["id"]: m["broughtInBy"] for m in members}
    assert by == {a["id"]: "Leads where Industry is one of Manufacturing.",
                  b["id"]: "Leads where Lead status is one of Qualified."}
    found = client.get(f"{API}/{lid}/members?q=bak").json()
    assert [m["id"] for m in found["members"]] == [b["id"]] and found["total"] == 1
    preview = client.post(f"{API}/preview", json={"recipe": {"include": [QUALIFIED], "exclude": [
        match("lead", ("industry", "in", ["Retail Trade"]))]}}).json()
    assert (preview["included"], preview["leftOut"], preview["total"]) == (2, 1, 1)


def test_a_static_list_is_never_run_and_a_dynamic_list_takes_no_hand_edits(monkeypatch):
    crm = ListCrm()
    a = _lead(crm, "Acme")
    client = _client(monkeypatch, crm, Both())
    sid = _new(client, "Picked", "static")
    did = _new(client, "Search", "dynamic", include=[QUALIFIED])
    resp = client.post(f"{API}/{sid}/run")
    assert resp.status_code == 400 and "never run" in resp.json()["detail"]
    for path in ("mark", "unmark"):
        resp = client.post(f"{API}/{did}/{path}", json={"key": f"lead:{a['id']}"})
        assert resp.status_code == 400 and "Exclude" in resp.json()["detail"]
    resp = client.post(f"{API}/{did}/add-people", json={"keys": [f"lead:{a['id']}"]})
    assert resp.status_code == 400 and "dynamic list is a search" in resp.json()["detail"]
    resp = client.post(f"{API}/{sid}/exclude", json={"key": f"lead:{a['id']}", "newName": "X"})
    assert resp.status_code == 400 and "Add people" in resp.json()["detail"]


def test_a_static_list_recipe_is_always_empty(monkeypatch):
    client = _client(monkeypatch, ListCrm(), Both())
    sid = _new(client, "Picked", "static", include=[QUALIFIED])
    assert client.get(f"{API}/{sid}").json()["list"]["recipe"] == {"include": [], "exclude": []}


def test_add_people_by_conditions_and_by_name_then_remove(monkeypatch):
    crm = ListCrm()
    a = _lead(crm, "Acme Tooling", industry="Manufacturing")
    b = _lead(crm, "Bakery", industry="Retail Trade")
    pat = _contact(crm, "Pat Acme")
    store = Both()
    client = _client(monkeypatch, crm, store)
    sid = _new(client, "Picked", "static")
    found = client.post(f"{API}/{sid}/find", json={"group": {"type": "lead", "conditions": [
        {"field": "industry", "op": "in", "value": ["Manufacturing"]}]}}).json()
    assert found["keys"] == [f"lead:{a['id']}"] and found["records"][0]["name"] == "Acme Tooling"
    bad = client.post(f"{API}/{sid}/find", json={"group": {"type": "lead", "conditions": []}})
    assert bad.status_code == 400 and "no conditions" in bad.json()["detail"]
    named = client.get("/campaigns/api/lists/search/records?type=all&q=acme").json()["records"]
    assert {r["key"] for r in named} == {f"lead:{a['id']}", f"contact:{pat['id']}"}
    first = client.post(f"{API}/{sid}/add-people", json={"keys": found["keys"]}).json()
    assert first == {"added": 1, "alreadyOn": 0}
    added = client.post(f"{API}/{sid}/add-people", json={"keys": [r["key"] for r in named]}).json()
    assert added == {"added": 1, "alreadyOn": 1}
    assert client.get(f"{API}/{sid}/members").json()["total"] == 2
    assert client.post(f"{API}/{sid}/unmark", json={"key": f"lead:{a['id']}"}).status_code == 200
    assert [m["id"] for m in client.get(f"{API}/{sid}/members").json()["members"]] == [pat["id"]]
    assert b["id"]
    listed = {l["id"]: l for l in client.get(API).json()["lists"]}
    assert listed[sid]["members"] == 1


def test_exclude_adds_to_an_exclusion_list_the_dynamic_list_leaves_out(monkeypatch):
    crm = ListCrm()
    a = _lead(crm, "Acme")
    b = _lead(crm, "Bakery")
    store = Both()
    client = _client(monkeypatch, crm, store)
    did = _new(client, "Qualified", "dynamic", include=[QUALIFIED])
    client.post(f"{API}/{did}/run")
    out = client.post(f"{API}/{did}/exclude", json={"key": f"lead:{a['id']}",
                                                    "newName": "Qualified — do not include"}).json()
    assert out["created"] and out["linked"]
    ex_id = out["exclusionList"]["id"]
    assert store.lists[ex_id]["kind"] == "static"
    assert store.lists[did]["recipe"]["exclude"] == [{"kind": "list", "listId": ex_id}]
    assert store.lists[did]["version"] == 2
    # gone from the grid at once, and from the next run; the Include groups
    # did not change, so the grid still says who brought the others in
    after = client.get(f"{API}/{did}/members").json()
    assert [m["id"] for m in after["members"]] == [b["id"]]
    assert after["members"][0]["broughtInBy"] == "Leads where Lead status is one of Qualified."
    assert after["changedSinceRun"] is True
    assert {l["id"]: l["members"] for l in client.get(API).json()["lists"]}[did] == 1
    assert client.post(f"{API}/{did}/run").json()["run"]["total"] == 1
    # a second exclusion into the same list does not add a second group
    again = client.post(f"{API}/{did}/exclude", json={"key": f"lead:{b['id']}", "targetListId": ex_id}).json()
    assert again["linked"] is False and len(store.lists[did]["recipe"]["exclude"]) == 1
    assert client.post(f"{API}/{did}/run").json()["run"]["total"] == 0
    resp = client.post(f"{API}/{did}/exclude", json={"key": f"lead:{a['id']}", "targetListId": did})
    assert resp.status_code == 400 and "static list" in resp.json()["detail"]
    # the exclusion list is in use by a group, so it cannot be deleted
    resp = client.delete(f"{API}/{ex_id}")
    assert resp.status_code == 400 and "Qualified" in resp.json()["detail"]


def test_the_kind_is_fixed_and_copy_makes_a_static_list(monkeypatch):
    crm = ListCrm()
    a = _lead(crm, "Acme")
    store = Both()
    client = _client(monkeypatch, crm, store)
    did = _new(client, "Qualified", "dynamic", include=[QUALIFIED])
    resp = client.put(f"{API}/{did}", json={"name": "Qualified", "kind": "static"})
    assert resp.status_code == 400 and "fixed" in resp.json()["detail"]
    camp = crm.add(cfg.CAMPAIGN, {"name": "C", "campaignKind": cfg.KIND_POSTCARD, "campaignStatus": cfg.STATUS_DRAFT})
    client.put(f"/campaigns/api/campaigns/{camp['id']}/audience", json={"listId": did})
    resp = client.post(f"{API}/{did}/copy", json={"name": ""})
    assert resp.status_code == 400 and "name" in resp.json()["detail"]
    copied = client.post(f"{API}/{did}/copy", json={"name": "Qualified on 26 Oct"}).json()
    assert copied["members"] == 1 and copied["list"]["kind"] == "static"
    new_id = copied["list"]["id"]
    assert [m["target_key"] for m in run(store.member_rows(new_id))] == [f"lead:{a['id']}"]
    assert store.audiences[camp["id"]]["list_id"] == did           # the campaign stays on the original
    used = client.get(f"{API}/{did}/used-by").json()["usedBy"]
    assert [u["name"] for u in used] == ["C"]


def test_saving_clears_needs_rebuild_and_a_changed_recipe_is_a_new_version(monkeypatch):
    crm = ListCrm()
    store = Both()
    client = _client(monkeypatch, crm, store)
    lid = _new(client, "L", "dynamic", include=[QUALIFIED])
    store.lists[lid]["needs_rebuild"] = True
    assert client.get(f"{API}/{lid}").json()["list"]["needsRebuild"] is True
    same = client.put(f"{API}/{lid}", json={"name": "L renamed", "kind": "dynamic",
                                            "recipe": {"include": [QUALIFIED], "exclude": []}}).json()["list"]
    assert same["version"] == 1 and same["needsRebuild"] is False
    changed = client.put(f"{API}/{lid}", json={
        "name": "L renamed", "kind": "dynamic",
        "recipe": {"include": [match("lead", ("leadStatus", "in", ["Unqualified"]))], "exclude": []}}).json()["list"]
    assert changed["version"] == 2


def test_in_use_list_cannot_be_deleted_and_retired_cannot_be_chosen(monkeypatch):
    crm = ListCrm()
    store = Both()
    client = _client(monkeypatch, crm, store)
    camp = crm.add(cfg.CAMPAIGN, {"name": "C", "campaignKind": cfg.KIND_POSTCARD, "campaignStatus": cfg.STATUS_DRAFT})
    lid = _new(client, "L", "dynamic", include=[QUALIFIED])
    assert client.put(f"/campaigns/api/campaigns/{camp['id']}/audience", json={"listId": lid}).status_code == 200
    resp = client.delete(f"{API}/{lid}")
    assert resp.status_code == 400 and "retire" in resp.json()["detail"]
    client.post(f"{API}/{lid}/retire")
    other = crm.add(cfg.CAMPAIGN, {"name": "D", "campaignKind": cfg.KIND_EMAIL, "campaignStatus": cfg.STATUS_DRAFT})
    resp = client.put(f"/campaigns/api/campaigns/{other['id']}/audience", json={"listId": lid})
    assert resp.status_code == 400 and "retired" in resp.json()["detail"]
    listed = {l["id"]: l for l in client.get(API).json()["lists"]}
    assert listed[lid]["lastUsed"]


def test_export_is_a_csv_of_the_members(monkeypatch):
    crm = ListCrm()
    a = _lead(crm, "Acme")
    client = _client(monkeypatch, crm, Both())
    lid = _new(client, "Q", "dynamic", include=[QUALIFIED])
    client.post(f"{API}/{lid}/run")
    resp = client.get(f"{API}/{lid}/export")
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/csv")
    lines = resp.text.lstrip("\ufeff").splitlines()
    assert lines[0].startswith("Type,Name,Brought in by,Lead status")
    assert "Acme" in lines[1] and a["id"] in lines[1]


class OrgCrm(ListCrm):
    """ListCrm plus the three organisation types and the links § 7c.3 walks."""

    LINKS = {
        "CEngagement": {"engagementClient": {"type": "belongsTo", "entity": "CClientProfile"},
                        "referringPartner": {"type": "belongsTo", "entity": "CPartnerProfile"},
                        "outreachCampaign": {"type": "belongsTo", "entity": cfg.CAMPAIGN}},
        "CClientProfile": {"linkedCompany": {"type": "hasOne", "entity": "Account", "foreign": "cClientProfile"}},
        "CPartnerProfile": {"partnerCompany": {"type": "belongsTo", "entity": "Account"},
                            "partnerManager": {"type": "belongsTo", "entity": "CMentorProfile"}},
        "CSponsorProfile": {"sponsorCompany": {"type": "belongsTo", "entity": "Account"},
                            "cBMSponsorManager": {"type": "belongsTo", "entity": "CMentorProfile"}},
    }
    FIELDS = {
        "CEngagement": {"engagementStatus": {"type": "enum", "options": ["Active", "Completed", "Inactive"]},
                        "closeDate": {"type": "date"}, "referringPartner": {"type": "link"},
                        "engagementClient": {"type": "link"}},
        "CClientProfile": {"industrySector": {"type": "enum", "options": ["", "Manufacturing", "Retail Trade"]}},
        "Account": {"billingAddressPostalCode": {"type": "varchar"},
                    "cIndustrySector": {"type": "enum", "options": ["", "Manufacturing"]}},
        "CPartnerProfile": {"partnershipStatus": {"type": "enum", "options": ["", "Candidate", "MOU/Contract Signed"]},
                            "partnerManager": {"type": "link"}, "partnerCompany": {"type": "link"}},
        "CSponsorProfile": {"funderStatus": {"type": "enum", "options": ["", "Active", "Ended"]},
                            "sponsorCompany": {"type": "link"}},
    }

    async def metadata(self, key: str):
        parts = key.split(".")
        if len(parts) == 3 and parts[0] == "entityDefs":
            if parts[2] == "links" and parts[1] in self.LINKS:
                return dict(self.LINKS[parts[1]])
            if parts[2] == "fields" and parts[1] in self.FIELDS:
                return dict(self.FIELDS[parts[1]])
        return await super().metadata(key)

    async def list_related(self, entity, record_id, link, *, select=None, max_size=200):
        ids = self.related.get((entity, record_id, link), set())
        return {"total": len(ids), "list": [{"id": i} for i in sorted(ids)]}


def _org_world():
    crm = OrgCrm()
    acme = crm.add(cfg.ACCOUNT, {"name": "Acme Tool", "billingAddressStreet": "1 Elm", "billingAddressCity": "Euclid",
                                 "billingAddressState": "OH", "billingAddressPostalCode": "44117"})
    shop = crm.add(cfg.ACCOUNT, {"name": "Corner Shop", "billingAddressStreet": "2 Oak", "billingAddressCity": "Parma",
                                 "billingAddressState": "OH", "billingAddressPostalCode": "44129"})
    p_acme = crm.add("CClientProfile", {"name": "Acme profile", "industrySector": "Manufacturing"})
    p_shop = crm.add("CClientProfile", {"name": "Shop profile", "industrySector": "Retail Trade"})
    acme["cClientProfileId"] = p_acme["id"]
    shop["cClientProfileId"] = p_shop["id"]
    boss = _contact(crm, "Ann Boss", cContactType=["Client"])
    clerk = _contact(crm, "Carl Clerk", cContactType=["Client"])
    e_acme = crm.add("CEngagement", {"name": "Acme — 2025", "engagementStatus": "Completed", "closeDate": "2025-01-10",
                                     "engagementClientId": p_acme["id"], "primaryEngagementContactId": boss["id"]})
    e_shop = crm.add("CEngagement", {"name": "Shop — 2026", "engagementStatus": "Active",
                                     "engagementClientId": p_shop["id"]})
    crm.related[("CEngagement", e_acme["id"], "engagementContacts")] = {boss["id"], clerk["id"]}
    return crm, {"acme": acme, "shop": shop, "e_acme": e_acme, "e_shop": e_shop, "boss": boss, "clerk": clerk}


def test_a_field_through_two_links_selects_the_client():
    crm, w = _org_world()
    cat = cat_for(crm)
    assert "engagementClient.industrySector" in [f["field"] for f in cat["client"]["fields"]]
    by_sector = recipe(include=[match("client", ("engagementClient.industrySector", "in", ["Manufacturing"]))])
    assert set(run(audience.run_recipe(crm, by_sector, cat))["keys"]) == {f"client:{w['e_acme']['id']}"}
    # the hasOne hop: the key sits on the Company (cClientProfileId)
    by_zip = recipe(include=[match("client", ("engagementClient.linkedCompany.billingAddressPostalCode", "in", "44129"))])
    assert set(run(audience.run_recipe(crm, by_zip, cat))["keys"]) == {f"client:{w['e_shop']['id']}"}


def test_closed_more_than_n_days_ago():
    crm, w = _org_world()
    cat = cat_for(crm)
    r = recipe(include=[match("client", ("engagementStatus", "in", ["Completed"]), ("closeDate", "olderDays", 365))])
    assert set(run(audience.run_recipe(crm, r, cat))["keys"]) == {f"client:{w['e_acme']['id']}"}


def test_a_client_reaches_its_primary_contact_or_every_contact():
    crm, w = _org_world()
    keys = [f"client:{w['e_acme']['id']}", f"client:{w['e_shop']['id']}"]
    primary = run(audience.resolve_targets(crm, cfg.KIND_EMAIL, keys))
    assert [t["id"] for t in primary["targets"]] == [w["boss"]["id"]]
    assert {s["code"]: s["count"] for s in primary["skipped"]} == {"no_primary": 1}
    every = run(audience.resolve_targets(crm, cfg.KIND_EMAIL, keys, every_contact=True))
    assert {t["id"] for t in every["targets"]} == {w["boss"]["id"], w["clerk"]["id"]}
    assert {s["code"]: s["count"] for s in every["skipped"]} == {"no_contacts": 1}


def test_a_client_postcard_goes_to_its_company_through_the_profile():
    crm, w = _org_world()
    out = run(audience.resolve_targets(crm, cfg.KIND_POSTCARD, [f"client:{w['e_shop']['id']}"]))
    assert [(t["kind"], t["id"]) for t in out["targets"]] == [("company", w["shop"]["id"])]


def test_a_partner_link_field_offers_names_and_filters_by_id():
    crm = OrgCrm()
    mgr = crm.add("CMentorProfile", {"name": "Mia Manager"})
    other = crm.add("CMentorProfile", {"name": "Otto Other"})
    mine = crm.add("CPartnerProfile", {"name": "Library", "partnerManagerId": mgr["id"]})
    crm.add("CPartnerProfile", {"name": "Chamber", "partnerManagerId": other["id"]})
    cat = cat_for(crm)
    f = next(x for x in cat["partner"]["fields"] if x["field"] == "partnerManager")
    assert {"value": mgr["id"], "label": "Mia Manager"} in f["options"]
    r = recipe(include=[match("partner", ("partnerManager", "in", [mgr["id"]]))])
    assert set(run(audience.run_recipe(crm, r, cat))["keys"]) == {f"partner:{mine['id']}"}


def test_import_matches_ids_and_emails_and_counts_the_rest():
    crm = ListCrm()
    a = _lead(crm, "Acme", email="hi@acme.example")
    b = _lead(crm, "Bakery")
    r = recipe(include=[imported("lead", f"{b['id']}\nHI@acme.example\nnobody@x.example")])
    out = run(audience.run_recipe(crm, r, cat_for(crm)))
    assert set(out["keys"]) == {f"lead:{a['id']}", f"lead:{b['id']}"}
    assert out["groups"][0]["unmatched"] == 1
    # a file can also leave people out
    r2 = recipe(include=[QUALIFIED], exclude=[imported("lead", "hi@acme.example")])
    assert set(run(audience.run_recipe(crm, r2, cat_for(crm)))["keys"]) == {f"lead:{b['id']}"}


def test_org_import_takes_ids_only():
    r = recipe(include=[imported("funder", "someone@x.example")])
    assert "CRM id only" in audience.check_recipe(r, cat_for(OrgCrm()))[0]["message"]


def test_lists_of_lists_and_the_cycle_guard():
    crm = ListCrm()
    store = FakeListStore()
    a = _lead(crm, "Acme")
    b = _lead(crm, "Bakery", leadStatus=cfg.LEAD_UNQUALIFIED)
    cat = cat_for(crm)
    everyone = run(store.create_list(name="Everyone", notes="", kind="dynamic", actor="M",
                                     recipe=recipe(include=[match("lead", ("leadStatus", "in", ["Qualified", "Unqualified"]))])))
    never = run(store.create_list(name="Never", notes="", kind="static", actor="M", recipe=audience.empty_recipe()))
    run(store.hand_add_many(never["id"], [f"lead:{b['id']}"], "M"))
    r = recipe(include=[of_list(everyone["id"])], exclude=[of_list(never["id"])])
    out = run(audience.run_recipe(crm, r, cat, store=store))
    assert set(out["keys"]) == {f"lead:{a['id']}"}
    assert "Everyone" in out["groups"][0]["summary"] and out["groups"][1]["count"] == 1
    # a list naming a list that names it back
    other = run(store.create_list(name="Other", notes="", kind="dynamic", actor="M",
                                  recipe=recipe(include=[of_list(everyone["id"])])))
    assert run(audience.reaches(store, [other["id"]], everyone["id"]))
    loop = recipe(include=[of_list(other["id"])])
    run(store.save_list(everyone["id"], name="Everyone", notes="", kind="dynamic", actor="M", recipe=loop))
    with pytest.raises(audience.AudienceError, match="cannot include itself"):
        run(audience.run_recipe(crm, loop, cat, store=store, _seen=(everyone["id"],)))


def test_saving_a_cycle_is_refused(monkeypatch):
    crm = ListCrm()
    client = _client(monkeypatch, crm, Both())
    a = _new(client, "A", "dynamic", include=[QUALIFIED])
    b = _new(client, "B", "dynamic", include=[of_list(a)])
    resp = client.put(f"{API}/{a}", json={"name": "A", "kind": "dynamic",
                                          "recipe": {"include": [of_list(b)], "exclude": []}})
    assert resp.status_code == 400 and "cannot include itself" in resp.json()["detail"]


# --- migration 0037: the old steps converted (build plan § 7e.8) ------------------------------

def _migration():
    path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "0037_lists_include_leave_out.py"
    spec = importlib.util.spec_from_file_location("m0037", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_migration_converts_each_old_step_kind():
    m = _migration()
    cond = [{"field": "leadStatus", "op": "in", "value": ["Qualified"]}]
    groups, rebuild = m.convert_steps({"steps": [
        {"action": "add", "type": "lead", "conditions": cond},
        {"action": "addList", "listId": "L1"},
        {"action": "import", "type": "contact", "values": ["a@x.example"]},
        {"action": "remove", "type": "lead", "conditions": cond},
        {"action": "removeList", "listId": "L2"},
    ]})
    assert not rebuild
    assert groups["include"] == [{"kind": "match", "type": "lead", "conditions": cond},
                                 {"kind": "list", "listId": "L1"},
                                 {"kind": "import", "type": "contact", "values": ["a@x.example"]}]
    assert groups["exclude"] == [{"kind": "match", "type": "lead", "conditions": cond},
                                 {"kind": "list", "listId": "L2"}]
    # what the new engine reads back is the same shape
    assert audience.normalise_recipe(groups) == groups


def test_the_migration_marks_keep_only_and_order_that_mattered():
    m = _migration()
    cond = [{"field": "industry", "op": "in", "value": ["Retail Trade"]}]
    keep, rebuild = m.convert_steps({"steps": [{"action": "add", "type": "lead", "conditions": cond},
                                               {"action": "keep", "type": "lead", "conditions": cond}]})
    assert rebuild and len(keep["include"]) == 1 and not keep["exclude"]
    _order, rebuild = m.convert_steps({"steps": [{"action": "add", "type": "lead", "conditions": cond},
                                                 {"action": "remove", "type": "lead", "conditions": cond},
                                                 {"action": "add", "type": "lead", "conditions": cond}]})
    assert rebuild
    _fine, rebuild = m.convert_steps({"steps": [{"action": "add", "type": "lead", "conditions": cond},
                                                {"action": "add", "type": "lead", "conditions": cond},
                                                {"action": "remove", "type": "lead", "conditions": cond}]})
    assert not rebuild


def test_the_migration_leaves_a_new_shape_recipe_alone():
    """An upgrade run again after a downgrade must not empty a converted list."""
    m = _migration()
    groups = {"include": [{"kind": "list", "listId": "L1"}], "exclude": []}
    assert m.convert_steps(groups) == (groups, False)
