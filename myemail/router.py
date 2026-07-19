"""FastAPI routes for My Email (``/myemail/api``).

The unified inbox: portal SSO session, gated to members of ANY session-tool
team (admins pass) — the row scope is the user's own managed records either
way (myemail.service). Opening a thread stamps it read; "Mark all read"
stamps the whole listed page.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from assignments.auth import clear_session, current_user, is_member, session_expired
from assignments.espo_user import client_for
from comms import service as comms_service
from core.config import get_settings
from core.espo import EspoError, forbidden_hint

from . import service

log = logging.getLogger("cbm_intake.myemail")

router = APIRouter(prefix="/myemail/api", tags=["myemail"])

TITLE = "My Email"


class MarkAllIn(BaseModel):
    conversationIds: list[str] = Field(default_factory=list)


def _require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    settings = get_settings()
    allowed = (
        is_member(user, settings.session_mentor_allowed_teams_list)
        or is_member(user, settings.session_partner_allowed_teams_list)
        or is_member(user, settings.session_sponsor_allowed_teams_list)
    )
    if not allowed:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Your account is not authorized to use {TITLE} "
                "(requires one of the management-tool teams)."
            ),
        )
    return user


def _comms_ready():
    settings = get_settings()
    if not settings.gmail_sync:
        raise HTTPException(
            status_code=503, detail="The email integration isn't enabled."
        )
    store = comms_service.get_store(settings)
    if store is None:
        raise HTTPException(
            status_code=503, detail="The email integration needs the database."
        )
    return settings, store


def _crm_failure(request: Request, exc: EspoError, message: str) -> HTTPException:
    if session_expired(exc):
        clear_session(request)
        return HTTPException(
            status_code=401, detail="Your session has expired — please sign in again."
        )
    actor = (current_user(request) or {}).get("userName", "?")
    log.warning("%s (user=%s): %s", message, actor, exc)
    hint = forbidden_hint(exc)
    if hint:
        return HTTPException(
            status_code=403,
            detail=f"{message}: your CRM role is missing {hint} — ask CBM staff to grant it.",
        )
    return HTTPException(status_code=502, detail=f"{message}: {exc}")


@router.get("/session")
async def session(request: Request) -> dict:
    user = _require_user(request)
    return {
        "userName": user["userName"],
        "name": user.get("name") or user["userName"],
        "isAdmin": bool(user.get("isAdmin")),
        "title": TITLE,
        "commsEnabled": get_settings().gmail_sync,
    }


@router.post("/logout")
async def logout(request: Request) -> dict:
    clear_session(request)
    return {"status": "ok"}


@router.get("/inbox")
async def inbox(request: Request) -> dict:
    user = _require_user(request)
    settings, store = _comms_ready()
    client = client_for(settings, user)
    try:
        return await service.build_inbox(settings, client, store, user)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load your email")


@router.get("/conversations/{conversation_id}")
async def conversation(conversation_id: str, request: Request) -> dict:
    """The thread — and the read stamp: opening it marks it seen."""
    user = _require_user(request)
    settings, store = _comms_ready()
    client = client_for(settings, user)
    try:
        thread = await comms_service.get_conversation(client, conversation_id)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load the conversation")
    thread["records"] = await service.conversation_records(client, conversation_id)
    try:
        await store.mark_seen(user["userName"], conversation_id)
    except Exception as exc:  # noqa: BLE001 — a read stamp never blocks reading
        log.warning("mark_seen failed for %s: %s", user["userName"], exc)
    return thread


@router.post("/markallread")
async def mark_all_read(body: MarkAllIn, request: Request) -> dict:
    user = _require_user(request)
    _, store = _comms_ready()
    ids = [str(i) for i in body.conversationIds][:200]
    try:
        await store.mark_many_seen(user["userName"], ids)
    except Exception as exc:  # noqa: BLE001
        log.warning("mark_many_seen failed for %s: %s", user["userName"], exc)
        raise HTTPException(status_code=502, detail="Couldn't save the read state — try again.")
    return {"status": "ok", "marked": len(ids)}
