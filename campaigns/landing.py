"""The postcard landing page — ``/p/{token}`` (build plan § 4).

A public route on the web process, gated by ``CAMPAIGNS_LANDING_PUBLIC`` (off,
the route 404s). A route, not a static file, for the same reasons the event
pages are: the body is filled server-side, and an unknown, cancelled or dead
token must 404 in the same words as a missing one.

**On load — the scan (rulings 16, 51).** The token resolves to a Sent or
Delivered touch (a Returned one too: the card reached someone after all). The
application writes ``firstScannedAt`` (first time only), increments
``scanCount`` and sets the outcome to Scanned. **A scan alone changes no status**
(ruling 51): there is no website or email in it to convert the lead with.
Best-effort: the write never blocks the page. A Planned
touch (a preview from the campaign screen) renders and writes nothing.

**What it shows (ruling 16).** The business name and the mailing address AS
MAILED — exactly what the holder is looking at — both editable. Nothing else the
chapter may hold is echoed: no email, no phone, no person's name, whatever the
lead carries. The harvester rule, kept.

**What it asks for.** The person's name, email, phone and website, and two ticks
worded for what each permits. Three actions, always clickable, validated on
click. The response is the sixth form kind, ``prospect-response``, posted to
``POST /api/campaigns/landing/{token}`` and delivered by the worker.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from core import branding
from core.config import Settings, get_settings
from core.espo import EspoApi, EspoError

from . import config as cfg
from .service import parse_address_text
from .tokens import looks_like_token

log = logging.getLogger("cbm_intake.campaigns.landing")

LANDING_FRONTEND_DIR = Path(__file__).resolve().parent / "landing_frontend"
NOT_FOUND = "Not found"

page_router = APIRouter(tags=["campaigns-landing"])

_template_cache: dict[str, str] = {}


def _template(name: str) -> str:
    text = _template_cache.get(name)
    if text is None:
        try:
            text = (LANDING_FRONTEND_DIR / name).read_text(encoding="utf-8")
        except OSError as exc:
            log.error("landing template %s unreadable: %s", name, exc)
            raise HTTPException(status_code=503, detail="The page is temporarily unavailable.")
        _template_cache[name] = text
    return text


def _crm_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _client(request: Request) -> EspoApi:
    factory = getattr(request.app.state, "events_client_factory", None)
    if factory is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return factory()


async def resolve_touch(client: EspoApi, scan_token: str,
                        campaign_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    """The touch a card token names, or None. A Cancelled touch is None too.

    Since § 7d.1 a card's token is the person's lead code, so a Contact sent
    cards by two list campaigns (ruling 68 does not apply ruling 14 to them)
    has two touches with one token: the campaign of the link the card was
    opened through decides, else the most recently sent card."""
    if not looks_like_token(scan_token):
        return None
    page = await client.list(cfg.TOUCH, select=cfg.TOUCH_SELECT, max_size=20,
                             where=[{"type": "equals", "attribute": "scanToken", "value": scan_token}])
    rows = [t for t in page.get("list", []) if t.get("touchStatus") != cfg.TOUCH_CANCELLED]
    if not rows:
        return None
    if campaign_id:
        mine = [t for t in rows if t.get("outreachCampaignId") == campaign_id]
        if mine:
            rows = mine
    rows.sort(key=lambda t: t.get("sentAt") or "", reverse=True)
    return rows[0]


async def _link_campaign(request: Request, link: str) -> Optional[str]:
    """The campaign of the link token the card was opened through, from the
    application's own database; None when unknown."""
    store = getattr(request.app.state, "campaign_store", None)
    if store is None or not looks_like_token(link or ""):
        return None
    try:
        row = await store.get_link_by_token(link.lower())
    except Exception as exc:  # noqa: BLE001
        log.info("landing: link %s not read (%s)", link, exc)
        return None
    return (row or {}).get("campaign_id") or None


async def lead_code_for(client: EspoApi, touch: dict[str, Any]) -> str:
    """The code the forms after this page carry (§ 7d.3): the card's own token
    when it is the person's lead code, else the lead's code (an older card),
    minted if the lead has none. "" on a CRM without the code fields or for a
    card to a Company. Best-effort."""
    from . import leadcode

    try:
        if not await leadcode.available(client):
            return ""
        if touch.get("prospectId"):
            return await leadcode.ensure_for_lead(client, touch["prospectId"]) or ""
        if touch.get("contactId"):
            return await leadcode.ensure_for_contact(client, touch["contactId"]) or ""
    except EspoError as exc:
        log.warning("landing: no lead code for touch %s: %s", touch.get("id"), exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("landing: lead code for touch %s errored: %s", touch.get("id"), exc)
    return ""


async def record_scan(client: EspoApi, touch: dict[str, Any]) -> dict[str, Any]:
    """Ruling 51: a scan alone changes no status. It is recorded on the touch
    (``firstScannedAt`` the first time, ``scanCount``, outcome Scanned), which
    the lead's page lists. Best-effort; a failure is logged and the page still
    renders."""
    out: dict[str, Any] = {"written": False}
    if touch.get("touchStatus") == cfg.TOUCH_PLANNED:
        out["preview"] = True
        return out
    try:
        stamps: dict[str, Any] = {
            "scanCount": int(touch.get("scanCount") or 0) + 1,
            "outcome": cfg.OUTCOME_SCANNED,
        }
        if not touch.get("firstScannedAt"):
            stamps["firstScannedAt"] = _crm_now()
        await client.update(cfg.TOUCH, touch["id"], stamps)
        out["written"] = True
    except EspoError as exc:
        log.warning("scan write for touch %s failed: %s", touch.get("id"), exc)
    return out


def _printed(touch: dict[str, Any]) -> dict[str, str]:
    """What the card carries and nothing else: the name and the address as mailed."""
    addr = parse_address_text(touch.get("mailedAddress") or "")
    return {
        "businessName": touch.get("prospectName") or touch.get("companyName") or "",
        **addr,
    }


def _render(settings: Settings, values: dict[str, str]) -> str:
    html = branding.render_page(_template("landing.html"), settings)
    for key, value in values.items():
        html = html.replace("{{" + key + "}}", escape(value or "", quote=True))
    return html


@page_router.get("/p/{scan_token}", response_class=HTMLResponse, include_in_schema=False)
async def landing_page(scan_token: str, request: Request, link: str = "") -> HTMLResponse:
    settings = get_settings()
    if not settings.campaigns_landing_active:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    scan_token = scan_token.lower()
    client = _client(request)
    try:
        touch = await resolve_touch(client, scan_token, await _link_campaign(request, link))
    except EspoError as exc:
        log.warning("landing resolve failed: %s", exc)
        raise HTTPException(status_code=503, detail="The page is temporarily unavailable.")
    if touch is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    scan = await record_scan(client, touch)
    printed = _printed(touch)
    # A preview writes nothing — no code is minted for an unsent card.
    code = "" if scan.get("preview") else await lead_code_for(client, touch)
    values = {
        "scanToken": scan_token,
        "campaignId": touch.get("outreachCampaignId") or "",
        "campaignName": touch.get("outreachCampaignName") or "",
        "linkToken": link.lower() if looks_like_token(link) else "",
        "prospectId": touch.get("prospectId") or "",
        "leadCode": code,
        "preview": "1" if scan.get("preview") else "",
        **printed,
    }
    return HTMLResponse(_render(settings, values), headers={"Cache-Control": "no-store"})


def make_landing_routes(process: Callable[[Any], Awaitable[Any]]) -> APIRouter:
    """The response endpoint, over the same durable pipeline as every form: the
    card's token comes from the URL and is merged into the body."""
    router = APIRouter(tags=["campaigns-landing"])

    @router.post("/api/campaigns/landing/{scan_token}", include_in_schema=False)
    async def respond(scan_token: str, request: Request):
        settings = get_settings()
        if not settings.campaigns_landing_active:
            raise HTTPException(status_code=404, detail=NOT_FOUND)
        scan_token = scan_token.lower()
        if not looks_like_token(scan_token):
            raise HTTPException(status_code=404, detail=NOT_FOUND)
        try:
            body = await request.json()
        except ValueError:
            return JSONResponse(status_code=422, content={"detail": "The request body is not JSON."})
        if not isinstance(body, dict):
            return JSONResponse(status_code=422, content={"detail": "The request body must be an object."})
        # The token in the URL is the one that counts; a body cannot name another card.
        body["scan_token"] = scan_token
        client = _client(request)
        try:
            touch = await resolve_touch(client, scan_token, body.get("campaign_id") or None)
        except EspoError as exc:
            log.warning("landing respond resolve failed: %s", exc)
            raise HTTPException(status_code=503, detail="Please try again in a moment.")
        if touch is None:
            raise HTTPException(status_code=404, detail=NOT_FOUND)
        body.setdefault("campaign_id", touch.get("outreachCampaignId") or None)
        body.setdefault("prospect_id", touch.get("prospectId") or None)
        return await process(body)

    return router
