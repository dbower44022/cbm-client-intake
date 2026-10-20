"""The free pass's worker job, and its Operations job (build plan § 2).

Each pass reads up to ``ENRICHMENT_BATCH`` open leads — Unqualified or
Qualified, no side exit — whose fit score is missing or was computed under an
older rule version, scores them and writes the nine fields. A version is the
rule number plus a hash of everything a chapter tunes (``ScoreContext.version``),
so changing the counties, the weights or a list rescores every lead with no
other step.

A website the web check verified is written only into an EMPTY website field
(ruling E14); a different stored website is named in the reasons and kept.
The lead's status is never touched: a website makes a lead eligible for
Qualified, never Qualified (rulings 42, 53).

Everything runs under the org-wide API key — a machine sweep, like the Stale
sweep. ``CustomAppAPIRole`` already edits ``CProspect``. Feature detection
fails closed: a CRM without the nine fields gets no pass and one log line.
A per-lead failure is logged and skipped for an hour, never fatal.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from core.config import Settings
from core.espo import EspoApi, EspoError

from . import fit, findability, geo
from .terms import build_segments, build_terms, fetch_json

log = logging.getLogger("cbm_intake.enrichment.sweep")

PROSPECT = "CProspect"
OPEN_STATUSES = ("Unqualified", "Qualified")
FIT_FIELDS = ("fitScore", "fitGate", "fitCounty", "fitOperating", "fitSegment",
              "fitFindability", "fitReasons", "fitScoredAt", "fitRuleVersion")
_BASE_SELECT = ("id,name,businessName,mailingAddressStreet,mailingAddressCity,"
                "mailingAddressState,mailingAddressPostalCode,website,email,leadStatus,"
                "sideExit,leadSource,importRow,createdAt,fitScoredAt,fitRuleVersion")
MAX_BATCH = 200          # the CRM's recordListMaxSizeLimit
_SERIAL_TTL = 3600.0
_FAILED_TTL = 3600.0

_failed: dict[str, float] = {}
_serial_cache: dict[str, Any] = {"at": 0.0, "counts": {}}


def _client(settings: Settings) -> Optional[EspoApi]:
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    from core.espo import EspoClient
    return EspoClient(settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds)


async def lead_fields(client: EspoApi) -> Optional[dict[str, Any]]:
    """The lead's field definitions, or None when the CRM lacks the lead or any
    of the nine fit fields. Fails closed."""
    try:
        fields = await client.metadata(f"entityDefs.{PROSPECT}.fields")
    except EspoError as exc:
        log.warning("fit sweep: lead metadata unreadable: %s", exc)
        return None
    if not isinstance(fields, dict) or any(f not in fields for f in FIT_FIELDS):
        return None
    return fields


def _select(fields: dict[str, Any]) -> str:
    # Ruling 66's industry, when the CRM has it: the segment signal reads it.
    return _BASE_SELECT + (",industry" if "industry" in fields else "")


async def build_context(settings: Settings, client: EspoApi) -> fit.ScoreContext:
    terms = build_terms(await fetch_json(settings.enrichment_terms_url))
    segments = build_segments(await fetch_json(settings.chapter_segments_url))
    return fit.ScoreContext(
        area=geo.parse_service_area(settings.chapter_counties),
        terms=terms, segments=segments,
        weights=fit.parse_weights(settings.fit_weights),
        serial_counts=await serial_counts(client),
    )


async def serial_counts(client: EspoApi, *, now: Optional[float] = None) -> dict[str, int]:
    """How many filings each associate is named on, across every lead whose
    import carried associates. Cached for an hour."""
    now = time.monotonic() if now is None else now
    if _serial_cache["counts"] and now - _serial_cache["at"] < _SERIAL_TTL:
        return _serial_cache["counts"]
    counts: dict[str, int] = {}
    offset = 0
    try:
        while offset < 50000:
            page = await client.list(PROSPECT, select="id,importRow",
                                     where=[{"type": "isNotNull", "attribute": "importRow"}],
                                     max_size=MAX_BATCH, offset=offset,
                                     order_by="createdAt", order="asc")
            batch = page.get("list", [])
            for row in batch:
                for person in set(fit.associates(row)):
                    counts[person] = counts.get(person, 0) + 1
            if len(batch) < MAX_BATCH:
                break
            offset += MAX_BATCH
    except EspoError as exc:
        log.warning("fit sweep: associate counts unreadable, serial filers not checked: %s", exc)
        return {}
    _serial_cache.update(at=now, counts=counts)
    return counts


def due_where(version: str) -> list[dict[str, Any]]:
    return [
        {"type": "in", "attribute": "leadStatus", "value": list(OPEN_STATUSES)},
        {"type": "isNull", "attribute": "sideExit"},
        {"type": "or", "value": [
            {"type": "isNull", "attribute": "fitScoredAt"},
            {"type": "notEquals", "attribute": "fitRuleVersion", "value": version},
        ]},
    ]


async def due_leads(client: EspoApi, fields: dict[str, Any], version: str, limit: int,
                    offset: int = 0) -> dict[str, Any]:
    return await client.list(PROSPECT, select=_select(fields), where=due_where(version),
                             max_size=max(1, min(limit, MAX_BATCH)), offset=offset,
                             order_by="createdAt", order="asc")


async def score_one(lead: dict[str, Any], ctx: fit.ScoreContext, *, http=None) -> fit.FitResult:
    web = None
    if http is not None:
        gate_out = bool(ctx.area) and fit.score_lead(lead, ctx).gate == fit.GATE_OUT
        if not gate_out:  # never spend a request on a lead the gate already stopped
            web = await findability.check(lead, ctx.terms, http,
                                          agent=fit.at_agent_address(lead, ctx.terms))
    return fit.score_lead(lead, ctx, web)


def write_payload(lead: dict[str, Any], result: fit.FitResult, version: str,
                  scored_at: str) -> dict[str, Any]:
    payload = result.payload(version, scored_at)
    if result.verified_website and not (lead.get("website") or "").strip():
        payload["website"] = result.verified_website   # E14: an empty field only
    return payload


async def run_pass(settings: Settings, client: EspoApi, *, web_checks: Optional[bool] = None,
                   limit: Optional[int] = None, now: Optional[float] = None) -> dict[str, int]:
    """Score one batch of due leads. Returns the counts for the summary line."""
    totals = {"scored": 0, "out_of_area": 0, "unknown": 0, "websites": 0, "failed": 0, "due": 0}
    fields = await lead_fields(client)
    if fields is None:
        log.info("fit sweep: this CRM lacks the lead fit fields; nothing scored "
                 "(lead-fit-score-crm-handoff.md)")
        return totals
    ctx = await build_context(settings, client)
    version = ctx.version
    batch = limit or settings.enrichment_batch
    page = await due_leads(client, fields, version, batch)
    totals["due"] = int(page.get("total") or 0)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    mono = time.monotonic() if now is None else now
    use_web = settings.enrichment_web_checks if web_checks is None else web_checks
    http = findability.make_client() if use_web else None
    try:
        for lead in page.get("list", []):
            lid = lead.get("id")
            if lid in _failed and mono - _failed[lid] < _FAILED_TTL:
                continue
            try:
                result = await score_one(lead, ctx, http=http)
                await client.update(PROSPECT, lid, write_payload(lead, result, version, stamp))
            except Exception as exc:  # noqa: BLE001 — one lead never stops the pass
                _failed[lid] = mono
                totals["failed"] += 1
                log.warning("fit sweep: lead %s not scored: %s", lid, exc)
                continue
            _failed.pop(lid, None)
            totals["scored"] += 1
            totals["out_of_area"] += result.gate == fit.GATE_OUT
            totals["unknown"] += result.gate == fit.GATE_UNKNOWN
            totals["websites"] += bool(result.verified_website and not (lead.get("website") or "").strip())
    finally:
        if http is not None:
            await http.aclose()
    return totals


async def run_fit_sweep(settings: Settings, *, client: Optional[EspoApi] = None) -> dict[str, int]:
    """The worker's pass. Best-effort, never raises."""
    totals: dict[str, int] = {}
    if not settings.enrichment_free_pass:
        return totals
    client = client or _client(settings)
    if client is None:
        return totals
    try:
        totals = await run_pass(settings, client)
    except Exception as exc:  # noqa: BLE001 — a sweep failure is a log line, never a crash
        log.warning("fit sweep failed: %s", exc)
        return {"failed": 1}
    if totals.get("due") or totals.get("failed"):
        log.info("fit sweep: scored=%(scored)s out_of_area=%(out_of_area)s unknown=%(unknown)s "
                 "websites=%(websites)s failed=%(failed)s due=%(due)s", totals)
    return totals


# --- the Operations job (dry run, then apply that exact plan) ----------------------------

def _need(settings: Settings) -> EspoApi:
    client = _client(settings)
    if client is None:
        raise RuntimeError("This deployment has no CRM credential (dry-run mode or no API key).")
    return client


async def plan_text(settings: Settings, client: EspoApi) -> str:
    """What the apply would do, with no clock and no web request in it, so the
    fingerprint holds unless the CRM or the settings moved."""
    fields = await lead_fields(client)
    if fields is None:
        raise RuntimeError("This CRM lacks the lead fit fields (lead-fit-score-crm-handoff.md).")
    ctx = await build_context(settings, client)
    page = await due_leads(client, fields, ctx.version, 50)
    due = int(page.get("total") or 0)
    head = [f"Rule version {ctx.version}. {due} open leads have no score under it and would be scored.",
            f"Service area: {settings.chapter_counties or '(not set — the gate is skipped)'}.",
            "Web checks: " + ("on — guessed web addresses are fetched" if settings.enrichment_web_checks
                              else "off") + ". The sample below never fetches."]
    lines = []
    for lead in page.get("list", []):
        r = fit.score_lead(lead, ctx)
        lines.append(f"  {lead['id']}  {r.score:>3}  {r.gate:<16}  {lead.get('businessName') or lead.get('name') or ''}")
    if lines:
        head.append(f"The first {len(lines)}, as they would score without the web check:")
    return "\n".join(head + lines)


async def job_dry_run(settings: Settings) -> str:
    return await plan_text(settings, _need(settings))


async def job_apply(settings: Settings) -> str:
    client = _need(settings)
    grand = {"scored": 0, "out_of_area": 0, "unknown": 0, "websites": 0, "failed": 0}
    for _ in range(500):   # 100,000 leads at most; the worker carries on after
        totals = await run_pass(settings, client, limit=MAX_BATCH)
        for k in grand:
            grand[k] += totals.get(k, 0)
        if not totals.get("scored"):
            break
    return (f"{grand['scored']} leads scored: {grand['out_of_area']} out of area, "
            f"{grand['unknown']} location unknown, {grand['websites']} websites written; "
            f"{grand['failed']} failed.")
