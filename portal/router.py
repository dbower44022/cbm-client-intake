"""FastAPI routes for the portal (``/api/portal``).

The portal is the single sign-in for everything: login accepts any **active
internal CRM user** (no team gate — ``authenticate(..., gate=False)``), stores
the user + their team names in the shared staff session, and returns the links
that user is entitled to. The staff apps stay individually protected — each
enforces its own team per request — so the portal listing is a convenience,
never the security boundary.

Entitlements (team names come from settings, so they match the app gates):
- any signed-in user: the public intake-form links
- Mentor Team: a link to the CRM itself + ``/mentorprofile/`` (My Mentor Profile)
- Client Administration Team: ``/assignments/``
- Mentor Administration Team: ``/mentoradmin/``
- Marketing Admin Team: ``/ops/`` (Submission Admin)
- CRM admins: everything.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from assignments.auth import (
    AuthError,
    authenticate,
    clear_session,
    current_user,
    is_member,
    refresh_membership,
    request_password_reset,
    set_session,
)
from core.config import Settings, get_settings

log = logging.getLogger("cbm_intake.portal")

router = APIRouter(prefix="/api/portal", tags=["portal"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class ForgotPasswordIn(BaseModel):
    username: str = Field(min_length=1)
    emailAddress: str = Field(min_length=3)


def _forms(request: Request) -> list[dict[str, str]]:
    """The public intake-form links (from the registered specs)."""
    specs = getattr(request.app.state, "form_specs", []) or []
    return [
        {"title": s.title, "url": f"/{s.slug}/"}
        for s in specs
        if s.frontend_dir is not None
    ]


def _apps_for(user: dict[str, Any], settings: Settings) -> list[dict[str, str]]:
    """The staff-app links this user's teams entitle them to (admins: all)."""
    apps = []
    if is_member(user, settings.assign_allowed_teams_list, settings.assign_allowed_roles_list):
        apps.append({"title": "Client Administration", "url": "/assignments/"})
    if is_member(user, settings.mentor_admin_allowed_teams_list):
        apps.append({"title": "Mentor Administration", "url": "/mentoradmin/"})
    if is_member(user, settings.ops_allowed_teams_list):
        apps.append({"title": "Submission Admin", "url": "/ops/"})
    # A mentor's self-service profile editor (own record + website preview).
    if is_member(user, settings.mentor_profile_allowed_teams_list):
        apps.append({"title": "My Mentor Profile", "url": "/mentorprofile/"})
    # Session Management tools — each gated to its own team.
    if is_member(user, settings.session_mentor_allowed_teams_list):
        apps.append({"title": "Mentor Sessions", "url": "/mentorsessions/"})
    if is_member(user, settings.session_partner_allowed_teams_list):
        apps.append({"title": "Partner Sessions", "url": "/partnersessions/"})
    if is_member(user, settings.session_sponsor_allowed_teams_list):
        apps.append({"title": "Sponsor Sessions", "url": "/sponsorsessions/"})
    return apps


def _home_payload(user: dict[str, Any], request: Request, settings: Settings) -> dict:
    mentor = is_member(user, [settings.mentor_team_name])
    return {
        "user": {
            "userName": user["userName"],
            "name": user.get("name") or user["userName"],
            "isAdmin": bool(user.get("isAdmin")),
        },
        "apps": _apps_for(user, settings),
        # The CRM itself, for mentors (and admins) — the deploy's own target,
        # so the crm-test app links to crm-test and prod to production.
        "crmUrl": settings.espo_base_url if mentor else None,
        "forms": _forms(request),
    }


@router.post("/login")
async def login(body: LoginIn, request: Request) -> dict:
    settings = get_settings()
    try:
        # gate=False: any active internal user may sign in to the portal; what
        # they can DO is decided per app, per request (is_member).
        user = await authenticate(settings, body.username, body.password, gate=False)
    except AuthError as exc:
        # Audit: failed sign-ins were previously invisible (the staff front
        # door had no log at all). Username only — never the password.
        log.warning("portal login FAILED for %s: %s", body.username, exc)
        raise HTTPException(status_code=401, detail=str(exc))
    set_session(request, user)
    log.info("portal login ok: %s (admin=%s)", user["userName"], user.get("isAdmin"))
    return _home_payload(user, request, settings)


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordIn) -> dict:
    """Email the user a CRM password-reset link (EspoCRM's own recovery flow).

    Unauthenticated by nature; the CRM does the matching, throttling, and the
    email itself. Failures come back as a readable ``detail`` string (exact
    messages per the project error policy — the CRM's own login page reports
    not-found the same way).
    """
    settings = get_settings()
    try:
        await request_password_reset(
            settings, body.username.strip(), body.emailAddress.strip()
        )
    except AuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "status": "ok",
        "message": (
            "A password reset email is on its way. Follow the link in it to "
            "choose a new password, then come back here to sign in."
        ),
    }


@router.get("/session")
async def session(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    settings = get_settings()
    # Re-read team/role membership from the CRM on every session restore: the
    # cookie caches teams at login time, so without this a team granted (or
    # removed) in the CRM never showed until the user signed out and back in.
    # The refreshed session is re-saved, so the staff apps' per-request gates
    # see the same up-to-date membership.
    try:
        user = await refresh_membership(settings, user)
    except AuthError as exc:
        clear_session(request)
        raise HTTPException(status_code=401, detail=str(exc))
    set_session(request, user)
    return _home_payload(user, request, settings)


@router.post("/logout")
async def logout(request: Request) -> dict:
    clear_session(request)
    return {"status": "ok"}
