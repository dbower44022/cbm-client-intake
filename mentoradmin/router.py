"""FastAPI routes for the Mentor Admin app (``/mentoradmin/api``).

Same EspoCRM team-based auth as the assignment dashboard, but gated to the
**Mentor Administration Team** and kept in its own session key, so it is
isolated from the assignment tool. All reads/writes run as the logged-in user
(their token) — EspoCRM enforces their edit permissions on CMentorProfile.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from assignments import service as assign_service
from assignments.auth import (
    AuthError,
    authenticate,
    clear_session,
    current_user,
    login_token,
    session_expired,
    set_session,
)
from assignments.espo_user import client_for
from core.config import Settings, get_settings
from core.espo import EspoClient, EspoError

from . import service

router = APIRouter(prefix="/mentoradmin/api", tags=["mentoradmin"])
log = logging.getLogger("cbm_intake.mentoradmin")

# Distinct session key so a Mentor-Admin login is separate from /assignments.
SESSION_KEY = "mentoradmin_user"


class LoginIn(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UpdateIn(BaseModel):
    changes: dict


def _require_user(request: Request) -> dict:
    user = current_user(request, SESSION_KEY)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user


def _crm_failure(request: Request, exc: EspoError, message: str) -> HTTPException:
    if session_expired(exc):
        clear_session(request, SESSION_KEY)
        return HTTPException(status_code=401, detail="Your session has expired — please sign in again.")
    # Log the full CRM error (includes the response body) so failures like a
    # value rejected by EspoCRM are diagnosable from the run logs.
    log.warning("%s: %s", message, exc)
    return HTTPException(status_code=502, detail=f"{message}: {exc}")


@router.post("/login")
async def login(body: LoginIn, request: Request) -> dict:
    settings = get_settings()
    try:
        user = await authenticate(
            settings, body.username, body.password,
            allowed_teams=settings.mentor_admin_allowed_teams_list, allowed_roles=[],
        )
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    set_session(request, user, SESSION_KEY)
    return {"userName": user["userName"], "name": user["name"], "isAdmin": user["isAdmin"]}


@router.post("/logout")
async def logout(request: Request) -> dict:
    clear_session(request, SESSION_KEY)
    return {"status": "ok"}


@router.get("/session")
async def session(request: Request) -> dict:
    user = _require_user(request)
    return {"userName": user["userName"], "name": user["name"], "isAdmin": user["isAdmin"]}


@router.get("/mentors")
async def mentors(request: Request) -> dict:
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        return {"mentors": await assign_service.list_all_mentors(client)}
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load mentors")


@router.get("/fields")
async def fields(request: Request) -> dict:
    """The editable-field spec + live enum options, for the detail form."""
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        return {"fields": service.EDITABLE_FIELDS, "options": await service.field_options(client)}
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load field options")


@router.get("/mentors/{mentor_id}")
async def mentor_detail(mentor_id: str, request: Request) -> dict:
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        rec = await service.get_mentor(client, mentor_id)
        comp = await service.check_completeness(client, rec)
        rec["completeness"] = comp
        rec["recordStatus"] = await service.sync_record_status(client, mentor_id, rec, comp["status"])
        return rec
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load mentor")


def _provision_factory(settings: Settings):
    """A lazy login factory for the provisioning admin, or None when disabled.

    EspoCRM only lets admins create Users (API keys can't), so provisioning acts
    as a dedicated admin service account via the App/user token flow — never the
    staff user's token. The returned async callable logs that account in (once,
    when a provisioning transition actually happens) and yields a privileged
    client. Gated on ``mentor_provision_users`` + configured credentials + a real
    (non-dry-run) base.
    """
    if (
        not settings.mentor_provision_users
        or settings.espo_dry_run
        or not (settings.espo_provision_username and settings.espo_provision_password)
    ):
        return None

    async def factory():
        user_name, token = await login_token(
            settings.espo_base_url,
            settings.espo_provision_username,
            settings.espo_provision_password,
            settings.request_timeout_seconds,
        )
        return EspoClient.for_user_token(
            settings.espo_base_url, user_name, token, settings.request_timeout_seconds
        )

    return factory


@router.put("/mentors/{mentor_id}")
async def mentor_update(mentor_id: str, body: UpdateIn, request: Request) -> dict:
    settings = get_settings()
    user = _require_user(request)
    client = client_for(settings, user)
    try:
        result = await service.update_mentor(
            client, mentor_id, body.changes,
            team_name=settings.mentor_team_name,
            admin_client_factory=_provision_factory(settings),
        )
        comp = await service.check_completeness(client, result)
        result["completeness"] = comp
        result["recordStatus"] = await service.sync_record_status(client, mentor_id, result, comp["status"])
        return result
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not save mentor")
