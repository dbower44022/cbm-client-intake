"""The Stale side exit (build plan § 1.2, § 6).

A lead still being worked — Unqualified or Qualified, no reason set — whose
last sign of life is older than ``PROSPECT_STALE_DAYS`` stops being worked by
``Stale`` (ruling 44: a lead that never responds stays Unqualified until this
sweep). Its last sign of life is the latest of: the status change (or the
lead's creation), and every touch's planned, sent, delivered, returned,
scanned and done time — so a scan, which changes no status (ruling 51), still
keeps a lead fresh. A lead with a Planned touch is in a running campaign
(ruling 10) and never goes stale. A converted or disqualified lead is not
worked, so the sweep never reads it.

Leads are never deleted; Stale is the re-entry point if a second-card
campaign is ever designed. A side exit is never written over another.

The worker runs the sweep (every ``PROSPECT_STALE_SWEEP_SECONDS``, default
nightly); ``/setup`` → Operations runs it as a dry run, then applies that exact
plan. The plan text is deterministic — the ids in order, no clock — so the
apply's re-derived fingerprint matches unless the CRM moved.

All reads and writes run under the org-wide API client: it is a machine sweep.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core.config import Settings
from core.espo import EspoApi, EspoError

from . import config as cfg
from . import service

log = logging.getLogger("cbm_intake.campaigns.stale")

_PAGE = 200
STALE_STATUSES = cfg.LEAD_OPEN_STATUSES
_TOUCH_TIMES = ("plannedAt", "sentAt", "deliveredAt", "returnedAt", "firstScannedAt", "doneAt")


def _parse(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def last_activity(prospect: dict[str, Any], touches: list[dict[str, Any]]) -> Optional[datetime]:
    stamps = [_parse(prospect.get("leadStatusChangedAt")), _parse(prospect.get("createdAt"))]
    for t in touches:
        stamps.extend(_parse(t.get(k)) for k in _TOUCH_TIMES)
    stamps = [s for s in stamps if s is not None]
    return max(stamps) if stamps else None


async def _touches_by_prospect(client: EspoApi) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    offset = 0
    while True:
        page = await client.list(cfg.TOUCH, select="id,prospectId,touchStatus," + ",".join(_TOUCH_TIMES),
                                 max_size=_PAGE, offset=offset, order_by="createdAt", order="asc")
        batch = page.get("list", [])
        for t in batch:
            if t.get("prospectId"):
                out.setdefault(t["prospectId"], []).append(t)
        if len(batch) < _PAGE or offset >= 50000:
            break
        offset += _PAGE
    return out


async def plan_stale(client: EspoApi, days: int, *, now: Optional[datetime] = None) -> list[dict[str, Any]]:
    """The leads the sweep would stop, oldest activity first."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(0, int(days)))
    prospects = await service._page_all(
        client, cfg.PROSPECT, select="id,name,businessName,leadStatus,sideExit,leadStatusChangedAt,createdAt",
        where=[{"type": "in", "attribute": "leadStatus", "value": list(STALE_STATUSES)},
               {"type": "isNull", "attribute": "sideExit"}],
        order_by="createdAt", order="asc", limit=50000,
    )
    touches = await _touches_by_prospect(client)
    out = []
    for p in prospects:
        if p.get("sideExit") or p.get("leadStatus") not in STALE_STATUSES:
            continue
        mine = touches.get(p["id"], [])
        if any(t.get("touchStatus") == cfg.TOUCH_PLANNED for t in mine):
            continue
        last = last_activity(p, mine)
        if last is not None and last >= cutoff:
            continue
        out.append({"id": p["id"], "name": p.get("businessName") or p.get("name") or p["id"],
                    "stage": p.get("leadStatus"), "lastActivity": last.strftime("%Y-%m-%d") if last else "never"})
    out.sort(key=lambda r: (r["lastActivity"], r["id"]))
    return out


def plan_text(plan: list[dict[str, Any]], days: int) -> str:
    """The plan as the Operations page shows it — and fingerprints it."""
    head = (f"Leads at Unqualified or Qualified with no touch for {days} days "
            f"and no planned touch: {len(plan)} would stop being worked as Stale.")
    lines = [f"  {r['id']}  {r['stage']:<11}  last activity {r['lastActivity']}  {r['name']}" for r in plan]
    return "\n".join([head, *lines]) if lines else head


async def apply_stale(client: EspoApi, plan: list[dict[str, Any]], days: int) -> dict[str, int]:
    """Stop each planned lead as Stale. Re-reads each lead first: one that has
    moved or stopped meanwhile is skipped, never overwritten."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    totals = {"stale": 0, "skipped": 0, "errors": 0}
    for row in plan:
        try:
            current = await client.get(cfg.PROSPECT, row["id"], select="id,leadStatus,sideExit")
            if not current or current.get("sideExit") or current.get("leadStatus") not in STALE_STATUSES:
                totals["skipped"] += 1
                continue
            await client.update(cfg.PROSPECT, row["id"], {
                "sideExit": cfg.EXIT_STALE, "sideExitAt": now,
                "sideExitNote": f"No touch for {days} days (the Stale sweep, PROSPECT_STALE_DAYS)."})
            totals["stale"] += 1
        except EspoError as exc:
            totals["errors"] += 1
            log.warning("stale sweep: %s not moved: %s", row.get("id"), exc)
    return totals


def _client(settings: Settings) -> Optional[EspoApi]:
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    from core.espo import EspoClient
    return EspoClient(settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds)


async def _available(client: EspoApi) -> bool:
    return (await service.availability(client))["available"]


async def run_stale_sweep(settings: Settings, *, client: Optional[EspoApi] = None) -> dict[str, int]:
    """The worker's pass. Best-effort, never raises."""
    totals = {"stale": 0, "skipped": 0, "errors": 0, "planned": 0}
    if not settings.campaigns_enabled:
        return totals
    client = client or _client(settings)
    if client is None:
        return totals
    try:
        if not await _available(client):
            return totals
        plan = await plan_stale(client, settings.prospect_stale_days)
        totals["planned"] = len(plan)
        totals.update(await apply_stale(client, plan, settings.prospect_stale_days))
    except Exception as exc:  # noqa: BLE001 — a sweep failure is a log line, never a crash
        totals["errors"] += 1
        log.warning("stale sweep failed: %s", exc)
    log.info("lead stale sweep: %s", totals)
    return totals


# --- the Operations job (dry run, then apply that exact plan) ----------------------------

async def job_dry_run(settings: Settings) -> str:
    client = _client(settings)
    if client is None:
        raise RuntimeError("This deployment has no CRM credential (dry-run mode or no API key).")
    if not await _available(client):
        raise RuntimeError("This CRM does not carry the lead entities yet.")
    return plan_text(await plan_stale(client, settings.prospect_stale_days), settings.prospect_stale_days)


async def job_apply(settings: Settings) -> str:
    client = _client(settings)
    if client is None:
        raise RuntimeError("This deployment has no CRM credential (dry-run mode or no API key).")
    plan = await plan_stale(client, settings.prospect_stale_days)
    totals = await apply_stale(client, plan, settings.prospect_stale_days)
    return (f"{totals['stale']} leads stopped as Stale; {totals['skipped']} skipped "
            f"(moved meanwhile); {totals['errors']} errors.")
