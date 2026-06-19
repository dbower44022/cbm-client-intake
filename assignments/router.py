"""FastAPI routes for the mentor assignment dashboard (``/assignments/api``)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core.config import get_settings
from core.espo import EspoError

from . import auth, service
from .espo_user import client_for

router = APIRouter(prefix="/assignments/api", tags=["assignments"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AssignIn(BaseModel):
    mentorProfileId: str = Field(min_length=1)


def _require_user(request: Request) -> dict:
    user = auth.current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user


@router.post("/login")
async def login(body: LoginIn, request: Request) -> dict:
    settings = get_settings()
    try:
        user = await auth.authenticate(settings, body.username, body.password)
    except auth.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    auth.set_session(request, user)
    return {"userName": user["userName"], "name": user["name"], "isAdmin": user["isAdmin"]}


@router.post("/logout")
async def logout(request: Request) -> dict:
    auth.clear_session(request)
    return {"status": "ok"}


@router.get("/session")
async def session(request: Request) -> dict:
    user = _require_user(request)
    return {"userName": user["userName"], "name": user["name"], "isAdmin": user["isAdmin"]}


@router.get("/engagements")
async def engagements(
    request: Request,
    status: list[str] | None = Query(default=None),
) -> dict:
    user = _require_user(request)
    client = client_for(get_settings(), user)
    # Keep only known statuses; default to Submitted (the primary triage view).
    statuses = [s for s in (status or []) if s in service.ENGAGEMENT_STATUSES]
    if not statuses:
        statuses = [service.STATUS_SUBMITTED]
    try:
        rows = await service.list_engagements(client, statuses)
    except EspoError as exc:
        raise HTTPException(status_code=502, detail=f"Could not load engagements: {exc}")
    return {
        "engagements": rows,
        "allStatuses": service.ENGAGEMENT_STATUSES,
        "selectedStatuses": statuses,
    }


@router.get("/mentors")
async def mentors(request: Request, all_: bool = Query(default=False, alias="all")) -> dict:
    """Eligible mentors (assign dropdown) by default; the full roster with ?all=true."""
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        rows = await (
            service.list_all_mentors(client) if all_
            else service.list_eligible_mentors(client)
        )
        return {"mentors": rows}
    except EspoError as exc:
        raise HTTPException(status_code=502, detail=f"Could not load mentors: {exc}")


@router.get("/engagements/{engagement_id}")
async def engagement_detail(engagement_id: str, request: Request) -> dict:
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        return await service.get_engagement_detail(client, engagement_id)
    except EspoError as exc:
        raise HTTPException(status_code=502, detail=f"Could not load engagement: {exc}")


@router.post("/engagements/{engagement_id}/assign")
async def assign(engagement_id: str, body: AssignIn, request: Request) -> dict:
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        return await service.assign_engagement(client, engagement_id, body.mentorProfileId)
    except service.AssignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise HTTPException(status_code=502, detail=f"Assignment failed: {exc}")
