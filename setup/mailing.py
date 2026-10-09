"""Connecting the mailing service — the OAuth2 round trip (plan § 11.3).

Three routes on ``/api/setup/mailing/``, all behind the System Settings gate
(EspoCRM administrators, page switched on):

* ``GET  /connect``    — builds the authorise address and sends the browser there.
* ``GET  /callback``   — the vendor sends the administrator back here with a
  code; verified, exchanged, stored, recorded, and the browser is returned to
  the Settings page's Readiness tab with a one-word outcome in the query.
* ``POST /disconnect`` — deletes the connection row and records the action.

The callback address is what is registered on the vendor's developer
application, so it is built from ``APP_BASE_URL`` (``Settings.mailing_redirect_uri``)
and never from the request — production answers on two hostnames and only one
is registered. The session cookie is SameSite=lax, so the vendor's top-level
redirect carries the administrator's session back to us.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from core import action_log
from core import mailing as mailing_mod
from core.config import get_settings
from core.mailing import MailingError

from .router import _actor, _require_admin

log = logging.getLogger("cbm_intake.setup.mailing")

mailing_router = APIRouter(prefix="/api/setup/mailing", tags=["setup"])

#: Where the browser lands after the round trip, with ``?mailing=<outcome>``.
SETTINGS_PAGE = "/setup/"

ACTION_CONNECTED = "Mailing service connected"
ACTION_DISCONNECTED = "Mailing service disconnected"


def _store(request: Request) -> Optional[mailing_mod.ConnectionStore]:
    return getattr(request.app.state, "mailing_store", None)


def _back(outcome: str, detail: str = "") -> RedirectResponse:
    query = {"mailing": outcome}
    if detail:
        query["detail"] = detail[:300]
    # 303: the callback was a GET and the page is a GET, but never let a
    # browser replay the callback's code on a refresh of the page.
    return RedirectResponse(f"{SETTINGS_PAGE}?{urlencode(query)}#readiness", status_code=303)


def _cannot_connect_reason(settings: Any, store: Any) -> str:
    """Why Connect cannot run yet, in the words the panel shows — or empty."""
    if store is None:
        return "No database is attached, so there is nowhere to hold the connection."
    if store._cipher is None:  # the store refuses tokens without one; say so before the trip
        return ("This deployment has no encryption key (APP_ENCRYPTION_KEY), so the "
                "connection cannot be stored.")
    if not settings.mailing_client_id or not settings.mailing_client_secret:
        return "Set the mailing service client ID and client secret first."
    if not settings.mailing_redirect_uri:
        return ("APP_BASE_URL is not set, so the redirect address cannot be built. "
                "Set it first; the address must match the one registered on the application.")
    if not settings.session_secret:
        return "No session secret is configured, so the authorisation state cannot be signed."
    return ""


async def _log(user: dict[str, Any], action: str, summary: str, details: dict) -> None:
    await action_log.log_action(
        app=action_log.APP_SETUP,
        category=action_log.CAT_CONFIG,
        action=action,
        parent_type="",
        parent_id="",
        summary=summary,
        actor_id=str(user.get("userId") or ""),
        actor_name=_actor(user),
        details=details,
    )


@mailing_router.get("/connect")
async def connect(request: Request) -> RedirectResponse:
    user = _require_admin(request)
    settings = get_settings()
    reason = _cannot_connect_reason(settings, _store(request))
    if reason:
        raise HTTPException(status_code=400, detail=reason)
    state = mailing_mod.sign_state(settings.session_secret, str(user.get("userId") or ""))
    url = mailing_mod.authorize_url(
        settings.mailing_client_id, settings.mailing_redirect_uri, state
    )
    return RedirectResponse(url, status_code=302)


@mailing_router.get("/callback")
async def callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
) -> RedirectResponse:
    user = _require_admin(request)
    settings = get_settings()
    store = _store(request)
    if error:
        # The user declined, or the vendor refused. Nothing to exchange.
        log.info("mailing: authorisation returned error=%s", error)
        return _back("declined", error_description or error)
    try:
        mailing_mod.verify_state(settings.session_secret, state, str(user.get("userId") or ""))
    except MailingError as exc:
        return _back("failed", str(exc))
    if not code:
        return _back("failed", "The mailing service returned no authorisation code.")
    reason = _cannot_connect_reason(settings, store)
    if reason:
        return _back("failed", reason)
    assert store is not None
    try:
        tokens = await mailing_mod.exchange_code(
            settings.mailing_client_id, settings.mailing_client_secret,
            code, settings.mailing_redirect_uri,
        )
    except MailingError as exc:
        return _back("failed", str(exc))

    # The account's name is a nicety for the panel — never fatal.
    label = ""
    try:
        async def _fresh(_force: bool) -> str:
            return tokens.access_token
        client = mailing_mod.MailingClient(_fresh, base_url=settings.mailing_base_url)
        label = await client.account_label()
    except MailingError as exc:
        log.info("mailing: account summary unavailable after connect: %s", exc)

    try:
        await store.save(
            tokens, account_label=label, connected_by=_actor(user), scopes=tokens.scope
        )
    except MailingError as exc:
        return _back("failed", str(exc))
    await _log(user, ACTION_CONNECTED,
               f"Mailing service connected as {label or 'the mailing account'}",
               {"accountLabel": label, "scopes": tokens.scope})
    return _back("connected", label)


@mailing_router.post("/disconnect")
async def disconnect(request: Request) -> dict:
    user = _require_admin(request)
    store = _store(request)
    if store is None:
        raise HTTPException(status_code=400, detail="No database is attached; there is no connection to remove.")
    existed = await store.delete()
    if existed:
        await _log(user, ACTION_DISCONNECTED, "Mailing service disconnected", {})
    return {"ok": True, "removed": bool(existed)}
