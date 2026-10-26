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

import asyncio
import csv
import io
import re
from dataclasses import dataclass, field, replace
from typing import Any, AsyncIterator, Optional

from core.espo import EspoApi, EspoError

from . import config as cfg
from . import ladder, review
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
    "fitScore",
    # The ladder's columns (build plan § 7e.4), sortable only when the CRM has them.
    "qualificationLevel", "assignedUserName", "lastName", "modifiedAt",
})
LADDER_SORT_FIELDS = frozenset({"qualificationLevel", "assignedUserName", "modifiedAt"})
#: The Leads tab's counts across the top (§ 7e.4), each a filter: the query
#: parameters a chip applies.
COUNT_KEYS = ("unqualified", "identified", "contactable", "referred", "replied", "disqualified", "mine")
ASSIGN_UNASSIGNED = "none"
ASSIGN_ME = "me"
ACTION_ASSIGN = "assign"
ASSIGN_LABEL = "Lead Assigned"
#: Lead enrichment's fit fields (prds/lead-enrichment/build-plan-phase-1.md),
#: read and filtered only when the CRM has them — a select naming a missing
#: attribute is refused by the CRM.
FIT_SELECT = "fitScore,fitGate,fitCounty,fitReasons"
FIT_GATES = ("Passed", "Location unknown", "Out of area")
FIT_EXPORT_COLUMNS = (("Fit score", "fitScore"), ("Service area", "fitGate"), ("County", "fitCounty"))
IN_CAMPAIGN_YES = "yes"
IN_CAMPAIGN_NO = "no"

BULK_ACTIONS = (review.ACTION_DISQUALIFY, review.ACTION_DO_NOT_CONTACT, ACTION_ASSIGN)

#: The Review tab's two modes (build plan § 7e.6, ruling 110). *Judge*:
#: Unqualified leads, decided on a website or an email. *Contacts*: Qualified
#: leads still at Identified, given a named person and a phone or an email.
MODE_JUDGE = "judge"
MODE_CONTACTS = "contacts"
REVIEW_MODES = (MODE_JUDGE, MODE_CONTACTS)
#: What the contacts row writes (§ 7e.6): the lead's own person fields, never a Contact.
CONTACT_FIELDS = ("firstName", "lastName", "phone", "email")

#: Read for every guarded decision: the fields the guard compares and the
#: names it reports.
GUARD_SELECT = cfg.PROSPECT_SELECT + ",modifiedByName,modifiedAt"
#: The guard's read on a CRM with the ladder: the assignee rides along, so a
#: bulk Assign can skip a lead that already has that person.
GUARD_SELECT_LADDER = GUARD_SELECT + "," + ladder.LADDER_SELECT

EXPORT_COLUMNS = (
    ("Business", "businessName"), ("First name", "firstName"), ("Last name", "lastName"),
    ("Lead status", "leadStatus"), ("Stopped because", "sideExit"), ("Lead Source", "leadSource"),
    ("Street", "mailingAddressStreet"), ("City", "mailingAddressCity"), ("State", "mailingAddressState"),
    ("ZIP", "mailingAddressPostalCode"), ("Address", "addressStatus"), ("Website", "website"),
    ("Email", "email"), ("Phone", "phone"), ("Filing number", "externalReference"),
    ("Batch", "importBatch"), ("Arrived", "createdAt"), ("Lead id", "id"),
)
LADDER_EXPORT_COLUMNS = (("Level", "qualificationLevel"), ("Assigned to", "assignedUserName"),
                         ("Referred by (partner)", "referredByPartnerName"), ("Referred by (name)", "referredByName"),
                         ("Replied", "replied"), ("Last activity", "modifiedAt"))

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
    gate: str = ""             # "" any, or one of FIT_GATES (design E13)
    min_fit: Optional[int] = None   # 0-100, the fit score at least
    level: str = ""            # "" any, or one of cfg.LEVELS (§ 7e.4; the ladder)
    assigned: str = ""         # "" any, "none" unassigned, or a User id ("me" resolved by the router)
    replied: str = ""          # "1": Replied, not yet converted
    mode: str = ""             # the Review queue's mode (judge / contacts), else ""
    sort: str = "createdAt"
    dir: str = "desc"
    offset: int = 0
    limit: int = PAGE
    errors: list[str] = field(default_factory=list)

    @classmethod
    def from_params(cls, params: dict[str, Any], *, review_queue: bool = False, me: str = "",
                    mode: str = "") -> "LeadQuery":
        g = lambda k: str(params.get(k) or "").strip()  # noqa: E731
        lq = cls(q=g("q")[:200], status=g("status"), exit=g("exit"), source=g("source"),
                 batch=g("batch")[:255], place=g("place")[:100], arrived_from=g("arrivedFrom"),
                 arrived_to=g("arrivedTo"), in_campaign=g("inCampaign"), gate=g("gate"),
                 level=g("level"), assigned=g("assigned"),
                 replied="1" if g("replied").lower() in ("1", "true", "yes") else "",
                 sort=g("sort") or ("createdAt"), dir=(g("dir") or ("asc" if review_queue else "desc")).lower())
        if lq.assigned == ASSIGN_ME:
            lq.assigned = me or ASSIGN_UNASSIGNED
        if lq.level and lq.level not in cfg.LEVELS:
            lq.errors.append("Unknown level.")
        if lq.assigned and lq.assigned != ASSIGN_UNASSIGNED and not _CRM_ID.match(lq.assigned):
            lq.errors.append("Unknown assignee.")
        try:
            lq.offset = max(0, int(params.get("offset") or 0))
        except (TypeError, ValueError):
            lq.offset = 0
        try:
            lq.limit = min(MAX_PAGE, max(1, int(params.get("limit") or PAGE)))
        except (TypeError, ValueError):
            lq.limit = PAGE
        if review_queue:
            # The Review queue (§ 7b.1, § 7e.6): no reason, oldest first. Judge
            # is Unqualified; contacts is Qualified at Identified.
            lq.mode = (mode or MODE_JUDGE).strip().lower()
            if lq.mode == MODE_CONTACTS:
                lq.status, lq.exit, lq.level = cfg.LEAD_QUALIFIED, "none", cfg.LEVEL_IDENTIFIED
            elif lq.mode == MODE_JUDGE:
                lq.status, lq.exit = cfg.LEAD_UNQUALIFIED, "none"
            else:
                lq.errors.append("Unknown review mode: choose judge or contacts.")
        if lq.sort not in SORT_FIELDS:
            lq.sort = "createdAt"
        if lq.dir not in ("asc", "desc"):
            lq.dir = "desc"
        for label, value in (("From", lq.arrived_from), ("To", lq.arrived_to)):
            if value and not _DATE.match(value):
                lq.errors.append(f"{label} date must be a date (YYYY-MM-DD).")
        if lq.in_campaign not in ("", IN_CAMPAIGN_YES, IN_CAMPAIGN_NO) and not _CRM_ID.match(lq.in_campaign):
            lq.errors.append("Unknown campaign.")
        if lq.gate and lq.gate not in FIT_GATES:
            lq.errors.append("Unknown service-area value.")
        raw_fit = g("minFit")
        if raw_fit:
            try:
                lq.min_fit = int(raw_fit)
                if not 0 <= lq.min_fit <= 100:
                    raise ValueError
            except ValueError:
                lq.min_fit = None
                lq.errors.append("Fit at least must be a whole number from 0 to 100.")
        return lq

    def without_fit(self) -> None:
        """Drop the fit filters and sort, for a CRM without the fit fields."""
        self.gate, self.min_fit = "", None
        if self.sort == "fitScore":
            self.sort = "createdAt"

    def without_ladder(self) -> None:
        """Drop the ladder's filters and sort, for a CRM without its fields."""
        self.level, self.assigned, self.replied = "", "", ""
        if self.sort in LADDER_SORT_FIELDS:
            self.sort = "createdAt"

    def params(self) -> dict[str, str]:
        """The query as request parameters (for a bulk resolve sent back)."""
        out = {"q": self.q, "status": self.status, "exit": self.exit, "source": self.source,
               "batch": self.batch, "place": self.place, "arrivedFrom": self.arrived_from,
               "arrivedTo": self.arrived_to, "inCampaign": self.in_campaign,
               "gate": self.gate, "minFit": "" if self.min_fit is None else str(self.min_fit),
               "level": self.level, "assigned": self.assigned, "replied": self.replied,
               "mode": self.mode, "sort": self.sort, "dir": self.dir}
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
    if lq.gate:
        where.append({"type": "equals", "attribute": "fitGate", "value": lq.gate})
    if lq.min_fit is not None:
        where.append({"type": "greaterThanOrEquals", "attribute": "fitScore", "value": lq.min_fit})
    if lq.level:
        where.append({"type": "equals", "attribute": "qualificationLevel", "value": lq.level})
    if lq.assigned == ASSIGN_UNASSIGNED:
        where.append({"type": "isNull", "attribute": "assignedUserId"})
    elif lq.assigned:
        where.append({"type": "equals", "attribute": "assignedUserId", "value": lq.assigned})
    if lq.replied:
        where.append({"type": "isTrue", "attribute": "replied"})
        where.append({"type": "notEquals", "attribute": "leadStatus", "value": cfg.LEAD_CONVERTED})
    return where


async def fit_available(client: EspoApi) -> bool:
    """Whether this CRM carries the lead fit fields. Fails closed."""
    reader = getattr(client, "metadata", None)
    if reader is None:          # a client that cannot read metadata has no fit fields
        return False
    try:
        fields = await reader(f"entityDefs.{cfg.PROSPECT}.fields")
    except EspoError:
        return False
    return isinstance(fields, dict) and all(f in fields for f in FIT_SELECT.split(","))


async def ladder_available(client: EspoApi) -> bool:
    """Whether this CRM carries the ladder's fields (marketing-redesign-crm-handoff.md)."""
    return await ladder.available(client)


def _refuse_contacts_without_ladder(lq: LeadQuery, has_ladder: bool) -> None:
    """The contacts queue needs the level; a CRM without it is told so, never
    handed the judge queue instead (§ 7e.6)."""
    if lq.mode == MODE_CONTACTS and not has_ladder:
        raise CampaignError("This CRM does not carry the ladder's lead fields yet, so the Find contacts "
                            "queue is not available here. The Judge queue still is.")


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
    fit = await fit_available(client)
    if not fit:
        lq.without_fit()
    has_ladder = await ladder_available(client)
    _refuse_contacts_without_ladder(lq, has_ladder)
    if not has_ladder:
        lq.without_ladder()
    select = cfg.PROSPECT_SELECT + ("," + FIT_SELECT if fit else "") + ("," + ladder.LADDER_SELECT if has_ladder else "")
    if _is_campaign(lq):
        rows = await _campaign_rows(client, lq, select=select)
        return {"prospects": rows[lq.offset:lq.offset + lq.limit], "total": len(rows),
                "offset": lq.offset, "limit": lq.limit, "fit": fit, "ladder": has_ladder}
    page = await client.list(cfg.PROSPECT, select=select, where=build_where(lq) or None,
                             max_size=lq.limit, offset=lq.offset, order_by=lq.sort, order=lq.dir)
    rows = page.get("list", [])
    total = page.get("total")
    if not isinstance(total, int) or total < 0:
        total = lq.offset + len(rows)
    return {"prospects": rows, "total": total, "offset": lq.offset, "limit": lq.limit, "fit": fit,
            "ladder": has_ladder}


def _count_queries(lq: LeadQuery, me: str = "") -> dict[str, LeadQuery]:
    """The counts across the top of the Leads tab (§ 7e.4), each the current
    filters with its own status, level or reply condition — plus *Mine*, the
    signed-in user's assigned leads (rulings 108, 115), when ``me`` is known."""
    base = replace(lq, status="", level="", replied="", offset=0)
    out = {
        "unqualified": replace(base, status=cfg.LEAD_UNQUALIFIED),
        "identified": replace(base, status=cfg.LEAD_QUALIFIED, level=cfg.LEVEL_IDENTIFIED),
        "contactable": replace(base, status=cfg.LEAD_QUALIFIED, level=cfg.LEVEL_CONTACTABLE),
        "referred": replace(base, status=cfg.LEAD_QUALIFIED, level=cfg.LEVEL_REFERRED),
        "replied": replace(base, replied="1"),
        "disqualified": replace(base, status=cfg.LEAD_DISQUALIFIED),
    }
    if me:
        out["mine"] = replace(base, assigned=me)
    return out


def _matches_count(row: dict[str, Any], q: LeadQuery) -> bool:
    if q.status and (row.get("leadStatus") or "") != q.status:
        return False
    if q.assigned and q.assigned != ASSIGN_UNASSIGNED and (row.get("assignedUserId") or "") != q.assigned:
        return False
    if q.level and (row.get("qualificationLevel") or "") != q.level:
        return False
    if q.replied and not (row.get("replied") and row.get("leadStatus") != cfg.LEAD_CONVERTED):
        return False
    return True


async def counts(client: EspoApi, lq: LeadQuery, me: str = "") -> dict[str, Any]:
    """The Leads tab's counts, one CRM ``total`` each, read side by side. A
    CRM without the ladder answers only Unqualified and Disqualified."""
    if lq.errors:
        raise CampaignError(" ".join(lq.errors))
    if not await fit_available(client):
        lq.without_fit()
    has_ladder = await ladder_available(client)
    if not has_ladder:
        lq.without_ladder()
    queries = _count_queries(lq, me)
    if not has_ladder:
        queries = {k: v for k, v in queries.items() if k in ("unqualified", "disqualified")}
    out: dict[str, Any] = {"ladder": has_ladder}
    if _is_campaign(lq):
        rows = await _campaign_rows(client, replace(lq, status="", level="", replied="", assigned=""),
                                    select="id,leadStatus,qualificationLevel,replied,assignedUserId" if has_ladder else "id,leadStatus")
        for key, q in queries.items():
            out[key] = sum(1 for r in rows if _matches_count(r, q))
        return out

    async def one(q: LeadQuery) -> int:
        page = await client.list(cfg.PROSPECT, select="id", where=build_where(q) or None, max_size=1)
        total = page.get("total")
        return total if isinstance(total, int) and total >= 0 else len(page.get("list", []))

    totals = await asyncio.gather(*(one(q) for q in queries.values()))
    out.update(dict(zip(queries.keys(), totals)))
    return out


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
    if not await fit_available(client):
        lq.without_fit()
    has_ladder = await ladder_available(client)
    _refuse_contacts_without_ladder(lq, has_ladder)
    if not has_ladder:
        lq.without_ladder()
    select = "id,leadStatus,sideExit" + (",qualificationLevel" if has_ladder else "")
    rows = await _all(client, lq, select=select, cap=BULK_CAP)
    return [{"id": r["id"], "leadStatus": r.get("leadStatus") or "", "sideExit": r.get("sideExit") or "",
             **({"qualificationLevel": r.get("qualificationLevel") or ""} if has_ladder else {})}
            for r in rows if r.get("id")]


def changed_since(lead: dict[str, Any], seen: dict[str, Any]) -> Optional[str]:
    """None when the lead is as the reviewer saw it, else the sentence that
    says what changed and who changed it (§ 7b answer 5)."""
    was_status = (seen.get("leadStatus") or "")
    was_exit = (seen.get("sideExit") or "")
    was_level = (seen.get("qualificationLevel") or "")
    now_status = lead.get("leadStatus") or ""
    now_exit = lead.get("sideExit") or ""
    now_level = lead.get("qualificationLevel") or ""
    if "leadStatus" in seen and was_status and was_status != now_status:
        what = now_status
    elif "sideExit" in seen and was_exit != now_exit:
        what = f"stopped ({now_exit})" if now_exit else "worked again"
    elif "qualificationLevel" in seen and was_level != now_level:
        # The contacts queue (§ 7e.6): someone else found the person first.
        what = now_level if now_level else "moved off its level"
    else:
        return None
    who = lead.get("modifiedByName") or "someone else"
    when = (lead.get("modifiedAt") or "")[:16]
    return f"Already {what}, by {who}" + (f" at {when} UTC" if when else "") + "."


def assign_payload(lead: dict[str, Any], assignee: dict[str, str]) -> dict[str, Any]:
    """The write that assigns a lead to a team member (ruling 108), or raises
    when the lead is not one to work. Pure, so the rule is tested without a CRM."""
    if lead.get("leadStatus") == cfg.LEAD_CONVERTED:
        raise CampaignError("This lead is Converted; its Company or Contact is the record to work now.")
    if lead.get("leadStatus") == cfg.LEAD_DISQUALIFIED:
        raise CampaignError("A Disqualified lead is not worked, so it is not assigned.")
    if lead.get("sideExit"):
        raise CampaignError(f"This lead stopped being worked ({lead['sideExit']}), so it is not assigned.")
    if lead.get("assignedUserId") == assignee["id"]:
        raise CampaignError(f"Already assigned to {assignee['name']}.")
    return {"assignedUserId": assignee["id"]}


async def apply_bulk(user_client: EspoApi, api_client: Optional[EspoApi], items: list[dict[str, Any]],
                     action: str, *, reviewer: str, note: str,
                     assignee: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """Apply one review action, or an assignment, to up to :data:`BULK_BATCH`
    leads. Never stops on one lead: each is done, skipped (with why) or failed
    (with the CRM's words)."""
    if action not in BULK_ACTIONS:
        raise CampaignError("Only Disqualify, Do Not Contact and Assign to run on many leads at once.")
    if len(items) > BULK_BATCH:
        raise CampaignError(f"At most {BULK_BATCH} leads per request.")
    if action == review.ACTION_DISQUALIFY and not (note or "").strip():
        raise CampaignError("Say why these leads will never be a client, partner or funder — the reason is required.")
    if action == ACTION_ASSIGN and not assignee:
        raise CampaignError("Choose the team member these leads go to.")
    out: dict[str, Any] = {"done": [], "skipped": [], "failed": []}
    for item in items:
        lead_id = str(item.get("id") or "")
        if not _CRM_ID.match(lead_id):
            out["failed"].append({"id": lead_id, "name": "", "why": "Not a lead id."})
            continue
        try:
            lead = await user_client.get(cfg.PROSPECT, lead_id,
                                         select=GUARD_SELECT_LADDER if action == ACTION_ASSIGN else GUARD_SELECT)
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
            if action == ACTION_ASSIGN:
                await user_client.update(cfg.PROSPECT, lead_id, assign_payload(lead, assignee or {}))
            else:
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
    columns = EXPORT_COLUMNS
    if await fit_available(client):
        columns = EXPORT_COLUMNS + FIT_EXPORT_COLUMNS
    else:
        lq.without_fit()
    if await ladder_available(client):
        columns = columns + LADDER_EXPORT_COLUMNS
    else:
        lq.without_ladder()
    select = ",".join(sorted({f for _, f in columns}))
    rows = await _all(client, lq, select=select, cap=EXPORT_CAP)

    async def gen() -> AsyncIterator[str]:
        yield "﻿" + _csv_line([label for label, _ in columns])
        for r in rows:
            yield _csv_line([r.get(f) for _, f in columns])
    return gen()


# --- the lead's page (build plan § 7e.4) -------------------------------------------------------

#: The gaps a person may fill inline on the lead's page, written as the user.
FACT_FIELDS = (
    "businessName", "firstName", "lastName", "phone", "email", "website",
    "mailingAddressStreet", "mailingAddressCity", "mailingAddressState", "mailingAddressPostalCode",
    "referredByName", "referredByPartnerId",
)
_LADDER_FACTS = ("referredByName", "referredByPartnerId")


def facts_payload(lead: dict[str, Any], changes: dict[str, Any], *, ladder_on: bool) -> dict[str, Any]:
    """The write an inline edit makes: only known fields, only values that
    changed, a website given its scheme, an email that looks like one, a
    changed business name carried into the record's name. Raises
    :class:`CampaignError` naming what is wrong."""
    out: dict[str, Any] = {}
    for key, raw in (changes or {}).items():
        if key not in FACT_FIELDS:
            raise CampaignError(f"\"{key}\" is not a field the lead's page edits.")
        if key in _LADDER_FACTS and not ladder_on:
            raise CampaignError("This CRM does not carry the referrer fields yet.")
        value = ("" if raw is None else str(raw)).strip()
        if key in ("website", "email"):
            typed = review.contact_changes(lead, value if key == "website" else None,
                                           value if key == "email" else None)
            if value and not typed:
                continue                      # unchanged
            out[key] = typed.get(key) if value else None
            if out[key] == (lead.get(key) or None):
                del out[key]
            continue
        if key == "referredByPartnerId" and value and not _CRM_ID.match(value):
            raise CampaignError("Unknown partner.")
        value = value[:255] or None
        if value == (lead.get(key) or None):
            continue
        out[key] = value
    if "businessName" in out and out["businessName"]:
        out["name"] = out["businessName"]
    if not out:
        raise CampaignError("Nothing changed.")
    return out


def contacts_payload(lead: dict[str, Any], typed: dict[str, Any]) -> dict[str, Any]:
    """The write a contacts-queue row makes (§ 7e.6): the four person fields
    through :func:`facts_payload`, so a typed email is checked and an unchanged
    value is not rewritten. Empty when nothing new was typed — the row may
    still be closing accepted findings. Raises :class:`CampaignError` for a
    field the row does not hold or a value that is not what it claims."""
    changes = {}
    for key, raw in (typed or {}).items():
        if key not in CONTACT_FIELDS:
            raise CampaignError(f"\"{key}\" is not a box on the contacts row.")
        if str(raw or "").strip():
            changes[key] = raw
    if not changes:
        return {}
    try:
        return facts_payload(lead, changes, ladder_on=True)
    except CampaignError as exc:
        if str(exc) == "Nothing changed.":
            return {}
        raise


def contacts_needed(lead: dict[str, Any]) -> str:
    """What an Identified lead still lacks to become Contactable, in plain
    words; empty when it lacks nothing."""
    have = ladder.facts(lead)
    missing = []
    if ladder.FACT_PERSON not in have:
        missing.append("the person's name")
    if ladder.FACT_PHONE not in have and ladder.FACT_EMAIL not in have:
        missing.append("a phone or an email")
    return " and ".join(missing)


def activity_rows(touches: list[dict[str, Any]], actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One timeline (§ 7e.4): touches and action-log rows, newest first. Each
    row is ``{at, kind, title, detail, by}``."""
    rows: list[dict[str, Any]] = []
    for t in touches:
        at = t.get("doneAt") or t.get("deliveredAt") or t.get("sentAt") or t.get("plannedAt") or t.get("createdAt") or ""
        channel = t.get("channel") or "Touch"
        status = t.get("touchStatus") or ""
        title = f"{channel} {status.lower()}".strip() if status else channel
        detail = " · ".join(x for x in (t.get("outreachCampaignName"), t.get("outcome"),
                                        f"scans {t.get('scanCount')}" if t.get("scanCount") else "",
                                        t.get("callNotes")) if x)
        rows.append({"at": at, "kind": "touch", "title": title, "detail": detail, "by": "", "id": t.get("id")})
    for a in actions:
        rows.append({"at": a.get("createdAt") or "", "kind": "action", "title": a.get("actionType") or a.get("name") or "",
                     "detail": a.get("summary") or "", "by": a.get("actorName") or "", "id": a.get("id")})
    rows.sort(key=lambda r: r["at"] or "", reverse=True)
    return rows
