"""Campaign Management — the staff API at ``/campaigns/api`` (build plan § 3.8).

Team-gated per request on ``CAMPAIGNS_ALLOWED_TEAMS`` (the Marketing Admin Team,
CM-1; administrators always pass) and on ``CAMPAIGNS_ENABLED`` (404 while off —
read per request, so a /setup change needs no restart). Reads and writes on a
campaign run AS the signed-in user; aggregates and the import's Company and
Contact writes run under the org-wide API client (ruling 33). Every mutation is
recorded through ``record_action`` here, at the router, which has the actor.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
import re
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from assignments import auth
from assignments.auth import current_user, is_member
from assignments.espo_user import client_for
from core.action_log import CAT_ASSIGNMENT, CAT_RECORD_EDIT, CAT_STATUS, record_action
from core.admin_client import admin_client_factory
from core.branding import abbr
from core.config import Settings, get_settings
from core.espo import EspoClient, EspoError, forbidden_hint, is_forbidden, validation_failure
from core.postal import estimated_cost
from core.qr import qr_png, qr_svg
from enrichment import runs as enrichment_runs
from forms import SPECS_BY_SLUG

from . import config as cfg
from . import audience, calls, email as email_kind, imports, ladder, leadcode, leads, postcard, reporting, review, service, sms
from . import import_templates as tpl
from . import ready_made, strip as strip_mod
from .store import BatchBusy
from .conversion import CompanyConflict, ConversionRefused, Details, can_convert, convert_lead
from .reporting import summarize_responses  # noqa: F401 — re-exported
from .public import destination_path
from .service import CampaignError

log = logging.getLogger("cbm_intake.campaigns")

api_router = APIRouter(prefix="/campaigns/api", tags=["campaigns"])

APP_CAMPAIGNS = "Marketing Management"


# --- the gate ------------------------------------------------------------------------

def _require_user(request: Request) -> dict:
    settings = get_settings()
    if not settings.campaigns_enabled:
        raise HTTPException(status_code=404, detail="Marketing Management is switched off.")
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    teams = settings.campaigns_allowed_teams_list
    if not is_member(user, teams):
        raise HTTPException(
            status_code=403,
            detail=(f"Your account is not authorized to use Marketing Management "
                    f"(requires the {', '.join(teams) or 'admin'} team)."),
        )
    return user


def _require_calls(settings: Settings) -> None:
    if not settings.campaigns_calls:
        raise HTTPException(status_code=404, detail="Campaign calls are switched off (CAMPAIGNS_CALLS at /setup).")


def _require_email(settings: Settings) -> None:
    if not settings.campaigns_email:
        raise HTTPException(status_code=404, detail="Campaign emails are switched off (CAMPAIGNS_EMAIL at /setup).")


def _require_sms(settings: Settings) -> None:
    if not settings.campaigns_sms:
        raise HTTPException(status_code=404, detail="Campaign texts are switched off (CAMPAIGNS_SMS at /setup).")


def _require_caller(request: Request) -> dict:
    """The Calls screen's gate (ruling 36): signed in, Campaign Management and
    its calls switched on. The team check is per campaign — the members of the
    teams it names — so it happens in ``calls``, not here."""
    settings = get_settings()
    if not settings.campaigns_enabled:
        raise HTTPException(status_code=404, detail="Marketing Management is switched off.")
    _require_calls(settings)
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user


def _crm_failure(request: Request, exc: EspoError, message: str) -> HTTPException:
    """A CRM error as something a staff member can act on: a dead session is
    cleared and a 401; a 403 names the missing grant; a rejected field is a 400;
    anything else is a 502 with the step named."""
    log.warning("campaigns %s: %s", message, exc)
    if auth.session_expired(exc):
        return HTTPException(status_code=401, detail="Your session has expired — please sign in again.")
    if is_forbidden(exc):
        return HTTPException(
            status_code=403,
            detail=(f"{message}: your CRM role is missing {hint} — ask {abbr()} staff to grant it."
                    if (hint := forbidden_hint(exc)) else
                    f"{message}: your CRM role does not allow that — ask {abbr()} staff to grant it."),
        )
    invalid = validation_failure(exc)
    if invalid:
        return HTTPException(status_code=400, detail=invalid)
    return HTTPException(status_code=502, detail=f"{message}: the CRM could not complete the request.")


def _system_client(settings: Settings) -> Optional[EspoClient]:
    """The org-wide API client, or None in dry-run / keyless deploys."""
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    return EspoClient(settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds)


def _api_client(settings: Settings, request: Request) -> EspoClient:
    client = _system_client(settings)
    if client is None:
        raise HTTPException(status_code=503, detail="This deployment has no CRM credential for aggregate reads.")
    return client


def _store(request: Request):
    store = getattr(request.app.state, "campaign_store", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="Campaign links and imports need the application database (DATABASE_URL), which is not configured.")
    return store


def _actor(request: Request):
    user = _require_user(request)
    return user, client_for(get_settings(), user)


def _base_url(request: Request, settings: Settings) -> str:
    return (settings.app_base_url or "").rstrip("/") or str(request.base_url).rstrip("/")


async def _campaign_or_404(request: Request, client, campaign_id: str) -> dict[str, Any]:
    try:
        row = await service.get_campaign(client, campaign_id)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not read the campaign")
    if not row or not row.get("id"):
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return row


# --- session and fields ----------------------------------------------------------------

@api_router.get("/session")
async def session(request: Request) -> dict[str, Any]:
    settings = get_settings()
    if not settings.campaigns_enabled:
        raise HTTPException(status_code=404, detail="Marketing Management is switched off.")
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    if not is_member(user, settings.campaigns_allowed_teams_list):
        # A caller from another team (ruling 114): the page shows the Calls tab
        # alone. This answer unlocks nothing — every other endpoint keeps its
        # team gate, and the call list is checked per campaign (ruling 36).
        return {
            "name": user.get("name"), "userName": user.get("userName"), "userId": user.get("userId"),
            "isAdmin": bool(user.get("isAdmin")),
            "callerOnly": True, "callsOn": settings.campaigns_calls,
        }
    client = client_for(settings, user)
    avail = await service.availability(client)
    return {
        "name": user.get("name"), "userName": user.get("userName"), "userId": user.get("userId"),
        "isAdmin": bool(user.get("isAdmin")), "callerOnly": False,
        "available": avail["available"], "reason": avail["reason"],
        "storeAvailable": getattr(request.app.state, "campaign_store", None) is not None,
        "landingPublic": settings.campaigns_landing_active,
        "postal": {"provider": settings.postal_provider, "testMode": settings.postal_test_mode,
                   "unitCost": settings.postal_unit_cost, "currency": settings.postal_currency},
        "baseUrl": _base_url(request, settings),
        "kindsBuilt": list(cfg.kinds_built(settings.campaigns_calls, settings.campaigns_sms, settings.campaigns_email)),
        "emailOn": settings.campaigns_email,
        "mailingConnected": bool(settings.mailing_client_id and settings.mailing_client_secret),
        "emailStages": list(email_kind.EMAILABLE_STAGES),
        "callsOn": settings.campaigns_calls,
        "smsOn": settings.campaigns_sms,
        "listsOn": settings.campaign_lists,
        # A list's copy in Constant Contact and the email campaign that sends to
        # it (§ 7e.9); needs the lists.
        "listSyncOn": settings.campaign_list_sync and settings.campaign_lists,
        # Every campaign sends to a list; the strip and tabs (§ 7e.9, M8).
        "listsOnlyOn": ready_made.lists_only(settings),
        # The Lists tab redesigned: the list view, Edit and View (§ 7e.14, M11).
        "listScreensOn": settings.campaign_list_screens and settings.campaign_lists,
        # The Constant Contact send report (§ 7e.9, M9).
        "sendReportOn": bool(settings.campaign_send_report),
        "ladderOn": settings.lead_ladder,
        "importTemplatesOn": settings.import_templates,
        "leadOutreachOn": settings.lead_outreach,
        "importSources": list(cfg.IMPORT_SOURCES),
        "levels": list(cfg.LEVELS),
        "sms": {"provider": settings.sms_provider, "hours": settings.sms_send_hours,
                "timezone": settings.sms_timezone, "stages": list(sms.TEXTABLE_STAGES)},
        "callStatuses": list(calls.CALLABLE_STATUSES),
        "callStages": list(calls.CALLABLE_STAGES),
        "formDestinations": [{"slug": s, "title": SPECS_BY_SLUG[s].title}
                             for s in cfg.FORM_DESTINATIONS if s in SPECS_BY_SLUG],
    }


@api_router.get("/fields")
async def fields(request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    try:
        options = await service.field_options(client, calls_on=get_settings().campaigns_calls,
                                              sms_on=get_settings().campaigns_sms,
                                              email_on=get_settings().campaigns_email)
        partners = await service.picker_options(client, cfg.PARTNER_PROFILE)
        funders_on = await service.funders_available(client)
        funders = await service.picker_options(client, cfg.SPONSOR_PROFILE) if funders_on else None
        events = await service.picker_options(client, cfg.EVENT)
        # The teams a call campaign may name as its callers (ruling 36). Names
        # only, read under the org-wide key: a marketing role may hold no Team
        # read, and the list is the choice, not anyone's data.
        teams = await service.picker_options(_system_client(get_settings()) or client, "Team")
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load the campaign form")
    return {
        "fields": [f.__dict__ for f in cfg.CAMPAIGN_FIELDS if f.name not in options["missingFields"]],
        "missingFields": options["missingFields"],
        "options": options["campaign"],
        "prospectOptions": options["prospect"],
        "kindsBuilt": options["kindsBuilt"],
        "partnerOptions": partners,       # None: the role may not list partners → read-only
        "fundersAvailable": funders_on,   # ruling 57: no picker until the CRM has the link
        "funderOptions": funders,
        "eventOptions": events,
        "teamOptions": teams,
    }


# --- campaigns -----------------------------------------------------------------------------

async def _decorate(request: Request, rows: list[dict[str, Any]], client) -> list[dict[str, Any]]:
    """The grid's per-campaign counts: links, visits and submissions from the
    store; partners by name (best-effort, per campaign, so a long list reads
    "—" rather than waiting)."""
    store = getattr(request.app.state, "campaign_store", None)
    out = []
    links_by_campaign: dict[str, list[dict[str, Any]]] = {}
    if store is not None:
        for row in rows[:200]:
            links_by_campaign[row["id"]] = await store.list_links(row["id"])
        all_links = [l for ls in links_by_campaign.values() for l in ls]
        visits = await store.visit_counts([l["id"] for l in all_links])
        subs = await store.submissions_by_link([l["token"] for l in all_links])
    else:
        visits, subs = {}, {}
    related = await _grid_relations(client, rows) if ready_made.lists_only(get_settings()) else None
    for row in rows:
        links = links_by_campaign.get(row["id"], [])
        v = sum(visits.get(l["id"], {}).get("visits", 0) for l in links)
        s = sum(sum(subs.get(l["token"], {}).values()) for l in links)
        extra: dict[str, Any] = {}
        if related is not None:
            # Ruling 101's grid: every row filled, whatever the count.
            extra = {**related.get(row["id"], {}), "stage": strip_mod.stage_of(row.get("campaignStatus")),
                     "reached": row.get("pieceCount")}
            partners = extra.pop("partners", None)
        else:
            partners = await service.related_names(client, row["id"], cfg.LINK_PARTNERS) if len(rows) <= 60 else None
        out.append({**row, "links": len(links), "visits": v, "submissions": s,
                    "partners": partners, "manualMoves": service.manual_moves(row), **extra})
    return out


#: Related reads the grid runs at once (lists only).
GRID_CONCURRENCY = 8


async def _grid_relations(client, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Partners, funders and events for every campaign on the grid (ruling
    101), up to 200 rows. The CRM returns a campaign's relationships only one
    campaign at a time (no field carries them on the list read — checked on
    crm-test 10-27-26), so the reads run ``GRID_CONCURRENCY`` at once."""
    import asyncio

    funders_on = await service.funders_available(client)
    gate = asyncio.Semaphore(GRID_CONCURRENCY)

    async def one(campaign_id: str, link: str):
        async with gate:
            return await service.related_names(client, campaign_id, link)

    out: dict[str, dict[str, Any]] = {}
    shown = rows[:200]
    links = [cfg.LINK_PARTNERS, cfg.LINK_EVENTS] + ([cfg.LINK_FUNDERS] if funders_on else [])
    results = await asyncio.gather(*(one(r["id"], link) for r in shown for link in links))
    keys = {cfg.LINK_PARTNERS: "partners", cfg.LINK_EVENTS: "events", cfg.LINK_FUNDERS: "funders"}
    it = iter(results)
    for r in shown:
        out[r["id"]] = {keys[link]: next(it) for link in links}
        if not funders_on:
            out[r["id"]]["funders"] = None
    return out


@api_router.get("/campaigns")
async def list_campaigns(request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    try:
        rows = await service.list_campaigns(client)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not list campaigns")
    return {"campaigns": await _decorate(request, rows, client)}


class CampaignIn(BaseModel):
    changes: dict[str, Any] = Field(default_factory=dict)
    partnerIds: Optional[list[str]] = None
    funderIds: Optional[list[str]] = None
    eventIds: Optional[list[str]] = None
    teamIds: Optional[list[str]] = None


@api_router.post("/campaigns")
async def create_campaign(body: CampaignIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    settings = get_settings()
    try:
        created = await service.create_campaign(client, body.changes, user_id=user.get("userId", ""),
                                                calls_on=settings.campaigns_calls, sms_on=settings.campaigns_sms,
                                                email_on=settings.campaigns_email)
        moved = await service.set_relations(
            client, created["id"], await _wanted(client, body.partnerIds, body.funderIds, body.eventIds),
            admin_factory=admin_client_factory(settings))
        if body.teamIds is not None and created.get("campaignKind") == cfg.KIND_CALL:
            await service.set_teams(client, created["id"], body.teamIds,
                                    admin_factory=admin_client_factory(settings))
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not create the campaign")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action="Campaign Created",
        parent_type=cfg.CAMPAIGN, parent_id=created["id"],
        summary=f"Created the {created.get('campaignKind') or ''} campaign \"{created.get('name')}\"",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""), details={"relations": moved},
    )
    return {"campaign": created, "relations": moved}


@api_router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    settings = get_settings()
    row = await _campaign_or_404(request, client, campaign_id)
    partners = await service.related_names(client, campaign_id, cfg.LINK_PARTNERS)
    funders = (await service.related_names(client, campaign_id, cfg.LINK_FUNDERS)
               if await service.funders_available(client) else None)
    events = await service.related_names(client, campaign_id, cfg.LINK_EVENTS)
    touches: list[dict[str, Any]] = []
    reader = _system_client(settings) or client
    try:
        touches = await service.campaign_touches(reader, campaign_id)
    except EspoError as exc:
        log.warning("touches of %s unreadable: %s", campaign_id, exc)
    rule = None
    if row.get("selectionRule"):
        try:
            import json
            saved = json.loads(row["selectionRule"])
            rule = (calls.normalise_rule(saved) if row.get("campaignKind") == cfg.KIND_CALL
                    else sms.normalise_rule(saved) if row.get("campaignKind") == cfg.KIND_SMS
                    else email_kind.normalise_rule(saved) if row.get("campaignKind") == cfg.KIND_EMAIL
                    else postcard.normalise_rule(saved))
        except Exception:  # noqa: BLE001
            rule = None
    caller_teams = None
    caller_team_ids = None
    if row.get("campaignKind") == cfg.KIND_CALL:
        # The teams named on the campaign decide who calls (ruling 36); a whole
        # read carries them (the field select does not).
        try:
            whole = await client.get(cfg.CAMPAIGN, campaign_id)
            caller_teams = calls.campaign_team_names(whole, settings.campaigns_allowed_teams_list)
            caller_team_ids = list(whole.get("teamsIds") or [])
        except EspoError as exc:
            log.warning("teams of %s unreadable: %s", campaign_id, exc)
    sms_check = None
    if row.get("campaignKind") == cfg.KIND_SMS:
        # The wording is not in the field select (a CRM without ruling 39's
        # field would refuse it); a whole read carries it when it exists.
        try:
            whole = await client.get(cfg.CAMPAIGN, campaign_id)
            row = {**row, "smsMessage": (whole or {}).get("smsMessage") or ""}
            sms_check = {**sms.check_message(row["smsMessage"]),
                         "fieldAvailable": await sms.message_field_available(client)}
        except EspoError as exc:
            log.warning("text message of %s unreadable: %s", campaign_id, exc)
    email_copy = None
    if row.get("campaignKind") == cfg.KIND_EMAIL and _copy_mode(settings):
        email_copy = await _email_copy(request, settings, campaign_id)
    strip = None
    if ready_made.lists_only(settings):
        strip = await _strip(request, user, row, sms_check)
    return {
        "listsOnly": ready_made.lists_only(settings), "strip": strip,
        "campaign": row, "partners": partners, "funders": funders, "events": events, "callerTeams": caller_teams,
        "smsCheck": sms_check, "emailCopy": email_copy,
        "callerTeamIds": caller_team_ids,
        "touches": touches, "touchSummary": service.touch_summary(touches),
        "callBreakdown": reporting.touch_breakdown(touches),
        "rule": rule or (calls.DEFAULT_RULE if row.get("campaignKind") == cfg.KIND_CALL
                         else sms.DEFAULT_RULE if row.get("campaignKind") == cfg.KIND_SMS
                         else email_kind.DEFAULT_RULE if row.get("campaignKind") == cfg.KIND_EMAIL
                         else postcard.DEFAULT_RULE),
        "manualMoves": service.manual_moves(row),
        "estimatedCost": estimated_cost(settings, service.touch_summary(touches)["planned"]),
        "currency": settings.postal_currency,
    }


async def _adopt(request: Request, user: dict, row: dict[str, Any]) -> Optional[str]:
    """Lists only: a campaign built by a rule box carries on with its kind's
    ready-made list (decision 1 at the M8 plan). Best-effort."""
    store = getattr(request.app.state, "campaign_store", None)
    try:
        return await ready_made.adopt(store, row, actor=user.get("name") or user.get("userName") or "")
    except Exception as exc:  # noqa: BLE001 — the page still opens
        log.warning("ready-made list for %s not given: %s", row.get("id"), exc)
        return None


async def _strip(request: Request, user: dict, row: dict[str, Any],
                 sms_check: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The stage strip: the campaign's list by name, and what its content lacks."""
    await _adopt(request, user, row)
    list_row, _chosen = await _campaign_list(request, row["id"])
    problem = ""
    if row.get("campaignKind") == cfg.KIND_SMS and sms_check and sms_check.get("problems"):
        problem = sms_check["problems"][0]
    return strip_mod.strip(row, list_name=(list_row or {}).get("name") or "", content_problem=problem)


def _copy_mode(settings: Settings) -> bool:
    """An email campaign sends to its list's copy (§ 7e.9): both switches on."""
    return bool(settings.campaign_list_sync and settings.campaign_lists)


async def _campaign_list(request: Request, campaign_id: str) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """The campaign's chosen list row and its audience row (the last build)."""
    store = getattr(request.app.state, "campaign_store", None)
    if store is None:
        return None, None
    chosen = await store.get_campaign_audience(campaign_id)
    if not chosen:
        return None, None
    return await store.get_list(chosen["list_id"]), chosen


async def _email_copy(request: Request, settings: Settings, campaign_id: str) -> dict[str, Any]:
    """What the email campaign's strip needs: its list, the copy's state, the
    picked email."""
    api = _api_client(settings, request)
    row, chosen = await _campaign_list(request, campaign_id)
    available = await email_kind.vendor_email_available(api)
    picked = ""
    if available:
        try:
            picked = (await api.get(cfg.CAMPAIGN, campaign_id, select=f"id,{email_kind.VENDOR_EMAIL_FIELD}")
                      or {}).get(email_kind.VENDOR_EMAIL_FIELD) or ""
        except EspoError as exc:
            log.warning("picked email of %s unreadable: %s", campaign_id, exc)
    return {"listId": (row or {}).get("id"), "listName": (row or {}).get("name") or "",
            "copyOn": bool((row or {}).get("cc_sync")), "listActive": (row or {}).get("status") == "active",
            "problem": email_kind.copy_refusal(row), "built": ((chosen or {}).get("build") or None),
            "pickedEmailId": picked, "fieldAvailable": available}


class ChangesIn(BaseModel):
    changes: dict[str, Any] = Field(default_factory=dict)


@api_router.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: str, body: ChangesIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    row = await _campaign_or_404(request, client, campaign_id)
    try:
        updated = await service.update_campaign(client, row, body.changes,
                                                calls_on=get_settings().campaigns_calls,
                                                sms_on=get_settings().campaigns_sms,
                                              email_on=get_settings().campaigns_email)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not save the campaign")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action="Campaign Edited",
        parent_type=cfg.CAMPAIGN, parent_id=campaign_id,
        summary=f"Edited the campaign \"{row.get('name')}\": {', '.join(sorted(body.changes)) or 'nothing'}",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return {"campaign": updated}


# --- the owner (ruling 76) ------------------------------------------------------------

def _owner_reader(request: Request, client):
    """The org-wide client for the team list, else the user's own (dry run)."""
    return _system_client(get_settings()) or client


async def _assignee(request: Request, client, user_id: str) -> dict[str, str]:
    """The team member a lead is assigned to (ruling 108: Marketing Admin Team
    members only) — the same list a campaign's owner comes from."""
    user_id = (user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="Choose the team member the lead goes to.")
    try:
        options = await service.owner_options(_owner_reader(request, client),
                                              get_settings().campaigns_allowed_teams_list)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not list the team members")
    chosen = next((o for o in options if o["id"] == user_id), None)
    if chosen is None:
        raise HTTPException(status_code=400, detail="That person is not an active member of the Marketing "
                                                    "Management team, so a lead cannot be assigned to them.")
    return chosen


@api_router.get("/owner-options")
async def owner_options(request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    try:
        options = await service.owner_options(_owner_reader(request, client),
                                              get_settings().campaigns_allowed_teams_list)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not list the people who may own a campaign")
    return {"options": options}


class OwnerIn(BaseModel):
    userId: str = ""


@api_router.put("/campaigns/{campaign_id}/owner")
async def change_owner(campaign_id: str, body: OwnerIn, request: Request) -> dict[str, Any]:
    """Any member of the Campaign Management team may hand a campaign to
    another active member (ruling 76); the write runs as the signed-in user."""
    user, client = _actor(request)
    row = await _campaign_or_404(request, client, campaign_id)
    try:
        options = await service.owner_options(_owner_reader(request, client),
                                              get_settings().campaigns_allowed_teams_list)
        updated, new_name = await service.change_owner(client, row, body.userId, options)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not change the campaign's owner")
    if new_name is None:
        return {"campaign": row, "changed": False}
    old_name = row.get("assignedUserName") or "nobody"
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action="Campaign Owner Changed",
        parent_type=cfg.CAMPAIGN, parent_id=campaign_id,
        summary=f"Changed the owner of the campaign \"{row.get('name')}\" from {old_name} to {new_name}",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return {"campaign": updated, "changed": True}


class RelationsIn(BaseModel):
    partnerIds: Optional[list[str]] = None
    funderIds: Optional[list[str]] = None
    eventIds: Optional[list[str]] = None


async def _wanted(client, partner_ids, funder_ids, event_ids) -> dict[str, list[str]]:
    """The relationships a save sets. Funders only when the CRM carries the
    link (ruling 57); a page that sent them to a CRM without it loses nothing."""
    wanted = {k: v for k, v in ((cfg.LINK_PARTNERS, partner_ids), (cfg.LINK_EVENTS, event_ids)) if v is not None}
    if funder_ids is not None and await service.funders_available(client):
        wanted[cfg.LINK_FUNDERS] = funder_ids
    return wanted


@api_router.put("/campaigns/{campaign_id}/relations")
async def set_relations(campaign_id: str, body: RelationsIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    settings = get_settings()
    row = await _campaign_or_404(request, client, campaign_id)
    wanted = await _wanted(client, body.partnerIds, body.funderIds, body.eventIds)
    try:
        moved = await service.set_relations(client, campaign_id, wanted, admin_factory=admin_client_factory(settings))
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not change the campaign's partners, funders or events")
    if any(m["added"] or m["removed"] for m in moved.values()):
        await record_action(
            client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action="Campaign Relations Changed",
            parent_type=cfg.CAMPAIGN, parent_id=campaign_id,
            summary=f"Changed the partners, funders or events of \"{row.get('name')}\"",
            actor_id=user.get("userId", ""), actor_name=user.get("name", ""), details=moved,
        )
    return {"relations": moved}


class StatusIn(BaseModel):
    status: str


@api_router.post("/campaigns/{campaign_id}/status")
async def set_status(campaign_id: str, body: StatusIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    row = await _campaign_or_404(request, client, campaign_id)
    try:
        updated = await service.set_status(client, row, body.status)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not change the campaign's status")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_STATUS, action="Campaign Status Changed",
        parent_type=cfg.CAMPAIGN, parent_id=campaign_id,
        summary=f"Moved \"{row.get('name')}\" from {row.get('campaignStatus')} to {body.status}",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return {"campaign": updated}


# --- the postcard kind ------------------------------------------------------------------------

class BuildIn(BaseModel):
    rule: Optional[dict[str, Any]] = None


@api_router.post("/campaigns/{campaign_id}/build")
async def build_list(campaign_id: str, body: BuildIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    settings = get_settings()
    row = await _campaign_or_404(request, client, campaign_id)
    api_client = _api_client(settings, request)
    store = getattr(request.app.state, "campaign_store", None)
    lists_only = ready_made.lists_only(settings)
    if lists_only:
        # Ruling 99: every campaign sends to a list; the rule boxes are gone.
        if body.rule is not None:
            raise HTTPException(status_code=400, detail=(
                "Campaigns send to lists now — choose a list on the campaign's Audience and content tab."))
        if store is None:
            raise HTTPException(status_code=503, detail="Lists need the application database, which is not configured.")
        await _adopt(request, user, row)
    try:
        # A campaign that names a list sends to it (build plan § 7c); None
        # when it names none or the lists are switched off.
        chosen = await audience.audience_for_build(api_client, store, settings, row)
        if lists_only and not chosen:
            raise CampaignError("Choose a list first — on the campaign's Audience and content tab.")
        if row.get("campaignKind") == cfg.KIND_CALL:
            _require_calls(settings)
            result = await calls.build_list(api_client, client, row, body.rule, audience=chosen)
        elif row.get("campaignKind") == cfg.KIND_SMS:
            _require_sms(settings)
            result = await sms.build_list(api_client, client, row, body.rule, audience=chosen)
        elif row.get("campaignKind") == cfg.KIND_EMAIL:
            _require_email(settings)
            if _copy_mode(settings):
                # Doug's two rulings at the M7 plan (10-26-26): an email
                # campaign needs a list, and its build writes no touches.
                result = await email_kind.build_for_copy(api_client, client, row, chosen)
            else:
                result = await email_kind.build_list(api_client, client, row, body.rule, audience=chosen)
        else:
            result = await postcard.build_list(api_client, client, row, body.rule, settings, audience=chosen)
        if chosen:
            await store.record_campaign_build(campaign_id, version=chosen["list"]["version"],
                                              build=result["audience"])
    except (CampaignError, audience.AudienceError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not build the list")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action="Campaign List Built",
        parent_type=cfg.CAMPAIGN, parent_id=campaign_id,
        summary=(f"Built the list of \"{row.get('name')}\": {result['pieces']} planned "
                 f"({result['created']} new, {result['cancelled']} dropped)"),
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
        details={"rule": result["rule"], **({"audience": result["audience"]} if result.get("audience") else {})},
    )
    return result


class SignOffIn(BaseModel):
    confirm: str = ""


@api_router.post("/campaigns/{campaign_id}/signoff")
async def sign_off(campaign_id: str, body: SignOffIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    settings = get_settings()
    row = await _campaign_or_404(request, client, campaign_id)
    api_client = _api_client(settings, request)
    try:
        if row.get("campaignKind") == cfg.KIND_CALL:
            _require_calls(settings)
            updated = await calls.sign_off(api_client, client, row,
                                           user_name=user.get("name") or user.get("userName") or "")
        elif row.get("campaignKind") == cfg.KIND_EMAIL and _copy_mode(settings):
            _require_email(settings)
            updated = await _sign_off_to_copy(request, settings, api_client, client, row, body.confirm,
                                              user.get("name") or user.get("userName") or "")
        elif row.get("campaignKind") == cfg.KIND_EMAIL:
            _require_email(settings)
            updated = await email_kind.sign_off(api_client, client, row, confirm=body.confirm,
                                                user_name=user.get("name") or user.get("userName") or "",
                                                settings=settings)
        elif row.get("campaignKind") == cfg.KIND_SMS:
            _require_sms(settings)
            updated = await sms.sign_off(api_client, client, row, confirm=body.confirm,
                                         user_name=user.get("name") or user.get("userName") or "")
        else:
            updated = await postcard.sign_off(api_client, client, row, confirm=body.confirm,
                                              user_name=user.get("name") or user.get("userName") or "",
                                              settings=settings)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not sign off the campaign")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_STATUS, action="Campaign Signed Off",
        parent_type=cfg.CAMPAIGN, parent_id=campaign_id,
        summary=(f"Signed off the call list of \"{row.get('name')}\" — it is running"
                 if row.get("campaignKind") == cfg.KIND_CALL else
                 f"Signed off the text message of \"{row.get('name')}\" to {updated.get('pieceCount')} people"
                 if row.get("campaignKind") == cfg.KIND_SMS else
                 (f"Signed off \"{row.get('name')}\": its list's copy in Constant Contact synced, "
                  f"{updated.get('pieceCount')} people on it" if _copy_mode(settings) else
                  f"Signed off the email list of \"{row.get('name')}\": {updated.get('pieceCount')} people")
                 if row.get("campaignKind") == cfg.KIND_EMAIL else
                 f"Signed off \"{row.get('name')}\": {updated.get('pieceCount')} pieces, "
                 f"estimated {updated.get('estimatedCost')} {updated.get('estimatedCostCurrency')}"),
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return {"campaign": updated}


@api_router.get("/campaigns/{campaign_id}/touches/{touch_id}/preview", response_class=Response)
async def touch_preview(campaign_id: str, touch_id: str, request: Request) -> Response:
    """The dry-run artefact: what the card would carry — the business name, the
    address as mailed and the QR of its own address. HTML, for a browser."""
    user, client = _actor(request)
    settings = get_settings()
    reader = _system_client(settings) or client
    try:
        touch = await reader.get(cfg.TOUCH, touch_id, select=cfg.TOUCH_SELECT)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not read the touch")
    if not touch or touch.get("outreachCampaignId") != campaign_id:
        raise HTTPException(status_code=404, detail="Touch not found.")
    store = _store(request)
    link = await store.landing_link(campaign_id)
    scan = touch.get("scanToken") or ""
    base = _base_url(request, settings)
    url = f"{base}/c/{link['token']}/{scan}" if link and scan else ""
    from html import escape
    svg = qr_svg(url) if url else ""
    name = escape(touch.get("prospectName") or touch.get("companyName") or touch.get("name") or "")
    address = escape(touch.get("mailedAddress") or "").replace("\n", "<br>")
    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Postcard preview</title>
<style>body{{font-family:system-ui,sans-serif;background:#eee;margin:0;padding:2rem}}
.card{{background:#fff;width:6in;height:4in;margin:0 auto;display:grid;grid-template-columns:1fr 2in;border:1px solid #bbb;box-shadow:0 4px 16px rgba(0,0,0,.15)}}
.msg{{padding:1.2rem;font-size:1rem}} .addr{{padding:1.2rem;font-size:.9rem;white-space:pre-line;border-left:1px dashed #bbb}}
.qr svg{{width:1.6in;height:1.6in}} .meta{{text-align:center;color:#555;font-size:.8rem;margin-top:1rem}}</style></head>
<body><div class="card"><div class="msg"><h2>Preview — {escape(settings.postal_provider)}{' (test mode)' if settings.postal_test_mode else ''}</h2>
<p>Scan the code to see what we have for <strong>{name}</strong> and tell us how we can help.</p>
<div class="qr">{svg}</div><p><small>{escape(url)}</small></p></div>
<div class="addr"><strong>{name}</strong><br>{address}</div></div>
<p class="meta">Touch {escape(touch_id)} · status {escape(touch.get('touchStatus') or '')} · piece {escape(touch.get('vendorPieceId') or '—')}</p>
</body></html>"""
    return Response(html, media_type="text/html", headers={"Cache-Control": "no-store"})


@api_router.post("/campaigns/{campaign_id}/touches/{touch_id}/simulate")
async def simulate_event(campaign_id: str, touch_id: str, body: StatusIn, request: Request) -> dict[str, Any]:
    """Dry run only: post the vendor's delivered or returned event for one piece
    without a vendor — the live-verification step 9 of build plan § 7."""
    user, client = _actor(request)
    settings = get_settings()
    api_client = _api_client(settings, request)
    kind = body.status.lower()
    if kind in ("stop", "text-delivered"):
        return await _simulate_text(campaign_id, touch_id, kind, request, user, client, api_client, settings)
    if settings.postal_provider != "dryrun":
        raise HTTPException(status_code=400, detail="Simulated events are a dry-run tool; a real vendor posts its own.")
    try:
        touch = await api_client.get(cfg.TOUCH, touch_id, select=cfg.TOUCH_SELECT)
        if not touch or touch.get("outreachCampaignId") != campaign_id or not touch.get("vendorPieceId"):
            raise HTTPException(status_code=404, detail="No mailed piece on this touch.")
        kind = body.status.lower()
        if kind not in ("delivered", "returned"):
            raise HTTPException(status_code=400, detail="The event is 'delivered' or 'returned'.")
        result = await postcard.apply_event(api_client, piece_id=touch["vendorPieceId"], kind=kind,
                                            vendor_status=f"{kind} (simulated)")
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not apply the event")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_STATUS, action="Postcard Event Simulated",
        parent_type=cfg.TOUCH, parent_id=touch_id,
        summary=f"Simulated a {body.status} event on a dry-run piece",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return result


# --- links (§ 3.7) -------------------------------------------------------------------------------

async def _link_rows(request: Request, store, campaign_id: str, client, settings: Settings) -> list[dict[str, Any]]:
    links = await store.list_links(campaign_id)
    visits = await store.visit_counts([l["id"] for l in links])
    subs = await store.submissions_by_link([l["token"] for l in links])
    base = _base_url(request, settings)
    out = []
    for l in links:
        if l["destination_kind"] == cfg.DEST_EVENT and l.get("destination_target"):
            # Refresh the cached slug from the CRM so the public resolve, which
            # never reads the CRM, follows a renamed event.
            try:
                ev = await client.get(cfg.EVENT, l["destination_target"], select="id,slug,name")
                slug = ev.get("slug") if ev else None
                if slug and slug != l.get("destination_slug"):
                    await store.refresh_slug(l["id"], slug)
                    l["destination_slug"] = slug
                l["destinationName"] = ev.get("name") if ev else None
            except EspoError:
                pass
        row = {k: v for k, v in l.items()}
        row["shortUrl"] = f"{base}/c/{l['token']}"
        row["destinationPath"] = destination_path(l, scan_token="CARD" if l["destination_kind"] == cfg.DEST_LANDING else None)
        row["counts"] = {**visits.get(l["id"], {"visits": 0, "late": 0, "scans": 0}),
                         "submissions": subs.get(l["token"], {})}
        out.append(row)
    return out


@api_router.get("/campaigns/{campaign_id}/links")
async def list_links(campaign_id: str, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    settings = get_settings()
    await _campaign_or_404(request, client, campaign_id)
    store = _store(request)
    return {"links": await _link_rows(request, store, campaign_id, client, settings)}


class LinkIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str
    target: Optional[str] = None


def _validate_destination(kind: str, target: Optional[str]) -> tuple[str, Optional[str]]:
    if kind == cfg.DEST_FORM:
        if target not in cfg.FORM_DESTINATIONS or target not in SPECS_BY_SLUG:
            raise HTTPException(status_code=400, detail="Choose one of the five public forms.")
        return kind, target
    if kind == cfg.DEST_PROGRAMME:
        return kind, None
    if kind == cfg.DEST_EVENT:
        if not target:
            raise HTTPException(status_code=400, detail="Choose the event the link opens.")
        return kind, target
    raise HTTPException(status_code=400, detail="A link opens a public form, the programme page or one event.")


@api_router.post("/campaigns/{campaign_id}/links")
async def create_link(campaign_id: str, body: LinkIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    settings = get_settings()
    row = await _campaign_or_404(request, client, campaign_id)
    store = _store(request)
    kind, target = _validate_destination(body.kind, body.target)
    slug = None
    if kind == cfg.DEST_EVENT:
        try:
            ev = await client.get(cfg.EVENT, target, select="id,slug")
            slug = (ev or {}).get("slug")
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not read the event")
    link = await store.create_link(campaign_id=campaign_id, name=body.name.strip(), destination_kind=kind,
                                   destination_target=target, destination_slug=slug,
                                   created_by=user.get("name") or user.get("userName") or "")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action="Campaign Link Created",
        parent_type=cfg.CAMPAIGN, parent_id=campaign_id,
        summary=f"Made the link \"{link['name']}\" ({link['token']}) on \"{row.get('name')}\" → {kind} {target or ''}".strip(),
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return {"link": link, "shortUrl": f"{_base_url(request, settings)}/c/{link['token']}"}


class LinkDestinationIn(BaseModel):
    kind: str
    target: Optional[str] = None


@api_router.put("/campaigns/{campaign_id}/links/{link_id}")
async def correct_link(campaign_id: str, link_id: str, body: LinkDestinationIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    row = await _campaign_or_404(request, client, campaign_id)
    store = _store(request)
    link = await store.get_link(link_id)
    if not link or link["campaign_id"] != campaign_id:
        raise HTTPException(status_code=404, detail="Link not found.")
    if link["destination_kind"] == cfg.DEST_LANDING:
        raise HTTPException(status_code=400, detail="The postcard's landing link always opens the landing page.")
    kind, target = _validate_destination(body.kind, body.target)
    slug = None
    if kind == cfg.DEST_EVENT:
        try:
            ev = await client.get(cfg.EVENT, target, select="id,slug")
            slug = (ev or {}).get("slug")
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not read the event")
    updated = await store.correct_destination(link_id, destination_kind=kind, destination_target=target,
                                              destination_slug=slug, actor=user.get("name") or "")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action="Campaign Link Corrected",
        parent_type=cfg.CAMPAIGN, parent_id=campaign_id,
        summary=(f"Corrected the link \"{link['name']}\" ({link['token']}) on \"{row.get('name')}\": "
                 f"{link['destination_kind']} {link.get('destination_target') or ''} → {kind} {target or ''}"),
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return {"link": updated}


@api_router.post("/campaigns/{campaign_id}/links/{link_id}/retire")
async def retire_link(campaign_id: str, link_id: str, request: Request) -> dict[str, Any]:
    return await _set_link_state(campaign_id, link_id, request, cfg.LINK_RETIRED)


@api_router.post("/campaigns/{campaign_id}/links/{link_id}/reactivate")
async def reactivate_link(campaign_id: str, link_id: str, request: Request) -> dict[str, Any]:
    return await _set_link_state(campaign_id, link_id, request, cfg.LINK_ACTIVE)


async def _set_link_state(campaign_id: str, link_id: str, request: Request, state: str) -> dict[str, Any]:
    user, client = _actor(request)
    row = await _campaign_or_404(request, client, campaign_id)
    store = _store(request)
    link = await store.get_link(link_id)
    if not link or link["campaign_id"] != campaign_id:
        raise HTTPException(status_code=404, detail="Link not found.")
    updated = await store.set_state(link_id, state, user.get("name") or "")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_STATUS,
        action="Campaign Link Retired" if state == cfg.LINK_RETIRED else "Campaign Link Reactivated",
        parent_type=cfg.CAMPAIGN, parent_id=campaign_id,
        summary=f"{'Retired' if state == cfg.LINK_RETIRED else 'Reactivated'} the link \"{link['name']}\" ({link['token']}) on \"{row.get('name')}\"",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return {"link": updated}


@api_router.get("/campaigns/{campaign_id}/links/{link_id}/qr.png")
async def link_qr(campaign_id: str, link_id: str, request: Request) -> Response:
    user, client = _actor(request)
    settings = get_settings()
    store = _store(request)
    link = await store.get_link(link_id)
    if not link or link["campaign_id"] != campaign_id:
        raise HTTPException(status_code=404, detail="Link not found.")
    png = qr_png(f"{_base_url(request, settings)}/c/{link['token']}")
    return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})


# --- responses (CM-9) -----------------------------------------------------------------------------

@api_router.get("/campaigns/{campaign_id}/responses")
async def responses(campaign_id: str, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    await _campaign_or_404(request, client, campaign_id)
    store = _store(request)
    rows = await store.recent_submissions(campaign_id)
    return summarize_responses(rows)


# summarize_responses lives in campaigns/reporting.py (§ 6: one module for every
# number); imported here so the route and older imports keep the name.


# --- prospects (§ 3.8) ------------------------------------------------------------------------------

@api_router.get("/prospects")
async def list_prospects(request: Request) -> dict[str, Any]:
    """One page of leads and the total the filter matches (build plan § 7b):
    the search box ``q``, the filters, ``sort``/``dir``, ``offset``/``limit``.
    ``review=1`` is the Review queue — no reason, oldest first; its ``mode``
    is ``judge`` (Unqualified; the default) or ``contacts`` (Qualified at
    Identified, build plan § 7e.6)."""
    user, client = _actor(request)
    params = dict(request.query_params)
    lq = leads.LeadQuery.from_params(params, review_queue=params.get("review") in ("1", "true"),
                                     me=user.get("userId") or "", mode=str(params.get("mode") or ""))
    try:
        return await leads.search(client, lq)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not list the leads")


@api_router.get("/prospects/counts")
async def prospect_counts(request: Request) -> dict[str, Any]:
    """The Leads tab's counts across the top (build plan § 7e.4): Unqualified,
    Identified, Contactable, Referred, Replied-not-converted, Disqualified, each
    under the current filters and each a filter itself. Off while the ladder is
    switched off."""
    user, client = _actor(request)
    settings = get_settings()
    if not settings.lead_ladder:
        return {"ladder": False}
    lq = leads.LeadQuery.from_params(dict(request.query_params), me=user.get("userId") or "")
    try:
        return await leads.counts(client, lq, me=user.get("userId") or "")
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not count the leads")


class BulkResolveIn(BaseModel):
    query: dict[str, Any] = Field(default_factory=dict)
    review: bool = False


class BulkIn(BaseModel):
    action: str
    note: str = Field(default="", max_length=4000)
    #: Assign to… (§ 7e.4): the team member's User id.
    assignee: str = ""
    items: list[dict[str, Any]] = Field(default_factory=list)


# The three /prospects/<word> routes are declared BEFORE /prospects/{prospect_id},
# or the word is read as an id (a 502 on 10-15-26).
@api_router.post("/prospects/bulk/resolve")
async def bulk_resolve(body: BulkResolveIn, request: Request) -> dict[str, Any]:
    """*Select all n matching*: every lead the filter matches, with the status
    and reason the guard compares, refused above the cap."""
    user, client = _actor(request)
    lq = leads.LeadQuery.from_params(body.query, review_queue=body.review, mode=str(body.query.get("mode") or ""))
    try:
        items = await leads.resolve(client, lq)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not read the matching leads")
    return {"items": items, "count": len(items), "batch": leads.BULK_BATCH}


@api_router.post("/prospects/bulk")
async def bulk_apply(body: BulkIn, request: Request) -> dict[str, Any]:
    """Disqualify or Do Not Contact on one batch of leads; one action-history
    row for the batch, naming every lead it changed."""
    user, client = _actor(request)
    settings = get_settings()
    assignee = None
    if body.action == leads.ACTION_ASSIGN:
        assignee = await _assignee(request, client, body.assignee)
    try:
        result = await leads.apply_bulk(client, _system_client(settings), body.items, body.action,
                                        reviewer=user.get("name") or user.get("userName") or "",
                                        note=body.note, assignee=assignee)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if body.action != leads.ACTION_ASSIGN:
        for d in result["done"]:
            await ladder.after_write(d["id"], client=_system_client(settings), settings=settings,
                                     store=getattr(request.app.state, "campaign_store", None))
    if result["done"] and body.action == leads.ACTION_ASSIGN:
        names = ", ".join(f'"{d["name"]}"' for d in result["done"][:20])
        more = len(result["done"]) - 20
        await record_action(
            client, app=APP_CAMPAIGNS, category=CAT_ASSIGNMENT, action=f"{leads.ASSIGN_LABEL} (bulk)",
            parent_type=cfg.PROSPECT, parent_id=result["done"][0]["id"],
            summary=(f"Assigned {len(result['done'])} leads to {assignee['name']} — {names}"
                     + (f" and {more} more" if more > 0 else "")),
            actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
            details={"assignee": assignee, "done": result["done"], "skipped": result["skipped"],
                     "failed": result["failed"]},
        )
    elif result["done"]:
        label = review.ACTION_LABELS[body.action]
        names = ", ".join(f'"{d["name"]}"' for d in result["done"][:20])
        more = len(result["done"]) - 20
        await record_action(
            client, app=APP_CAMPAIGNS, category=CAT_STATUS, action=f"{label} (bulk)",
            parent_type=cfg.PROSPECT, parent_id=result["done"][0]["id"],
            summary=(f"{label}: {len(result['done'])} leads — {names}" + (f" and {more} more" if more > 0 else "")
                     + (f" — {body.note.strip()}" if body.note.strip() else "")),
            actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
            details={"done": result["done"], "skipped": result["skipped"], "failed": result["failed"]},
        )
    return result


@api_router.get("/prospects/export")
async def export_prospects(request: Request) -> StreamingResponse:
    """The matching leads as a CSV file, the filters the grid holds."""
    user, client = _actor(request)
    lq = leads.LeadQuery.from_params(dict(request.query_params))
    try:
        rows = await leads.export_rows(client, lq)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not export the leads")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return StreamingResponse(rows, media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="leads-{stamp}.csv"'})


# Declared BEFORE /prospects/{prospect_id}, or "imports" is read as an id (a 502 on 10-15-26).
@api_router.get("/prospects/imports")
async def recent_imports(request: Request) -> dict[str, Any]:
    _actor(request)
    store = _store(request)
    rows = await store.recent_batches()
    return {"batches": [{
        "id": b["id"], "name": b["name"], "source": b["door"], "rowCount": b["row_count"],
        "status": b["status"], "createdAt": b["created_at"].isoformat() if b.get("created_at") else None,
        "appliedAt": b["applied_at"].isoformat() if b.get("applied_at") else None,
        "counts": (b.get("plan") or {}).get("counts"), "result": b.get("result"),
        # M4: the preview job, the file and template, the Undo stamp.
        "planStatus": b.get("plan_status"), "fileName": b.get("file_name"),
        "templateName": (b.get("plan") or {}).get("templateName") or "",
        "excluded": len(b.get("excluded_rows") or []),
        "undoneAt": b["undone_at"].isoformat() if b.get("undone_at") else None,
        "undoneBy": b.get("undone_by"), "undoResult": b.get("undo_result"),
    } for b in rows]}


@api_router.get("/prospects/partner-options")
async def prospect_partner_options(request: Request) -> dict[str, Any]:
    """The partners a lead may name as its referrer (the lead page)."""
    user, client = _actor(request)
    try:
        return {"options": await service.partner_options(client)}
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not list the partners")


async def _lead_or_404(request: Request, client, prospect_id: str, *, select: str):
    try:
        row = await client.get(cfg.PROSPECT, prospect_id, select=select)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not read the lead")
    if not row or not row.get("id"):
        raise HTTPException(status_code=404, detail="Lead not found.")
    return row


async def _lead_select(client) -> tuple[str, bool]:
    has_ladder = await leads.ladder_available(client)
    select = cfg.PROSPECT_SELECT + ("," + ladder.LADDER_SELECT if has_ladder else "")
    if await leadcode.available(client):
        select += "," + leadcode.LEAD_FIELD      # the page shows the code and offers New code
    return select, has_ladder


@api_router.get("/prospects/{prospect_id}")
async def get_prospect(prospect_id: str, request: Request) -> dict[str, Any]:
    """One lead with everything its page shows (build plan § 7e.4): the record,
    its touches, the action history and one Activity timeline, the hand-set
    snapshot, and whether this CRM carries the ladder."""
    user, client = _actor(request)
    settings = get_settings()
    select, has_ladder = await _lead_select(client)
    row = await _lead_or_404(request, client, prospect_id, select=select)
    try:
        touches = await service.prospect_touches(client, prospect_id)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not read the lead's touches")
    actions = await service.record_actions(_system_client(settings), prospect_id)
    manual = None
    store = getattr(request.app.state, "campaign_store", None)
    if store is not None and has_ladder and row.get("levelSetAt"):
        try:
            manual = await store.get_level_manual(prospect_id)
        except Exception as exc:  # noqa: BLE001 — the page shows the CRM's who and when regardless
            log.warning("level snapshot for %s not read: %s", prospect_id, exc)
    return {"prospect": row, "touches": touches, "ladder": has_ladder and settings.lead_ladder,
            "activity": leads.activity_rows(touches, actions),
            "manualLevel": ({"level": manual["level"], "facts": manual.get("facts") or [],
                             "setBy": manual.get("set_by")} if manual else None),
            "levels": list(cfg.LEVELS)}


class FactsIn(BaseModel):
    changes: dict[str, Any] = Field(default_factory=dict)


@api_router.patch("/prospects/{prospect_id}/facts")
async def edit_prospect_facts(prospect_id: str, body: FactsIn, request: Request) -> dict[str, Any]:
    """An inline gap filled on the lead's page (§ 7e.4), written as the user;
    placement then runs under the API client."""
    user, client = _actor(request)
    settings = get_settings()
    select, has_ladder = await _lead_select(client)
    lead = await _lead_or_404(request, client, prospect_id, select=select)
    try:
        payload = leads.facts_payload(lead, body.changes, ladder_on=has_ladder)
        updated = await client.update(cfg.PROSPECT, prospect_id, payload)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not save the lead")
    level = await ladder.after_write(prospect_id, client=_system_client(settings), settings=settings,
                                     store=getattr(request.app.state, "campaign_store", None))
    name = lead.get("businessName") or lead.get("name") or prospect_id
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action="Lead Edited",
        parent_type=cfg.PROSPECT, parent_id=prospect_id,
        summary=f"Edited the lead \"{name}\": {', '.join(k for k in sorted(payload) if k != 'name')}",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
        details={"written": {k: v for k, v in payload.items()},
                 "was": {k: lead.get(k) for k in payload}, "level": level},
    )
    return {"prospect": updated, "written": sorted(payload), "level": level}


class LevelIn(BaseModel):
    level: str


@api_router.put("/prospects/{prospect_id}/level")
async def set_prospect_level(prospect_id: str, body: LevelIn, request: Request) -> dict[str, Any]:
    """Set level by hand (the ladder): written as the user with who and when;
    the facts snapshot kept so only a new fact moves it later."""
    user, client = _actor(request)
    settings = get_settings()
    if not settings.lead_ladder:
        raise HTTPException(status_code=404, detail="The qualification ladder is switched off on this deployment.")
    select, has_ladder = await _lead_select(client)
    if not has_ladder:
        raise HTTPException(status_code=409, detail="This CRM does not carry the ladder's lead fields yet.")
    lead = await _lead_or_404(request, client, prospect_id, select=select)
    try:
        result = await ladder.set_by_hand(client, getattr(request.app.state, "campaign_store", None), lead,
                                          body.level, user_id=user.get("userId", ""), user_name=user.get("name", ""))
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not set the level")
    name = lead.get("businessName") or lead.get("name") or prospect_id
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_STATUS, action="Lead Level Set",
        parent_type=cfg.PROSPECT, parent_id=prospect_id,
        summary=f"Set the level of \"{name}\" to {body.level}" + (f" (was {result['was']})" if result["was"] else ""),
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
        details={"written": result["written"], "was": result["was"]},
    )
    return result


class AssigneeIn(BaseModel):
    userId: str = ""


@api_router.put("/prospects/{prospect_id}/assignee")
async def assign_prospect(prospect_id: str, body: AssigneeIn, request: Request) -> dict[str, Any]:
    """Assign the lead to a Marketing Admin Team member, as the user."""
    user, client = _actor(request)
    select, has_ladder = await _lead_select(client)
    if not has_ladder:
        raise HTTPException(status_code=409, detail="This CRM does not carry the lead's Assigned to field yet.")
    lead = await _lead_or_404(request, client, prospect_id, select=select)
    assignee = await _assignee(request, client, body.userId)
    try:
        updated = await client.update(cfg.PROSPECT, prospect_id, leads.assign_payload(lead, assignee))
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not assign the lead")
    name = lead.get("businessName") or lead.get("name") or prospect_id
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_ASSIGNMENT, action=leads.ASSIGN_LABEL,
        parent_type=cfg.PROSPECT, parent_id=prospect_id,
        summary=f"Assigned the lead \"{name}\" to {assignee['name']}"
                + (f" (was {lead.get('assignedUserName')})" if lead.get("assignedUserName") else ""),
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
        details={"assignee": assignee, "was": lead.get("assignedUserId")},
    )
    return {"prospect": updated, "assignee": assignee}


@api_router.post("/prospects/{prospect_id}/code")
async def new_prospect_code(prospect_id: str, request: Request) -> dict[str, Any]:
    """*New code* (build plan § 7d.1; ruling 126): a fresh lead code, written
    under the API key; the old one stops resolving at once. Action-logged with
    the old code's last four characters, never the whole code."""
    user, client = _actor(request)
    settings = get_settings()
    lead = await _lead_or_404(request, client, prospect_id, select="id,name,businessName,leadStatus")
    api_client = _api_client(settings, request)
    try:
        old, new = await leadcode.replace_for_lead(api_client, prospect_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not write the new code")
    name = lead.get("businessName") or lead.get("name") or prospect_id
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action="Lead Code Replaced",
        parent_type=cfg.PROSPECT, parent_id=prospect_id,
        summary=f"New code for the lead \"{name}\" (was {leadcode.code_tail(old)})",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
        details={"was": leadcode.code_tail(old)},
    )
    return {"replaced": bool(old), "code": new}


@api_router.post("/prospects/{prospect_id}/convert")
async def convert_prospect(prospect_id: str, request: Request) -> dict[str, Any]:
    """Convert the lead from its own email or website: the Company and/or
    Contact are made under the API client, like every other conversion."""
    user, client = _actor(request)
    settings = get_settings()
    select, has_ladder = await _lead_select(client)
    lead = await _lead_or_404(request, client, prospect_id, select=select)
    if lead.get("leadStatus") == cfg.LEAD_CONVERTED:
        raise HTTPException(status_code=400, detail="This lead is already Converted.")
    if lead.get("sideExit"):
        raise HTTPException(status_code=400, detail=f"This lead stopped being worked ({lead['sideExit']}); "
                                                    "clear that first if it should be converted.")
    details = Details()
    if not can_convert(lead, details):
        raise HTTPException(status_code=400, detail="A lead converts from an email, or a website for a business. "
                                                    "Fill one in under What we know first.")
    api_client = _api_client(settings, request)
    try:
        done = await convert_lead(api_client, lead, details, campaign_id=None)
    except CompanyConflict as exc:
        raise HTTPException(status_code=409, detail=(
            f"A company named {exc.name} already exists at a different web address ({exc.existing_website}). "
            "Settle which company this is in the CRM, then convert the lead there."))
    except ConversionRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not convert the lead")
    name = lead.get("businessName") or lead.get("name") or prospect_id
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_STATUS, action="Lead Converted",
        parent_type=cfg.PROSPECT, parent_id=prospect_id,
        summary=f"Converted the lead \"{name}\" from its page",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
        details=done.result(),
    )
    return {"converted": done.result()}


async def _claim_write(store, batch_id: str, actor: str, verb: str) -> None:
    """Take the batch's write lease or answer 409 naming who holds it."""
    try:
        await store.claim_write(batch_id, actor)
    except BatchBusy as exc:
        raise HTTPException(
            status_code=409,
            detail=(f"This import is being {verb} by {exc.held_by} right now. Wait for it to finish, "
                    f"then look at the History block before trying again."))


def _require_templates(settings: Settings) -> None:
    if not settings.import_templates:
        raise HTTPException(status_code=404, detail="Import templates are switched off (IMPORT_TEMPLATES at /setup).")


class ImportPlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source: str = cfg.SOURCE_FILING
    #: The CSV path as it has always worked: the file's text.
    text: str = ""
    qualifiedBy: str = ""
    listSource: str = ""
    #: M4 (IMPORT_TEMPLATES): the file as base64 inside the JSON, never
    #: multipart; a sheet for a workbook with several; the template, or a
    #: one-off mapping with the template's settings.
    fileBase64: str = ""
    fileName: str = ""
    sheet: str = ""
    templateId: str = ""
    mapping: Optional[list[dict[str, Any]]] = None
    entersAt: str = ""
    referrerPartnerId: str = ""
    referrerPartnerName: str = ""


async def _template_or_404(store, template_id: str) -> dict[str, Any]:
    row = await store.get_template(template_id)
    if not row:
        raise HTTPException(status_code=404, detail="That import template was not found.")
    return row


async def _plan_settings_from(body: ImportPlanIn, store) -> dict[str, Any]:
    if body.templateId:
        template = await _template_or_404(store, body.templateId)
        return tpl.plan_settings(template, door=template["door"])
    try:
        mapping = tpl.validate_mapping(body.mapping or [])
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    enters_at = body.entersAt.strip() or tpl.ENTERS_UNQUALIFIED
    if enters_at not in tpl.ENTERS_AT:
        raise HTTPException(status_code=400, detail="Enters at is Unqualified or Qualified.")
    return tpl.plan_settings(None, door=body.source, qualified_by=body.qualifiedBy.strip(),
                             list_source=body.listSource.strip(), enters_at=enters_at,
                             referrer_partner_id=body.referrerPartnerId.strip(),
                             referrer_partner_name=body.referrerPartnerName.strip(), mapping=mapping)


def _read_table(body_file: str, name: str, sheet: str, text: str) -> tuple[dict[str, Any], str]:
    """The uploaded file as a table, plus its hash. A workbook with several
    sheets answers 409 with the sheet names; the page asks and posts again."""
    try:
        if body_file:
            data = imports.decode_file(body_file)
            return imports.read_file(name, data, sheet or None), imports.bytes_hash(data)
        return imports.read_file(name or "file.csv", text, None), imports.file_hash(text)
    except imports.SheetChoice as exc:
        raise HTTPException(status_code=409, detail={"sheets": exc.sheets, "message": str(exc)})
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@api_router.post("/prospects/import/plan")
async def import_plan(body: ImportPlanIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    settings = get_settings()
    api_client = None if settings.espo_dry_run else _api_client(settings, request)
    store = _store(request)
    templated = settings.import_templates and (body.fileBase64 or body.templateId or body.mapping is not None)
    if not templated:
        # The CSV path, exactly as before the import tool.
        if api_client is None:
            api_client = _api_client(settings, request)
        try:
            plan = await imports.plan_import(api_client, store, text=body.text, name=body.name.strip(), door=body.source,
                                             qualified_by=body.qualifiedBy.strip(), list_source=body.listSource.strip())
        except CampaignError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not plan the import")
        return plan
    plan_settings = await _plan_settings_from(body, store)
    table, sha = _read_table(body.fileBase64, body.fileName, body.sheet, body.text)
    try:
        batch = await imports.queue_plan(store, name=body.name.strip(), settings=plan_settings, table=table,
                                         file_sha256=sha, file_name=body.fileName or "file.csv",
                                         created_by=user.get("name") or user.get("userName") or "")
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if settings.espo_dry_run:
        # Dev has no worker worth waiting for: plan inline, so the harness and
        # the tests see the finished preview at once.
        inline = getattr(request.app.state, "import_plan_client", None) or client
        try:
            await imports.plan_batch_now(inline, store, batch["id"], ladder=False)
        except CampaignError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not plan the import")
        except Exception as exc:  # noqa: BLE001 — recorded on the batch; the poll shows it
            log.warning("inline import plan failed: %s", exc)
    return imports.plan_payload(await store.get_batch(batch["id"]))


@api_router.get("/prospects/import/{batch_id}")
async def import_status(batch_id: str, request: Request) -> dict[str, Any]:
    """The poll while the worker plans (ruling 123), and the plan once ready."""
    _actor(request)
    store = _store(request)
    batch = await store.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="That import was not found.")
    return imports.plan_payload(batch)


class ExcludedIn(BaseModel):
    hashes: list[str] = Field(default_factory=list, max_length=5000)


@api_router.put("/prospects/import/{batch_id}/excluded")
async def import_excluded(batch_id: str, body: ExcludedIn, request: Request) -> dict[str, Any]:
    """Per-row exclude (ruling 83): the row hashes the apply skips."""
    _actor(request)
    settings = get_settings()
    _require_templates(settings)
    store = _store(request)
    batch = await store.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="That import was not found.")
    if batch.get("status") == "applied":
        raise HTTPException(status_code=400, detail="This import has been applied; nothing more can be excluded.")
    known = {e["hash"] for e in (batch.get("plan") or {}).get("rows") or []}
    hashes = [h for h in body.hashes if h in known]
    await store.set_excluded_rows(batch_id, hashes)
    return {"batchId": batch_id, "excludedRows": sorted(set(hashes))}


class UndoIn(BaseModel):
    #: Delete at most this many of the batch's leads, then answer with
    #: ``remaining``; the page calls again until it is 0.
    maxLeads: Optional[int] = Field(default=None, ge=1, le=500)


@api_router.post("/prospects/import/{batch_id}/undo")
async def import_undo(batch_id: str, body: UndoIn, request: Request) -> dict[str, Any]:
    """*Undo this import* (rulings 87, 127)."""
    user, client = _actor(request)
    settings = get_settings()
    _require_templates(settings)
    api_client = getattr(request.app.state, "import_plan_client", None) if settings.espo_dry_run else None
    api_client = api_client or _api_client(settings, request)
    store = _store(request)
    batch = await store.get_batch(batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="That import was not found.")
    actor = user.get("name") or user.get("userName") or ""
    await _claim_write(store, batch_id, actor, "undone")
    try:
        result = await imports.undo_import(api_client, store, batch, actor=actor, max_leads=body.maxLeads)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not undo the import")
    finally:
        await store.release_write(batch_id)
    if result["done"]:
        total = result["total"]
        deleted, touched = total.get("deleted") or [], total.get("touched") or []
        summary = (f"Undid the import \"{batch['name']}\": {len(deleted)} leads deleted, "
                   f"{len(touched)} touched and left")
        # The history row needs a record that still exists: a deleted lead
        # cannot carry it (the CRM refuses the link — found on the M4 pass,
        # 10-25-26). A touched lead stands for the batch; when every lead was
        # deleted there is none, the batch row keeps the full result, and the
        # web log names every id.
        anchor = touched[0].get("id") if touched else None
        log.info("import undone: %s by %s — deleted %s; left %s", batch["name"], actor, deleted,
                 [t.get("id") for t in touched])
        if anchor:
            await record_action(
                client, app=APP_CAMPAIGNS, category=CAT_STATUS, action="Import Undone",
                parent_type=cfg.PROSPECT, parent_id=anchor, summary=summary,
                actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
                details={"deleted": deleted, "touched": touched, "pressedBy": actor},
            )
        else:
            log.warning("import undone: no lead left to carry the history row for \"%s\" (%s deleted)",
                        batch["name"], len(deleted))
    return {"batchId": batch_id, "result": result}


class ImportApplyIn(BaseModel):
    batchId: str
    #: Write at most this many rows, then answer with ``remaining``; the page
    #: calls again until it is 0 (10-20-26: 800 creates outlast one request).
    maxRows: Optional[int] = Field(default=None, ge=1, le=500)


@api_router.post("/prospects/import/apply")
async def import_apply(body: ImportApplyIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    settings = get_settings()
    api_client = getattr(request.app.state, "import_plan_client", None) if settings.espo_dry_run else None
    api_client = api_client or _api_client(settings, request)
    store = _store(request)
    batch = await store.get_batch(body.batchId)
    if not batch:
        raise HTTPException(status_code=404, detail="That import plan was not found — plan it again.")
    actor_name = user.get("name") or user.get("userName") or ""
    # One request writes a batch at a time (migration 0036): two presses of
    # Confirm within a second created every lead twice on the M4 pass.
    await _claim_write(store, batch["id"], actor_name, "written")
    try:
        result = await imports.apply_import(api_client, client, store, batch, user_name=actor_name,
                                            max_rows=body.maxRows)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not apply the import")
    finally:
        await store.release_write(batch["id"])
    # The action log needs a record to hang on; an import has many. The first
    # lead it made stands for the batch (an empty id is refused by
    # both the stream note and the CActionLog row — seen 10-15-26).
    first_id = result.get("firstProspectId")
    if body.maxRows is not None:
        # Applied in parts: one history row, when the last part finishes,
        # counted from the plan (the parts' own counts are the page's).
        if result.get("remaining") or result.get("errors"):
            return {"batchId": batch["id"], "result": result}
        counts = (batch.get("plan") or {}).get("counts") or {}
        excluded_hashes = set(batch.get("excluded_rows") or [])
        excluded_rows = [e for e in (batch.get("plan") or {}).get("rows") or [] if e.get("hash") in excluded_hashes]
        excluded = len(excluded_rows)
        ex_create = [e for e in excluded_rows if e.get("outcome") == imports.OUTCOME_CREATE]
        first_id = first_id or await store.first_prospect_id(batch["id"])
        result_summary = {"created": counts.get("create", 0) - len(ex_create),
                          "qualified": counts.get("qualified", 0) - sum(1 for e in ex_create if e.get("status") == cfg.LEAD_QUALIFIED),
                          "unqualified": counts.get("unqualified", 0) - sum(1 for e in ex_create if e.get("status") != cfg.LEAD_QUALIFIED),
                          "duplicates": counts.get("alreadyKnown", 0) - sum(1 for e in excluded_rows if e.get("outcome") == imports.OUTCOME_ALREADY_KNOWN),
                          "filled": counts.get("fills", 0) - sum(1 for e in excluded_rows if e.get("outcome") == imports.OUTCOME_FILLS),
                          "excluded": excluded, "errors": 0}
        if first_id:
            await record_action(
                client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action="Leads Imported",
                parent_type=cfg.PROSPECT, parent_id=first_id,
                summary=(f"Imported \"{batch['name']}\" ({batch['door']}) in parts: {result_summary['created']} leads "
                         f"({result_summary['qualified']} Qualified, {result_summary['unqualified']} Unqualified), "
                         f"{result_summary['duplicates']} duplicates"
                         + (f", {result_summary['filled']} leads filled" if result_summary["filled"] else "")
                         + (f", {excluded} rows excluded" if excluded else "")),
                actor_id=user.get("userId", ""), actor_name=user.get("name", ""), details=result_summary,
            )
        return {"batchId": batch["id"], "result": result}
    if first_id:
        await record_action(
            client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action="Leads Imported",
            parent_type=cfg.PROSPECT, parent_id=first_id,
            summary=(f"Imported \"{batch['name']}\" ({batch['door']}): {result['created']} leads "
                     f"({result['qualified']} Qualified, {result['unqualified']} Unqualified), "
                     f"{result['duplicates']} duplicates, {result['errors']} errors"),
            actor_id=user.get("userId", ""), actor_name=user.get("name", ""), details=result,
        )
    return {"batchId": batch["id"], "result": result}


# --- import templates (rulings 79, 81, 82; M4) ------------------------------------------------

class RecogniseIn(BaseModel):
    fileBase64: str = ""
    fileName: str = ""
    sheet: str = ""
    text: str = ""


@api_router.post("/prospects/import/recognise")
async def import_recognise(body: RecogniseIn, request: Request) -> dict[str, Any]:
    """The file's headers → the suggested template with its differences, every
    template's score, and the first rows for the mapping screen."""
    _actor(request)
    settings = get_settings()
    _require_templates(settings)
    store = _store(request)
    table, sha = _read_table(body.fileBase64, body.fileName, body.sheet, body.text)
    templates = await store.list_templates()
    found = tpl.recognise(templates, table["columns"])
    return {"columns": table["columns"], "rowCount": len(table["rows"]), "sheet": table.get("sheet"),
            "sample": table["rows"][:3], "fileSha256": sha,
            "priorBatch": ({"id": prior["id"], "appliedAt": prior["applied_at"].isoformat()}
                           if (prior := await store.find_batch_by_file(sha)) else None),
            "suggested": found["suggested"], "candidates": found["candidates"],
            "identityMapping": tpl.identity_mapping(table["columns"]),
            "fields": [{"name": k, "label": v} for k, v in tpl.FIELD_LABELS.items()]}


async def _template_log_parent(store, template: dict[str, Any]) -> Optional[str]:
    """The lead a template's history row hangs on: the first lead of its last
    batch. With none there is no record to hang it on, and — as the import's
    own history row does — the entry is skipped rather than refused."""
    if template.get("last_batch_id"):
        return await store.first_prospect_id(template["last_batch_id"])
    return None


async def _log_template(request: Request, client, store, template: dict[str, Any], action: str, user: dict) -> None:
    parent = await _template_log_parent(store, template)
    if not parent:
        log.info("import template %s (%s) by %s — no lead to record the history on yet",
                 action.lower(), template.get("name"), user.get("name"))
        return
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action=action,
        parent_type=cfg.PROSPECT, parent_id=parent,
        summary=f"{action}: \"{template.get('name')}\" ({template.get('door')}, enters {template.get('enters_at')})",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
        details={"templateId": template.get("id"), "mapping": template.get("mapping")},
    )


@api_router.get("/import-templates")
async def import_templates_list(request: Request) -> dict[str, Any]:
    _actor(request)
    _require_templates(get_settings())
    store = _store(request)
    return {"templates": [tpl.template_payload(t) for t in await store.list_templates()],
            "fields": [{"name": k, "label": v} for k, v in tpl.FIELD_LABELS.items()],
            "entersAt": list(tpl.ENTERS_AT), "sources": list(cfg.IMPORT_SOURCES)}


@api_router.post("/import-templates")
async def import_template_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    _require_templates(get_settings())
    store = _store(request)
    try:
        values = tpl.validate_template(body)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    row = await store.create_template(values, actor=user.get("name") or user.get("userName") or "")
    await _log_template(request, client, store, row, "Import Template Created", user)
    return {"template": tpl.template_payload(row)}


@api_router.put("/import-templates/{template_id}")
async def import_template_update(template_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    _require_templates(get_settings())
    store = _store(request)
    await _template_or_404(store, template_id)
    try:
        values = tpl.validate_template(body)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    row = await store.update_template(template_id, values, actor=user.get("name") or user.get("userName") or "")
    await _log_template(request, client, store, row, "Import Template Changed", user)
    return {"template": tpl.template_payload(row)}


@api_router.delete("/import-templates/{template_id}")
async def import_template_delete(template_id: str, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    _require_templates(get_settings())
    store = _store(request)
    row = await _template_or_404(store, template_id)
    await store.delete_template(template_id)
    await _log_template(request, client, store, row, "Import Template Deleted", user)
    return {"deleted": template_id}




# --- review (§ 2.3, § 3.8; rulings 18 and 29) ---------------------------------------------------

class ReviewIn(BaseModel):
    action: str
    note: str = Field(default="", max_length=4000)
    #: Typed into the Review row (§ 7b answer 2); written with the action.
    website: str = Field(default="", max_length=255)
    email: str = Field(default="", max_length=255)
    #: What the reviewer saw (§ 7b answer 5): refused, naming who, if the
    #: lead has changed since. Absent from an older page, which skips it.
    seenStatus: Optional[str] = None
    seenExit: Optional[str] = None


@api_router.post("/prospects/{prospect_id}/review")
async def review_prospect(prospect_id: str, body: ReviewIn, request: Request) -> dict[str, Any]:
    """Qualify, Disqualify, Do Not Contact or Not the same company — the lead
    written as the reviewer, the one link clear under the API client."""
    user, client = _actor(request)
    settings = get_settings()
    if body.action not in review.ACTIONS:
        raise HTTPException(status_code=400, detail="Unknown review action.")
    try:
        prospect = await client.get(cfg.PROSPECT, prospect_id, select=leads.GUARD_SELECT)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not read the lead")
    if not prospect or not prospect.get("id"):
        raise HTTPException(status_code=404, detail="Lead not found.")
    seen: dict[str, Any] = {}
    if body.seenStatus is not None:
        seen["leadStatus"] = body.seenStatus
    if body.seenExit is not None:
        seen["sideExit"] = body.seenExit
    moved = leads.changed_since(prospect, seen) if seen else None
    if moved:
        raise HTTPException(status_code=409, detail=moved)
    try:
        result = await review.apply_action(client, _system_client(settings), prospect, body.action,
                                           reviewer=user.get("name") or user.get("userName") or "",
                                           note=body.note, website=body.website, email=body.email)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not save the review")
    # The ladder (§ 7e.3): a qualify, a typed website or email, or a disqualify
    # changes what the level should be. Best-effort, under the API client.
    result["level"] = await ladder.after_write(
        prospect_id, client=_system_client(settings), settings=settings,
        store=getattr(request.app.state, "campaign_store", None))
    name = prospect.get("businessName") or prospect.get("name") or prospect_id
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_STATUS, action=review.ACTION_LABELS[body.action],
        parent_type=cfg.PROSPECT, parent_id=prospect_id,
        summary=(f"{review.ACTION_LABELS[body.action]}: \"{name}\""
                 + (f" — {body.note.strip()}" if body.note.strip() else "")),
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
        details={"written": result["written"], "was": {"leadStatus": prospect.get("leadStatus"),
                                                       "sideExit": prospect.get("sideExit")}},
    )
    return result


# --- the research queue's contacts mode (build plan § 7e.6; rulings 110, 121) ------------------

class ContactsIn(BaseModel):
    """What a contacts-queue row sends on Enter: the four boxes (each optional),
    what the reviewer saw (the guard), and the findings the boxes were filled
    from (closed Accepted once the values are written)."""
    firstName: str = Field(default="", max_length=255)
    lastName: str = Field(default="", max_length=255)
    phone: str = Field(default="", max_length=255)
    email: str = Field(default="", max_length=255)
    seenStatus: Optional[str] = None
    seenExit: Optional[str] = None
    seenLevel: Optional[str] = None
    findingIds: list[str] = Field(default_factory=list, max_length=50)


ACTION_CONTACT_FOUND = "Lead Contact Found"


@api_router.post("/prospects/{prospect_id}/contacts")
async def lead_contacts(prospect_id: str, body: ContactsIn, request: Request) -> dict[str, Any]:
    """The contacts queue's write: the person's name, phone and email typed
    into the row, written as the user through the lead page's normalisation;
    placement under the API client; the named findings closed Accepted.
    ``stays`` says the lead is still Identified (the row stays, ``needs`` says
    what is missing)."""
    user, client = _actor(request)
    settings = get_settings()
    has_ladder = await leads.ladder_available(client)
    lead = await _lead_or_404(request, client, prospect_id,
                              select=leads.GUARD_SELECT_LADDER if has_ladder else leads.GUARD_SELECT)
    seen: dict[str, Any] = {}
    if body.seenStatus is not None:
        seen["leadStatus"] = body.seenStatus
    if body.seenExit is not None:
        seen["sideExit"] = body.seenExit
    if body.seenLevel is not None and has_ladder:
        seen["qualificationLevel"] = body.seenLevel
    moved = leads.changed_since(lead, seen) if seen else None
    if moved:
        raise HTTPException(status_code=409, detail=moved)
    if lead.get("leadStatus") != cfg.LEAD_QUALIFIED or lead.get("sideExit"):
        raise HTTPException(status_code=400, detail=(
            "Only a Qualified lead still being worked takes a contact from this queue; this one is "
            f"{lead.get('leadStatus') or 'unknown'}" + (f" and stopped ({lead['sideExit']})" if lead.get("sideExit") else "") + "."))
    try:
        payload = leads.contacts_payload(lead, {"firstName": body.firstName, "lastName": body.lastName,
                                                "phone": body.phone, "email": body.email})
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not payload and not body.findingIds:
        raise HTTPException(status_code=400, detail="Type the person's name and a phone or an email first — nothing new to save.")
    updated = lead
    if payload:
        try:
            updated = await client.update(cfg.PROSPECT, prospect_id, payload)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not save the contact")
    system = _system_client(settings)
    level = await ladder.after_write(prospect_id, client=system, settings=settings,
                                     store=getattr(request.app.state, "campaign_store", None))
    findings: dict[str, Any] = {"closed": [], "skipped": []}
    if body.findingIds:
        if system is None:
            findings["skipped"] = [{"id": i, "why": "This deployment has no CRM credential to close findings."} for i in body.findingIds]
        else:
            findings = await enrichment_runs.close_findings(system, body.findingIds, target_id=prospect_id,
                                                            actor=user.get("name") or user.get("userName") or "staff")
    after = {**lead, **payload}
    final_level = level if level is not None else (after.get("qualificationLevel") or "")
    stays = final_level not in (cfg.LEVEL_CONTACTABLE, cfg.LEVEL_REFERRED)
    needs = leads.contacts_needed(after) if stays else ""
    name = lead.get("businessName") or lead.get("name") or prospect_id
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action=ACTION_CONTACT_FOUND,
        parent_type=cfg.PROSPECT, parent_id=prospect_id,
        summary=(f"Contact found for \"{name}\": " + (", ".join(sorted(payload)) if payload else "nothing new")
                 + (f" — level {final_level}" if final_level else "")
                 + (f"; {len(findings['closed'])} AI finding(s) accepted" if findings["closed"] else "")),
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
        details={"written": payload, "was": {k: lead.get(k) for k in payload}, "level": level,
                 "findings": findings},
    )
    return {"prospect": updated, "written": sorted(payload), "level": final_level or None, "stays": stays,
            "needs": needs, "findings": findings}


@api_router.get("/prospects/{prospect_id}/suggestions")
async def lead_suggestions(prospect_id: str, request: Request) -> dict[str, Any]:
    """The lead's Proposed AI findings mapped onto the Review row's boxes
    (§ 7e.6), read under the org-wide key, plus whether research is still
    running for it (``researching``)."""
    user, client = _actor(request)
    settings = get_settings()
    await _lead_or_404(request, client, prospect_id, select="id,name")
    out: dict[str, Any] = {b: "" for b in enrichment_runs.SUGGESTION_BOXES}
    out.update({"findingIds": [], "researching": False, "available": False})
    system = _system_client(settings)
    if system is None or not await enrichment_runs.available(system):
        return out
    out["available"] = True
    try:
        out.update(enrichment_runs.suggestions(await enrichment_runs.existing_findings(system, prospect_id=prospect_id)))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not read the lead's AI findings")
    store = getattr(request.app.state, "enrichment_store", None)
    if store is not None:
        try:
            out["researching"] = (await store.target_pending(prospect_id)) > 0
        except Exception as exc:  # noqa: BLE001 — a store hiccup never hides the findings
            log.warning("pending research read for %s failed: %s", prospect_id, exc)
    return out


# --- calls (§ 3.4; ruling 36) ---------------------------------------------------------------------

@api_router.get("/calls/session")
async def calls_session(request: Request) -> dict[str, Any]:
    """Who is signed in, for the Calls page a caller outside the campaigns team
    opens directly."""
    user = _require_caller(request)
    return {"name": user.get("name"), "userName": user.get("userName"),
            "isAdmin": bool(user.get("isAdmin")),
            "campaignsTeam": is_member(user, get_settings().campaigns_allowed_teams_list)}


@api_router.get("/calls")
async def call_list(request: Request) -> dict[str, Any]:
    user = _require_caller(request)
    settings = get_settings()
    client = client_for(settings, user)
    api_client = _api_client(settings, request)
    try:
        return await calls.call_list(api_client, client, user, settings)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not read the call list")


#: A plain shape check for a caller-typed email; the CRM is the real gate.
_EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class OutcomeIn(BaseModel):
    outcome: str
    notes: str = Field(default="", max_length=8000)
    callAgain: bool = False
    # Interested on a lead (ruling 47): either an email or a website converts it.
    email: str = Field(default="", max_length=255)
    website: str = Field(default="", max_length=255)
    firstName: str = Field(default="", max_length=100)
    lastName: str = Field(default="", max_length=100)


@api_router.post("/calls/{touch_id}/outcome")
async def record_outcome(touch_id: str, body: OutcomeIn, request: Request) -> dict[str, Any]:
    user = _require_caller(request)
    settings = get_settings()
    client = client_for(settings, user)
    api_client = _api_client(settings, request)
    try:
        email = body.email.strip().lower()
        if email and not _EMAIL_SHAPE.match(email):
            raise CampaignError(f"\"{body.email.strip()}\" is not an email address.")
        details = Details(email=email, website=body.website.strip(),
                          first_name=body.firstName.strip(), last_name=body.lastName.strip())
        result = await calls.record_outcome(api_client, client, user, touch_id, outcome=body.outcome,
                                            notes=body.notes, call_again=body.callAgain, settings=settings,
                                            details=details)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not record the call")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_STATUS, action="Call Recorded",
        parent_type=cfg.TOUCH, parent_id=touch_id,
        summary=(f"Recorded a call on \"{result.get('campaignName')}\": {body.outcome}"
                 + (", call again" if body.callAgain else "")),
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
        details={"consequences": result["consequences"], "warnings": result["warnings"]},
    )
    return result


class TeamsIn(BaseModel):
    teamIds: list[str] = Field(default_factory=list)


@api_router.put("/campaigns/{campaign_id}/teams")
async def set_teams(campaign_id: str, body: TeamsIn, request: Request) -> dict[str, Any]:
    """Who calls for a call campaign (ruling 36): the campaign's own teams,
    written as the signed-in user. None named means the Marketing Admin Team."""
    user, client = _actor(request)
    row = await _campaign_or_404(request, client, campaign_id)
    if row.get("campaignKind") != cfg.KIND_CALL:
        raise HTTPException(status_code=400, detail="Only a call campaign names the teams that call.")
    try:
        await service.set_teams(client, campaign_id, body.teamIds,
                                admin_factory=admin_client_factory(get_settings()))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not change who calls")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action="Campaign Callers Changed",
        parent_type=cfg.CAMPAIGN, parent_id=campaign_id,
        summary=f"Changed the teams that call for \"{row.get('name')}\"",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""), details={"teamIds": body.teamIds},
    )
    return {"teamIds": body.teamIds}


async def _simulate_text(campaign_id: str, touch_id: str, kind: str, request: Request, user, client,
                         api_client, settings: Settings) -> dict[str, Any]:
    """Dry run only: what the texting service would post back for one sent
    text — its delivery report, or the person replying STOP (ruling 38)."""
    if settings.sms_provider != "dryrun":
        raise HTTPException(status_code=400, detail="Simulated replies are a dry-run tool; the real service posts its own.")
    try:
        touch = await api_client.get(cfg.TOUCH, touch_id, select=cfg.TOUCH_SELECT)
        if (not touch or touch.get("outreachCampaignId") != campaign_id or touch.get("channel") != cfg.KIND_SMS
                or not touch.get("vendorPieceId")):
            raise HTTPException(status_code=404, detail="No sent text on this row.")
        if kind == "stop":
            changed = await sms.apply_stop(api_client, touch.get("calledPhone") or "")
            result: dict[str, Any] = {"applied": True, "optedOut": changed}
        else:
            result = await sms.apply_status(api_client, message_id=touch["vendorPieceId"], status="delivered")
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not apply the simulated reply")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_STATUS, action="Text Reply Simulated",
        parent_type=cfg.TOUCH, parent_id=touch_id,
        summary=f"Simulated {'a STOP reply' if kind == 'stop' else 'a delivery report'} on a dry-run text",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return result


async def _sign_off_to_copy(request: Request, settings: Settings, api_client, client, row: dict[str, Any],
                            confirm: str, user_name: str) -> dict[str, Any]:
    """Sign-off with the switch on: every refusal first, then *Sync now* for
    the campaign's list, then Signed off. A failed sync leaves the campaign
    where it was and says why."""
    from .lists_router import run_sync_now

    list_row, chosen = await _campaign_list(request, row["id"])
    email_kind.check_sign_off_to_copy(row, confirm=confirm, built=(chosen or {}).get("build"),
                                      list_row=list_row, settings=settings)
    result = await run_sync_now(settings, request, _store(request), list_row)
    return {**await email_kind.signed_off_to_copy(api_client, client, row, user_name=user_name,
                                                  synced=result.summary),
            "copy": result.summary}


@api_router.get("/campaigns/{campaign_id}/emails")
async def sent_emails(campaign_id: str, request: Request) -> dict[str, Any]:
    """*Pick the email*: the account's emails sent to the campaign's list copy
    in the last 30 days."""
    _user, client = _actor(request)
    settings = get_settings()
    _require_email(settings)
    if not _copy_mode(settings):
        raise HTTPException(status_code=404, detail="Copies in Constant Contact are switched off (Campaign list copies at /setup).")
    row = await _campaign_or_404(request, client, campaign_id)
    if row.get("campaignKind") != cfg.KIND_EMAIL:
        raise HTTPException(status_code=400, detail="This is not an email campaign.")
    list_row, _chosen = await _campaign_list(request, campaign_id)
    problem = email_kind.copy_refusal(list_row)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    if not list_row.get("cc_list_id"):
        raise HTTPException(status_code=400, detail=(
            f"The list \"{list_row['name']}\" has no copy in Constant Contact yet — sign off the campaign "
            "(it syncs the copy), or press Sync now on the list."))
    from . import list_sync
    from core.mailing import MailingError
    try:
        emails = await list_sync.emails_for_list(settings, list_row["cc_list_id"])
    except MailingError as exc:
        raise HTTPException(status_code=502, detail=f"Constant Contact could not list the emails: {exc}")
    return {"listName": list_row["name"], "emails": emails}


class PickIn(BaseModel):
    emailId: str = Field(min_length=1, max_length=64)


@api_router.post("/campaigns/{campaign_id}/pick-email")
async def pick_email(campaign_id: str, body: PickIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    settings = get_settings()
    _require_email(settings)
    if not _copy_mode(settings):
        raise HTTPException(status_code=404, detail="Copies in Constant Contact are switched off (Campaign list copies at /setup).")
    row = await _campaign_or_404(request, client, campaign_id)
    api_client = _api_client(settings, request)
    copy = await _email_copy(request, settings, campaign_id)
    row = {**row, email_kind.VENDOR_EMAIL_FIELD: copy["pickedEmailId"]}
    try:
        email_kind.check_pick(row)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    listed = await sent_emails(campaign_id, request)
    try:
        result = await email_kind.pick_email(api_client, client, row, email_id=body.emailId, sent=listed["emails"])
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not record the email")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_STATUS, action="Campaign Email Picked",
        parent_type=cfg.CAMPAIGN, parent_id=campaign_id,
        summary=(f"Picked the email \"{result['email']['name']}\", sent from Constant Contact to the list "
                 f"\"{listed['listName']}\", for \"{row.get('name')}\""),
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
        details={"email": result["email"]},
    )
    return result


@api_router.post("/campaigns/{campaign_id}/mark-sent")
async def mark_sent(campaign_id: str, request: Request) -> dict[str, Any]:
    """Email kind: staff sent the notice at the mailing service (§ 3.3). The
    switch-off path only; with copies on, *Pick the email* is the confirmation."""
    user, client = _actor(request)
    settings = get_settings()
    _require_email(settings)
    if _copy_mode(settings):
        raise HTTPException(status_code=400, detail=(
            "Pick the email you sent from Constant Contact instead — picking it is the confirmation."))
    row = await _campaign_or_404(request, client, campaign_id)
    try:
        result = await email_kind.mark_as_sent(_api_client(settings, request), row)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not mark the campaign sent")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_STATUS, action="Campaign Marked Sent",
        parent_type=cfg.CAMPAIGN, parent_id=campaign_id,
        summary=f"Marked \"{row.get('name')}\" sent at the mailing service: {result['sent']} people",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""),
    )
    return result


# --- the send report and Recipients (§ 7e.9, ruling 96; M9) ------------------------------

@api_router.post("/campaigns/{campaign_id}/report")
async def read_report_now(campaign_id: str, request: Request) -> dict[str, Any]:
    """*Read the report now*: one email campaign's Constant Contact report,
    written as its recipients' touches (at most ``WEB_WRITE_CAP`` writes; the
    nightly pass finishes the rest)."""
    from . import list_sync, send_report
    from core.mailing import MailingError

    user, client = _actor(request)
    settings = get_settings()
    problem = send_report.refusal(settings)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    row = await _campaign_or_404(request, client, campaign_id)
    if row.get("campaignKind") != cfg.KIND_EMAIL:
        raise HTTPException(status_code=400, detail="Only an email campaign has a send report.")
    api_client = _api_client(settings, request)
    try:
        whole = await api_client.get(cfg.CAMPAIGN, campaign_id, select=f"id,{email_kind.VENDOR_EMAIL_FIELD}") or {}
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not read the campaign")
    row = {**row, email_kind.VENDOR_EMAIL_FIELD: whole.get(email_kind.VENDOR_EMAIL_FIELD) or ""}
    if not row[email_kind.VENDOR_EMAIL_FIELD]:
        raise HTTPException(status_code=400, detail="Pick the email you sent first — the report belongs to that email.")
    try:
        mail, _conn = list_sync.mail_clients(settings)
    except MailingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    result = await send_report.read_campaign(settings, row, crm=api_client, mail=mail,
                                             store=getattr(request.app.state, "campaign_store", None),
                                             max_writes=send_report.WEB_WRITE_CAP)
    if not result.ok:
        raise HTTPException(status_code=502, detail=result.words())
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action="Campaign Report Read",
        parent_type=cfg.CAMPAIGN, parent_id=campaign_id,
        summary=f"Read the Constant Contact report of \"{row.get('name')}\": {result.words()}",
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""), details=result.summary(),
    )
    return {"report": result.summary(), "words": result.words()}


RECIPIENTS_CAP = 5000


def _reached_at(t: dict[str, Any]) -> str:
    """Where the touch reached the person: the email (in the report's touch
    name), the phone called, or the first line of the address mailed."""
    if t.get("calledPhone"):
        return t["calledPhone"]
    if t.get("mailedAddress"):
        return str(t["mailedAddress"]).splitlines()[0]
    name = str(t.get("name") or "")
    if t.get("channel") == cfg.KIND_EMAIL and " — " in name:
        tail = name.rsplit(" — ", 1)[1]
        return tail if "@" in tail else ""
    return ""


async def _recipients(request: Request, campaign_id: str) -> tuple[list[dict[str, Any]], bool]:
    from . import send_report

    user, client = _actor(request)
    settings = get_settings()
    await _campaign_or_404(request, client, campaign_id)
    reader = _system_client(settings) or client
    opens = await send_report.open_fields_available(reader)
    select = cfg.TOUCH_SELECT + ",clickCount,firstClickedAt" + (",openCount,firstOpenedAt" if opens else "")
    rows: list[dict[str, Any]] = []
    offset = 0
    try:
        while len(rows) < RECIPIENTS_CAP:
            page = await reader.list(cfg.TOUCH, select=select, max_size=200, offset=offset, order_by="createdAt",
                                     order="asc", where=[{"type": "equals", "attribute": "outreachCampaignId",
                                                          "value": campaign_id}])
            batch = page.get("list", [])
            rows.extend(batch)
            if len(batch) < 200:
                break
            offset += 200
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not read the recipients")
    out = []
    for t in rows:
        out.append({
            "id": t.get("id"), "who": t.get("contactName") or t.get("prospectName") or t.get("companyName") or "",
            "whoType": "contact" if t.get("contactId") else "lead" if t.get("prospectId") else "company" if t.get("companyId") else "",
            "whoId": t.get("contactId") or t.get("prospectId") or t.get("companyId") or "",
            "reachedAt": _reached_at(t), "channel": t.get("channel") or "", "status": t.get("touchStatus") or "",
            "outcome": t.get("outcome") or "", "sentAt": t.get("sentAt") or "",
            "deliveredAt": t.get("deliveredAt") or "", "returnedAt": t.get("returnedAt") or "",
            "vendorStatus": t.get("vendorStatus") or "", "opens": t.get("openCount") if opens else None,
            "firstOpenedAt": t.get("firstOpenedAt") or "", "clicks": t.get("clickCount") or 0,
            "firstClickedAt": t.get("firstClickedAt") or "", "scans": t.get("scanCount") or 0,
        })
    return out, opens


def _match(r: dict[str, Any], q: str, status: str) -> bool:
    if status and r["status"] != status:
        return False
    return not q or q in f"{r['who']} {r['reachedAt']}".lower()


@api_router.get("/campaigns/{campaign_id}/recipients")
async def recipients(campaign_id: str, request: Request, q: str = "", status: str = "",
                     offset: int = 0, limit: int = 50) -> dict[str, Any]:
    """The campaign's touches as recipients: paged, searchable by name or
    address, filtered by status (ruling 96's Recipients view)."""
    rows, opens = await _recipients(request, campaign_id)
    q = q.strip().lower()
    found = [r for r in rows if _match(r, q, status)]
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    return {"recipients": found[offset: offset + limit], "total": len(found), "all": len(rows),
            "statusCounts": counts, "opensRecorded": opens, "offset": offset, "limit": limit,
            "capped": len(rows) >= RECIPIENTS_CAP}


@api_router.get("/campaigns/{campaign_id}/recipients.csv")
async def recipients_csv(campaign_id: str, request: Request, q: str = "", status: str = "") -> StreamingResponse:
    import csv
    import io

    rows, opens = await _recipients(request, campaign_id)
    q = q.strip().lower()
    heads = ["Recipient", "Type", "Reached at", "Channel", "Status", "Outcome", "Sent", "Delivered", "Returned",
             "Delivery note"] + (["Opens", "First opened"] if opens else []) + ["Clicks", "First clicked", "Scans",
                                                                                 "CRM id"]

    def line(values: list[Any]) -> str:
        buf = io.StringIO()
        csv.writer(buf).writerow(["" if v is None else v for v in values])
        return buf.getvalue()

    def gen():
        yield line(heads)
        for r in rows:
            if not _match(r, q, status):
                continue
            yield line([r["who"], r["whoType"], r["reachedAt"], r["channel"], r["status"], r["outcome"], r["sentAt"],
                        r["deliveredAt"], r["returnedAt"], r["vendorStatus"]]
                       + ([r["opens"], r["firstOpenedAt"]] if opens else [])
                       + [r["clicks"], r["firstClickedAt"], r["scans"], r["whoId"]])

    return StreamingResponse(gen(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="recipients-{campaign_id}.csv"',
                                      "Cache-Control": "no-store"})


# Personal outreach (build plan § 7e.5) registers its endpoints on api_router;
# the import sits last because that module uses this one's gate and helpers.
from . import outreach_router  # noqa: E402,F401
