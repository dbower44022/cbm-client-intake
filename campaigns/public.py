"""The public, unauthenticated half of Campaign Management (build plan § 3.7).

    GET /c/{token}                        resolve a campaign link: count the visit, 302 on
    GET /c/{token}/{scan}                 a card's code: count the visit, 302 to /p/{scan}
    GET /c/{token}/{scan}/qr.png          the card's QR image, for the vendor's template
    GET /api/campaigns/public/{id}        the campaign's NAME and nothing else (the banner)

Rules kept here:

* **The resolve never calls the CRM** (ruling 31). A link's destination, state
  and an event link's cached slug all live in the application database.
* **A token that resolves to nothing is a 404 in the same words whatever the
  reason** — malformed, unknown, or a landing link opened without a card token —
  so the route cannot be used to probe which tokens exist.
* **A visit is the resolve.** A retired link still redirects (a visitor holding a
  card never meets a dead page); its visit is flagged late.
* **The name lookup answers the name or a 404 and nothing else** — the partner
  lookup's shape and the harvester rule. Nothing about a person is ever served.
* Rate-limited per address by the intake middleware (``core/app.py`` names these
  paths), because a GET is otherwise unthrottled.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from core.config import Settings, get_settings
from core.espo import EspoError
from core.qr import qr_png

from . import config as cfg
from .tokens import looks_like_token

log = logging.getLogger("cbm_intake.campaigns.public")

NOT_FOUND = "Not found"
_RECORD_ID = re.compile(r"^[A-Za-z0-9]{1,32}$")

public_router = APIRouter(tags=["campaigns-public"])


def _store(request: Request):
    store = getattr(request.app.state, "campaign_store", None)
    if store is None:
        # No database: there are no links to resolve. Same words as an unknown
        # token, on purpose.
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return store


def _active(settings: Settings) -> None:
    if not settings.campaigns_enabled:
        raise HTTPException(status_code=404, detail=NOT_FOUND)


def destination_path(link: dict[str, Any], *, scan_token: Optional[str] = None) -> Optional[str]:
    """Where a link sends the visitor, with the campaign id and the link token
    appended (``?campaign=&link=``) so the door it opens can carry them into the
    captured payload. None when there is nowhere sensible to go."""
    kind = link.get("destination_kind")
    params = {"campaign": link["campaign_id"], "link": link["token"]}
    if kind == cfg.DEST_FORM:
        slug = link.get("destination_target") or ""
        if slug not in cfg.FORM_DESTINATIONS:
            return None
        return f"/{slug}/?{urlencode(params)}"
    if kind == cfg.DEST_PROGRAMME:
        return f"/webinars/?{urlencode(params)}"
    if kind == cfg.DEST_EVENT:
        slug = link.get("destination_slug") or ""
        if not slug:
            # An event that has lost its slug: the programme page still shows it.
            return f"/webinars/?{urlencode(params)}"
        return f"/webinars/{slug}?{urlencode(params)}"
    if kind == cfg.DEST_LANDING:
        if not scan_token:
            return None
        return f"/p/{scan_token}?{urlencode({'link': link['token']})}"
    return None


def _client_address(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "?"


async def _resolve(request: Request, token: str, scan_token: Optional[str]) -> RedirectResponse:
    settings = get_settings()
    _active(settings)
    if not looks_like_token(token) or (scan_token is not None and not looks_like_token(scan_token)):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    store = _store(request)
    link = await store.get_link_by_token(token)
    if link is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    target = destination_path(link, scan_token=scan_token)
    if target is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    try:
        await store.record_visit(
            link, address=_client_address(request),
            user_agent=request.headers.get("user-agent", ""),
            salt=settings.session_secret or settings.espo_api_key or "cbm",
            scan_token=scan_token,
        )
    except Exception as exc:  # noqa: BLE001 — the visitor still gets through
        log.warning("campaign link visit not recorded for %s: %s", token, exc)
    # 302, not 307/308: the destination can be corrected after the card is
    # printed, so nothing may cache it as permanent.
    return RedirectResponse(url=target, status_code=302, headers={"Cache-Control": "no-store"})


@public_router.get("/c/{token}", include_in_schema=False)
async def resolve_link(token: str, request: Request):
    return await _resolve(request, token.lower(), None)


@public_router.get("/c/{token}/{scan_token}", include_in_schema=False)
async def resolve_card(token: str, scan_token: str, request: Request):
    return await _resolve(request, token.lower(), scan_token.lower())


@public_router.get("/c/{token}/{scan_token}/qr.png", include_in_schema=False)
async def card_qr(token: str, scan_token: str, request: Request):
    """The card's QR image, keyed on the link and the card token — for a vendor
    template that fetches its image by address. The image encodes the card's
    own resolve address; nothing is read from the CRM."""
    settings = get_settings()
    _active(settings)
    if not (looks_like_token(token) and looks_like_token(scan_token)):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    store = _store(request)
    link = await store.get_link_by_token(token.lower())
    if link is None or link.get("destination_kind") != cfg.DEST_LANDING:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    base = (settings.app_base_url or "").rstrip("/") or str(request.base_url).rstrip("/")
    png = qr_png(f"{base}/c/{token.lower()}/{scan_token.lower()}")
    return Response(png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@public_router.get("/api/campaigns/public/{campaign_id}", include_in_schema=False)
async def campaign_name(campaign_id: str, request: Request) -> dict[str, Any]:
    """The banner's lookup: ``{"campaign": {"id", "name"}}`` or 404. Read under
    the org-wide API key; 404 on anything it cannot resolve, a CRM outage
    included — a bad id never breaks the form that asked."""
    settings = get_settings()
    _active(settings)
    if not _RECORD_ID.match(campaign_id or ""):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    factory = getattr(request.app.state, "events_client_factory", None)
    found = None
    if factory is not None:
        try:
            row = await factory().get(cfg.CAMPAIGN, campaign_id, select="id,name,campaignStatus")
            if row and row.get("id") and row.get("campaignStatus") != cfg.STATUS_CANCELLED:
                found = {"id": row["id"], "name": row.get("name") or ""}
        except EspoError as exc:
            log.info("campaign lookup %s failed: %s", campaign_id, exc)
        except Exception as exc:  # noqa: BLE001 — degrade, never 500
            log.warning("campaign lookup %s errored: %s", campaign_id, exc)
    if not found:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return {"campaign": found}


@public_router.get("/api/campaigns/prospect/{prospect_id}", include_in_schema=False)
async def prospect_printed(prospect_id: str, request: Request) -> dict[str, Any]:
    """The standard forms' prefill after a landing-page handoff: ONLY the
    business name and the mailing address — what the card printed (ruling 16
    applies to the prefill as it does to the page). Never a person's details."""
    settings = get_settings()
    _active(settings)
    if not _RECORD_ID.match(prospect_id or ""):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    factory = getattr(request.app.state, "events_client_factory", None)
    if factory is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    try:
        row = await factory().get(
            cfg.PROSPECT, prospect_id,
            select="id,businessName,name,mailingAddressStreet,mailingAddressCity,"
                   "mailingAddressState,mailingAddressPostalCode,website")
    except EspoError as exc:
        log.info("prospect lookup %s failed: %s", prospect_id, exc)
        row = None
    except Exception as exc:  # noqa: BLE001
        log.warning("prospect lookup %s errored: %s", prospect_id, exc)
        row = None
    if not row or not row.get("id"):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return {"prospect": {
        "id": row["id"],
        "businessName": row.get("businessName") or row.get("name") or "",
        "street": row.get("mailingAddressStreet") or "", "city": row.get("mailingAddressCity") or "",
        "state": row.get("mailingAddressState") or "", "zip": row.get("mailingAddressPostalCode") or "",
        "website": row.get("website") or "",
    }}


@public_router.post("/api/campaigns/postal/events", include_in_schema=False)
async def postal_events(request: Request) -> dict[str, Any]:
    """The mail vendor's delivery and return events (build plan § 3.2, ruling
    15). Signature-verified over the raw body, otherwise unauthenticated; 404 in
    the usual words until a webhook secret is configured. Each event lands on
    its touch under the org-wide key; a piece we do not know is acknowledged
    and ignored (the vendor retries on anything else)."""
    settings = get_settings()
    _active(settings)
    if not settings.postal_webhook_secret:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    from core.postal import PostalSignatureError, make_client
    from . import postcard

    raw = await request.body()
    vendor = make_client(settings)
    try:
        events = vendor.parse_events(headers=dict(request.headers), body=raw,
                                     secret=settings.postal_webhook_secret)
    except PostalSignatureError as exc:
        log.warning("postal event refused: %s", exc)
        raise HTTPException(status_code=401, detail="The event's signature does not verify.")
    except ValueError:
        raise HTTPException(status_code=400, detail="The event body is not JSON.")
    factory = getattr(request.app.state, "events_client_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="No CRM client.")
    client = factory()
    results = []
    for ev in events:
        try:
            results.append(await postcard.apply_event(client, piece_id=ev.piece_id, kind=ev.kind,
                                                      vendor_status=ev.vendor_status))
        except EspoError as exc:
            log.warning("postal event for piece %s failed: %s", ev.piece_id, exc)
            results.append({"applied": False, "reason": "CRM write failed"})
    return {"received": len(events), "results": results}


# --- the texting service's callbacks (rulings 38, 39) ----------------------------------

async def _twilio_form(request: Request, settings) -> dict[str, str]:
    """The posted form, verified against Twilio's signature over the address
    Twilio called — the deployment's public address, since the request reaches
    us through the edge — and every POST parameter. 404 in the usual words
    until the real service is configured; 401 on a bad signature."""
    _active(settings)
    if not settings.campaigns_sms or settings.sms_provider != "twilio" or not settings.sms_auth_token:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    from core.sms import SmsSignatureError, verify_twilio_signature

    # Parsed by hand: python-multipart is not installed, and Twilio posts
    # application/x-www-form-urlencoded.
    from urllib.parse import parse_qsl
    form = dict(parse_qsl((await request.body()).decode("utf-8", "replace"), keep_blank_values=True))
    base = (settings.app_base_url or str(request.base_url)).rstrip("/")
    try:
        verify_twilio_signature(settings.sms_auth_token, base + request.url.path, form,
                                request.headers.get("X-Twilio-Signature", ""))
    except SmsSignatureError as exc:
        log.warning("texting callback refused: %s", exc)
        raise HTTPException(status_code=401, detail="The request's signature does not verify.")
    return form


def _crm(request: Request):
    factory = getattr(request.app.state, "events_client_factory", None)
    if factory is None:
        raise HTTPException(status_code=503, detail="No CRM client.")
    return factory()


@public_router.post("/api/campaigns/sms/inbound", include_in_schema=False)
async def sms_inbound(request: Request) -> Response:
    """A reply to a campaign text. A STOP reply opts the number out at once
    (ruling 38); anything else is logged and left (no conversation is kept).
    Answers an empty TwiML document, so the service sends nothing back of ours
    (its own STOP confirmation is the carrier's)."""
    settings = get_settings()
    form = await _twilio_form(request, settings)
    from core.sms import is_stop_reply
    from . import sms

    sender, body = form.get("From", ""), form.get("Body", "")
    if is_stop_reply(body):
        try:
            changed = await sms.apply_stop(_crm(request), sender)
            log.info("texting: STOP from …%s opted out %s contact(s)", sender[-4:], len(changed))
        except EspoError as exc:
            log.warning("texting: STOP from …%s could not be written: %s", sender[-4:], exc)
            raise HTTPException(status_code=502, detail="The opt-out could not be recorded; retry.")
    else:
        log.info("texting: a reply from …%s that is not an opt-out (%s characters) — not kept", sender[-4:], len(body))
    return Response('<?xml version="1.0" encoding="UTF-8"?><Response></Response>', media_type="text/xml")


@public_router.post("/api/campaigns/sms/status", include_in_schema=False)
async def sms_status(request: Request) -> dict[str, Any]:
    """The service's delivery report for one text."""
    settings = get_settings()
    form = await _twilio_form(request, settings)
    from . import sms

    try:
        return await sms.apply_status(_crm(request), message_id=form.get("MessageSid", ""),
                                      status=form.get("MessageStatus", ""), error_code=form.get("ErrorCode", ""))
    except EspoError as exc:
        log.warning("texting status for %s failed: %s", form.get("MessageSid"), exc)
        raise HTTPException(status_code=502, detail="The report could not be recorded; retry.")
