"""The Leads and Review grids at volume (build plan § 7b; Doug 10-20-26).

About 10,000 leads a year (§ 7b answer 1), so nothing here loads every lead:
the CRM searches, sorts and counts, and the grid asks for one page at a time.
The old list loaded everything and stopped silently at 2,000.

* :class:`LeadQuery` — the search box and the filters, parsed once from the
  request and turned into the CRM's ``where`` (§ 7b answer 3).
* :func:`search` — one page and the true total. The "in this campaign" filter
  is the one the CRM cannot express as a clause on the lead, so it reads that
  campaign's touches for their lead ids and asks for those leads 100 at a time.
* :func:`resolve` — every id a filter matches, for *select all n matching*;
  refused above :data:`BULK_CAP` (§ 7b.1, "narrow the filter").
* :func:`apply_bulk` — Disqualify or Do Not Contact over a batch, each lead
  re-read and skipped, never overwritten, when it changed since the reviewer
  saw it (§ 7b answer 5) or the review rules refuse it (ruling 50).
* :func:`export_rows` — the matching leads as CSV rows, page by page.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from core.espo import EspoApi, EspoError

from . import config as cfg
from . import review
from .service import CampaignError

PAGE = 50
MAX_PAGE = 200          # the CRM's own recordListMaxSizeLimit
BULK_CAP = 2000         # one bulk action covers at most this many leads
BULK_BATCH = 50         # the browser applies in batches of this size
EXPORT_CAP = 20000
CAMPAIGN_IDS_CAP = 5000
_CHUNK = 100

#: What the search box matches (§ 7b answer 3).
SEARCH_FIELDS = (
    "businessName", "name", "firstName", "lastName", "email", "phone", "website",
    "mailingAddressStreet", "mailingAddressCity", "mailingAddressPostalCode", "externalReference",
)
#: The columns a grid may sort on — a whitelist, so a request cannot ask the
#: CRM to order by an arbitrary attribute.
SORT_FIELDS = frozenset({
    "name", "businessName", "leadStatus", "sideExit", "leadSource", "mailingAddressCity",
    "mailingAddressPostalCode", "addressStatus", "importBatch", "createdAt",
})
IN_CAMPAIGN_YES = "yes"
IN_CAMPAIGN_NO = "no"

BULK_ACTIONS = (review.ACTION_DISQUALIFY, review.ACTION_DO_NOT_CONTACT)

#: Read for every guarded decision: the fields the guard compares and the
#: names it reports.
GUARD_SELECT = cfg.PROSPECT_SELECT + ",modifiedByName,modifiedAt"

EXPORT_COLUMNS = (
    ("Business", "businessName"), ("First name", "firstName"), ("Last name", "lastName"),
    ("Lead status", "leadStatus"), ("Stopped because", "sideExit"), ("Lead Source", "leadSource"),
    ("Street", "mailingAddressStreet"), ("City", "mailingAddressCity"), ("State", "mailingAddressState"),
    ("ZIP", "mailingAddressPostalCode"), ("Address", "addressStatus"), ("Website", "website"),
    ("Email", "email"), ("Phone", "phone"), ("Filing number", "externalReference"),
    ("Batch", "importBatch"), ("Arrived", "createdAt"), ("Lead id", "id"),
)

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CRM_ID = re.compile(r"^[A-Za-z0-9]{6,32}$")


@dataclass
class LeadQuery:
    q: str = ""
    status: str = ""
    exit: str = ""             # "" any, "none" still worked, or a reason
    source: str = ""
    batch: str = ""
    place: str = ""            # a ZIP (digits) or a city
    arrived_from: str = ""     # YYYY-MM-DD, inclusive
    arrived_to: str = ""       # YYYY-MM-DD, inclusive
    in_campaign: str = ""      # "", "yes", "no" or a campaign id
    sort: str = "createdAt"
    dir: str = "desc"
    offset: int = 0
    limit: int = PAGE
    errors: list[str] = field(default_factory=list)

    @classmethod
    def from_params(cls, params: dict[str, Any], *, review_queue: bool = False) -> "LeadQuery":
        g = lambda k: str(params.get(k) or "").strip()  # noqa: E731
        lq = cls(q=g("q")[:200], status=g("status"), exit=g("exit"), source=g("source"),
                 batch=g("batch")[:255], place=g("place")[:100], arrived_from=g("arrivedFrom"),
                 arrived_to=g("arrivedTo"), in_campaign=g("inCampaign"),
                 sort=g("sort") or ("createdAt"), dir=(g("dir") or ("asc" if review_queue else "desc")).lower())
        try:
            lq.offset = max(0, int(params.get("offset") or 0))
        except (TypeError, ValueError):
            lq.offset = 0
        try:
            lq.limit = min(MAX_PAGE, max(1, int(params.get("limit") or PAGE)))
        except (TypeError, ValueError):
            lq.limit = PAGE
        if review_queue:
            # The Review queue: Unqualified, no reason (§ 7b.1), oldest first.
            lq.status, lq.exit = cfg.LEAD_UNQUALIFIED, "none"
        if lq.sort not in SORT_FIELDS:
            lq.sort = "createdAt"
        if lq.dir not in ("asc", "desc"):
            lq.dir = "desc"
        for label, value in (("From", lq.arrived_from), ("To", lq.arrived_to)):
            if value and not _DATE.match(value):
                lq.errors.append(f"{label} date must be a date (YYYY-MM-DD).")
        if lq.in_campaign not in ("", IN_CAMPAIGN_YES, IN_CAMPAIGN_NO) and not _CRM_ID.match(lq.in_campaign):
            lq.errors.append("Unknown campaign.")
        return lq

    def params(self) -> dict[str, str]:
        """The query as request parameters (for a bulk resolve sent back)."""
        out = {"q": self.q, "status": self.status, "exit": self.exit, "source": self.source,
               "batch": self.batch, "place": self.place, "arrivedFrom": self.arrived_from,
               "arrivedTo": self.arrived_to, "inCampaign": self.in_campaign,
               "sort": self.sort, "dir": self.dir}
        return {k: v for k, v in out.items() if v}


def _search_clause(q: str) -> Optional[dict[str, Any]]:
    q = q.strip()
    if not q:
        return None
    ors = [{"type": "contains", "attribute": f, "value": q} for f in SEARCH_FIELDS]
    digits = re.sub(r"\D", "", q)
    # A phone typed as "216-555-0141" against a stored "+12165550141".
    if len(digits) >= 4 and digits != q:
        ors.append({"type": "contains", "attribute": "phone", "value": digits})
    return {"type": "or", "value": ors}


def build_where(lq: LeadQuery) -> list[dict[str, Any]]:
    where: list[dict[str, Any]] = []
    clause = _search_clause(lq.q)
    if clause:
        where.append(clause)
    if lq.status:
        where.append({"type": "equals", "attribute": "leadStatus", "value": lq.status})
    if lq.exit == "none":
        where.append({"type": "isNull", "attribute": "sideExit"})
    elif lq.exit:
        where.append({"type": "equals", "attribute": "sideExit", "value": lq.exit})
    if lq.source:
        where.append({"type": "equals", "attribute": "leadSource", "value": lq.source})
    if lq.batch:
        # Contains, not equals: a list batch is stored as "<list> — <name>".
        where.append({"type": "contains", "attribute": "importBatch", "value": lq.batch})
    if lq.place:
        if lq.place.isdigit():
            where.append({"type": "startsWith", "attribute": "mailingAddressPostalCode", "value": lq.place})
        else:
            where.append({"type": "contains", "attribute": "mailingAddressCity", "value": lq.place})
    if lq.arrived_from:
        where.append({"type": "greaterThanOrEquals", "attribute": "createdAt",
                      "value": f"{lq.arrived_from} 00:00:00"})
    if lq.arrived_to:
        where.append({"type": "lessThanOrEquals", "attribute": "createdAt",
                      "value": f"{lq.arrived_to} 23:59:59"})
    if lq.in_campaign == IN_CAMPAIGN_YES:
        where.append({"type": "isLinked", "attribute": "touches"})
    elif lq.in_campaign == IN_CAMPAIGN_NO:
        where.append({"type": "isNotLinked", "attribute": "touches"})
    return where


def _is_campaign(lq: LeadQuery) -> bool:
    return lq.in_campaign not in ("", IN_CAMPAIGN_YES, IN_CAMPAIGN_NO)


async def campaign_lead_ids(client: EspoApi, campaign_id: str) -> list[str]:
    """The leads a campaign has a touch for (any status but Cancelled)."""
    ids: list[str] = []
    seen: set[str] = set()
    offset = 0
    while True:
        page = await client.list(cfg.TOUCH, select="id,prospectId,touchStatus", max_size=MAX_PAGE, offset=offset,
                                 where=[{"type": "equals", "attribute": "outreachCampaignId", "value": campaign_id},
                                        {"type": "isNotNull", "attribute": "prospectId"}])
        batch = page.get("list", [])
        for t in batch:
            pid = t.get("prospectId")
            if pid and pid not in seen and t.get("touchStatus") != cfg.TOUCH_CANCELLED:
                seen.add(pid)
                ids.append(pid)
        if len(batch) < MAX_PAGE:
            break
        offset += MAX_PAGE
        if len(ids) > CAMPAIGN_IDS_CAP:
            raise CampaignError(f"That campaign reaches more than {CAMPAIGN_IDS_CAP:,} leads; "
                                "filter by import batch or ZIP instead.")
    return ids


async def _campaign_rows(client: EspoApi, lq: LeadQuery, *, select: str) -> list[dict[str, Any]]:
    """Every lead in the campaign that also meets the other filters, sorted."""
    ids = await campaign_lead_ids(client, lq.in_campaign)
    base = build_where(lq)
    rows: list[dict[str, Any]] = []
    for i in range(0, len(ids), _CHUNK):
        chunk = ids[i:i + _CHUNK]
        page = await client.list(cfg.PROSPECT, select=select, max_size=MAX_PAGE,
                                 where=base + [{"type": "in", "attribute": "id", "value": chunk}])
        rows.extend(page.get("list", []))
    # Sorted like the CRM would, with empty values last in either direction.
    filled = [r for r in rows if r.get(lq.sort) not in (None, "")]
    empty = [r for r in rows if r.get(lq.sort) in (None, "")]
    filled.sort(key=lambda r: str(r.get(lq.sort)).lower(), reverse=lq.dir == "desc")
    return filled + empty


async def search(client: EspoApi, lq: LeadQuery) -> dict[str, Any]:
    """One page of leads and the total the filter matches."""
    if lq.errors:
        raise CampaignError(" ".join(lq.errors))
    if _is_campaign(lq):
        rows = await _campaign_rows(client, lq, select=cfg.PROSPECT_SELECT)
        return {"prospects": rows[lq.offset:lq.offset + lq.limit], "total": len(rows),
                "offset": lq.offset, "limit": lq.limit}
    page = await client.list(cfg.PROSPECT, select=cfg.PROSPECT_SELECT, where=build_where(lq) or None,
                             max_size=lq.limit, offset=lq.offset, order_by=lq.sort, order=lq.dir)
    rows = page.get("list", [])
    total = page.get("total")
    if not isinstance(total, int) or total < 0:
        total = lq.offset + len(rows)
    return {"prospects": rows, "total": total, "offset": lq.offset, "limit": lq.limit}


async def _all(client: EspoApi, lq: LeadQuery, *, select: str, cap: int) -> list[dict[str, Any]]:
    if _is_campaign(lq):
        rows = await _campaign_rows(client, lq, select=select)
        if len(rows) > cap:
            raise CampaignError(f"{len(rows):,} leads match; narrow the filter to {cap:,} or fewer.")
        return rows
    where = build_where(lq) or None
    first = await client.list(cfg.PROSPECT, select=select, where=where, max_size=MAX_PAGE,
                              order_by=lq.sort, order=lq.dir)
    total = first.get("total") if isinstance(first.get("total"), int) else None
    if total is not None and total > cap:
        raise CampaignError(f"{total:,} leads match; narrow the filter to {cap:,} or fewer.")
    rows = list(first.get("list", []))
    offset = MAX_PAGE
    while len(first.get("list", [])) == MAX_PAGE and (total is None or len(rows) < total):
        page = await client.list(cfg.PROSPECT, select=select, where=where, max_size=MAX_PAGE,
                                 offset=offset, order_by=lq.sort, order=lq.dir)
        batch = page.get("list", [])
        rows.extend(batch)
        if len(batch) < MAX_PAGE or len(rows) > cap:
            break
        offset += MAX_PAGE
    if len(rows) > cap:
        raise CampaignError(f"More than {cap:,} leads match; narrow the filter.")
    return rows


async def resolve(client: EspoApi, lq: LeadQuery) -> list[dict[str, str]]:
    """Every lead the filter matches, as ``{id, leadStatus, sideExit}`` — what
    the bulk guard compares against."""
    if lq.errors:
        raise CampaignError(" ".join(lq.errors))
    rows = await _all(client, lq, select="id,leadStatus,sideExit", cap=BULK_CAP)
    return [{"id": r["id"], "leadStatus": r.get("leadStatus") or "", "sideExit": r.get("sideExit") or ""}
            for r in rows if r.get("id")]


def changed_since(lead: dict[str, Any], seen: dict[str, Any]) -> Optional[str]:
    """None when the lead is as the reviewer saw it, else the sentence that
    says what changed and who changed it (§ 7b answer 5)."""
    was_status = (seen.get("leadStatus") or "")
    was_exit = (seen.get("sideExit") or "")
    now_status = lead.get("leadStatus") or ""
    now_exit = lead.get("sideExit") or ""
    if "leadStatus" in seen and was_status and was_status != now_status:
        what = now_status
    elif "sideExit" in seen and was_exit != now_exit:
        what = f"stopped ({now_exit})" if now_exit else "worked again"
    else:
        return None
    who = lead.get("modifiedByName") or "someone else"
    when = (lead.get("modifiedAt") or "")[:16]
    return f"Already {what}, by {who}" + (f" at {when} UTC" if when else "") + "."


async def apply_bulk(user_client: EspoApi, api_client: Optional[EspoApi], items: list[dict[str, Any]],
                     action: str, *, reviewer: str, note: str) -> dict[str, Any]:
    """Apply one review action to up to :data:`BULK_BATCH` leads. Never stops
    on one lead: each is done, skipped (with why) or failed (with the CRM's
    words)."""
    if action not in BULK_ACTIONS:
        raise CampaignError("Only Disqualify and Do Not Contact run on many leads at once.")
    if len(items) > BULK_BATCH:
        raise CampaignError(f"At most {BULK_BATCH} leads per request.")
    if action == review.ACTION_DISQUALIFY and not (note or "").strip():
        raise CampaignError("Say why these leads will never be a client, partner or funder — the reason is required.")
    out: dict[str, Any] = {"done": [], "skipped": [], "failed": []}
    for item in items:
        lead_id = str(item.get("id") or "")
        if not _CRM_ID.match(lead_id):
            out["failed"].append({"id": lead_id, "name": "", "why": "Not a lead id."})
            continue
        try:
            lead = await user_client.get(cfg.PROSPECT, lead_id, select=GUARD_SELECT)
        except EspoError as exc:
            out["failed"].append({"id": lead_id, "name": "", "why": str(exc)})
            continue
        if not lead or not lead.get("id"):
            out["skipped"].append({"id": lead_id, "name": "", "why": "The lead no longer exists."})
            continue
        name = lead.get("businessName") or lead.get("name") or lead_id
        moved = changed_since(lead, item)
        if moved:
            out["skipped"].append({"id": lead_id, "name": name, "why": moved})
            continue
        try:
            await review.apply_action(user_client, api_client, lead, action, reviewer=reviewer, note=note)
        except CampaignError as exc:
            out["skipped"].append({"id": lead_id, "name": name, "why": str(exc)})
            continue
        except EspoError as exc:
            out["failed"].append({"id": lead_id, "name": name, "why": str(exc)})
            continue
        out["done"].append({"id": lead_id, "name": name,
                            "was": {"leadStatus": lead.get("leadStatus"), "sideExit": lead.get("sideExit")}})
    return out


def _csv_line(values: list[Any]) -> str:
    buf = io.StringIO()
    csv.writer(buf).writerow(["" if v is None else v for v in values])
    return buf.getvalue()


async def export_rows(client: EspoApi, lq: LeadQuery) -> AsyncIterator[str]:
    """The header, then one CSV line per matching lead. Capped at
    :data:`EXPORT_CAP`; a refusal is raised before the first line."""
    if lq.errors:
        raise CampaignError(" ".join(lq.errors))
    select = ",".join(sorted({f for _, f in EXPORT_COLUMNS}))
    rows = await _all(client, lq, select=select, cap=EXPORT_CAP)

    async def gen() -> AsyncIterator[str]:
        yield "﻿" + _csv_line([label for label, _ in EXPORT_COLUMNS])
        for r in rows:
            yield _csv_line([r.get(f) for _, f in EXPORT_COLUMNS])
    return gen()
