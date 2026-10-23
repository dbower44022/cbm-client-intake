"""Lead enrichment's endpoints (build plan phase 2 § 4.4) — ``/enrichment/api``.

Two gates, chosen by what the request is about:

* **a lead** — Campaign Management's gate (``CAMPAIGNS_ENABLED`` and
  ``CAMPAIGNS_ALLOWED_TEAMS``), because the lead screens live there (ruling 56);
* **a client** — Client Administration's gate (``ASSIGN_ALLOWED_TEAMS``),
  because only that team decides a client's findings (ruling E19). A client is
  named by its engagement; the router resolves the Company through it.

Reads and writes go to the CRM under the org-wide API client after the gate
(``enrichment/runs.py``). Starting a run and every Accept or Reject is
recorded through ``record_action`` as the signed-in user.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from assignments import auth
from assignments.auth import current_user
from assignments.espo_user import client_for
from core.action_log import CAT_RECORD_EDIT, record_action
from core.config import get_settings
from core.espo import EspoError

from . import runs
from .store import EnrichmentStore

log = logging.getLogger("cbm_intake.enrichment.router")

router = APIRouter(prefix="/enrichment/api", tags=["enrichment"])
APP_NAME = "Lead Enrichment"
ACT_RUN_STARTED = "AI Research Started"
ACT_FINDING_ACCEPTED = "Enrichment Finding Accepted"
ACT_FINDING_REJECTED = "Enrichment Finding Rejected"


def _gate(request: Request, target_type: str) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    settings = get_settings()
    if target_type == runs.TARGET_LEAD:
        if not settings.campaigns_enabled:
            raise HTTPException(status_code=404, detail="Marketing Management is switched off.")
        teams, app = settings.campaigns_allowed_teams_list, "Marketing Management"
        ok = auth.is_member(user, teams)
    elif target_type == runs.TARGET_COMPANY:
        teams, app = settings.assign_allowed_teams_list, "Client Administration"
        ok = auth.is_member(user, teams, settings.assign_allowed_roles_list)
    else:
        raise HTTPException(status_code=400, detail="Unknown record type.")
    if not ok:
        raise HTTPException(status_code=403, detail=(
            f"Your account is not authorized to do this in {app} "
            f"(requires the {', '.join(teams) or 'admin'} team)."))
    return user


def _client():
    client = runs.api_client(get_settings())
    if client is None:
        raise HTTPException(status_code=503, detail="This deployment has no CRM credential.")
    return client


def _store(request: Request) -> Optional[EnrichmentStore]:
    return getattr(request.app.state, "enrichment_store", None)


def _need_store(request: Request) -> EnrichmentStore:
    store = _store(request)
    if store is None:
        raise HTTPException(status_code=503, detail="AI research needs the application database.")
    return store


def _actor(user: dict) -> str:
    return user.get("name") or user.get("userName") or "staff"


async def _company_of_engagement(client: Any, engagement_id: str) -> dict[str, str]:
    """The client's Company: the engagement's own link, else its client
    profile's (intake-created engagements carry it only there)."""
    try:
        eng = await client.get("CEngagement", engagement_id,
                               select="id,clientOrganizationId,clientOrganizationName,engagementClientId")
        cid, cname = eng.get("clientOrganizationId"), eng.get("clientOrganizationName")
        if not cid and eng.get("engagementClientId"):
            prof = await client.get("CClientProfile", eng["engagementClientId"],
                                    select="linkedCompanyId,linkedCompanyName")
            cid, cname = prof.get("linkedCompanyId"), prof.get("linkedCompanyName")
    except EspoError as exc:
        raise HTTPException(status_code=502, detail=f"Reading the engagement failed: {exc}") from exc
    if not cid:
        raise HTTPException(status_code=400, detail="This engagement has no company to research.")
    return {"id": cid, "name": cname or ""}


async def _panel(request: Request, client: Any, *, target_type: str, target_id: str) -> dict[str, Any]:
    settings = get_settings()
    out: dict[str, Any] = {"available": await runs.available(client), "ready": runs.readiness(settings) is None,
                           "reason": runs.readiness(settings) or "", "summary": None, "findings": [],
                           "pending": 0, "last": None}
    if not out["available"]:
        out["reason"] = "This CRM does not have the Enrichment Finding record type yet."
        return out
    kw = {"prospect_id": target_id} if target_type == runs.TARGET_LEAD else {"company_id": target_id}
    out.update(runs.present(await runs.existing_findings(client, **kw)))
    store = _store(request)
    if store is not None:
        out["pending"] = await store.target_pending(target_id)
        last = await store.target_last(target_id)
        if last:
            out["last"] = {"status": last["status"], "error": last.get("error"), "cost": round(last["cost"], 3),
                           "at": last["finished_at"].isoformat() if last.get("finished_at") else None}
    return out


@router.get("/status")
async def status(request: Request, targetType: str = runs.TARGET_LEAD) -> dict:
    """Whether AI research can start here — for a screen deciding whether to
    offer it at all (the feature ships dark)."""
    _gate(request, targetType)
    settings = get_settings()
    client = runs.api_client(settings)
    available = bool(client) and await runs.available(client)
    return {"available": available, "ready": available and runs.readiness(settings) is None,
            "reason": runs.readiness(settings) or ("" if available else "This CRM does not have the Enrichment Finding record type yet.")}


@router.get("/lead/{lead_id}")
async def lead_panel(lead_id: str, request: Request) -> dict:
    _gate(request, runs.TARGET_LEAD)
    return await _panel(request, _client(), target_type=runs.TARGET_LEAD, target_id=lead_id)


@router.get("/engagement/{engagement_id}")
async def engagement_panel(engagement_id: str, request: Request) -> dict:
    _gate(request, runs.TARGET_COMPANY)
    client = _client()
    company = await _company_of_engagement(client, engagement_id)
    out = await _panel(request, client, target_type=runs.TARGET_COMPANY, target_id=company["id"])
    out["company"] = company
    return out


class RunIn(BaseModel):
    targetType: str
    ids: list[str] = Field(default_factory=list, max_length=5000)
    engagementId: str = ""
    estimate: Optional[float] = None


async def _targets(body: RunIn, client: Any) -> tuple[list[str], str]:
    if body.targetType == runs.TARGET_COMPANY:
        if not body.engagementId:
            raise HTTPException(status_code=400, detail="Name the engagement.")
        company = await _company_of_engagement(client, body.engagementId)
        return [company["id"]], body.engagementId
    return list(body.ids), ""


@router.post("/estimate")
async def estimate(body: RunIn, request: Request) -> dict:
    _gate(request, body.targetType)
    ids, _ = await _targets(body, _client())
    out = await runs.estimate(_need_store(request), get_settings(), len(ids))
    out["reason"] = runs.readiness(get_settings()) or ""
    return out


@router.post("/start")
async def start(body: RunIn, request: Request) -> dict:
    user = _gate(request, body.targetType)
    client = _client()
    if not await runs.available(client):
        raise HTTPException(status_code=409, detail="This CRM does not have the Enrichment Finding record type yet.")
    ids, engagement_id = await _targets(body, client)
    try:
        out = await runs.start_run(_need_store(request), get_settings(), target_type=body.targetType,
                                   target_ids=ids, started_by=_actor(user), confirm_estimate=body.estimate)
    except runs.EnrichmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    parent_type, parent_id = (("CEngagement", engagement_id) if engagement_id
                              else ("CProspect", ids[0]) if len(ids) == 1 else ("", ""))
    await record_action(
        client_for(get_settings(), user), app=APP_NAME, category=CAT_RECORD_EDIT, action=ACT_RUN_STARTED,
        parent_type=parent_type, parent_id=parent_id,
        summary=f"Started AI research on {out['records']} record(s), estimated ${out['estimate']:.2f}",
        actor_id=user.get("id", ""), actor_name=_actor(user),
        details={"run": out["run"], "records": out["records"], "estimate": out["estimate"]})
    return out


@router.get("/run/{run_id}")
async def run_status(run_id: str, request: Request) -> dict:
    if not current_user(request):
        raise HTTPException(status_code=401, detail="Not authenticated.")
    run = await _need_store(request).get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="No such run.")
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in run.items()}


class DecideIn(BaseModel):
    targetType: str
    recordId: str          # the lead's id, or the engagement's id for a client
    findingId: str
    decision: str          # Accepted | Rejected


@router.post("/decide")
async def decide(body: DecideIn, request: Request) -> dict:
    user = _gate(request, body.targetType)
    client = _client()
    if body.targetType == runs.TARGET_COMPANY:
        target_id = (await _company_of_engagement(client, body.recordId))["id"]
        parent_type = "CEngagement"
    else:
        target_id, parent_type = body.recordId, "CProspect"
    try:
        out = await runs.decide(client, body.findingId, body.decision, actor=_actor(user),
                                target_type=body.targetType, target_id=target_id)
    except runs.EnrichmentError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except EspoError as exc:
        raise HTTPException(status_code=502, detail=f"The CRM refused it: {exc}") from exc
    await record_action(
        client_for(get_settings(), user), app=APP_NAME, category=CAT_RECORD_EDIT,
        action=ACT_FINDING_ACCEPTED if body.decision == runs.ST_ACCEPTED else ACT_FINDING_REJECTED,
        parent_type=parent_type, parent_id=body.recordId,
        summary=f"{body.decision} an enrichment finding" + (f": {out['note']}" if out.get("note") else ""),
        actor_id=user.get("id", ""), actor_name=_actor(user), details={"finding": body.findingId})
    return out
