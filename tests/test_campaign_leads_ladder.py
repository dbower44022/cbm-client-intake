"""The Leads tab and the lead's page under the ladder (build plan § 7e.4;
rulings 104, 108, 113).

What these prove: the query carries the ladder's filters only when the CRM has
the fields; the six counts across the top are one ``total`` each under the
other filters; Assign to is a guarded bulk action for team members on leads
still being worked; an inline gap write is whitelisted and normalised; the
Activity timeline merges touches and the action history newest first; the
export grows the ladder's columns.
"""

from __future__ import annotations

import asyncio
import csv
import io

import pytest

from campaigns import config as cfg
from campaigns import ladder, leads, review
from campaigns.service import CampaignError

I, C, RF = cfg.LEVEL_IDENTIFIED, cfg.LEVEL_CONTACTABLE, cfg.LEVEL_REFERRED


def run(coro):
    return asyncio.run(coro)


def _match(row, clause):
    t, a, v = clause["type"], clause.get("attribute"), clause.get("value")
    x = row.get(a) if a else None
    if t == "or":
        return any(_match(row, c) for c in v)
    if t == "equals":
        return (x or "") == (v or "")
    if t == "notEquals":
        return (x or "") != (v or "")
    if t == "in":
        return (x or "") in v
    if t == "isNull":
        return x in (None, "")
    if t == "isNotNull":
        return x not in (None, "")
    if t == "isTrue":
        return bool(x)
    if t == "contains":
        return str(v).lower() in str(x or "").lower()
    if t == "startsWith":
        return str(x or "").startswith(v)
    raise AssertionError(f"unexpected where type {t}")


class FakeCrm:
    def __init__(self, *, ladder_fields=True):
        self.rows = {}
        self.lists = []
        self.updates = []
        self.ladder_fields = ladder_fields
        self._n = 0

    def lead(self, **row):
        self._n += 1
        row.setdefault("id", f"lead{self._n:03d}")
        row.setdefault("leadStatus", cfg.LEAD_QUALIFIED)
        row.setdefault("name", row.get("businessName") or f"Lead {self._n}")
        row.setdefault("createdAt", f"2026-10-{1 + self._n % 28:02d} 12:00:00")
        row.setdefault("modifiedAt", row["createdAt"])
        self.rows[row["id"]] = row
        return row

    async def metadata(self, key):
        if key.endswith(".links"):
            return {l: {} for l in ladder.LINKS} if self.ladder_fields else {}
        return {f: {} for f in ladder.FIELDS} if self.ladder_fields else {"leadStatus": {}}

    async def list(self, entity, select="", where=None, max_size=50, offset=0, order_by=None, order=None, **_):
        assert max_size <= 200
        self.lists.append({"select": select, "where": where or [], "max_size": max_size})
        rows = [r for r in self.rows.values() if all(_match(r, c) for c in (where or []))]
        if order_by:
            rows.sort(key=lambda r: str(r.get(order_by) or ""), reverse=order == "desc")
        return {"list": [dict(r) for r in rows[offset:offset + max_size]], "total": len(rows)}

    async def get(self, entity, record_id, select=""):
        return dict(self.rows.get(record_id) or {})

    async def update(self, entity, record_id, payload):
        self.updates.append((record_id, dict(payload)))
        self.rows[record_id].update(payload)
        return dict(self.rows[record_id])


def _crm():
    crm = FakeCrm()
    crm.lead(businessName="Acme", leadStatus=cfg.LEAD_UNQUALIFIED)
    crm.lead(businessName="Birch", qualificationLevel=I)
    crm.lead(businessName="Cedar", qualificationLevel=C, firstName="Ann", email="a@b.com", assignedUserId="u1", assignedUserName="Mark")
    crm.lead(businessName="Dune", qualificationLevel=RF, replied=True)
    crm.lead(businessName="Elm", leadStatus=cfg.LEAD_CONVERTED, replied=True)
    crm.lead(businessName="Fir", leadStatus=cfg.LEAD_DISQUALIFIED)
    return crm


# --- the query ---------------------------------------------------------------------------------

def test_the_ladder_filters_ride_the_query_and_mine_resolves_to_the_user():
    lq = leads.LeadQuery.from_params({"level": C, "assigned": "me", "replied": "true"}, me="u1")
    assert (lq.level, lq.assigned, lq.replied) == (C, "u1", "1")
    assert lq.params()["assigned"] == "u1" and lq.params()["replied"] == "1"
    where = leads.build_where(lq)
    assert {"type": "equals", "attribute": "qualificationLevel", "value": C} in where
    assert {"type": "equals", "attribute": "assignedUserId", "value": "u1"} in where
    assert {"type": "isTrue", "attribute": "replied"} in where
    assert {"type": "notEquals", "attribute": "leadStatus", "value": cfg.LEAD_CONVERTED} in where
    assert leads.LeadQuery.from_params({"level": "Hot"}).errors == ["Unknown level."]
    assert leads.LeadQuery.from_params({"assigned": "bad id!"}).errors == ["Unknown assignee."]
    unassigned = leads.build_where(leads.LeadQuery.from_params({"assigned": "none"}))
    assert {"type": "isNull", "attribute": "assignedUserId"} in unassigned


def test_search_adds_the_ladder_select_only_when_the_crm_has_the_fields():
    crm = _crm()
    res = run(leads.search(crm, leads.LeadQuery.from_params({"level": C})))
    assert res["ladder"] is True and [r["businessName"] for r in res["prospects"]] == ["Cedar"]
    assert "qualificationLevel" in crm.lists[-1]["select"] and "assignedUserName" in crm.lists[-1]["select"]
    bare = FakeCrm(ladder_fields=False)
    bare.lead(businessName="Acme")
    lq = leads.LeadQuery.from_params({"level": C, "assigned": "none", "sort": "qualificationLevel"})
    res = run(leads.search(bare, lq))
    assert res["ladder"] is False and len(res["prospects"]) == 1
    assert (lq.level, lq.assigned, lq.sort) == ("", "", "createdAt")
    assert "qualificationLevel" not in bare.lists[-1]["select"]


# --- the counts across the top -----------------------------------------------------------------------

def test_counts_are_six_totals_under_the_other_filters():
    crm = _crm()
    res = run(leads.counts(crm, leads.LeadQuery.from_params({})))
    assert res == {"ladder": True, "unqualified": 1, "identified": 1, "contactable": 1, "referred": 1,
                   "replied": 1, "disqualified": 1}
    assert all(l["max_size"] == 1 for l in crm.lists), "one total each, never a page of rows"
    # The other filters narrow every count; the status / level / replied ones do not.
    res = run(leads.counts(crm, leads.LeadQuery.from_params({"q": "Cedar", "level": I, "status": "Unqualified"})))
    assert (res["contactable"], res["identified"], res["unqualified"]) == (1, 0, 0)


def test_counts_without_the_ladder_are_the_two_statuses_alone():
    bare = FakeCrm(ladder_fields=False)
    bare.lead(leadStatus=cfg.LEAD_UNQUALIFIED); bare.lead(leadStatus=cfg.LEAD_DISQUALIFIED); bare.lead()
    assert run(leads.counts(bare, leads.LeadQuery.from_params({}))) == {"ladder": False, "unqualified": 1, "disqualified": 1}


# --- Assign to ---------------------------------------------------------------------------------------

def test_assign_payload_is_for_leads_still_being_worked():
    mark = {"id": "u1", "name": "Mark"}
    assert leads.assign_payload({"leadStatus": cfg.LEAD_QUALIFIED}, mark) == {"assignedUserId": "u1"}
    assert leads.assign_payload({"leadStatus": cfg.LEAD_UNQUALIFIED, "assignedUserId": "u2"}, mark) == {"assignedUserId": "u1"}
    for lead, words in (({"leadStatus": cfg.LEAD_CONVERTED}, "Converted"),
                        ({"leadStatus": cfg.LEAD_DISQUALIFIED}, "Disqualified"),
                        ({"leadStatus": cfg.LEAD_QUALIFIED, "sideExit": cfg.EXIT_STALE}, "stopped being worked"),
                        ({"leadStatus": cfg.LEAD_QUALIFIED, "assignedUserId": "u1"}, "Already assigned to Mark")):
        with pytest.raises(CampaignError, match=words):
            leads.assign_payload(lead, mark)


def test_bulk_assign_writes_as_the_user_and_skips_what_it_must():
    crm = _crm()
    items = [{"id": i, "leadStatus": crm.rows[i]["leadStatus"], "sideExit": ""} for i in crm.rows]
    out = run(leads.apply_bulk(crm, None, items, leads.ACTION_ASSIGN, reviewer="M", note="",
                               assignee={"id": "u1", "name": "Mark"}))
    assert sorted(d["name"] for d in out["done"]) == ["Acme", "Birch", "Dune"]
    assert {s["name"]: s["why"] for s in out["skipped"]} == {
        "Cedar": "Already assigned to Mark.",
        "Elm": "This lead is Converted; its Company or Contact is the record to work now.",
        "Fir": "A Disqualified lead is not worked, so it is not assigned.",
    }
    assert all(p == {"assignedUserId": "u1"} for _, p in crm.updates)
    with pytest.raises(CampaignError, match="Choose the team member"):
        run(leads.apply_bulk(crm, None, items[:1], leads.ACTION_ASSIGN, reviewer="M", note=""))


# --- the lead's page -----------------------------------------------------------------------------------

def test_facts_payload_whitelists_normalises_and_refuses_nothing_changed():
    lead = {"businessName": "Acme", "website": "", "email": "", "phone": "216", "firstName": ""}
    out = leads.facts_payload(lead, {"website": "acme.com", "firstName": " Ann ", "phone": "216",
                                     "referredByName": "Pat"}, ladder_on=True)
    assert out == {"website": "https://acme.com", "firstName": "Ann", "referredByName": "Pat"}
    assert leads.facts_payload(lead, {"businessName": "Acme Inc"}, ladder_on=True) == {"businessName": "Acme Inc", "name": "Acme Inc"}
    assert leads.facts_payload({"email": "a@b.com"}, {"email": ""}, ladder_on=True) == {"email": None}
    with pytest.raises(CampaignError, match="not a field"):
        leads.facts_payload(lead, {"leadStatus": "Qualified"}, ladder_on=True)
    with pytest.raises(CampaignError, match="referrer fields"):
        leads.facts_payload(lead, {"referredByName": "Pat"}, ladder_on=False)
    with pytest.raises(CampaignError, match="not an email address"):
        leads.facts_payload(lead, {"email": "nope"}, ladder_on=True)
    with pytest.raises(CampaignError, match="Unknown partner"):
        leads.facts_payload(lead, {"referredByPartnerId": "x!"}, ladder_on=True)
    with pytest.raises(CampaignError, match="Nothing changed"):
        leads.facts_payload(lead, {"phone": "216"}, ladder_on=True)


def test_activity_rows_merge_touches_and_history_newest_first():
    touches = [{"id": "t1", "channel": "Postcard", "touchStatus": "Sent", "sentAt": "2026-10-01 10:00:00",
                "outreachCampaignName": "September cards", "scanCount": 2},
               {"id": "t2", "channel": "Call", "touchStatus": "Done", "doneAt": "2026-10-20 10:00:00", "outcome": "No answer"}]
    actions = [{"id": "a1", "actionType": "Lead Level Set", "summary": "Set the level to Contactable",
                "actorName": "Mark Marketing", "createdAt": "2026-10-15 09:00:00"}]
    rows = leads.activity_rows(touches, actions)
    assert [r["title"] for r in rows] == ["Call done", "Lead Level Set", "Postcard sent"]
    assert rows[2]["detail"] == "September cards · scans 2" and rows[1]["by"] == "Mark Marketing"
    assert [r["kind"] for r in rows] == ["touch", "action", "touch"]


def test_export_grows_the_ladder_columns_when_the_crm_has_them():
    crm = _crm()
    gen = run(leads.export_rows(crm, leads.LeadQuery.from_params({})))

    async def collect():
        return [line async for line in gen]
    lines = run(collect())
    header = next(csv.reader(io.StringIO(lines[0].lstrip("﻿"))))
    assert "Level" in header and "Assigned to" in header and "Referred by (partner)" in header
    rows = list(csv.reader(io.StringIO("".join(lines[1:]))))
    cedar = next(r for r in rows if r[0] == "Cedar")
    assert cedar[header.index("Level")] == C and cedar[header.index("Assigned to")] == "Mark"


def test_review_labels_and_the_assign_label_are_distinct_vocabulary():
    assert leads.ASSIGN_LABEL not in review.ACTION_LABELS.values()
    assert leads.ACTION_ASSIGN in leads.BULK_ACTIONS
