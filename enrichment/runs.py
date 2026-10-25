"""AI research runs: starting one under the budget, the worker's queue, where
findings land, and Accept / Reject (build plan phase 2 §§ 4.2–4.4).

Rulings: E7 (what a run may send), E8 and E9 (the monthly budget, refused with
the amounts named), E10 (a person found becomes a Contact only when accepted,
never opted in to marketing), E12 (Verified is counted by the application),
E14 (a Verified website or email goes into an EMPTY field on a lead), E18 (a
person starts every run), E19 (only Client Administration decides a client's
findings — enforced by the router's team gate).

Every CRM read and write here runs under the org-wide API client: the worker
has no user, and Accept / Reject are gated by the application before they get
here. ``CustomAppAPIRole`` creates and edits ``CEnrichmentFinding``
(``scripts/migrate_enrichment_roles.py``).
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from core.config import Settings
from core.crm_upsert import website_key
from core.espo import EspoApi, EspoError
from core.phone import e164_or_none

from . import fit, research
from .store import EnrichmentStore
from .terms import build_terms

log = logging.getLogger("cbm_intake.enrichment.runs")

FINDING = "CEnrichmentFinding"
PROSPECT = "CProspect"
ACCOUNT = "Account"
CONTACT = "Contact"
TIER_AI = "AI research"
TARGET_LEAD, TARGET_COMPANY = "lead", "company"
KIND_FIELD, KIND_PERSON, KIND_SUMMARY = "Field value", "Person", "Summary"
ST_PROPOSED, ST_ACCEPTED, ST_REJECTED, ST_APPLIED = "Proposed", "Accepted", "Rejected", "Applied"
#: Before 50 records have been researched, the estimate's cost per record.
DEFAULT_RECORD_COST = 0.20
_CRM_ID = re.compile(r"^[A-Za-z0-9]{6,32}$")

#: candidate kind -> the field it fills, per record type
LEAD_FIELDS = {"website": "website", "email": "email", "phone": "phone", "industry": "industry"}
COMPANY_FIELDS = {"website": "website", "email": "emailAddress", "phone": "phoneNumber", "industry": "industry"}
FINDING_SELECT = ("id,name,kind,targetField,proposedValue,currentValue,personName,personTitle,personEmail,"
                  "summary,confidence,factsMatched,sourceUrl,tier,findingStatus,decidedBy,decidedAt,runRef,"
                  "prospectId,companyId,createdAt")


class EnrichmentError(Exception):
    """A refusal to show the person as it stands."""


def _now_crm() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def api_client(settings: Settings) -> Optional[EspoApi]:
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    from core.espo import EspoClient
    return EspoClient(settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds)


async def available(client: EspoApi) -> bool:
    """Whether this CRM carries ``CEnrichmentFinding`` and both its links.
    Fails closed."""
    try:
        links = await client.metadata(f"entityDefs.{FINDING}.links")
    except EspoError:
        return False
    return isinstance(links, dict) and "prospect" in links and "company" in links


def readiness(settings: Settings) -> Optional[str]:
    """None when a run may start, else the reason in plain words."""
    if not settings.enrichment_ai:
        return "AI research is switched off (System Settings, 'AI research')."
    if not settings.anthropic_api_key:
        return "AI research needs the Anthropic API key (System Settings, Integrations)."
    if not settings.store_enabled:
        return "AI research needs the application database."
    return None


# --- starting a run ---------------------------------------------------------------------------

async def estimate(store: EnrichmentStore, settings: Settings, count: int) -> dict[str, Any]:
    avg = await store.average_item_cost()
    per = avg if avg is not None else DEFAULT_RECORD_COST
    spent = await store.month_spend()
    reserved = (await store.queued_items()) * per
    budget = float(settings.enrichment_monthly_budget)
    est = count * per
    return {"records": count, "perRecord": round(per, 4), "estimate": round(est, 2),
            "spent": round(spent, 2), "reserved": round(reserved, 2), "budget": round(budget, 2),
            "left": round(max(0.0, budget - spent - reserved), 2),
            "fits": spent + reserved + est <= budget, "measured": avg is not None}


async def start_run(store: EnrichmentStore, settings: Settings, *, target_type: str,
                    target_ids: list[str], started_by: str, confirm_estimate: Optional[float] = None
                    ) -> dict[str, Any]:
    """Queue a run, or refuse with the reason. ``confirm_estimate`` is what the
    person saw; a run whose estimate grew since is refused so they look again."""
    why = readiness(settings)
    if why:
        raise EnrichmentError(why)
    ids = list(dict.fromkeys(i for i in target_ids if _CRM_ID.match(str(i or ""))))
    if not ids:
        raise EnrichmentError("Choose at least one record to research.")
    if target_type not in (TARGET_LEAD, TARGET_COMPANY):
        raise EnrichmentError("Unknown record type.")
    cap = int(settings.enrichment_ai_max_records)
    if len(ids) > cap:
        raise EnrichmentError(f"{len(ids):,} records chosen; a run takes at most {cap:,}. Narrow the selection.")
    est = await estimate(store, settings, len(ids))
    if not est["fits"]:
        raise EnrichmentError(
            f"This run would cost about ${est['estimate']:.2f}, and only ${est['left']:.2f} of this "
            f"month's ${est['budget']:.2f} is left (${est['spent']:.2f} spent, ${est['reserved']:.2f} "
            f"held for runs still going). Choose fewer records, or raise the budget at System Settings.")
    if confirm_estimate is not None and est["estimate"] > float(confirm_estimate) + 0.005:
        raise EnrichmentError(f"The estimate changed to ${est['estimate']:.2f} since you looked. Check it and start again.")
    run = await store.create_run(tier=TIER_AI, target_type=target_type, target_ids=ids, estimate=est["estimate"],
                                 model=settings.enrichment_ai_model, started_by=started_by)
    return {"run": run["id"], **est}


# --- the subject (ruling E7) -----------------------------------------------------------------

async def _options(client: EspoApi, entity: str, field: str) -> list[str]:
    try:
        meta = await client.metadata(f"entityDefs.{entity}.fields.{field}")
    except EspoError:
        return []
    opts = meta.get("options") if isinstance(meta, dict) else None
    return [o for o in opts if isinstance(o, str) and o] if isinstance(opts, list) else []


async def lead_subject(client: EspoApi, lead_id: str) -> tuple[research.Subject, dict[str, Any], bool]:
    fields = await client.metadata(f"entityDefs.{PROSPECT}.fields") or {}
    has_industry = isinstance(fields, dict) and "industry" in fields
    select = ("id,name,businessName,mailingAddressStreet,mailingAddressCity,mailingAddressState,"
              "mailingAddressPostalCode,website,email,phone,importRow" + (",industry" if has_industry else ""))
    lead = await client.get(PROSPECT, lead_id, select=select)
    name = (lead.get("businessName") or "").strip()
    if not name:
        raise EnrichmentError("This lead has no business name; AI research looks up businesses only.")
    terms = build_terms()
    subject = research.Subject(
        name=name, street=lead.get("mailingAddressStreet") or "", city=lead.get("mailingAddressCity") or "",
        state=lead.get("mailingAddressState") or "", postal=lead.get("mailingAddressPostalCode") or "",
        website=lead.get("website") or "",
        associates=[a.title() for a in fit.associates(lead)],   # a public filing's names (E7)
        agent_address=fit.at_agent_address(lead, terms),
        industry_options=await _options(client, PROSPECT, "industry") if has_industry else [])
    return subject, lead, has_industry


async def company_subject(client: EspoApi, company_id: str) -> tuple[research.Subject, dict[str, Any]]:
    company = await client.get(ACCOUNT, company_id, select=(
        "id,name,billingAddressStreet,billingAddressCity,billingAddressState,billingAddressPostalCode,"
        "website,emailAddress,phoneNumber,industry"))
    subject = research.Subject(
        name=(company.get("name") or "").strip(), street=company.get("billingAddressStreet") or "",
        city=company.get("billingAddressCity") or "", state=company.get("billingAddressState") or "",
        postal=company.get("billingAddressPostalCode") or "", website=company.get("website") or "",
        industry_options=await _options(client, ACCOUNT, "industry"))
    if not subject.name:
        raise EnrichmentError("This company has no name.")
    return subject, company


# --- landing findings -------------------------------------------------------------------------

def _norm(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip().lower().rstrip("/")


async def existing_findings(client: EspoApi, *, prospect_id: str = "", company_id: str = "") -> list[dict[str, Any]]:
    attr, rid = ("prospectId", prospect_id) if prospect_id else ("companyId", company_id)
    out: list[dict[str, Any]] = []
    offset = 0
    while offset < 2000:
        page = await client.list(FINDING, select=FINDING_SELECT, max_size=200, offset=offset,
                                 where=[{"type": "equals", "attribute": attr, "value": rid}],
                                 order_by="createdAt", order="desc")
        rows = page.get("list", [])
        out.extend(rows)
        if len(rows) < 200:
            break
        offset += 200
    return out


def _phone_key(v: Any) -> str:
    raw = str(v or "")
    return e164_or_none(raw) or re.sub(r"\D", "", raw)


def same_value(field: str, current: Any, proposed: Any) -> bool:
    """True when the record's value and a finding's value are one value to a
    person: a website under ``website_key`` (scheme, ``www.`` and a trailing
    slash ignored), an email address whatever its capitals, a phone number by
    its digits; anything else under ``_norm``. An empty value never matches."""
    f = (field or "").lower()
    if "website" in f:
        a, b = website_key(str(current or "")), website_key(str(proposed or ""))
    elif "email" in f:
        a, b = str(current or "").strip().lower(), str(proposed or "").strip().lower()
    elif "phone" in f:
        a, b = _phone_key(current), _phone_key(proposed)
    else:
        a, b = _norm(current), _norm(proposed)
    return bool(a) and a == b


def _finding_key(kind: str, target: str, value: str) -> tuple[str, str, str]:
    return (kind, target, _norm(value))


async def land(client: EspoApi, result: research.Result, *, target_type: str, record: dict[str, Any],
               run_id: str, lead_has_industry: bool = False) -> dict[str, int]:
    """Write a result's findings onto the record (design § 6). Returns counts."""
    counts = {"created": 0, "applied": 0, "skipped": 0}
    is_lead = target_type == TARGET_LEAD
    link = {"prospectId": record["id"]} if is_lead else {"companyId": record["id"]}
    field_map = dict(LEAD_FIELDS if is_lead else COMPANY_FIELDS)
    if is_lead and not lead_has_industry:
        field_map.pop("industry", None)
    have = await existing_findings(client, **({"prospect_id": record["id"]} if is_lead else {"company_id": record["id"]}))
    keys = {_finding_key(f.get("kind") or "", f.get("targetField") or f.get("personName") or "",
                         f.get("proposedValue") or f.get("personName") or "") for f in have}
    base = {"tier": TIER_AI, "runRef": run_id, **link}

    for c in result.candidates:
        target = field_map.get(c.kind)
        if not target or c.confidence == research.UNVERIFIED:
            counts["skipped"] += 1
            continue
        current = record.get(target) or ""
        if same_value(target, current, c.value) or _finding_key(KIND_FIELD, target, c.value) in keys:
            counts["skipped"] += 1
            continue
        status = ST_PROPOSED
        if (is_lead and c.confidence == research.VERIFIED and c.kind in ("website", "email")
                and not str(current).strip()):
            await client.update(PROSPECT, record["id"], {target: c.value})   # E14: an empty field only
            record[target] = c.value
            status = ST_APPLIED
            counts["applied"] += 1
            # A new email may lift the lead's level (build plan § 7e.3).
            from campaigns.ladder import after_write
            await after_write(record["id"], client=client)
        await client.create(FINDING, {
            **base, "name": f"{target}: {c.value}"[:150], "kind": KIND_FIELD, "targetField": target,
            "proposedValue": c.value, "currentValue": str(current) or None, "confidence": c.confidence,
            "factsMatched": research.facts_text(c.facts), "sourceUrl": c.source_url or None,
            "findingStatus": status,
            **({"decidedBy": "AI research (ruling E14)", "decidedAt": _now_crm()} if status == ST_APPLIED else {})})
        keys.add(_finding_key(KIND_FIELD, target, c.value))
        counts["created"] += 1

    for p in result.people:
        if p.confidence == research.UNVERIFIED or _finding_key(KIND_PERSON, p.name, p.name) in keys:
            counts["skipped"] += 1
            continue
        await client.create(FINDING, {
            **base, "name": f"Person: {p.name}"[:150], "kind": KIND_PERSON, "personName": p.name[:150],
            "personTitle": p.title[:150] or None, "personEmail": p.email[:150] or None,
            "confidence": p.confidence, "factsMatched": research.facts_text(p.facts),
            "sourceUrl": p.source_url or None, "findingStatus": ST_PROPOSED})
        keys.add(_finding_key(KIND_PERSON, p.name, p.name))
        counts["created"] += 1

    if result.found and result.summary:
        await client.create(FINDING, {
            **base, "name": "Summary", "kind": KIND_SUMMARY, "summary": result.summary,
            "confidence": research.VERIFIED if result.candidates else research.LIKELY,
            "factsMatched": "\n".join(result.summary_sources) or None,
            "sourceUrl": (result.summary_sources[0] if result.summary_sources else None),
            "findingStatus": ST_PROPOSED})
        counts["created"] += 1
    return counts


# --- the worker -------------------------------------------------------------------------------

def anthropic_client(settings: Settings) -> Any:
    import anthropic
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=600.0, max_retries=2)


async def research_item(settings: Settings, client: EspoApi, ai: Any, item: dict[str, Any]) -> dict[str, Any]:
    """Research one queued record and land its findings. Never raises."""
    target_type, target_id = item["target_type"], item["target_id"]
    try:
        if target_type == TARGET_LEAD:
            subject, record, has_ind = await lead_subject(client, target_id)
        else:
            (subject, record), has_ind = await company_subject(client, target_id), False
    except (EnrichmentError, EspoError) as exc:
        return {"ok": False, "cost": 0.0, "findings": 0, "error": str(exc)}
    result = await research.research(
        ai, subject, model=item.get("model") or settings.enrichment_ai_model,
        max_searches=settings.enrichment_ai_max_searches, fallback=settings.enrichment_ai_fallback,
        record_cap=float(settings.enrichment_ai_record_cap))
    detail = {"model": result.model, "searches": result.searches, "found": result.found}
    if not result.ok:
        return {"ok": False, "cost": result.cost, "findings": 0, "error": result.error, "detail": detail}
    try:
        counts = await land(client, result, target_type=target_type, record=record,
                            run_id=item["run_id"], lead_has_industry=has_ind)
    except EspoError as exc:
        return {"ok": False, "cost": result.cost, "findings": 0, "error": f"Saving the findings failed: {exc}",
                "detail": detail}
    detail.update(counts)
    return {"ok": True, "cost": result.cost, "findings": counts["created"], "error": None, "detail": detail}


async def run_research_cycle(settings: Settings, store: EnrichmentStore, *, client: Optional[EspoApi] = None,
                             ai: Any = None, batch: int = 2) -> int:
    """Take up to ``batch`` queued records and research them side by side.
    Returns how many were taken. Best-effort: never raises."""
    if readiness(settings):
        return 0
    client = client or api_client(settings)
    if client is None or not await available(client):
        return 0
    items = await store.claim(batch)
    if not items:
        return 0
    ai = ai or anthropic_client(settings)
    outcomes = await asyncio.gather(*(research_item(settings, client, ai, it) for it in items),
                                    return_exceptions=True)
    for it, out in zip(items, outcomes):
        if isinstance(out, Exception):
            out = {"ok": False, "cost": 0.0, "findings": 0, "error": f"{type(out).__name__}: {out}"}
        await store.finish_item(it["run_id"], it["target_id"], ok=out["ok"], cost=out["cost"],
                                findings=out["findings"], detail=out.get("detail"), error=out.get("error"))
        log.info("ai research: %s %s %s cost=$%.3f findings=%s%s", it["target_type"], it["target_id"],
                 "done" if out["ok"] else "failed", out["cost"], out["findings"],
                 "" if out["ok"] else f" ({out.get('error')})")
    return len(items)


# --- Accept and Reject ----------------------------------------------------------------------

async def decide(client: EspoApi, finding_id: str, decision: str, *, actor: str,
                 target_type: str, target_id: str) -> dict[str, Any]:
    """Accept or reject one Proposed finding on the record it belongs to.

    Accepting a field value writes it into the EMPTY field (never over a
    value); a person on a client becomes a Contact linked to the Company,
    carrying the Company's owners, not opted in to anything (E10). A person
    on a lead, and a summary, can only be rejected (ruling 43: a lead's people
    stay on the lead until first contact)."""
    if decision not in (ST_ACCEPTED, ST_REJECTED):
        raise EnrichmentError("Accept or Reject only.")
    f = await client.get(FINDING, finding_id, select=FINDING_SELECT)
    owner = f.get("prospectId") if target_type == TARGET_LEAD else f.get("companyId")
    if not f or owner != target_id:
        raise EnrichmentError("That finding does not belong to this record.")
    if f.get("findingStatus") != ST_PROPOSED:
        who = f.get("decidedBy") or "someone else"
        raise EnrichmentError(f"Already {str(f.get('findingStatus')).lower()} by {who}.")
    stamp = {"decidedBy": actor, "decidedAt": _now_crm()}
    note = ""
    if decision == ST_ACCEPTED:
        kind = f.get("kind")
        if kind == KIND_SUMMARY:
            raise EnrichmentError("A summary is for reading; it has nothing to accept.")
        if kind == KIND_PERSON and target_type == TARGET_LEAD:
            raise EnrichmentError("A person found on a lead stays on the lead until first contact (ruling 43).")
        if kind == KIND_FIELD:
            entity = PROSPECT if target_type == TARGET_LEAD else ACCOUNT
            field = f.get("targetField") or ""
            record = await client.get(entity, target_id, select=f"id,{field}")
            held = record.get(field)
            if same_value(field, held, f.get("proposedValue")):
                # Found before the comparison knew www. from no www. (10-22-26):
                # nothing to write, so accepting simply closes the finding.
                note = "the record already holds this"
            elif str(held or "").strip():
                raise EnrichmentError(f"The record already holds {record.get(field)!s} there; a finding never "
                                      "replaces a value. Change it by hand if the finding is right.")
            else:
                await client.update(entity, target_id, {field: f.get("proposedValue")})
                note = f"{field} set to {f.get('proposedValue')}"
                if target_type == TARGET_LEAD:
                    # A new phone or email may lift the lead's level (§ 7e.3).
                    from campaigns.ladder import after_write
                    await after_write(target_id, client=client)
        elif kind == KIND_PERSON:
            note = await _create_person(client, f, target_id, actor)
    await client.update(FINDING, finding_id, {"findingStatus": decision, **stamp})
    return {"id": finding_id, "status": decision, "note": note}


async def _create_person(client: EspoApi, f: dict[str, Any], company_id: str, actor: str) -> str:
    email = (f.get("personEmail") or "").strip()
    if email:
        page = await client.list(CONTACT, select="id,name", max_size=1,
                                 where=[{"type": "equals", "attribute": "emailAddress", "value": email}])
        if page.get("list"):
            raise EnrichmentError(f"{email} already belongs to the contact {page['list'][0].get('name')}; "
                                  "link them by hand if they belong to this company.")
    parts = (f.get("personName") or "").strip().split()
    first, last = (" ".join(parts[:-1]), parts[-1]) if len(parts) > 1 else ("", parts[0] if parts else "")
    company = await client.get(ACCOUNT, company_id, select="id,assignedUsersIds,teamsIds")
    payload: dict[str, Any] = {
        "firstName": first or None, "lastName": last, "accountId": company_id,
        "description": (f"Found by AI research and accepted by {actor} on {_now_crm()[:10]}"
                        + (f" ({f.get('personTitle')})" if f.get("personTitle") else "")
                        + (f". Source: {f.get('sourceUrl')}" if f.get("sourceUrl") else "")
                        + ". Not opted in to any marketing (ruling E10)."),
    }
    if email:
        payload["emailAddress"] = email
    if company.get("assignedUsersIds"):
        payload["assignedUsersIds"] = company["assignedUsersIds"]
    if company.get("teamsIds"):
        payload["teamsIds"] = company["teamsIds"]
    contact = await client.create(CONTACT, payload)
    return f"contact {contact.get('id')} created"


# --- what the screens read ------------------------------------------------------------------

def present(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Findings grouped for a panel: the newest summary, then the rest."""
    summaries = [f for f in findings if f.get("kind") == KIND_SUMMARY and f.get("findingStatus") != ST_REJECTED]
    rest = [f for f in findings if f.get("kind") != KIND_SUMMARY]
    order = {ST_PROPOSED: 0, ST_APPLIED: 1, ST_ACCEPTED: 2, ST_REJECTED: 3}
    rest.sort(key=lambda f: (order.get(f.get("findingStatus"), 9), f.get("kind") or ""))
    return {"summary": summaries[0] if summaries else None, "findings": rest}
