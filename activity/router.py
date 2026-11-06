"""FastAPI routes for the activity page (``/activity/api``) — mentor login
integrity step 6 (plan § 4.5).

Behind ``ACTIVITY_PAGE`` (read per request) and gated per request to
``SYSTEM_MANAGEMENT_ALLOWED_TEAMS`` (default "System Management Team");
Administrator-type logins always pass. Every CRM read runs under the
application's key-based account.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from assignments.auth import clear_session, current_user, is_member
from core.config import get_settings

from . import service

router = APIRouter(prefix="/activity/api", tags=["activity"])
log = logging.getLogger("cbm_intake.activity")


def _require_user(request: Request) -> dict:
    """The shared staff session, the switch and this page's team gate, per
    request (401 = not signed in; 404 = switched off; 403 = not on the
    team; administrators always pass)."""
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    settings = get_settings()
    if not settings.activity_page:
        raise HTTPException(status_code=404, detail="The activity page is not switched on.")
    teams = settings.system_management_allowed_teams_list
    if not is_member(user, teams):
        raise HTTPException(status_code=403, detail=(
            "Your account is not authorized to use the activity page "
            f"(requires the {', '.join(teams) or 'admin'} team)."))
    return user


def _key():
    key = service.key_client(get_settings())
    if key is None:
        raise HTTPException(status_code=503, detail="The CRM is not connected on this server.")
    return key


@router.post("/logout")
async def logout(request: Request) -> dict:
    clear_session(request)
    return {"status": "ok"}


@router.get("/session")
async def session(request: Request) -> dict:
    user = _require_user(request)
    return {"userName": user["userName"], "name": user["name"], "isAdmin": user["isAdmin"]}


@router.get("/people")
async def people(request: Request) -> dict:
    _require_user(request)
    try:
        return {"people": await service.people(_key())}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("activity: people list unreadable: %s", exc)
        raise HTTPException(status_code=502, detail="The list of people could not be read from the CRM.")


@router.get("/changes")
async def changes(
    request: Request,
    person: str = Query(default=""),
    since: str = Query(default=""),
    until: str = Query(default=""),
) -> dict:
    """Every change by ``person`` (a login, or "__system__") and/or between
    ``since`` and ``until`` (UTC, ``YYYY-MM-DD HH:MM:SS``)."""
    user = _require_user(request)
    try:
        return await service.activity(person_id=person, since=since, until=until,
                                      viewer=user, key=_key())
    except service.ActivityError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.warning("activity: read failed: %s", exc)
        raise HTTPException(status_code=502, detail="The changes could not be read from the CRM.")
