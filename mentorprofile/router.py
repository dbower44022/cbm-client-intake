"""FastAPI routes for My Mentor Profile (``/mentorprofile/api``).

Uses the shared staff session (sign in once at the portal ``/``), gated per
request to the **Mentor Team** (admins always pass). Every endpoint operates on
the caller's OWN profile — no record id is ever taken from the request; the
profile is resolved server-side from the session's user id. All reads/writes
run as the logged-in user (their token), so EspoCRM enforces their ACL.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from assignments.auth import clear_session, current_user, is_member, session_expired
from assignments.espo_user import client_for
from core.config import get_settings
from core.espo import EspoError, validation_message

from . import service

router = APIRouter(prefix="/mentorprofile/api", tags=["mentorprofile"])
log = logging.getLogger("cbm_intake.mentorprofile")


class UpdateIn(BaseModel):
    changes: dict


class PhotoIn(BaseModel):
    filename: str = ""
    contentType: str = Field(min_length=1)
    dataBase64: str = Field(min_length=1, max_length=service.MAX_PHOTO_B64_CHARS)


def _require_user(request: Request) -> dict:
    """The shared staff session + THIS app's team gate, per request (401 = not
    signed in — the frontend sends the user to the portal; 403 = signed in but
    not on the Mentor Team; admins always pass)."""
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    settings = get_settings()
    if not is_member(user, settings.mentor_profile_allowed_teams_list):
        raise HTTPException(
            status_code=403,
            detail=(
                "Your account is not authorized to use My Mentor Profile "
                f"(requires the {', '.join(settings.mentor_profile_allowed_teams_list) or 'admin'} team)."
            ),
        )
    return user


def _crm_failure(request: Request, exc: EspoError, message: str) -> HTTPException:
    if session_expired(exc):
        clear_session(request)
        return HTTPException(status_code=401, detail="Your session has expired — please sign in again.")
    # Log the full CRM error (includes the response body) so failures like a
    # value rejected by EspoCRM are diagnosable from the run logs.
    log.warning("%s: %s", message, exc)
    # A CRM validation rejection is the caller's data, not a server fault —
    # answer with a readable 400 naming the field, never a raw 502/504.
    friendly = validation_message(exc)
    if friendly:
        return HTTPException(status_code=400, detail=friendly)
    return HTTPException(status_code=502, detail=f"{message}: {exc}")


@router.get("/session")
async def session(request: Request) -> dict:
    user = _require_user(request)
    return {"userName": user["userName"], "name": user["name"], "isAdmin": user["isAdmin"]}


@router.post("/logout")
async def logout(request: Request) -> dict:
    clear_session(request)
    return {"status": "ok"}


@router.get("/fields")
async def fields(request: Request) -> dict:
    """The editable-field spec + live enum options + required flags."""
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        return {
            "fields": service.PROFILE_FIELDS,
            "options": await service.field_options(client),
            "required": await service.field_required(client),
        }
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load field options")


@router.get("/profile")
async def profile(request: Request) -> dict:
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        return await service.get_own_profile(client, user["userId"])
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load your profile")


@router.put("/profile")
async def profile_update(body: UpdateIn, request: Request) -> dict:
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        return await service.update_own_profile(client, user["userId"], body.changes)
    except service.MentorProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not save your profile")


@router.post("/photo")
async def photo_upload(body: PhotoIn, request: Request) -> dict:
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        return await service.set_own_photo(
            client,
            user["userId"],
            filename=body.filename,
            content_type=body.contentType,
            data_base64=body.dataBase64,
        )
    except service.MentorProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not save your photo")


@router.get("/photo")
async def photo(request: Request) -> Response:
    """The caller's own photo bytes — the app proxies the CRM attachment (the
    browser can't reach EspoCRM directly). 404 when no photo is set, so the
    <img> falls back to its placeholder."""
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        result = await service.get_own_photo(client, user["userId"])
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load your photo")
    if result is None:
        raise HTTPException(status_code=404, detail="No profile photo.")
    data, content_type = result
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "private, no-store"},
    )


@router.delete("/photo")
async def photo_delete(request: Request) -> dict:
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        await service.clear_own_photo(client, user["userId"])
    except service.MentorProfileError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not remove your photo")
    return {"status": "ok"}
