"""The Leads and Review grids at volume (build plan § 7b, Doug 10-20-26).

What these prove: the query is parsed and whitelisted; the CRM does the
searching, sorting and counting (a page and a true total, never a silent cap);
the in-a-campaign filter; select-all refuses above the cap; every bulk and
single decision re-reads the lead and is skipped or refused, naming who, when
someone else changed it; a website or email typed into a Review row rides with
Qualify; the export is a CSV of what the filters match.
"""

from __future__ import annotations

import asyncio
import csv
import io
from typing import Any

import pytest

from campaigns import config as cfg
from campaigns import leads, review
from campaigns.service import CampaignError


def _match(row: dict, clause: dict) -> bool:
    t, a, v = clause["type"], clause.get("attribute"), clause.get("value")
    x = row.get(a) if a else None
    if t == "or":
        return any(_match(row, c) for c in v)
    if t == "equals":
        return x == v
    if t == "in":
        return x in v
    if t == "isNull":
        return x in (None, "")
    if t == "isNotNull":
        return x not in (None, "")
    if t == "contains":
        return v.lower() in str(x or "").lower()
    if t == "startsWith":
        return str(x or "").startswith(v)
    if t == "greaterThanOrEquals":
        return str(x or "") >= v
    if t == "lessThanOrEquals":
        return str(x or "") <= v
    if t == "isLinked":
        return bool(row.get("_touches"))
    if t == "isNotLinked":
        return not row.get("_touches")
    raise AssertionError(f"unexpected where type {t}")


class FakeCrm:
    def __init__(self):
        self.rows: dict[str, dict[str, dict]] = {cfg.PROSPECT: {}, cfg.TOUCH: {}}
        self.lists: list[tuple[str, int, int]] = []
        self.updates: list[tuple[str, str, dict]] = []
        self._n = 0

    def lead(self, **row) -> dict:
        self._n += 1
        row.setdefault("id", f"lead{self._n:04d}")
        row.setdefault("leadStatus", cfg.LEAD_UNQUALIFIED)
        row.setdefault("createdAt", f"2026-10-{1 + self._n % 28:02d} 12:00:00")
        self.rows[cfg.PROSPECT][row["id"]] = row
        return row

    def touch(self, campaign: str, lead_id: str, status: str = cfg.TOUCH_SENT) -> None:
        self._n += 1
        tid = f"touch{self._n:04d}"
        self.rows[cfg.TOUCH][tid] = {"id": tid, "outreachCampaignId": campaign, "prospectId": lead_id,
                                     "touchStatus": status}
        self.rows[cfg.PROSPECT][lead_id]["_touches"] = True

    async def list(self, entity, select="", where=None, max_size=50, offset=0, order_by=None, order=None, **_):
        assert max_size <= 200, "the CRM refuses a page over 200"
        self.lists.append((entity, offset, max_size))
        rows = [r for r in self.rows[entity].values() if all(_match(r, c) for c in (where or []))]
        if order_by:
            rows.sort(key=lambda r: str(r.get(order_by) or ""), reverse=order == "desc")
        return {"list": [dict(r) for r in rows[offset:offset + max_size]], "total": len(rows)}

    async def get(self, entity, record_id, select=""):
        return dict(self.rows[entity].get(record_id) or {})

    async def update(self, entity, record_id, payload):
        self.updates.append((entity, record_id, dict(payload)))
        self.rows[entity][record_id].update(payload)
        return dict(self.rows[entity][record_id])


def run(coro):
    return asyncio.run(coro)


# --- the query -----------------------------------------------------------------------------

def test_review_queue_is_fixed_to_unqualified_and_oldest_first():
    lq = leads.LeadQuery.from_params({"status": "Qualified", "exit": "Stale"}, review_queue=True)
    assert (lq.status, lq.exit, lq.dir) == (cfg.LEAD_UNQUALIFIED, "none", "asc")


def test_sort_is_whitelisted_and_page_capped_at_200():
    lq = leads.LeadQuery.from_params({"sort": "description; drop", "limit": "5000", "offset": "-3"})
    assert (lq.sort, lq.limit, lq.offset) == ("createdAt", 200, 0)


def test_a_bad_date_or_campaign_is_refused_in_words():
    lq = leads.LeadQuery.from_params({"arrivedFrom": "10/01/2026", "inCampaign": "x y"})
    with pytest.raises(CampaignError, match="YYYY-MM-DD"):
        run(leads.search(FakeCrm(), lq))


def test_search_box_covers_every_named_field_and_a_typed_phone():
    clause = leads.build_where(leads.LeadQuery.from_params({"q": "216-555-0141"}))[0]
    attrs = {c["attribute"] for c in clause["value"]}
    assert set(leads.SEARCH_FIELDS) <= attrs
    assert {"type": "contains", "attribute": "phone", "value": "2165550141"} in clause["value"]


def test_place_is_a_zip_prefix_or_a_city():
    zip_ = leads.build_where(leads.LeadQuery.from_params({"place": "4410"}))
    city = leads.build_where(leads.LeadQuery.from_params({"place": "Lakewood"}))
    assert zip_[0]["type"] == "startsWith" and zip_[0]["attribute"] == "mailingAddressPostalCode"
    assert city[0]["type"] == "contains" and city[0]["attribute"] == "mailingAddressCity"


# --- search ----------------------------------------------------------------------------------

def _crm_with(n: int) -> FakeCrm:
    crm = FakeCrm()
    for i in range(n):
        crm.lead(businessName=f"Business {i:05d}", mailingAddressPostalCode="44102" if i % 2 else "44113",
                 phone=f"+1216555{i:04d}")
    return crm


def test_a_page_and_the_true_total_with_no_silent_cap():
    crm = _crm_with(2600)
    res = run(leads.search(crm, leads.LeadQuery.from_params({"offset": "2550", "limit": "50"})))
    assert res["total"] == 2600 and len(res["prospects"]) == 50
    assert len(crm.lists) == 1, "one CRM call for a page, never every lead"


def test_search_finds_by_phone_typed_with_dashes():
    crm = _crm_with(30)
    res = run(leads.search(crm, leads.LeadQuery.from_params({"q": "216-555-0017"})))
    assert [p["businessName"] for p in res["prospects"]] == ["Business 00017"]


def test_in_a_campaign_filters_by_its_touches_and_the_other_filters():
    crm = _crm_with(300)
    ids = list(crm.rows[cfg.PROSPECT])
    for lid in ids[:250]:
        crm.touch("camp0001", lid)
    crm.touch("camp0001", ids[260], cfg.TOUCH_CANCELLED)
    lq = leads.LeadQuery.from_params({"inCampaign": "camp0001", "place": "44102", "limit": "20",
                                      "sort": "businessName", "dir": "asc"})
    res = run(leads.search(crm, lq))
    assert res["total"] == 125
    names = [p["businessName"] for p in res["prospects"]]
    assert names == sorted(names) and len(names) == 20
    yes = run(leads.search(crm, leads.LeadQuery.from_params({"inCampaign": "yes"})))
    no = run(leads.search(crm, leads.LeadQuery.from_params({"inCampaign": "no"})))
    assert yes["total"] + no["total"] == 300


def test_select_all_refuses_above_the_cap():
    crm = _crm_with(leads.BULK_CAP + 1)
    with pytest.raises(CampaignError, match="narrow the filter"):
        run(leads.resolve(crm, leads.LeadQuery.from_params({})))
    items = run(leads.resolve(crm, leads.LeadQuery.from_params({"place": "44102"})))
    assert len(items) == leads.BULK_CAP // 2 and set(items[0]) == {"id", "leadStatus", "sideExit"}


# --- the guard and the bulk actions ----------------------------------------------------------------

def test_changed_since_names_who():
    lead = {"leadStatus": cfg.LEAD_QUALIFIED, "sideExit": None, "modifiedByName": "Mark Marketing",
            "modifiedAt": "2026-10-20 13:05:00"}
    assert leads.changed_since(lead, {"leadStatus": cfg.LEAD_UNQUALIFIED}) == \
        "Already Qualified, by Mark Marketing at 2026-10-20 13:05 UTC."
    assert leads.changed_since(lead, {"leadStatus": cfg.LEAD_QUALIFIED, "sideExit": ""}) is None


def test_bulk_does_skips_and_never_overwrites():
    crm = FakeCrm()
    a = crm.lead(businessName="A Holdings")
    b = crm.lead(businessName="B Holdings", leadStatus=cfg.LEAD_QUALIFIED, modifiedByName="Sam")
    c = crm.lead(businessName="C Holdings", sideExit=cfg.EXIT_STALE)
    items = [{"id": a["id"], "leadStatus": cfg.LEAD_UNQUALIFIED, "sideExit": ""},
             {"id": b["id"], "leadStatus": cfg.LEAD_UNQUALIFIED, "sideExit": ""},   # changed since seen
             {"id": c["id"], "leadStatus": cfg.LEAD_UNQUALIFIED, "sideExit": cfg.EXIT_STALE},  # rule refuses
             {"id": "missing0001"}]
    out = run(leads.apply_bulk(crm, None, items, review.ACTION_DISQUALIFY, reviewer="Mark", note="holding company"))
    assert [d["name"] for d in out["done"]] == ["A Holdings"]
    assert {s["name"] for s in out["skipped"]} == {"B Holdings", "C Holdings", ""}
    assert "by Sam" in next(s["why"] for s in out["skipped"] if s["name"] == "B Holdings")
    assert crm.rows[cfg.PROSPECT][a["id"]]["leadStatus"] == cfg.LEAD_DISQUALIFIED
    assert crm.rows[cfg.PROSPECT][b["id"]]["leadStatus"] == cfg.LEAD_QUALIFIED
    assert [u[1] for u in crm.updates] == [a["id"]]


def test_bulk_refuses_qualify_a_missing_reason_and_a_big_batch():
    crm = FakeCrm()
    with pytest.raises(CampaignError, match="Only Disqualify and Do Not Contact"):
        run(leads.apply_bulk(crm, None, [], review.ACTION_QUALIFY, reviewer="M", note=""))
    with pytest.raises(CampaignError, match="reason is required"):
        run(leads.apply_bulk(crm, None, [{"id": "abcdef1"}], review.ACTION_DISQUALIFY, reviewer="M", note=" "))
    with pytest.raises(CampaignError, match="At most 50"):
        run(leads.apply_bulk(crm, None, [{"id": f"abcdef{i}"} for i in range(51)],
                             review.ACTION_DO_NOT_CONTACT, reviewer="M", note=""))


# --- Qualify with a typed website or email ---------------------------------------------------------

def test_qualify_carries_the_typed_website():
    lead = {"id": "l1", "leadStatus": cfg.LEAD_UNQUALIFIED}
    crm = FakeCrm(); crm.rows[cfg.PROSPECT]["l1"] = dict(lead)
    out = run(review.apply_action(crm, None, lead, review.ACTION_QUALIFY, reviewer="Mark",
                                  website="shorewaysigns.example.com"))
    stored = crm.rows[cfg.PROSPECT]["l1"]
    assert stored["website"] == "https://shorewaysigns.example.com"
    assert stored["leadStatus"] == cfg.LEAD_QUALIFIED and "website" in out["written"]


def test_qualify_without_either_says_where_to_type_it():
    with pytest.raises(CampaignError, match="Website or Email box"):
        review.plan_action({"leadStatus": cfg.LEAD_UNQUALIFIED}, review.ACTION_QUALIFY, reviewer="M")


def test_a_bad_email_is_refused_and_an_unchanged_one_not_rewritten():
    with pytest.raises(CampaignError, match="not an email address"):
        review.contact_changes({}, None, "owner at shop")
    assert review.contact_changes({"email": "A@b.com"}, None, "a@B.com") == {}


# --- export ----------------------------------------------------------------------------------------

def test_export_is_a_csv_of_what_the_filters_match():
    crm = _crm_with(12)

    async def collect():
        gen = await leads.export_rows(crm, leads.LeadQuery.from_params({"place": "44113"}))
        return "".join([line async for line in gen])

    body = run(collect())
    rows = list(csv.reader(io.StringIO(body.lstrip("﻿"))))
    assert rows[0][0] == "Business" and rows[0][-1] == "Lead id"
    assert len(rows) == 1 + 6


# --- the routes ------------------------------------------------------------------------------------

def _client(monkeypatch, crm):
    from tests.test_campaigns import MARKETING, build
    return build(monkeypatch, user=MARKETING, crm=crm)


def test_routes_list_review_guard_bulk_and_export(monkeypatch):
    crm = _crm_with(5)
    import campaigns.router as router_mod
    monkeypatch.setattr(router_mod, "_system_client", lambda settings: None)
    client = _client(monkeypatch, crm)
    res = client.get("/campaigns/api/prospects?limit=2&sort=businessName&dir=asc").json()
    assert res["total"] == 5 and [p["businessName"] for p in res["prospects"]] == ["Business 00000", "Business 00001"]
    lead_id = res["prospects"][0]["id"]
    stale = client.post(f"/campaigns/api/prospects/{lead_id}/review",
                        json={"action": "qualify", "website": "x.example.com", "seenStatus": "Qualified"})
    assert stale.status_code == 409 and stale.json()["detail"].startswith("Already Unqualified")
    ok = client.post(f"/campaigns/api/prospects/{lead_id}/review",
                     json={"action": "qualify", "website": "x.example.com", "seenStatus": "Unqualified", "seenExit": ""})
    assert ok.status_code == 200
    items = client.post("/campaigns/api/prospects/bulk/resolve",
                        json={"query": {"place": "44102"}, "review": True}).json()["items"]
    assert len(items) == 2
    done = client.post("/campaigns/api/prospects/bulk",
                       json={"action": "do-not-contact", "note": "", "items": items}).json()
    assert len(done["done"]) == 2
    csv_resp = client.get("/campaigns/api/prospects/export?place=44113")
    assert csv_resp.status_code == 200 and csv_resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv_resp.headers["content-disposition"]
