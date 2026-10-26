"""The import tool (build plan § 7e.7; rulings 79-88, 111, 123, 127) — step M4.

What these prove: a template is recognised by header overlap and its
differences named (new, missing, likely renames), never applied by itself;
each of the four fixes maps a row; a required field left unmapped stops the
import with the field named; Excel reads like CSV, a workbook with several
sheets asks which, ``.xls`` is refused; the preview is a worker job (queued →
running → ready / failed) that dry-run runs inline; a repeat row fills only a
lead's EMPTY fields; the level per row follows the ladder's own rule with the
template's partner as referrer; excluded rows are skipped and counted; Undo
deletes only untouched leads under the org-wide key, lists the touched ones,
forgets the deleted rows and stamps the batch; the template endpoints are shared
by the team; the switch off leaves every endpoint as it was.
"""

from __future__ import annotations

import asyncio
import base64
import io
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from openpyxl import Workbook

from campaigns import config as cfg
from campaigns import import_templates as tpl
from campaigns import imports
from campaigns.service import CampaignError
from campaigns.store import PLAN_FAILED, PLAN_QUEUED, PLAN_READY, PLAN_RUNNING
from core.config import Settings, get_settings
from tests.test_campaigns import FakeCrm, FakeStore, MARKETING, build

I, C, R = cfg.LEVEL_IDENTIFIED, cfg.LEVEL_CONTACTABLE, cfg.LEVEL_REFERRED


def run(coro):
    return asyncio.run(coro)


def _now():
    return datetime.now(timezone.utc)


# --- fakes ------------------------------------------------------------------------------------------

class TemplateStore(FakeStore):
    """The campaign store with the M4 methods, in memory."""

    def __init__(self):
        super().__init__()
        self.templates: dict[str, dict] = {}
        self.members: set[str] = set()
        self.progress: list[dict] = []

    async def list_templates(self): return sorted(self.templates.values(), key=lambda t: t["name"])
    async def get_template(self, template_id): return self.templates.get(template_id)
    async def create_template(self, values, *, actor):
        row = {"id": f"t{len(self.templates) + 1}abcdef", **values, "created_by": actor, "created_at": _now(),
               "updated_by": actor, "updated_at": _now(), "last_batch_id": None}
        self.templates[row["id"]] = row; return row
    async def update_template(self, template_id, values, *, actor):
        self.templates[template_id].update(values, updated_by=actor, updated_at=_now()); return self.templates[template_id]
    async def delete_template(self, template_id): return self.templates.pop(template_id, None) is not None
    async def set_template_last_batch(self, template_id, batch_id):
        if template_id in self.templates:
            self.templates[template_id]["last_batch_id"] = batch_id

    async def create_batch(self, **kw):
        kw.setdefault("plan_status", None); kw.setdefault("template_id", None); kw.setdefault("file_name", None)
        row = await super().create_batch(**kw)
        row.update(excluded_rows=None, undone_at=None, undone_by=None, undo_result=None, plan_error=None,
                   plan_progress=None, plan_claimed_at=None, created_at=_now())
        return row
    async def find_batch_by_file(self, sha):
        return next((b for b in self.batches.values() if b["file_sha256"] == sha and b["status"] == "applied"), None)
    async def claim_plan(self, now=None):
        for b in self.batches.values():
            if b.get("plan_status") == PLAN_QUEUED:
                b["plan_status"] = PLAN_RUNNING; b["plan_claimed_at"] = _now(); return dict(b)
        return None
    async def set_plan_progress(self, batch_id, progress):
        self.batches[batch_id]["plan_progress"] = progress; self.progress.append(progress)
    async def finish_plan(self, batch_id, *, plan, status, error=None, row_count=None):
        b = self.batches[batch_id]; b.update(plan_status=status, plan_error=error, plan_progress=None)
        if plan is not None: b["plan"] = plan
    async def set_excluded_rows(self, batch_id, hashes): self.batches[batch_id]["excluded_rows"] = sorted(set(hashes))
    async def mark_applied(self, batch_id, result):
        self.batches[batch_id].update(status="applied", result=result, applied_at=_now())
    async def first_prospect_id(self, batch_id):
        return next((r["prospect_id"] for r in self.rows if r.get("batch_id") == batch_id and r.get("prospect_id")), None)
    async def record_rows(self, batch_id, rows):
        self.rows.extend([{**r, "batch_id": batch_id, "created_at": _now()} for r in rows])
    async def leads_for_hashes(self, hashes):
        out = {}
        for r in self.rows:
            if r["row_hash"] in hashes and r.get("prospect_id") and (r["row_hash"] not in out or r["outcome"] != "fills"):
                out[r["row_hash"]] = r["prospect_id"]
        return out
    async def batch_created_leads(self, batch_id):
        return [{"prospect_id": r["prospect_id"], "row_hash": r["row_hash"], "business_name": r.get("business_name"),
                 "created_at": r.get("created_at"), "outcome": r["outcome"]}
                for r in self.rows if r.get("batch_id") == batch_id and r.get("prospect_id") and r["outcome"] != "fills"]
    async def filled_by_later_batch(self, batch_id, prospect_ids):
        out = {}
        for r in self.rows:
            if r.get("prospect_id") in prospect_ids and r["outcome"] == "fills" and r.get("batch_id") != batch_id:
                out.setdefault(r["prospect_id"], self.batches[r["batch_id"]]["name"])
        return out
    async def forget_hashes(self, hashes):
        self.rows = [r for r in self.rows if r["row_hash"] not in set(hashes)]
    async def forget_rows(self, batch_id, prospect_ids):
        self.rows = [r for r in self.rows if r.get("prospect_id") not in set(prospect_ids)]
    async def record_undo(self, batch_id, *, deleted, touched, errors, done, actor):
        b = self.batches[batch_id]
        result = dict(b.get("undo_result") or {"deleted": [], "touched": [], "errors": []})
        known = {t["id"] for t in result["touched"]}
        result["deleted"] = result["deleted"] + list(deleted)
        result["touched"] = result["touched"] + [t for t in touched if t["id"] not in known]
        result["errors"] = list(errors); b["undo_result"] = result
        if done: b.update(undone_at=_now(), undone_by=actor)
        return result
    async def list_memberships(self, keys): return {k for k in keys if k in self.members}


class Crm(FakeCrm):
    """The campaign fake with the ladder's fields, an ``in`` on ids, touches by
    prospect, delete, and the conversation link when asked."""

    def __init__(self, *, ladder=True, conversations=False):
        super().__init__()
        self.ladder = ladder
        self.conversations = conversations
        self.deleted: list[str] = []
        self.conversed: set[str] = set()

    async def metadata(self, key):
        if key == f"entityDefs.{cfg.PROSPECT}.fields" and self.ladder:
            from campaigns import ladder
            return {**(await super().metadata(key)), **{f: {} for f in ladder.FIELDS}}
        if key == f"entityDefs.{cfg.PROSPECT}.links":
            from campaigns import ladder
            out = {l: {} for l in ladder.LINKS} if self.ladder else {}
            if self.conversations:
                out["conversations"] = {"type": "hasMany"}
            return out
        return await super().metadata(key)

    async def list(self, entity, *, where=None, **kw):
        if entity == "CConversation":
            ids = set((where or [{}])[0].get("value") or [])
            hit = [{"id": "conv1"}] if ids & self.conversed else []
            return {"total": len(hit), "list": hit}
        return await super().list(entity, where=where, **kw)

    async def list_related(self, entity, record_id, link, **kw):
        if link == "conversations":
            return {"list": [{"id": "conv1"}] if record_id in self.conversed else []}
        return await super().list_related(entity, record_id, link, **kw)

    async def delete(self, entity, record_id):
        if record_id not in self.rows.get(entity, {}):
            from core.espo import EspoError
            raise EspoError(f"delete {entity}/{record_id} failed: HTTP 404")
        del self.rows[entity][record_id]; self.deleted.append(record_id)


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def xlsx(sheets: dict[str, list[list[Any]]]) -> bytes:
    wb = Workbook(); first = True
    for name, rows in sheets.items():
        ws = wb.active if first else wb.create_sheet(); ws.title = name; first = False
        for r in rows:
            ws.append(r)
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


MAPPING = [
    {"column": "company", "field": "business_name"},
    {"column": "address", "field": "mailing_street"},
    {"column": "town", "field": "mailing_city"},
    {"fixed": "OH", "field": "mailing_state"},
    {"column": "postcode", "field": "mailing_zip"},
    {"split_name": "owner"},
    {"column": "e_mail", "field": "email"},
    {"column": "ref", "field": "external_reference"},
    {"ignore": "internal_notes"},
]
HEADERS = ["company", "address", "town", "postcode", "owner", "e_mail", "ref", "internal_notes", "phone"]


def _template(store, **over) -> dict:
    body = {"name": "Chamber list", "source": cfg.SOURCE_LIST, "listSource": "Chamber", "qualifiedBy": "the chamber",
            "entersAt": "Qualified", "referrerPartnerId": "partner1234567890", "referrerPartnerName": "Westside Chamber",
            "mapping": MAPPING, **over}
    return run(store.create_template(tpl.validate_template(body), actor="Mark Marketing"))


# --- the mapping and its fixes (ruling 82) --------------------------------------------------------

def test_each_fix_maps_a_row():
    mapping = tpl.validate_mapping(MAPPING + [{"join": ["Area Code", "Number"], "field": "phone", "with": "-"}])
    row = tpl.apply_mapping(mapping, {"company": " Acme Widgets ", "address": "1 Main St", "town": "Cleveland",
                                      "postcode": "44113", "owner": "Mary Ann Lee", "e_mail": "M@Acme.com",
                                      "ref": "OH-1", "internal_notes": "call Tuesday", "area_code": "216", "number": "5550100",
                                      "extra": "rides along"})
    assert row["business_name"] == "Acme Widgets" and row["mailing_state"] == "OH"       # column + fixed
    assert row["contact_first_name"] == "Mary Ann" and row["contact_last_name"] == "Lee"  # split_name
    assert row["phone"] == "216-5550100"                                                  # join
    assert "internal_notes" not in row and row["extra"] == "rides along"                  # ignore; unmapped rides along
    assert imports.normalise(row)["email"] == "m@acme.com"


def test_a_bad_mapping_is_refused_in_words():
    with pytest.raises(CampaignError, match="unknown"):
        tpl.validate_mapping([{"column": "x", "field": "nonsense"}])
    with pytest.raises(CampaignError, match="mapped twice"):
        tpl.validate_mapping([{"column": "a", "field": "email"}, {"fixed": "x", "field": "email"}])
    with pytest.raises(CampaignError, match="at least two"):
        tpl.validate_mapping([{"join": ["a"], "field": "phone"}])


def test_a_required_field_unmapped_stops_the_import_with_the_field_named():
    partial = [e for e in MAPPING if e.get("field") != "mailing_zip"]
    assert tpl.missing_required(tpl.validate_mapping(partial)) == ["ZIP"]
    with pytest.raises(CampaignError, match="ZIP"):
        imports.mapped_rows({"columns": HEADERS, "rows": [{"company": "A"}]}, tpl.validate_mapping(partial))
    with pytest.raises(CampaignError, match="Business name"):
        tpl.validate_template({"name": "x", "source": cfg.SOURCE_LIST, "mapping": MAPPING[1:5]})


def test_a_qualified_template_names_who_qualifies():
    with pytest.raises(CampaignError, match="Qualified by"):
        tpl.validate_template({"name": "x", "source": cfg.SOURCE_LIST, "entersAt": "Qualified", "mapping": MAPPING})
    t = tpl.validate_template({"name": "x", "source": cfg.SOURCE_LIST, "entersAt": "Unqualified", "mapping": MAPPING})
    assert t["header_signature"] == tpl.source_columns(t["mapping"])


# --- recognition (ruling 81) ------------------------------------------------------------------------

def test_recognition_suggests_the_closest_template_and_names_every_difference():
    store = TemplateStore()
    chamber = _template(store)
    _template(store, name="State filing", source=cfg.SOURCE_FILING, entersAt="Unqualified",
              mapping=[{"column": "business_name", "field": "business_name"}, {"column": "mailing_street", "field": "mailing_street"},
                       {"column": "mailing_city", "field": "mailing_city"}, {"column": "mailing_state", "field": "mailing_state"},
                       {"column": "mailing_zip", "field": "mailing_zip"}])
    # The chamber's file, with one column renamed and one new.
    headers = ["company", "address", "town", "post_code", "owner", "e_mail", "ref", "website"]
    found = tpl.recognise(run(store.list_templates()), headers)
    assert found["suggested"]["id"] == chamber["id"] and found["suggested"]["score"] == 0.86
    assert found["suggested"]["renamed"] == [{"from": "post_code", "to": "postcode", "ratio": 0.94}]
    assert found["suggested"]["new"] == ["website"] and found["suggested"]["missing"] == []
    assert [c["name"] for c in found["candidates"]] == ["Chamber list", "State filing"]
    # Nothing close enough: no suggestion, every candidate still scored.
    none = tpl.recognise(run(store.list_templates()), ["a", "b", "c"])
    assert none["suggested"] is None and all(c["score"] == 0 for c in none["candidates"])
    # Accepting the rename rewrites the mapping; the signature follows.
    renamed = tpl.rename_mapping(chamber["mapping"], {"postcode": "post_code"})
    assert {"column": "post_code", "field": "mailing_zip"} in renamed


# --- reading files (ruling 80) ------------------------------------------------------------------------

def test_excel_reads_like_csv_and_whole_numbers_keep_no_decimal():
    data = xlsx({"Members": [["Company", "Address", "Town", "Postcode", "Owner", "E-mail", "Ref", "Internal notes", "Phone"],
                             ["Acme", "1 Main St", "Cleveland", 44113, "Ann Lee", "ann@acme.com", 7, "x", 2165550100],
                             [None, None, None, None, None, None, None, None, None]]})
    table = imports.read_file("members.xlsx", data)
    assert table["columns"] == HEADERS and table["sheet"] == "Members"
    assert table["rows"] == [{"company": "Acme", "address": "1 Main St", "town": "Cleveland", "postcode": "44113",
                              "owner": "Ann Lee", "e_mail": "ann@acme.com", "ref": "7", "internal_notes": "x", "phone": "2165550100"}]
    csv_table = imports.read_file("members.csv", "Company,Postcode\nAcme,44113\n")
    assert csv_table["columns"] == ["company", "postcode"] and csv_table["sheet"] is None
    # Bytes that are a workbook are read as one whatever the name says.
    assert imports.read_file("members.csv", data)["sheet"] == "Members"


def test_several_sheets_ask_which_and_xls_is_refused():
    data = xlsx({"Members": [["Company"], ["A"]], "Lapsed": [["Company"], ["B"]]})
    with pytest.raises(imports.SheetChoice) as exc:
        imports.read_file("members.xlsx", data)
    assert exc.value.sheets == ["Members", "Lapsed"]
    assert imports.read_file("members.xlsx", data, "Lapsed")["rows"] == [{"company": "B"}]
    with pytest.raises(CampaignError, match="no sheet named"):
        imports.read_file("members.xlsx", data, "Other")
    with pytest.raises(CampaignError, match=r"save it as \.xlsx"):
        imports.read_file("members.xls", b"anything")
    with pytest.raises(CampaignError, match="5 MB"):
        imports.decode_file(base64.b64encode(b"x" * (imports.MAX_TEXT + 1)).decode())


# --- the plan: fills, the level, the status (rulings 83, 84, 111) --------------------------------------

def _table(rows):
    return {"columns": HEADERS, "rows": rows, "sheet": None}


def _chamber_rows():
    return [
        {"company": "Acme Widgets", "address": "1 Main St", "town": "Cleveland", "postcode": "44113", "owner": "Ann Lee",
         "e_mail": "ann@acme.example", "ref": "A1"},
        {"company": "Quiet Shop", "address": "2 Main St", "town": "Cleveland", "postcode": "44113", "owner": "", "e_mail": "", "ref": "Q2"},
        {"company": "Named Only", "address": "3 Main St", "town": "Cleveland", "postcode": "44113", "owner": "Bo Ray", "e_mail": "", "ref": "N3"},
    ]


def _queue(store, settings=None, rows=None, name="Chamber, October"):
    settings = settings or tpl.plan_settings(_template(store), door=cfg.SOURCE_LIST)
    return run(imports.queue_plan(store, name=name, settings=settings, table=_table(rows or _chamber_rows()),
                                  file_sha256="sha-" + name, file_name="members.xlsx", created_by="Mark"))


def test_the_plan_is_a_job_the_worker_runs_with_progress():
    store, crm = TemplateStore(), Crm()
    batch = _queue(store)
    assert batch["plan_status"] == PLAN_QUEUED and batch["plan"]["input"][0]["business_name"] == "Acme Widgets"
    assert run(store.get_template(batch["template_id"]))["last_batch_id"] == batch["id"]
    payload = imports.plan_payload(run(store.get_batch(batch["id"])))
    assert payload["planStatus"] == PLAN_QUEUED and "rows" not in payload
    settings = _settings(campaigns_enabled=True, import_templates=True, lead_ladder=True,
                         database_url="postgresql://x/y", espo_dry_run=False, espo_api_key="k")
    assert run(imports.run_plan_cycle(settings, store=store, client=crm)) == 1
    done = run(store.get_batch(batch["id"]))
    assert done["plan_status"] == PLAN_READY and "input" not in done["plan"] and done["plan"]["ladder"] is True
    assert store.progress[0]["checked"] == 0 and store.progress[0]["of"] == 3
    payload = imports.plan_payload(done)
    assert payload["counts"]["create"] == 3 and payload["counts"]["qualified"] == 1 and payload["counts"]["unqualified"] == 2
    by_name = {r["name"]: r for r in payload["rows"]}
    # Ruling 111 with ruling 42's floor: Qualified needs a website or an email.
    assert by_name["Acme Widgets"]["status"] == "Qualified" and by_name["Acme Widgets"]["level"] == R
    assert by_name["Quiet Shop"]["status"] == "Unqualified" and "no website or email" in by_name["Quiet Shop"]["note"]
    assert by_name["Named Only"]["status"] == "Unqualified"
    assert payload["counts"]["referred"] == 1
    # Nothing left: the next cycle takes nothing.
    assert run(imports.run_plan_cycle(settings, store=store, client=crm)) == 0


def test_a_failing_plan_is_marked_failed_with_the_reason():
    class Broken(TemplateStore):
        async def known_row_hashes(self, hashes): raise RuntimeError("database gone")
    store, crm = Broken(), Crm()
    batch = _queue(store)
    settings = _settings(campaigns_enabled=True, import_templates=True, database_url="postgresql://x/y",
                         espo_dry_run=False, espo_api_key="k")
    assert run(imports.run_plan_cycle(settings, store=store, client=crm)) == 1
    b = run(store.get_batch(batch["id"]))
    assert b["plan_status"] == PLAN_FAILED and "database gone" in b["plan_error"]
    assert imports.plan_payload(b)["planError"] == b["plan_error"]


def test_the_cycle_is_off_without_the_switches():
    store, crm = TemplateStore(), Crm()
    _queue(store)
    off = _settings(campaigns_enabled=True, import_templates=False, database_url="postgresql://x/y", espo_dry_run=False, espo_api_key="k")
    assert run(imports.run_plan_cycle(off, store=store, client=crm)) == 0


@pytest.mark.parametrize("row, level", [
    ({"contact_first_name": "Ann", "phone": "216"}, C),
    ({"contact_first_name": "Ann", "phone": "216", "referrer": True}, R),
    ({"email": "a@b.c"}, I),
    ({"contact_last_name": "Lee"}, I),
    ({"phone": "216", "referrer": True}, R),
])
def test_the_level_per_row_is_the_ladders_rule_with_the_templates_partner(row, level):
    settings = {"referrerPartnerId": "partner1234567890" if row.pop("referrer", False) else ""}
    assert imports.entry_level(row, settings) == level


def test_enters_at_replaces_the_fixed_rule_and_keeps_the_floor():
    q = {"door": cfg.SOURCE_LIST, "entersAt": "Qualified"}
    assert imports.entry_status_for(q, {"website": "x.com"}) == "Qualified"
    assert imports.entry_status_for(q, {"email": "a@b.c"}) == "Qualified"
    assert imports.entry_status_for(q, {"phone": "216"}) == "Unqualified"
    u = {"door": cfg.SOURCE_FILING, "entersAt": "Unqualified"}
    assert imports.entry_status_for(u, {"website": "x.com"}) == "Unqualified"
    # No template: ruling 53 as before.
    assert imports.entry_status_for({"door": cfg.SOURCE_FILING}, {"website": "x.com"}) == "Qualified"
    assert imports.entry_status_for({"door": cfg.SOURCE_LIST}, {"website": "x.com"}) == "Unqualified"


def _plan_and_apply(store, crm, rows=None, name="Chamber, October", settings=None, max_rows=None):
    batch = _queue(store, settings=settings, rows=rows, name=name)
    run(imports.plan_batch_now(crm, store, batch["id"], ladder=True))
    batch = run(store.get_batch(batch["id"]))
    while True:
        result = run(imports.apply_import(crm, crm, store, batch, user_name="Mark", max_rows=max_rows))
        if not result["remaining"]:
            break
    return run(store.get_batch(batch["id"])), result


def test_apply_writes_the_level_and_the_referrer_and_a_repeat_fills_only_empty_fields():
    store, crm = TemplateStore(), Crm()
    batch, result = _plan_and_apply(store, crm)
    assert result["created"] == 3 and result["qualified"] == 1 and result["filled"] == 0
    leads = {p["businessName"]: p for p in crm.rows[cfg.PROSPECT].values()}
    acme = leads["Acme Widgets"]
    assert acme["qualificationLevel"] == R and acme["referredByPartnerId"] == "partner1234567890"
    assert acme["firstName"] == "Ann" and acme["lastName"] == "Lee" and acme["qualifiedBy"] == "the chamber"
    assert acme["importBatch"] == "Chamber — Chamber, October"
    assert "qualificationLevel" not in leads["Quiet Shop"] and leads["Quiet Shop"]["referredByPartnerId"]
    # Next month's file: the same reference, with a phone and an owner for the quiet shop,
    # and a DIFFERENT email for Acme — which is never overwritten.
    rows = _chamber_rows()
    rows[1].update(owner="Pat Quiet", e_mail="pat@quiet.example")
    rows[0].update(e_mail="other@acme.example")
    rows[0]["phone"] = "2165550100"
    crm.updated.clear()
    batch2, result2 = _plan_and_apply(store, crm, rows=rows, name="Chamber, November")
    counts = batch2["plan"]["counts"]
    assert counts["fills"] == 2 and counts["knownRow"] == 1 and counts["create"] == 0
    by_name = {r["name"]: r for r in batch2["plan"]["rows"]}
    assert by_name["Acme Widgets"]["fill"] == {"phone": "2165550100"}          # not the email
    assert by_name["Quiet Shop"]["fill"] == {"firstName": "Pat", "lastName": "Quiet", "email": "pat@quiet.example"}
    assert by_name["Named Only"]["outcome"] == "known_row" and "nothing to fill" in by_name["Named Only"]["note"]
    assert result2["filled"] == 2 and result2["created"] == 0
    acme = crm.rows[cfg.PROSPECT][acme["id"]]
    assert acme["email"] == "ann@acme.example" and acme["phone"] == "2165550100"
    quiet = leads["Quiet Shop"]
    assert crm.rows[cfg.PROSPECT][quiet["id"]]["firstName"] == "Pat"
    fills = [u for u in crm.updated if u[0] == cfg.PROSPECT and u[1] == quiet["id"]]
    assert fills[0][2] == {"firstName": "Pat", "lastName": "Quiet", "email": "pat@quiet.example"}
    # The ledger knows the fill, and the fill's hash maps to the ORIGINAL lead.
    assert run(store.leads_for_hashes([by_name["Quiet Shop"]["hash"]])) == {by_name["Quiet Shop"]["hash"]: quiet["id"]}
    # A third run has nothing to fill: known rows, nothing to do.
    batch3 = _queue(store, rows=rows, name="Chamber, again")
    run(imports.plan_batch_now(crm, store, batch3["id"], ladder=True))
    payload = imports.plan_payload(run(store.get_batch(batch3["id"])))
    assert payload["nothingToDo"] is True and payload["counts"]["knownRow"] == 3


def test_fills_resume_in_parts_without_doubling():
    store, crm = TemplateStore(), Crm()
    _plan_and_apply(store, crm)
    rows = _chamber_rows()
    for r in rows:
        r["phone"] = "2165550100"
    crm.updated.clear()
    batch, result = _plan_and_apply(store, crm, rows=rows, name="Nov", max_rows=2)
    assert result["filled"] == 1 and batch["status"] == "applied"
    assert len([u for u in crm.updated if u[0] == cfg.PROSPECT and "phone" in u[2]]) == 3


def test_excluded_rows_are_skipped_and_counted():
    store, crm = TemplateStore(), Crm()
    batch = _queue(store)
    run(imports.plan_batch_now(crm, store, batch["id"], ladder=False))
    batch = run(store.get_batch(batch["id"]))
    quiet = next(r for r in batch["plan"]["rows"] if r["name"] == "Quiet Shop")
    run(store.set_excluded_rows(batch["id"], [quiet["hash"], "not-a-row"]))
    batch = run(store.get_batch(batch["id"]))
    result = run(imports.apply_import(crm, crm, store, batch, user_name="Mark"))
    assert result["created"] == 2 and result["excluded"] == 1
    assert "Quiet Shop" not in {p["businessName"] for p in crm.rows[cfg.PROSPECT].values()}


def test_apply_refuses_a_plan_still_running():
    store, crm = TemplateStore(), Crm()
    batch = _queue(store)
    with pytest.raises(CampaignError, match="not finished its preview"):
        run(imports.apply_import(crm, crm, store, batch, user_name="Mark"))


def test_a_company_or_contact_match_keeps_the_duplicate_lead():
    """Ruling 85: a matched record is left alone; the lead is created and closed Duplicate."""
    store, crm = TemplateStore(), Crm()
    crm.add(cfg.ACCOUNT, {"name": "Acme Widgets", "billingAddressPostalCode": "44113"})
    batch, result = _plan_and_apply(store, crm)
    acme = next(p for p in crm.rows[cfg.PROSPECT].values() if p["businessName"] == "Acme Widgets")
    assert acme["sideExit"] == "Duplicate" and acme["alreadyKnownCompanyId"]
    assert result["duplicates"] == 1 and [e for e, _ in crm.created if e == cfg.ACCOUNT] == []


# --- Undo (rulings 87, 127) ---------------------------------------------------------------------------

def _hour_ago():
    return _now() - timedelta(hours=1)


def test_touched_reasons_name_every_reason_and_spare_the_imports_own_writes():
    written = _hour_ago()
    stamp = lambda dt: dt.strftime("%Y-%m-%d %H:%M:%S")  # noqa: E731
    clean = {"leadStatus": "Qualified", "leadStatusChangedAt": stamp(written + timedelta(seconds=2)),
             "modifiedAt": stamp(written + timedelta(seconds=3))}
    assert imports.touched_reasons(clean, written, has_touch=False, in_list=False, has_conversation=False) == []
    dup = {**clean, "sideExit": "Duplicate", "sideExitAt": stamp(written + timedelta(seconds=2))}
    assert imports.touched_reasons(dup, written, has_touch=False, in_list=False, has_conversation=False) == []
    later = stamp(written + timedelta(hours=1))
    reasons = imports.touched_reasons({**clean, "leadStatusChangedAt": later, "leadStatus": "Disqualified",
                                       "levelSetAt": later, "sideExit": "Do Not Contact", "sideExitAt": later},
                                      written, has_touch=True, in_list=True, has_conversation=True)
    assert reasons == ["has a touch", "is on a campaign list", "has a conversation", "status changed since (Disqualified)",
                       "level set by hand", "stopped (Do Not Contact)"]
    assert imports.touched_reasons({**clean, "modifiedAt": later}, written, has_touch=False, in_list=False,
                                   has_conversation=False) == ["edited since the import"]


def test_undo_deletes_untouched_leads_lists_touched_ones_and_stamps_the_batch():
    store, crm = TemplateStore(), Crm(conversations=True)
    batch, _ = _plan_and_apply(store, crm)
    leads = {p["businessName"]: p for p in crm.rows[cfg.PROSPECT].values()}
    # Quiet Shop got a touch; Named Only sits on a list; Acme stays clean. The rows
    # were written moments ago, so the create's own stamps fall inside the window.
    crm.add(cfg.TOUCH, {"prospectId": leads["Quiet Shop"]["id"], "touchStatus": "Sent"})
    store.members.add(f"lead:{leads['Named Only']['id']}")
    result = run(imports.undo_import(crm, store, batch, actor="Mark Marketing"))
    assert result["done"] is True and result["remaining"] == 0
    assert result["deleted"] == [leads["Acme Widgets"]["id"]] and crm.deleted == [leads["Acme Widgets"]["id"]]
    assert sorted(t["why"] for t in result["touched"]) == ["has a touch", "is on a campaign list"]
    b = run(store.get_batch(batch["id"]))
    assert b["undone_at"] and b["undone_by"] == "Mark Marketing"
    assert b["undo_result"]["deleted"] == [leads["Acme Widgets"]["id"]] and len(b["undo_result"]["touched"]) == 2
    # The deleted row is forgotten, so the same row imports again; the touched rows stay known.
    hashes = {r["business_name"]: r["row_hash"] for r in store.rows}
    assert "Acme Widgets" not in hashes and "Quiet Shop" in hashes
    with pytest.raises(CampaignError, match="already been undone"):
        run(imports.undo_import(crm, store, b, actor="Mark"))


def test_undo_counts_a_conversation_as_a_touch_and_runs_in_parts():
    store, crm = TemplateStore(), Crm(conversations=True)
    batch, _ = _plan_and_apply(store, crm)
    leads = {p["businessName"]: p for p in crm.rows[cfg.PROSPECT].values()}
    crm.conversed.add(leads["Acme Widgets"]["id"])
    first = run(imports.undo_import(crm, store, batch, actor="Mark", max_leads=2))
    assert first["remaining"] == 1 and first["done"] is False
    assert run(store.get_batch(batch["id"]))["undone_at"] is None
    second = run(imports.undo_import(crm, store, run(store.get_batch(batch["id"])), actor="Mark", max_leads=2))
    assert second["done"] is True
    total = second["total"]
    assert [t["why"] for t in total["touched"]] == ["has a conversation"]
    assert sorted(total["deleted"]) == sorted([leads["Quiet Shop"]["id"], leads["Named Only"]["id"]])


def test_undo_refuses_an_unapplied_batch_and_a_delete_the_role_lacks_is_an_error_not_a_crash():
    store, crm = TemplateStore(), Crm()
    batch = _queue(store)
    with pytest.raises(CampaignError, match="Only an applied import"):
        run(imports.undo_import(crm, store, batch, actor="Mark"))

    class NoDelete(Crm):
        async def delete(self, entity, record_id):
            from core.espo import EspoError
            raise EspoError(f"delete {entity}/{record_id} failed: HTTP 403 No delete access")
    store, crm = TemplateStore(), NoDelete()
    batch, _ = _plan_and_apply(store, crm)
    result = run(imports.undo_import(crm, store, batch, actor="Mark"))
    assert result["done"] is False and len(result["errors"]) == 3 and "403" in result["errors"][0]["error"]
    assert run(store.get_batch(batch["id"]))["undone_at"] is None and len(store.rows) == 3


# --- the endpoints ------------------------------------------------------------------------------------

def _client(monkeypatch, store, crm, *, on="true"):
    monkeypatch.setenv("IMPORT_TEMPLATES", on)
    client = build(monkeypatch, user=MARKETING, crm=crm, store=store)
    client.app.state.import_plan_client = crm
    import campaigns.router as router_mod
    monkeypatch.setattr(router_mod, "_api_client", lambda settings, request: crm)
    return client


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def test_the_switch_off_leaves_every_new_endpoint_dark_and_the_csv_import_as_it_was(monkeypatch):
    store, crm = TemplateStore(), Crm()
    client = _client(monkeypatch, store, crm, on="false")
    assert client.get("/campaigns/api/import-templates").status_code == 404
    assert client.post("/campaigns/api/prospects/import/recognise", json={"text": "a,b\n1,2\n"}).status_code == 404
    assert client.get("/campaigns/api/session").json()["importTemplatesOn"] is False
    csv_text = "business_name,mailing_street,mailing_city,mailing_state,mailing_zip,website\nAcme,1 Main St,Cleveland,OH,44113,acme.com\n"
    res = client.post("/campaigns/api/prospects/import/plan", json={"name": "Filings", "source": cfg.SOURCE_FILING, "text": csv_text})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["counts"]["create"] == 1 and "planStatus" not in body and body["rows"][0]["status"] == "Qualified"
    assert "row" not in body["rows"][0]


def test_templates_are_shared_created_changed_and_deleted_through_the_endpoints(monkeypatch):
    store, crm = TemplateStore(), Crm()
    client = _client(monkeypatch, store, crm)
    assert client.get("/campaigns/api/session").json()["importTemplatesOn"] is True
    body = {"name": "Chamber list", "source": cfg.SOURCE_LIST, "listSource": "Chamber", "qualifiedBy": "the chamber",
            "entersAt": "Qualified", "referrerPartnerId": "partner1234567890", "referrerPartnerName": "Westside", "mapping": MAPPING}
    res = client.post("/campaigns/api/import-templates", json=body)
    assert res.status_code == 200, res.text
    t = res.json()["template"]
    assert t["source"] == cfg.SOURCE_LIST and t["headerSignature"] == tpl.source_columns(tpl.validate_mapping(MAPPING))
    listed = client.get("/campaigns/api/import-templates").json()
    assert [x["name"] for x in listed["templates"]] == ["Chamber list"] and listed["entersAt"] == ["Unqualified", "Qualified"]
    assert {f["name"] for f in listed["fields"]} == set(tpl.FIELD_LABELS)
    bad = client.post("/campaigns/api/import-templates", json={**body, "mapping": MAPPING[1:]})
    assert bad.status_code == 400 and "Business name" in bad.json()["detail"]
    res = client.put(f"/campaigns/api/import-templates/{t['id']}", json={**body, "name": "Chamber members"})
    assert res.status_code == 200 and res.json()["template"]["name"] == "Chamber members"
    assert client.put("/campaigns/api/import-templates/nope", json=body).status_code == 404
    assert client.delete(f"/campaigns/api/import-templates/{t['id']}").json() == {"deleted": t["id"]}
    assert client.get("/campaigns/api/import-templates").json()["templates"] == []


def test_recognise_then_plan_then_poll_then_exclude_then_apply_then_undo(monkeypatch):
    store, crm = TemplateStore(), Crm()
    client = _client(monkeypatch, store, crm)
    t = _template(store)
    data = xlsx({"Members": [["Company", "Address", "Town", "Postcode", "Owner", "E-mail", "Ref", "Internal notes"],
                             ["Acme Widgets", "1 Main St", "Cleveland", 44113, "Ann Lee", "ann@acme.example", "A1", "x"],
                             ["Quiet Shop", "2 Main St", "Cleveland", 44113, None, None, "Q2", None]]})
    rec = client.post("/campaigns/api/prospects/import/recognise", json={"fileBase64": _b64(data), "fileName": "members.xlsx"})
    assert rec.status_code == 200, rec.text
    body = rec.json()
    assert body["suggested"]["id"] == t["id"] and body["rowCount"] == 2 and body["sample"][0]["company"] == "Acme Widgets"
    assert body["columns"][0] == "company" and body["identityMapping"] == []
    # Two sheets: 409 with the names, then the sheet is posted.
    two = xlsx({"A": [["Company"], ["x"]], "B": [["Company"], ["y"]]})
    res = client.post("/campaigns/api/prospects/import/recognise", json={"fileBase64": _b64(two), "fileName": "two.xlsx"})
    assert res.status_code == 409 and res.json()["detail"]["sheets"] == ["A", "B"]
    assert client.post("/campaigns/api/prospects/import/recognise",
                       json={"fileBase64": _b64(two), "fileName": "two.xlsx", "sheet": "B"}).json()["sample"] == [{"company": "y"}]
    res = client.post("/campaigns/api/prospects/import/recognise", json={"fileBase64": _b64(b"x"), "fileName": "old.xls"})
    assert res.status_code == 400 and "save it as .xlsx" in res.json()["detail"]
    # Plan with the template: dry run plans inline, so the poll is ready at once.
    res = client.post("/campaigns/api/prospects/import/plan",
                      json={"name": "Chamber, October", "templateId": t["id"], "fileBase64": _b64(data), "fileName": "members.xlsx"})
    assert res.status_code == 200, res.text
    plan = res.json()
    assert plan["planStatus"] == PLAN_READY and plan["counts"]["create"] == 2 and plan["templateName"] == "Chamber list"
    poll = client.get(f"/campaigns/api/prospects/import/{plan['batchId']}").json()
    assert poll["planStatus"] == PLAN_READY and poll["rows"][0]["row"]["business_name"] == "Acme Widgets"
    assert client.get("/campaigns/api/prospects/import/nope").status_code == 404
    quiet = next(r for r in poll["rows"] if r["name"] == "Quiet Shop")
    ex = client.put(f"/campaigns/api/prospects/import/{plan['batchId']}/excluded", json={"hashes": [quiet["hash"]]})
    assert ex.json()["excludedRows"] == [quiet["hash"]]
    # Apply in parts, as the page does.
    res = client.post("/campaigns/api/prospects/import/apply", json={"batchId": plan["batchId"], "maxRows": 100})
    assert res.status_code == 200, res.text
    r = res.json()["result"]
    assert r["created"] == 1 and r["excluded"] == 1 and r["remaining"] == 0
    assert [p["businessName"] for p in crm.rows[cfg.PROSPECT].values()] == ["Acme Widgets"]
    imports_list = client.get("/campaigns/api/prospects/imports").json()["batches"]
    assert imports_list[0]["status"] == "applied"
    # Undo: the one lead is untouched.
    res = client.post(f"/campaigns/api/prospects/import/{plan['batchId']}/undo", json={"maxLeads": 100})
    assert res.status_code == 200, res.text
    u = res.json()["result"]
    assert u["done"] is True and len(u["deleted"]) == 1 and crm.rows[cfg.PROSPECT] == {}
    assert client.get(f"/campaigns/api/prospects/import/{plan['batchId']}").json()["undoneBy"] == "Mark Marketing"
    again = client.post(f"/campaigns/api/prospects/import/{plan['batchId']}/undo", json={})
    assert again.status_code == 400 and "already been undone" in again.json()["detail"]


def test_a_one_off_mapping_plans_without_a_template_and_a_required_gap_is_a_400(monkeypatch):
    store, crm = TemplateStore(), Crm()
    client = _client(monkeypatch, store, crm)
    text = "Company,Address,Town,Postcode\nAcme,1 Main St,Cleveland,44113\n"
    res = client.post("/campaigns/api/prospects/import/plan", json={
        "name": "One-off", "source": cfg.SOURCE_PARTNER_FILE, "text": text, "fileName": "list.csv", "entersAt": "Unqualified",
        "mapping": [{"column": "company", "field": "business_name"}, {"column": "address", "field": "mailing_street"},
                    {"column": "town", "field": "mailing_city"}, {"fixed": "OH", "field": "mailing_state"},
                    {"column": "postcode", "field": "mailing_zip"}]})
    assert res.status_code == 200, res.text
    assert res.json()["counts"]["create"] == 1 and res.json()["rows"][0]["status"] == "Unqualified"
    res = client.post("/campaigns/api/prospects/import/plan", json={
        "name": "One-off", "source": cfg.SOURCE_LIST, "text": text, "fileName": "list.csv",
        "mapping": [{"column": "company", "field": "business_name"}]})
    assert res.status_code == 400 and "Street" in res.json()["detail"]


# --- the reset, the roles, the worker ----------------------------------------------------------------

def test_the_template_table_resets_nightly_and_the_api_role_gains_delete():
    from core.sandbox_reset import RESET_TABLES
    assert "import_template" in RESET_TABLES
    import importlib.util, pathlib
    path = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "migrate_outreach_roles.py"
    spec = importlib.util.spec_from_file_location("migrate_outreach_roles", path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)  # type: ignore[union-attr]
    api_lead = next(g for r, s, g in mod.ROLE_SCOPE_GRANTS if r == "CustomAppAPIRole" and s == "CProspect")
    assert api_lead["delete"] == "all"
    marketing_lead = next(g for r, s, g in mod.ROLE_SCOPE_GRANTS if r == "Marketing Admin Role" and s == "CProspect")
    assert "delete" not in marketing_lead


def test_the_settings_exist_with_the_ruled_defaults():
    s = _settings()
    assert s.import_templates is False and s.import_plan_poll_seconds == 5


# --- found on the live pass, 10-25-26 ---------------------------------------------------------------

def test_a_lead_a_later_import_filled_is_touched_whatever_the_clock_says():
    """The rehearsal's fills landed four minutes after the create — inside the
    write window — and Undo deleted the filled leads. The ledger knows better."""
    store, crm = TemplateStore(), Crm()
    first, _ = _plan_and_apply(store, crm)
    rows = _chamber_rows()
    rows[1].update(owner="Pat Quiet", e_mail="pat@quiet.example")
    _plan_and_apply(store, crm, rows=rows, name="Chamber, November")
    result = run(imports.undo_import(crm, store, run(store.get_batch(first["id"])), actor="Mark"))
    leads = {p["businessName"]: p for p in crm.rows[cfg.PROSPECT].values()}
    assert [t["name"] for t in result["touched"]] == ["Quiet Shop"]
    assert result["touched"][0]["why"] == "filled by a later import (Chamber, November)"
    assert "Quiet Shop" in leads and len(result["deleted"]) == 2
    assert crm.rows[cfg.PROSPECT][leads["Quiet Shop"]["id"]]["firstName"] == "Pat"


def test_the_undo_history_row_hangs_on_a_lead_that_still_exists(monkeypatch):
    """The CRM refuses a history row linked to a deleted record; a touched lead
    carries it, and with none left the row is skipped and the log names the ids."""
    store, crm = TemplateStore(), Crm()
    client = _client(monkeypatch, store, crm)
    import campaigns.router as router_mod
    logged: list[dict] = []

    async def capture(user_client, **kw):
        logged.append(kw)
    monkeypatch.setattr(router_mod, "record_action", capture)
    t = _template(store)
    data = xlsx({"Members": [["Company", "Address", "Town", "Postcode", "Owner", "E-mail", "Ref", "Internal notes"],
                             ["Acme Widgets", "1 Main St", "Cleveland", 44113, "Ann Lee", "ann@acme.example", "A1", "x"],
                             ["Quiet Shop", "2 Main St", "Cleveland", 44113, None, None, "Q2", None]]})
    plan = client.post("/campaigns/api/prospects/import/plan",
                       json={"name": "October", "templateId": t["id"], "fileBase64": _b64(data), "fileName": "m.xlsx"}).json()
    client.post("/campaigns/api/prospects/import/apply", json={"batchId": plan["batchId"], "maxRows": 100})
    leads = {p["businessName"]: p for p in crm.rows[cfg.PROSPECT].values()}
    crm.add(cfg.TOUCH, {"prospectId": leads["Quiet Shop"]["id"], "touchStatus": "Sent"})
    res = client.post(f"/campaigns/api/prospects/import/{plan['batchId']}/undo", json={"maxLeads": 100}).json()["result"]
    assert res["deleted"] == [leads["Acme Widgets"]["id"]]
    undone = [l for l in logged if l["action"] == "Import Undone"]
    assert len(undone) == 1 and undone[0]["parent_id"] == leads["Quiet Shop"]["id"]
    assert "1 leads deleted, 1 touched and left" in undone[0]["summary"]
    # Every lead deleted: no record is left to carry the row, so none is written.
    logged.clear()
    plan2 = client.post("/campaigns/api/prospects/import/plan",
                        json={"name": "November", "templateId": t["id"], "fileBase64": _b64(xlsx({"S": [
                            ["Company", "Address", "Town", "Postcode", "Owner", "E-mail", "Ref", "Internal notes"],
                            ["Third Place", "3 Main St", "Cleveland", 44113, None, None, "T3", None]]})), "fileName": "n.xlsx"}).json()
    client.post("/campaigns/api/prospects/import/apply", json={"batchId": plan2["batchId"], "maxRows": 100})
    res2 = client.post(f"/campaigns/api/prospects/import/{plan2['batchId']}/undo", json={"maxLeads": 100}).json()["result"]
    assert len(res2["deleted"]) == 1 and [l for l in logged if l["action"] == "Import Undone"] == []


def test_the_parts_summary_counts_exclude_the_excluded_rows(monkeypatch):
    store, crm = TemplateStore(), Crm()
    client = _client(monkeypatch, store, crm)
    import campaigns.router as router_mod
    logged: list[dict] = []

    async def capture(user_client, **kw):
        logged.append(kw)
    monkeypatch.setattr(router_mod, "record_action", capture)
    t = _template(store)
    data = xlsx({"Members": [["Company", "Address", "Town", "Postcode", "Owner", "E-mail", "Ref", "Internal notes"],
                             ["Acme Widgets", "1 Main St", "Cleveland", 44113, "Ann Lee", "ann@acme.example", "A1", "x"],
                             ["Quiet Shop", "2 Main St", "Cleveland", 44113, None, None, "Q2", None]]})
    plan = client.post("/campaigns/api/prospects/import/plan",
                       json={"name": "October", "templateId": t["id"], "fileBase64": _b64(data), "fileName": "m.xlsx"}).json()
    quiet = next(r for r in plan["rows"] if r["name"] == "Quiet Shop")
    client.put(f"/campaigns/api/prospects/import/{plan['batchId']}/excluded", json={"hashes": [quiet["hash"]]})
    client.post("/campaigns/api/prospects/import/apply", json={"batchId": plan["batchId"], "maxRows": 100})
    row = [l for l in logged if l["action"] == "Leads Imported"][0]
    assert row["details"]["created"] == 1 and row["details"]["unqualified"] == 0 and row["details"]["excluded"] == 1
    assert "1 leads (1 Qualified, 0 Unqualified)" in row["summary"] and "1 rows excluded" in row["summary"]


def test_a_ledger_row_whose_lead_is_gone_plans_as_a_create_again():
    """Round two of the live pass: a lead deleted while another batch's fills
    row still named it read as "known, nothing to fill". The row is new."""
    store, crm = TemplateStore(), Crm()
    first, _ = _plan_and_apply(store, crm)
    leads = {p["businessName"]: p for p in crm.rows[cfg.PROSPECT].values()}
    # A stale ledger row: the lead is deleted by hand, the row stays.
    del crm.rows[cfg.PROSPECT][leads["Quiet Shop"]["id"]]
    batch = _queue(store, name="Again")
    run(imports.plan_batch_now(crm, store, batch["id"], ladder=True))
    by_name = {r["name"]: r for r in run(store.get_batch(batch["id"]))["plan"]["rows"]}
    assert by_name["Quiet Shop"]["outcome"] == "create" and by_name["Acme Widgets"]["outcome"] == "known_row"
    assert by_name["Quiet Shop"]["stale"] is True
    # And the apply CREATES it (the across-batch check must not skip a stale hash — v0.286.3).
    result = run(imports.apply_import(crm, crm, store, run(store.get_batch(batch["id"])), user_name="Mark"))
    assert result["created"] == 1 and result["skipped"] == 2
    assert "Quiet Shop" in {p["businessName"] for p in crm.rows[cfg.PROSPECT].values()}
    assert len([r for r in store.rows if r["business_name"] == "Quiet Shop"]) == 1
    # And Undo forgets every row naming a deleted lead, other batches' fills included.
    rows = _chamber_rows(); rows[2].update(owner="Bo Ray", e_mail="bo@named.example")
    _plan_and_apply(store, crm, rows=rows, name="Fill Named Only")
    named = leads["Named Only"]["id"]
    assert [r for r in store.rows if r["prospect_id"] == named and r["outcome"] == "fills"]
    run(store.forget_rows(first["id"], [named]))
    assert [r for r in store.rows if r["prospect_id"] == named] == []
