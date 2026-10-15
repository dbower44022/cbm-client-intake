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
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from assignments import auth
from assignments.auth import current_user, is_member
from assignments.espo_user import client_for
from core.action_log import CAT_RECORD_EDIT, CAT_STATUS, record_action
from core.admin_client import admin_client_factory
from core.branding import abbr
from core.config import Settings, get_settings
from core.espo import EspoClient, EspoError, forbidden_hint, is_forbidden, validation_failure
from core.postal import estimated_cost
from core.qr import qr_png, qr_svg
from forms import SPECS_BY_SLUG

from . import config as cfg
from . import imports, postcard, service
from .public import destination_path
from .service import CampaignError

log = logging.getLogger("cbm_intake.campaigns")

api_router = APIRouter(prefix="/campaigns/api", tags=["campaigns"])

APP_CAMPAIGNS = "Campaign Management"


# --- the gate ------------------------------------------------------------------------

def _require_user(request: Request) -> dict:
    settings = get_settings()
    if not settings.campaigns_enabled:
        raise HTTPException(status_code=404, detail="Campaign Management is switched off.")
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    teams = settings.campaigns_allowed_teams_list
    if not is_member(user, teams):
        raise HTTPException(
            status_code=403,
            detail=(f"Your account is not authorized to use Campaign Management "
                    f"(requires the {', '.join(teams) or 'admin'} team)."),
        )
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
            detail=forbidden_hint(exc) or f"Your CRM role does not allow that — ask {abbr()} staff to grant it.",
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
    user, client = _actor(request)
    settings = get_settings()
    avail = await service.availability(client)
    return {
        "name": user.get("name"), "userName": user.get("userName"), "userId": user.get("userId"),
        "isAdmin": bool(user.get("isAdmin")),
        "available": avail["available"], "reason": avail["reason"],
        "storeAvailable": getattr(request.app.state, "campaign_store", None) is not None,
        "landingPublic": settings.campaigns_landing_active,
        "postal": {"provider": settings.postal_provider, "testMode": settings.postal_test_mode,
                   "unitCost": settings.postal_unit_cost, "currency": settings.postal_currency},
        "baseUrl": _base_url(request, settings),
        "kindsBuilt": list(cfg.PHASE_1_KINDS),
        "formDestinations": [{"slug": s, "title": SPECS_BY_SLUG[s].title}
                             for s in cfg.FORM_DESTINATIONS if s in SPECS_BY_SLUG],
    }


@api_router.get("/fields")
async def fields(request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    try:
        options = await service.field_options(client)
        partners = await service.picker_options(client, cfg.PARTNER_PROFILE)
        events = await service.picker_options(client, cfg.EVENT)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load the campaign form")
    return {
        "fields": [f.__dict__ for f in cfg.CAMPAIGN_FIELDS],
        "options": options["campaign"],
        "prospectOptions": options["prospect"],
        "kindsBuilt": options["kindsBuilt"],
        "partnerOptions": partners,       # None: the role may not list partners → read-only
        "eventOptions": events,
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
    for row in rows:
        links = links_by_campaign.get(row["id"], [])
        v = sum(visits.get(l["id"], {}).get("visits", 0) for l in links)
        s = sum(sum(subs.get(l["token"], {}).values()) for l in links)
        partners = await service.related_names(client, row["id"], cfg.LINK_PARTNERS) if len(rows) <= 60 else None
        out.append({**row, "links": len(links), "visits": v, "submissions": s,
                    "partners": partners, "manualMoves": service.manual_moves(row)})
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
    eventIds: Optional[list[str]] = None


@api_router.post("/campaigns")
async def create_campaign(body: CampaignIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    settings = get_settings()
    try:
        created = await service.create_campaign(client, body.changes, user_id=user.get("userId", ""))
        moved = await service.set_relations(
            client, created["id"],
            {k: v for k, v in ((cfg.LINK_PARTNERS, body.partnerIds), (cfg.LINK_EVENTS, body.eventIds)) if v is not None},
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
            rule = postcard.normalise_rule(json.loads(row["selectionRule"]))
        except Exception:  # noqa: BLE001
            rule = None
    return {
        "campaign": row, "partners": partners, "events": events,
        "touches": touches, "touchSummary": service.touch_summary(touches),
        "rule": rule or postcard.DEFAULT_RULE,
        "manualMoves": service.manual_moves(row),
        "estimatedCost": estimated_cost(settings, service.touch_summary(touches)["planned"]),
        "currency": settings.postal_currency,
    }


class ChangesIn(BaseModel):
    changes: dict[str, Any] = Field(default_factory=dict)


@api_router.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: str, body: ChangesIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    row = await _campaign_or_404(request, client, campaign_id)
    try:
        updated = await service.update_campaign(client, row, body.changes)
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


class RelationsIn(BaseModel):
    partnerIds: Optional[list[str]] = None
    eventIds: Optional[list[str]] = None


@api_router.put("/campaigns/{campaign_id}/relations")
async def set_relations(campaign_id: str, body: RelationsIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    settings = get_settings()
    row = await _campaign_or_404(request, client, campaign_id)
    wanted = {k: v for k, v in ((cfg.LINK_PARTNERS, body.partnerIds), (cfg.LINK_EVENTS, body.eventIds)) if v is not None}
    try:
        moved = await service.set_relations(client, campaign_id, wanted, admin_factory=admin_client_factory(settings))
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not change the campaign's partners or events")
    if any(m["added"] or m["removed"] for m in moved.values()):
        await record_action(
            client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action="Campaign Relations Changed",
            parent_type=cfg.CAMPAIGN, parent_id=campaign_id,
            summary=f"Changed the partners or events of \"{row.get('name')}\"",
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
    try:
        result = await postcard.build_list(api_client, client, row, body.rule, settings)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not build the list")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action="Campaign List Built",
        parent_type=cfg.CAMPAIGN, parent_id=campaign_id,
        summary=(f"Built the list of \"{row.get('name')}\": {result['pieces']} planned "
                 f"({result['created']} new, {result['cancelled']} dropped)"),
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""), details={"rule": result["rule"]},
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
        updated = await postcard.sign_off(api_client, client, row, confirm=body.confirm,
                                          user_name=user.get("name") or user.get("userName") or "", settings=settings)
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not sign off the campaign")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_STATUS, action="Campaign Signed Off",
        parent_type=cfg.CAMPAIGN, parent_id=campaign_id,
        summary=(f"Signed off \"{row.get('name')}\": {updated.get('pieceCount')} pieces, "
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
    if settings.postal_provider != "dryrun":
        raise HTTPException(status_code=400, detail="Simulated events are a dry-run tool; a real vendor posts its own.")
    api_client = _api_client(settings, request)
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
    totals: dict[str, int] = {}
    for r in rows:
        totals[r["form_slug"]] = totals.get(r["form_slug"], 0) + 1
    out = []
    for r in rows:
        result = r.get("result") or {}
        out.append({
            "id": r["id"], "form": r["form_slug"], "status": r["status"],
            "receivedAt": r["received_at"].isoformat() if r.get("received_at") else None,
            "linkToken": r.get("link_token"), "email": r.get("email"),
            "records": {k: v for k, v in result.items() if isinstance(v, str) and k.endswith("Id")} if isinstance(result, dict) else {},
        })
    return {"responses": out, "totals": totals}


# --- prospects (§ 3.8) ------------------------------------------------------------------------------

@api_router.get("/prospects")
async def list_prospects(request: Request, stage: Optional[str] = None, exit: Optional[str] = None,
                         door: Optional[str] = None, batch: Optional[str] = None) -> dict[str, Any]:
    user, client = _actor(request)
    try:
        rows = await service.list_prospects(client, stage=stage, exit_=exit, door=door, batch=batch)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not list prospects")
    return {"prospects": rows}


@api_router.get("/prospects/{prospect_id}")
async def get_prospect(prospect_id: str, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    try:
        row = await service.get_prospect(client, prospect_id)
        touches = await service.prospect_touches(client, prospect_id)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not read the prospect record")
    if not row or not row.get("id"):
        raise HTTPException(status_code=404, detail="Prospect record not found.")
    return {"prospect": row, "touches": touches}


class ImportPlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    door: str = cfg.DOOR_FILING
    text: str
    qualifiedBy: str = ""
    listSource: str = ""


@api_router.post("/prospects/import/plan")
async def import_plan(body: ImportPlanIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    settings = get_settings()
    api_client = _api_client(settings, request)
    store = _store(request)
    try:
        plan = await imports.plan_import(api_client, store, text=body.text, name=body.name.strip(), door=body.door,
                                         qualified_by=body.qualifiedBy.strip(), list_source=body.listSource.strip())
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not plan the import")
    return plan


class ImportApplyIn(BaseModel):
    batchId: str


@api_router.post("/prospects/import/apply")
async def import_apply(body: ImportApplyIn, request: Request) -> dict[str, Any]:
    user, client = _actor(request)
    settings = get_settings()
    api_client = _api_client(settings, request)
    store = _store(request)
    batch = await store.get_batch(body.batchId)
    if not batch:
        raise HTTPException(status_code=404, detail="That import plan was not found — plan it again.")
    try:
        result = await imports.apply_import(api_client, client, store, batch,
                                            user_name=user.get("name") or user.get("userName") or "")
    except CampaignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not apply the import")
    await record_action(
        client, app=APP_CAMPAIGNS, category=CAT_RECORD_EDIT, action="Prospects Imported",
        parent_type=cfg.PROSPECT, parent_id="",
        summary=(f"Imported \"{batch['name']}\" ({batch['door']}): {result['created']} prospect records, "
                 f"{result['alreadyKnown']} already known, {result['companies']} companies and "
                 f"{result['contacts']} contacts typed Prospect, {result['errors']} errors"),
        actor_id=user.get("userId", ""), actor_name=user.get("name", ""), details=result,
    )
    return {"batchId": batch["id"], "result": result}


@api_router.get("/prospects/imports")
async def recent_imports(request: Request) -> dict[str, Any]:
    _actor(request)
    store = _store(request)
    rows = await store.recent_batches()
    return {"batches": [{
        "id": b["id"], "name": b["name"], "door": b["door"], "rowCount": b["row_count"],
        "status": b["status"], "createdAt": b["created_at"].isoformat() if b.get("created_at") else None,
        "appliedAt": b["applied_at"].isoformat() if b.get("applied_at") else None,
        "counts": (b.get("plan") or {}).get("counts"), "result": b.get("result"),
    } for b in rows]}
