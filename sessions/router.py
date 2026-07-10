"""FastAPI routes for a Session Management domain (``/{slug}/api``).

:func:`make_router` builds one router per domain from a
:class:`sessions.config.DomainConfig`. All three share this code; only the
config differs. Uses the shared staff session (sign in once at the portal),
gated per request to the domain's team (admins always pass). All reads/writes
run as the logged-in user, so EspoCRM enforces their ACL.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from assignments.auth import clear_session, current_user, is_member, session_expired
from assignments.espo_user import client_for
from core.config import get_settings
from core.espo import EspoError

from . import details as details_svc
from . import service
from .config import DomainConfig

log = logging.getLogger("cbm_intake.sessions")


class SessionIn(BaseModel):
    changes: dict = {}
    # Contact ids for the session's attendees. None => leave attendees unchanged
    # (on edit); [] => clear them. Sent by the frontend attendee picker.
    attendees: Optional[list[str]] = None


class CoMentorIn(BaseModel):
    mentorProfileId: str


class DetailsSaveIn(BaseModel):
    changes: dict = {}


# Phase-one detail tabs, common to all three domains. Overview + Sessions are
# built; Details (full company/contact/profile fields, editable), Communications
# (email/SMS threads), and Documents (uploads) are placeholders for now.
COMMON_DETAIL_TABS = [
    {"key": "overview", "label": "Overview"},
    {"key": "details", "label": "Details"},
    {"key": "sessions", "label": "Sessions"},
    {"key": "communications", "label": "Communications", "placeholder": True},
    {"key": "documents", "label": "Documents", "placeholder": True},
]


def make_router(cfg: DomainConfig) -> APIRouter:
    router = APIRouter(prefix=f"/{cfg.slug}/api", tags=[cfg.slug])

    def _allowed_teams() -> list[str]:
        return getattr(get_settings(), cfg.allowed_teams_attr)

    def _require_user(request: Request) -> dict:
        """Shared staff session + this domain's team gate (401 = not signed in →
        the frontend sends the user to the portal; 403 = signed in but not on the
        domain's team; admins always pass)."""
        user = current_user(request)
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated.")
        teams = _allowed_teams()
        if not is_member(user, teams):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Your account is not authorized to use {cfg.title} "
                    f"(requires the {', '.join(teams) or 'admin'} team)."
                ),
            )
        return user

    def _crm_failure(request: Request, exc: EspoError, message: str) -> HTTPException:
        if session_expired(exc):
            clear_session(request)
            return HTTPException(status_code=401, detail="Your session has expired — please sign in again.")
        log.warning("%s (%s): %s", message, cfg.slug, exc)
        return HTTPException(status_code=502, detail=f"{message}: {exc}")

    @router.get("/session")
    async def session(request: Request) -> dict:
        user = _require_user(request)
        return {
            "userName": user["userName"],
            "name": user["name"],
            "isAdmin": user["isAdmin"],
            "domain": cfg.slug,
            "title": cfg.title,
            "subtitle": cfg.subtitle,
            "parentLabel": cfg.parent_label,
            "columns": [{"key": c.key, "label": c.label} for c in cfg.list_columns],
            "emptyMessage": cfg.empty_message,
            "detailTabs": COMMON_DETAIL_TABS,
            "supportsComentor": cfg.supports_comentor,
            "defaultSessionType": cfg.default_session_type,
        }

    @router.post("/logout")
    async def logout(request: Request) -> dict:
        clear_session(request)
        return {"status": "ok"}

    @router.get("/records")
    async def records(request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await service.list_records(cfg, client, user)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load records")

    @router.get("/fields")
    async def fields(request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return {
                "fields": service.field_spec(),
                "options": await service.field_options(client),
                "required": await service.field_required(client),
            }
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load field options")

    @router.get("/records/{parent_id}")
    async def record_detail(parent_id: str, request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await service.get_detail(cfg, client, parent_id)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load record")

    @router.get("/details/{parent_id}")
    async def details(parent_id: str, request: Request) -> dict:
        """The Details tab: editable field sections for the company, profile, and
        related contacts behind this record."""
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await details_svc.build_details(cfg, client, parent_id, user.get("userId"))
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load details")

    @router.put("/details/{entity}/{record_id}")
    async def save_details(entity: str, record_id: str, body: DetailsSaveIn, request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await details_svc.save_details(client, entity, record_id, body.changes)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not save details")

    @router.get("/peek/{entity}/{record_id}")
    async def peek(entity: str, record_id: str, request: Request) -> dict:
        """Pop-up detail for a linked contact / company / client on the Overview."""
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await service.peek(client, entity, record_id)
        except service.SessionError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load details")

    @router.get("/sessions/{session_id}")
    async def session_detail(session_id: str, request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await service.get_session(client, session_id)
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not load session")

    @router.post("/records/{parent_id}/sessions")
    async def create_session(parent_id: str, body: SessionIn, request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await service.create_session(
                cfg, client, parent_id, body.changes, body.attendees,
                owner_user_id=user["userId"],
            )
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not create session")

    @router.put("/sessions/{session_id}")
    async def update_session(session_id: str, body: SessionIn, request: Request) -> dict:
        user = _require_user(request)
        client = client_for(get_settings(), user)
        try:
            return await service.update_session(
                client, session_id, body.changes, body.attendees
            )
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not save session")

    if cfg.supports_comentor:

        @router.get("/mentors")
        async def mentors(request: Request) -> dict:
            user = _require_user(request)
            client = client_for(get_settings(), user)
            try:
                return {"mentors": await service.mentor_options(client)}
            except EspoError as exc:
                raise _crm_failure(request, exc, "Could not load mentors")

        @router.post("/records/{parent_id}/comentors")
        async def add_comentor(parent_id: str, body: CoMentorIn, request: Request) -> dict:
            user = _require_user(request)
            client = client_for(get_settings(), user)
            try:
                await service.add_comentor(client, parent_id, body.mentorProfileId)
                return {"status": "ok"}
            except EspoError as exc:
                raise _crm_failure(request, exc, "Could not add co-mentor")

    return router
