"""FastAPI routes for the Mentor Admin app (``/mentoradmin/api``).

Same EspoCRM team-based auth as the assignment dashboard, but gated to the
**Mentor Administration Team** and kept in its own session key, so it is
isolated from the assignment tool. All reads/writes run as the logged-in user
(their token) — EspoCRM enforces their edit permissions on CMentorProfile.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from assignments import service as assign_service
from assignments.auth import (
    AuthError,
    authenticate,
    clear_session,
    current_user,
    session_expired,
    set_session,
)
from assignments.espo_user import client_for
from core.config import Settings, get_settings
from core.espo import EspoClient, EspoError

from . import service

router = APIRouter(prefix="/mentoradmin/api", tags=["mentoradmin"])

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
        return await service.get_mentor(client, mentor_id)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load mentor")


def _provision_client(settings: Settings):
    """Privileged backend client for user provisioning, or None when disabled.

    Uses the service API key (not the staff user's token), so provisioning never
    needs the logged-in user to have user-create rights. Gated on
    ``mentor_provision_users`` and a real (non-dry-run) API key.
    """
    if not settings.mentor_provision_users or settings.espo_dry_run or not settings.espo_api_key:
        return None
    return EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )


@router.put("/mentors/{mentor_id}")
async def mentor_update(mentor_id: str, body: UpdateIn, request: Request) -> dict:
    settings = get_settings()
    user = _require_user(request)
    client = client_for(settings, user)
    try:
        return await service.update_mentor(
            client, mentor_id, body.changes,
            team_name=settings.mentor_team_name,
            admin_client=_provision_client(settings),
        )
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not save mentor")
