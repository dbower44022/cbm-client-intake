"""The qualification ladder (build plan § 7e.3; rulings 105, 106, 111, 117).

What these prove: the facts a lead holds earn exactly one level (105); the
level never moves backwards and, after a hand setting, moves forward only on a
NEW fact (106); a hand-set level with no snapshot is never moved (117); the
level is empty at any status but Qualified; placement after a write is
best-effort and feature-detected; the sweep reads only leads modified since
its watermark; the import computes the level into the create; Set level by
hand writes who and when and records the snapshot.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest

from campaigns import config as cfg
from campaigns import imports, ladder
from campaigns.service import CampaignError

P, PH, E, R = ladder.FACT_PERSON, ladder.FACT_PHONE, ladder.FACT_EMAIL, ladder.FACT_REFERRER
I, C, RF = cfg.LEVEL_IDENTIFIED, cfg.LEVEL_CONTACTABLE, cfg.LEVEL_REFERRED


def run(coro):
    return asyncio.run(coro)


# --- the rule, pure ---------------------------------------------------------------------------

@pytest.mark.parametrize("lead, expected", [
    ({}, set()),
    ({"firstName": "Ann"}, {P}),
    ({"lastName": "Lee", "phone": "216 555 0100"}, {P, PH}),
    ({"email": "a@b.com"}, {E}),
    ({"referredByName": "Pat at the chamber"}, {R}),
    ({"referredByPartnerId": "pp1", "email": "a@b.com", "firstName": " "}, {R, E}),
])
def test_facts_name_what_the_lead_holds(lead, expected):
    assert set(ladder.facts(lead)) == expected


@pytest.mark.parametrize("have, level", [
    (set(), I),
    ({P}, I),                       # a name alone is not reachable
    ({PH}, I),                      # a phone with no named person is Identified
    ({P, PH}, C),
    ({P, E}, C),
    ({R}, I),                       # ruling 105: a referrer with no phone or email is Identified
    ({R, E}, RF),
    ({R, PH, P}, RF),
])
def test_placed_is_ruling_105(have, level):
    assert ladder.placed(have) == level


def test_next_level_never_moves_backwards():
    assert ladder.next_level(RF, False, {P}, None) is None
    assert ladder.next_level(C, False, set(), None) is None
    assert ladder.next_level(C, False, {P, PH}, None) is None       # already there


def test_next_level_moves_forward_with_no_hand_setting():
    assert ladder.next_level(None, False, set(), None) == I
    assert ladder.next_level(I, False, {P, E}, None) == C
    assert ladder.next_level(C, False, {R, E, P}, None) == RF


def test_a_hand_set_level_moves_only_on_a_new_fact():
    # Set to Identified by hand while the lead held a person and a phone: the
    # same facts never lift it (an unrelated edit leaves the level alone).
    assert ladder.next_level(I, True, {P, PH}, [P, PH]) is None
    # A referrer arrives: a new fact, and the facts now earn Referred.
    assert ladder.next_level(I, True, {P, PH, R}, [P, PH]) == RF
    # A new fact that earns nothing higher moves nothing.
    assert ladder.next_level(C, True, {P, PH, E}, [P, PH]) is None


def test_a_hand_set_level_with_no_snapshot_is_never_moved():
    assert ladder.next_level(I, True, {P, PH, R, E}, None) is None       # ruling 117


def test_plan_level_clears_outside_qualified_and_leaves_empty_alone():
    assert ladder.plan_level({"leadStatus": cfg.LEAD_UNQUALIFIED, "qualificationLevel": C}, None) == ""
    assert ladder.plan_level({"leadStatus": cfg.LEAD_CONVERTED, "qualificationLevel": I}, None) == ""
    assert ladder.plan_level({"leadStatus": cfg.LEAD_DISQUALIFIED}, None) is None
    assert ladder.plan_level({"leadStatus": cfg.LEAD_QUALIFIED, "email": "a@b.com", "firstName": "A"}, None) == C
    hand = {"leadStatus": cfg.LEAD_QUALIFIED, "qualificationLevel": I, "levelSetAt": "2026-10-25 01:00:00",
            "firstName": "A", "phone": "1", "referredByName": "Pat"}
    assert ladder.plan_level(hand, None) is None                               # 117: no snapshot
    assert ladder.plan_level(hand, {"facts": [P, PH]}) == RF                   # the referrer is new
    assert ladder.plan_level(hand, {"facts": [P, PH, R]}) is None              # nothing new


# --- the CRM side ------------------------------------------------------------------------------

class FakeCrm:
    def __init__(self, *, has_fields: bool = True):
        self.rows: dict[str, dict] = {}
        self.updates: list[tuple[str, dict]] = []
        self.has_fields = has_fields
        self.lists: list[dict] = []

    def lead(self, **row):
        row.setdefault("id", f"lead{len(self.rows) + 1}")
        row.setdefault("leadStatus", cfg.LEAD_QUALIFIED)
        row.setdefault("modifiedAt", "2026-10-25 10:00:00")
        self.rows[row["id"]] = row
        return row

    async def metadata(self, key):
        if not self.has_fields:
            return {"leadStatus": {}}
        if key.endswith(".fields"):
            return {f: {} for f in ladder.FIELDS}
        return {l: {} for l in ladder.LINKS}

    async def get(self, entity, record_id, select=""):
        return dict(self.rows.get(record_id) or {})

    async def update(self, entity, record_id, payload):
        self.updates.append((record_id, dict(payload)))
        self.rows[record_id].update(payload)
        return dict(self.rows[record_id])

    async def list(self, entity, select="", where=None, max_size=50, offset=0, order_by=None, order=None, **_):
        assert max_size <= 200
        self.lists.append({"where": where, "offset": offset})
        since = next(c["value"] for c in where if c["attribute"] == "modifiedAt")
        rows = sorted((r for r in self.rows.values() if r["modifiedAt"] > since), key=lambda r: r["modifiedAt"])
        return {"list": [dict(r) for r in rows[offset:offset + max_size]], "total": len(rows)}


class FakeStore:
    def __init__(self):
        self.snapshots: dict[str, dict] = {}

    async def get_level_manual(self, lead_id):
        return self.snapshots.get(lead_id)

    async def put_level_manual(self, lead_id, *, level, facts, set_by_id, set_by):
        self.snapshots[lead_id] = {"lead_id": lead_id, "level": level, "facts": list(facts),
                                   "set_by_id": set_by_id, "set_by": set_by}
        return self.snapshots[lead_id]

    async def level_manual_for(self, ids):
        return {i: s for i, s in self.snapshots.items() if i in ids}


class S:
    """The settings placement reads."""
    lead_ladder = True
    campaigns_enabled = True
    espo_dry_run = False
    espo_api_key = "k"
    espo_base_url = "https://crm"
    request_timeout_seconds = 5
    store_enabled = False
    database_url = ""


def test_after_write_places_the_level_under_the_given_client():
    crm = FakeCrm()
    lead = crm.lead(firstName="Ann", email="ann@b.com")
    out = run(ladder.after_write(lead["id"], client=crm, settings=S(), store=FakeStore()))
    assert out == C
    assert crm.updates == [(lead["id"], {"qualificationLevel": C})]


def test_after_write_is_silent_while_off_or_without_the_fields():
    crm = FakeCrm()
    lead = crm.lead(firstName="Ann", email="ann@b.com")
    off = S(); off.lead_ladder = False
    assert run(ladder.after_write(lead["id"], client=crm, settings=off, store=FakeStore())) is None
    bare = FakeCrm(has_fields=False)
    bare.lead(id=lead["id"], firstName="Ann", email="ann@b.com")
    assert run(ladder.after_write(lead["id"], client=bare, settings=S(), store=FakeStore())) is None
    assert crm.updates == [] and bare.updates == []


def test_after_write_never_raises():
    class Broken(FakeCrm):
        async def get(self, *a, **k):
            raise RuntimeError("down")
    crm = Broken(); crm.lead(firstName="Ann")
    assert run(ladder.after_write("lead1", client=crm, settings=S(), store=FakeStore())) is None


def test_set_by_hand_writes_who_and_when_and_records_the_snapshot():
    crm, store = FakeCrm(), FakeStore()
    lead = crm.lead(firstName="Ann", phone="216", qualificationLevel=C)
    out = run(ladder.set_by_hand(crm, store, lead, I, user_id="u1", user_name="Mark Marketing"))
    assert out["was"] == C and set(out["written"]) == {"qualificationLevel", "levelSetByHandId", "levelSetAt"}
    written = crm.updates[0][1]
    assert written["qualificationLevel"] == I and written["levelSetByHandId"] == "u1" and written["levelSetAt"]
    assert store.snapshots[lead["id"]]["facts"] == sorted([P, PH])
    # The same facts never lift it back; a new email does (ruling 106).
    assert run(ladder.after_write(lead["id"], client=crm, settings=S(), store=store)) is None
    crm.rows[lead["id"]]["email"] = "ann@b.com"
    assert run(ladder.after_write(lead["id"], client=crm, settings=S(), store=store)) == C


def test_set_by_hand_refuses_a_bad_level_or_an_unqualified_lead():
    crm = FakeCrm()
    with pytest.raises(CampaignError):
        run(ladder.set_by_hand(crm, FakeStore(), crm.lead(), "Hot", user_id="u", user_name="M"))
    with pytest.raises(CampaignError):
        run(ladder.set_by_hand(crm, FakeStore(), crm.lead(leadStatus=cfg.LEAD_UNQUALIFIED), I,
                               user_id="u", user_name="M"))
    with pytest.raises(CampaignError):
        run(ladder.set_by_hand(crm, FakeStore(), crm.lead(sideExit=cfg.EXIT_STALE), I, user_id="u", user_name="M"))
    assert crm.updates == []


# --- the sweep -----------------------------------------------------------------------------------

def test_sweep_reads_since_the_watermark_and_places_only_what_changes():
    ladder.reset()
    crm, store = FakeCrm(), FakeStore()
    a = crm.lead(firstName="Ann", email="a@b.com", modifiedAt="2026-10-25 09:30:00")              # -> Contactable
    b = crm.lead(qualificationLevel=C, firstName="Bob", modifiedAt="2026-10-25 09:40:00")           # stays (never backwards)
    c = crm.lead(leadStatus=cfg.LEAD_DISQUALIFIED, qualificationLevel=I, modifiedAt="2026-10-25 09:50:00")  # cleared
    d = crm.lead(firstName="Old", email="o@b.com", modifiedAt="2026-10-23 09:00:00")               # before the lookback
    now = datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc)
    totals = run(ladder.run_level_sweep(S(), client=crm, store=store, now=now))
    assert (totals["planned"], totals["placed"], totals["cleared"], totals["errors"]) == (2, 1, 1, 0)
    assert totals["since"] == "2026-10-24 10:00:00"
    assert dict(crm.updates) == {a["id"]: {"qualificationLevel": C}, c["id"]: {"qualificationLevel": None}}
    assert crm.rows[b["id"]]["qualificationLevel"] == C and "qualificationLevel" not in crm.rows[d["id"]]
    # The second pass asks from a minute before the first pass started.
    crm.updates.clear()
    run(ladder.run_level_sweep(S(), client=crm, store=store, now=now))
    assert crm.lists[-1]["where"][0]["value"] == "2026-10-25 09:59:00"
    assert crm.updates == []


def test_sweep_is_off_without_the_switch():
    ladder.reset()
    off = S(); off.lead_ladder = False
    crm = FakeCrm(); crm.lead(firstName="Ann", email="a@b.com")
    totals = run(ladder.run_level_sweep(off, client=crm, store=FakeStore()))
    assert totals["planned"] == 0 and crm.lists == []


def test_plan_text_names_each_move():
    text = ladder.plan_text([{"id": "l1", "name": "Acme", "from": "", "to": C}], "2026-10-24 10:00:00")
    assert "whose level would change: 1" in text and "(none)" in text and "Contactable" in text and "Acme" in text


# --- the import -----------------------------------------------------------------------------------

def _plan(door=cfg.SOURCE_FILING):
    return {"door": door, "listSource": "", "qualifiedBy": "the state"}


def test_import_computes_the_level_into_the_create_only_when_asked():
    row = {"business_name": "Acme", "website": "https://acme.com", "contact_first_name": "Ann", "phone": "216"}
    plain = imports._lead_payload(row, _plan(), "batch", {"outcome": imports.OUTCOME_CREATE})
    assert plain["leadStatus"] == cfg.LEAD_QUALIFIED and "qualificationLevel" not in plain
    with_level = imports._lead_payload(row, _plan(), "batch", {"outcome": imports.OUTCOME_CREATE}, ladder_fields=True)
    assert with_level["qualificationLevel"] == C
    alone = imports._lead_payload({"business_name": "Acme", "website": "https://acme.com"}, _plan(), "batch",
                                  {"outcome": imports.OUTCOME_CREATE}, ladder_fields=True)
    assert alone["qualificationLevel"] == I
    unq = imports._lead_payload({"business_name": "Acme"}, _plan(cfg.SOURCE_LIST), "batch",
                                {"outcome": imports.OUTCOME_CREATE}, ladder_fields=True)
    assert unq["leadStatus"] == cfg.LEAD_UNQUALIFIED and "qualificationLevel" not in unq
