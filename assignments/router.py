"""FastAPI routes for the mentor assignment dashboard (``/assignments/api``)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from core.config import get_settings
from core.espo import EspoError, forbidden_hint, is_forbidden, validation_message

from . import auth, service
from .espo_user import client_for

router = APIRouter(prefix="/assignments/api", tags=["assignments"])


class AssignIn(BaseModel):
    mentorProfileId: str = Field(min_length=1)


class NotesIn(BaseModel):
    # Empty string is a valid value — it clears the notes.
    notes: str = Field(default="", max_length=65535)


def _require_user(request: Request) -> dict:
    """The shared staff session + THIS app's team gate, per request.

    Sign-in happens once at the portal (`/`, ungated); authorization is
    enforced here: the user must be an admin, in an ASSIGN_ALLOWED_TEAMS team,
    or hold an ASSIGN_ALLOWED_ROLES role. 401 = not signed in (the frontend
    sends the user to the portal); 403 = signed in but not entitled to this app.
    """
    user = auth.current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    settings = get_settings()
    if not auth.is_member(
        user, settings.assign_allowed_teams_list, settings.assign_allowed_roles_list
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Your account is not authorized to use Client Administration "
                f"(requires the {', '.join(settings.assign_allowed_teams_list) or 'admin'} team)."
            ),
        )
    return user


def _crm_failure(request: Request, exc: EspoError, message: str) -> HTTPException:
    """Turn a per-user CRM error into the right HTTP response. An expired token
    clears the (shared staff) session and returns 401 so the UI re-prompts login,
    rather than a confusing 502."""
    if auth.session_expired(exc):
        auth.clear_session(request)
        return HTTPException(
            status_code=401, detail="Your session has expired — please sign in again."
        )
    # A CRM validation rejection is the caller's data, not a server fault —
    # answer with a readable 400 naming the field, never a raw 502/504.
    friendly = validation_message(exc)
    if friendly:
        return HTTPException(status_code=400, detail=friendly)
    # A CRM 403 is a permission gap — name the exact missing grant (Doug's
    # ask 2026-07-16) so the CRM admin knows what to add.
    if is_forbidden(exc):
        hint = forbidden_hint(exc)
        return HTTPException(
            status_code=403,
            detail=(
                f"{message}: your CRM role is missing {hint} — "
                "ask CBM staff to grant it."
                if hint else
                f"{message}: your account doesn't have permission to do this "
                "in the CRM — ask CBM staff if you need it."
            ),
        )
    return HTTPException(status_code=502, detail=f"{message}: {exc}")


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
        raise _crm_failure(request, exc, "Could not load engagements")
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
        # {"mentors": [...], "metricsAvailable": bool} — served as-is.
        return await (
            service.list_all_mentors(client) if all_
            else service.list_eligible_mentors(client)
        )
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load mentors")


@router.get("/engagements/{engagement_id}")
async def engagement_detail(engagement_id: str, request: Request) -> dict:
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        return await service.get_engagement_detail(client, engagement_id)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not load engagement")


@router.put("/engagements/{engagement_id}/notes")
async def update_notes(engagement_id: str, body: NotesIn, request: Request) -> dict:
    """Save the grid's internal process notes (``CEngagement.description``)."""
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        return await service.update_engagement_notes(client, engagement_id, body.notes)
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not save notes")


@router.post("/engagements/{engagement_id}/assign")
async def assign(engagement_id: str, body: AssignIn, request: Request) -> dict:
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        result = await service.assign_engagement(client, engagement_id, body.mentorProfileId)
    except service.AssignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Assignment failed")
    # DOC-09: the assigned mentor gains the engagement folder's Drive Commenter
    # grant in the same action that grants the entitlement (no-op until the
    # record has a folder). Best-effort — never fails the assignment; the
    # nightly reconciliation is the backstop.
    from docs import grants as doc_grants

    await doc_grants.sync_record_grants_safe(
        get_settings(), service.ENGAGEMENT, engagement_id
    )
    return result


@router.post("/engagements/{engagement_id}/reassign")
async def reassign(engagement_id: str, body: AssignIn, request: Request) -> dict:
    """Replace the engagement's primary mentor (Reassign Mentor). The stream
    note names the acting user — 'Mentor X was replaced with Mentor Y … by
    user NAME'."""
    user = _require_user(request)
    client = client_for(get_settings(), user)
    try:
        result = await service.reassign_engagement(
            client, engagement_id, body.mentorProfileId, actor=user.get("name")
        )
    except service.AssignError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure(request, exc, "Reassignment failed")
    # DOC-09: re-derive the engagement folder's Drive grants (new mentor gains,
    # the replaced mentor loses). Best-effort, like the assign path.
    from docs import grants as doc_grants

    await doc_grants.sync_record_grants_safe(
        get_settings(), service.ENGAGEMENT, engagement_id
    )
    return result


# Quick-send email (the email-address links product-wide): GET /mailbox +
# POST /sendmail, behind this app's own gate. See comms/quicksend.py.
from comms.quicksend import register_quicksend  # noqa: E402  (needs router + helpers above)

register_quicksend(router, _require_user, client_for, _crm_failure)
