"""FastAPI routes for one Workspace Directory (``/directory/{kind}/api``).

:func:`make_router` builds one router per kind from a
:class:`directory.config.DirectoryConfig`. All three share this code. Uses the
shared staff session (sign in once at the portal), gated per request to the
workspace team (admins always pass). Every read/write runs as the logged-in
user, so EspoCRM enforces their ACL — the team gate is only "who sees the
workspace at all".
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from assignments.auth import clear_session, current_user, is_member, session_expired
from assignments.espo_user import client_for
from core.config import get_settings
from core.espo import EspoError, forbidden_hint, is_forbidden, validation_message

from . import service
from .config import DirectoryConfig

log = logging.getLogger("cbm_intake.directory")


class SaveIn(BaseModel):
    changes: dict = {}


def make_router(cfg: DirectoryConfig) -> APIRouter:
    router = APIRouter(prefix=f"/directory/{cfg.slug}/api", tags=[f"directory-{cfg.slug}"])

    def _allowed_teams() -> list[str]:
        return get_settings().workspace_allowed_teams_list

    def _require_user(request: Request) -> dict:
        user = current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated.")
        teams = _allowed_teams()
        if not is_member(user, teams):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Your account is not authorized to use the {cfg.title} directory "
                    f"(requires the {', '.join(teams) or 'admin'} team)."
                ),
            )
        return user

    def _crm_failure(request: Request, exc: EspoError, message: str) -> HTTPException:
        if session_expired(exc):
            clear_session(request)
            return HTTPException(
                status_code=401, detail="Your session has expired — please sign in again."
            )
        actor = (current_user(request) or {}).get("userName", "?")
        log.warning("%s (%s, user=%s): %s", message, cfg.slug, actor, exc)
        friendly = validation_message(exc)
        if friendly:
            return HTTPException(status_code=400, detail=friendly)
        if is_forbidden(exc):
            hint = forbidden_hint(exc)
            return HTTPException(
                status_code=403,
                detail=(
                    f"{message}: your CRM role is missing {hint} — ask CBM staff to grant it."
                    if hint else
                    f"{message}: your account doesn't have permission to do this in "
                    "the CRM — ask CBM staff if you need it."
                ),
            )
        return HTTPException(status_code=502, detail=f"{message}: {exc}")

    @router.get("/session")
    async def session(request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            filter_defs = await service.filters(client, cfg)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load the directory")
        return {
            "userName": user["userName"],
            "name": user["name"],
            "isAdmin": user["isAdmin"],
            "kind": cfg.slug,
            "title": cfg.title,
            "entity": cfg.entity,
            "editable": cfg.editable,
            "editHandoff": cfg.edit_handoff,
            "filters": filter_defs,
        }

    @router.post("/logout")
    async def logout(request: Request) -> dict:
        clear_session(request)
        return {"status": "ok"}

    @router.get("/records")
    async def records(
        request: Request,
        q: str = "",
        page: int = 1,
        pageSize: int = 50,
        orderBy: str = "",
        order: str = "asc",
        filters: str = "",
    ) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            applied = json.loads(filters) if filters else {}
            if not isinstance(applied, dict):
                applied = {}
        except ValueError:
            applied = {}
        try:
            return await service.list_records(
                client, cfg, q=q, applied_filters=applied,
                page=page, page_size=pageSize,
                order_by=orderBy or None, order=order,
            )
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load the directory")

    @router.get("/records/{record_id}")
    async def record_detail(record_id: str, request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await service.detail(client, cfg, record_id, user.get("userId"))
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load the record")

    @router.put("/records/{record_id}")
    async def save_record(record_id: str, body: SaveIn, request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            result = await service.save(client, cfg, record_id, body.changes)
        except service.DirectoryError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not save the record")
        # Audit: which fields changed (never the values — they may be PII).
        log.info(
            "directory %s save %s/%s by %s (fields: %s)",
            cfg.slug, cfg.entity, record_id, user["userName"],
            ", ".join(sorted(body.changes)) or "-",
        )
        return result

    # /mailbox + /sendmail + /emailwriteback — the shared quick-compose behind
    # every email address shown in the grid/preview/pop-up (product rule: an
    # address is a compose link, not a bare mailto). Falls back to mailto in the
    # frontend when sending is unavailable (GMAIL_SYNC off / no CBM mailbox).
    from comms.quicksend import register_quicksend

    register_quicksend(
        router, _require_user, client_for, _crm_failure, include_mailbox=True
    )

    return router
