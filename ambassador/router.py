"""The Ambassador Program's routes (PRD § 3, § 5), all under ``/ambassador/api``.

* The mentor's routes (``AMBASSADOR_ALLOWED_TEAMS``): who is signed in, the
  lookups, saving a report, My activity and a correction.
* The program team's routes (``AMBASSADOR_REVIEW_TEAMS``): the review list,
  Mark done, Link, Create and Dismiss, the target search, and a mentor's
  activities for Mentor Administration's tab (also open to
  ``MENTOR_ADMIN_ALLOWED_TEAMS``).

Everything answers 404 while ``AMBASSADOR_PROGRAM`` is off. The page signs in
through the portal's own ``/api/portal/login`` (the shared sign-in box), so
the cookie is the one every application reads.

**Who a report belongs to is the sign-in**: the server resolves the mentor's
profile from the session, never from the browser.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from assignments.auth import clear_session, current_user, is_member
from assignments.espo_user import client_for
from core.config import Settings, get_settings
from core.branding import render_text
from core.espo import EspoError, forbidden_hint, is_forbidden

from . import config as cfg
from . import lookup, service
from .store import report_store

log = logging.getLogger("cbm_intake.ambassador")

router = APIRouter(prefix="/ambassador/api", tags=["ambassador"])

NOT_ON = "The Ambassador Program is not switched on."


def _crm_failure(what: str, exc: Exception) -> HTTPException:
    log.warning("ambassador: %s failed: %s", what, exc)
    if is_forbidden(exc):
        return HTTPException(status_code=403, detail=forbidden_hint(exc) or (
            f"The CRM refused to {what} for your account."))
    return HTTPException(status_code=502, detail=f"The CRM could not {what} just now. "
                                                 "Try again in a minute.")


def _user(request: Request) -> tuple[dict[str, Any], Settings]:
    settings = get_settings()
    if not settings.ambassador_program:
        raise HTTPException(status_code=404, detail=NOT_ON)
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user, settings


def _mentor(request: Request) -> tuple[dict[str, Any], Settings]:
    user, settings = _user(request)
    teams = settings.ambassador_allowed_teams_list
    if not is_member(user, teams):
        raise HTTPException(status_code=403, detail=(
            "Your account is not set up to log ambassador activities "
            f"(it needs the {', '.join(teams) or 'admin'} team)."))
    return user, settings


def _reviewer(request: Request, *, mentor_admin: bool = False) -> tuple[dict[str, Any], Settings]:
    user, settings = _user(request)
    teams = list(settings.ambassador_review_teams_list)
    if mentor_admin:
        teams += settings.mentor_admin_allowed_teams_list
    if not is_member(user, teams):
        raise HTTPException(status_code=403, detail=(
            "Your account is not on the Ambassador Program team "
            f"(it needs the {', '.join(settings.ambassador_review_teams_list) or 'admin'} team)."))
    return user, settings


def _key(settings: Settings):
    client = service.key_client(settings)
    if client is None:
        raise HTTPException(status_code=503, detail="The CRM is not connected on this server.")
    return client


async def _built(settings: Settings) -> Any:
    client = _key(settings)
    if not await service.available(client):
        raise HTTPException(status_code=503, detail=(
            "The CRM does not have the Ambassador Activity record type yet "
            "(ambassador-activity-crm-handoff.md)."))
    return client


async def _profile_id(settings: Settings, user: dict[str, Any]) -> str:
    """The signed-in mentor's own profile, resolved on the server."""
    from sessions.service import resolve_manager_profile

    try:
        profile = await resolve_manager_profile(client_for(settings, user), user.get("userId") or "")
    except EspoError as exc:
        raise _crm_failure("find your mentor profile", exc)
    if not profile:
        raise HTTPException(status_code=409, detail=(
            "Your sign-in is not linked to a mentor profile, so a report cannot be credited "
            "to you. Ask Mentor Administration to link your profile to your login."))
    return profile


async def _log(user: dict[str, Any], *, action: str, record_id: str, summary: str,
               mentor_id: str = "",
               before: Optional[dict[str, Any]] = None,
               after: Optional[dict[str, Any]] = None) -> None:
    from core.action_log import log_action
    from core.history import field_details

    # The action log's record link has a fixed list of record types and cannot
    # name an Ambassador Activity (the feedback lesson of 11-21-26), so an
    # entry points at the ambassador's mentor profile and names the activity.
    details: dict[str, Any] = {"activityId": record_id}
    if after:
        details["fields"] = field_details(before or {}, after, list(after))
    await log_action(app=cfg.APP, category="Ambassador", action=action,
                     parent_type=cfg.MENTOR if mentor_id else "", parent_id=mentor_id or "",
                     summary=summary, actor_id=user.get("userId") or "",
                     actor_name=user.get("userName") or "", details=details)


# --- who is signed in ----------------------------------------------------------------

@router.get("/session")
async def session(request: Request) -> dict:
    """What the page needs to draw itself. 401 shows the sign-in box."""
    user, settings = _user(request)
    client = service.key_client(settings)
    built = bool(client is not None and await service.available(client))
    return {
        "user": {"name": user.get("name") or user.get("userName") or "",
                 "userName": user.get("userName") or ""},
        "canLog": is_member(user, settings.ambassador_allowed_teams_list),
        "isReviewer": is_member(user, settings.ambassador_review_teams_list),
        "built": built,
        "editDays": settings.ambassador_edit_days,
        "activities": [{"value": v, "label": render_text(cfg.ACTIVITY_LABELS[v], settings),
                        "contact": "none" if v in cfg.NO_CONTACT else
                        ("required" if v in cfg.CONTACT_REQUIRED else "optional")}
                       for v in cfg.ACTIVITY_TYPES],
        "personKinds": [{"value": v, "label": cfg.PERSON_LABELS[v]} for v in cfg.PERSON_KINDS],
        "referralKinds": sorted(cfg.REFERRAL_KINDS),
        "today": date.today().isoformat(),
    }


@router.post("/logout")
async def logout(request: Request) -> dict:
    clear_session(request)
    return {"status": "ok"}


# --- the lookups (AM3a; read as the mentor) ------------------------------------------

@router.get("/lookup/email")
async def lookup_email(email: str, request: Request) -> dict:
    user, settings = _mentor(request)
    return await lookup.by_email(settings, client_for(settings, user), email)


@router.get("/lookup/people")
async def lookup_people(q: str, request: Request) -> dict:
    user, settings = _mentor(request)
    return {"people": await lookup.people(settings, client_for(settings, user), q)}


@router.get("/lookup/person/{contact_id}")
async def lookup_person(contact_id: str, request: Request) -> dict:
    user, settings = _mentor(request)
    person = await lookup.person_by_id(settings, client_for(settings, user), contact_id)
    if person is None:
        raise HTTPException(status_code=404, detail="That person was not found.")
    company = None
    if person.get("companyId"):
        try:
            got = await client_for(settings, user).get(cfg.ACCOUNT, person["companyId"],
                                                        select=lookup.COMPANY_SELECT)
            company = {"isPartner": "Partner" in (got.get("cCompanyType") or [])}
        except EspoError:
            company = None
    return {"person": person, "isPartner": bool(company and company["isPartner"])}


# --- a report --------------------------------------------------------------------------

class ContactIn(BaseModel):
    contactId: str = Field(default="", max_length=32)
    companyId: str = Field(default="", max_length=32)
    firstName: str = Field(default="", max_length=100)
    lastName: str = Field(default="", max_length=100)
    email: str = Field(default="", max_length=255)
    organization: str = Field(default="", max_length=255)
    title: str = Field(default="", max_length=100)
    phone: str = Field(default="", max_length=40)


class CorrectionIn(BaseModel):
    field: str = Field(max_length=40)
    ours: str = Field(default="", max_length=255)
    theirs: str = Field(default="", max_length=255)


class ReportIn(BaseModel):
    submissionToken: str = Field(min_length=8, max_length=64)
    activityDate: str = Field(default="", max_length=10)
    activityType: str = Field(default="", max_length=64)
    contact: Optional[ContactIn] = None
    personKind: str = Field(default="", max_length=40)
    marketingAgreed: bool = False
    followUp: Optional[bool] = None
    note: str = Field(default="", max_length=4000)
    corrections: list[CorrectionIn] = Field(default_factory=list, max_length=10)


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate(body: ReportIn, settings: Settings) -> dict[str, Any]:
    """The report as stored, or a 400 naming what is missing (validate on
    click, never a disabled button)."""
    if body.activityType not in cfg.ACTIVITY_TYPES:
        raise HTTPException(status_code=400, detail="Choose what you did.")
    try:
        when = date.fromisoformat(body.activityDate)
    except ValueError:
        raise HTTPException(status_code=400, detail="Enter the date you did it.")
    if when > date.today():
        raise HTTPException(status_code=400, detail="The date cannot be in the future.")
    if body.followUp is None:
        from core.branding import abbr

        raise HTTPException(status_code=400, detail=f'Answer "Does {abbr()} need to follow up?"')
    if body.followUp and not body.note.strip():
        raise HTTPException(status_code=400, detail=(
            "You asked for follow-up: say in \"Anything we should know?\" what help you need."))
    contact = body.contact.model_dump() if body.contact else {}
    contact = {k: (v or "").strip() for k, v in contact.items()}
    has_person = any(contact.get(k) for k in ("contactId", "firstName", "lastName", "email"))
    if body.activityType in cfg.NO_CONTACT:
        contact, has_person = {}, False
    if body.activityType in cfg.CONTACT_REQUIRED and not has_person:
        raise HTTPException(status_code=400, detail=(
            "Say who you referred: their email address, or their name."))
    if contact.get("email") and not _EMAIL.match(contact["email"]):
        raise HTTPException(status_code=400, detail="That email address does not look right.")
    if has_person and body.personKind not in cfg.PERSON_KINDS:
        raise HTTPException(status_code=400, detail="Answer \"This person is…\".")
    if has_person and lookup.is_member_address(settings, contact.get("email") or ""):
        raise HTTPException(status_code=400, detail=(
            "That is a member's address. A fellow member is not recorded as a contact: "
            "remove the address, or log the activity without a contact."))
    return {
        "activityDate": when.isoformat(),
        "activityType": body.activityType,
        "contact": contact if has_person else {},
        "personKind": body.personKind if has_person else "",
        "marketingAgreed": bool(body.marketingAgreed and has_person
                                and body.personKind in cfg.REFERRAL_KINDS),
        "followUp": bool(body.followUp),
        "note": body.note.strip(),
        "corrections": [c.model_dump() for c in body.corrections] if has_person else [],
    }


async def deliver_now(settings: Settings, report: dict[str, Any]) -> Optional[str]:
    """The web's one try at recording a report; the worker retries a failure.
    Returns the activity id, or None when it did not finish."""
    from . import runner

    store = report_store(settings)
    client = service.key_client(settings)
    if store is None or client is None:
        return None
    return await runner.deliver_one(settings, store, client, report)


@router.post("/reports")
async def save_report(body: ReportIn, request: Request) -> dict:
    """Capture first (PRD § 4.1), then try once to record it in the CRM."""
    user, settings = _mentor(request)
    await _built(settings)
    payload = _validate(body, settings)
    profile_id = await _profile_id(settings, user)
    store = report_store(settings)
    if store is None:
        raise HTTPException(status_code=503, detail=(
            "This server has no database, so a report cannot be kept safely."))
    report, created = await store.capture(
        token=body.submissionToken, user_id=user.get("userId") or "",
        user_name=user.get("name") or user.get("userName") or "",
        mentor_profile_id=profile_id, payload=payload, lease_seconds=cfg.INLINE_LEASE_SECONDS)
    recorded = report.get("status") == "delivered"
    if created:
        recorded = bool(await deliver_now(settings, report))
    log.info("ambassador report %s by %s (%s)", report["reference"], user.get("userName"),
             "recorded" if recorded else "queued")
    return {"reference": report["reference"], "recorded": recorded,
            "followUp": payload["followUp"]}


@router.get("/mine")
async def mine(request: Request) -> dict:
    user, settings = _mentor(request)
    if not await service.available(service.key_client(settings)):
        return {"built": False, "rows": []}
    profile_id = await _profile_id(settings, user)
    try:
        rows = await service.my_activity(client_for(settings, user), profile_id,
                                         settings.ambassador_edit_days)
    except EspoError as exc:
        raise _crm_failure("read your activity", exc)
    saving: list[dict[str, Any]] = []
    store = report_store(settings)
    if store is not None:
        saving = [service.saving_view(r) for r in await store.undelivered_for(user.get("userId") or "")]
    return {"built": True, "rows": saving + rows, "editDays": settings.ambassador_edit_days}


class CorrectIn(BaseModel):
    activityDate: Optional[str] = Field(default=None, max_length=10)
    activityType: Optional[str] = Field(default=None, max_length=64)
    note: Optional[str] = Field(default=None, max_length=4000)


@router.put("/mine/{activity_id}")
async def correct(activity_id: str, body: CorrectIn, request: Request) -> dict:
    user, settings = _mentor(request)
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if changes.get("activityDate"):
        try:
            if date.fromisoformat(changes["activityDate"]) > date.today():
                raise HTTPException(status_code=400, detail="The date cannot be in the future.")
        except ValueError:
            raise HTTPException(status_code=400, detail="Enter the date you did it.")
    try:
        before, after = await service.correct(client_for(settings, user), activity_id, changes,
                                              settings.ambassador_edit_days)
    except service.CorrectionRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure("save your correction", exc)
    if after:
        await _log(user, action="Corrected", record_id=activity_id,
                   mentor_id=await _profile_id(settings, user),
                   summary="Corrected their ambassador report", before=before, after=after)
    return {"changed": sorted(after)}


# --- the program team ------------------------------------------------------------------

@router.get("/review")
async def review(request: Request) -> dict:
    user, settings = _reviewer(request)
    key = await _built(settings)
    try:
        rows = await service.review_rows(key)
    except EspoError as exc:
        raise _crm_failure("read the review list", exc)
    return {"rows": rows}


class NoteIn(BaseModel):
    note: str = Field(default="", max_length=4000)


async def _row(key: Any, activity_id: str) -> dict[str, Any]:
    try:
        return await key.get(cfg.ACTIVITY, activity_id, select=service.ACTIVITY_SELECT)
    except EspoError as exc:
        raise _crm_failure("read that report", exc)


@router.post("/review/{activity_id}/done")
async def mark_done(activity_id: str, body: NoteIn, request: Request) -> dict:
    user, settings = _reviewer(request)
    key = await _built(settings)
    row = await _row(key, activity_id)
    try:
        before, after = await service.mark_done(client_for(settings, user), key, settings,
                                                activity_id, body.note,
                                                user.get("name") or user.get("userName") or "")
    except service.CorrectionRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure("mark the follow-up done", exc)
    await _log(user, action="Follow-up done", record_id=activity_id,
               mentor_id=row.get("mentorProfileId") or "",
               summary="Marked an ambassador follow-up done", before=before, after=after)
    return {"status": "ok"}


@router.post("/review/{activity_id}/dismiss")
async def dismiss(activity_id: str, body: NoteIn, request: Request) -> dict:
    user, settings = _reviewer(request)
    key = await _built(settings)
    if not body.note.strip():
        raise HTTPException(status_code=400, detail="Say why it is dismissed.")
    row = await _row(key, activity_id)
    try:
        before, after = await service.set_review(client_for(settings, user), activity_id,
                                                 cfg.R_DISMISSED, body.note,
                                                 user.get("name") or user.get("userName") or "")
    except EspoError as exc:
        raise _crm_failure("dismiss it", exc)
    await _log(user, action="Dismissed", record_id=activity_id,
               mentor_id=row.get("mentorProfileId") or "",
               summary="Dismissed an ambassador contact from review", before=before, after=after)
    return {"status": "ok"}


@router.post("/review/{activity_id}/seen")
async def seen(activity_id: str, request: Request) -> dict:
    """A mentor's correction has been read; staff change the CRM record in
    its own screen if it should change (PRD § 5.2)."""
    user, settings = _reviewer(request)
    key = await _built(settings)
    row = await _row(key, activity_id)
    try:
        before, after = await service.set_review(client_for(settings, user), activity_id,
                                                 cfg.R_SEEN, "", user.get("name") or user.get("userName") or "")
    except EspoError as exc:
        raise _crm_failure("record that", exc)
    await _log(user, action="Seen", record_id=activity_id,
               mentor_id=row.get("mentorProfileId") or "",
               summary="Read an ambassador's correction", before=before, after=after)
    return {"status": "ok"}


class LinkIn(BaseModel):
    kind: str = Field(max_length=16)
    recordId: str = Field(min_length=1, max_length=32)


@router.get("/review/targets")
async def targets(kind: str, q: str, request: Request) -> dict:
    user, settings = _reviewer(request)
    key = await _built(settings)
    try:
        return {"targets": await service.search_targets(key, kind, q)}
    except EspoError as exc:
        raise _crm_failure("search", exc)


@router.post("/review/{activity_id}/link")
async def link(activity_id: str, body: LinkIn, request: Request) -> dict:
    user, settings = _reviewer(request)
    key = await _built(settings)
    if body.kind not in service.TARGETS:
        raise HTTPException(status_code=400, detail="Choose partner, funder or client.")
    row = await _row(key, activity_id)
    try:
        line = await service.link_to(key, settings, row, body.kind, body.recordId)
        before, after = await service.set_review(client_for(settings, user), activity_id,
                                                 cfg.R_LINKED, line,
                                                 user.get("name") or user.get("userName") or "")
    except service.CorrectionRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure("link it", exc)
    await _log(user, action="Linked", record_id=activity_id,
               mentor_id=row.get("mentorProfileId") or "",
               summary=f"Linked an ambassador contact to a {body.kind}", before=before, after=after)
    return {"status": "ok", "routed": line}


class CreateIn(BaseModel):
    kind: str = Field(max_length=16)


@router.post("/review/{activity_id}/create")
async def create(activity_id: str, body: CreateIn, request: Request) -> dict:
    user, settings = _reviewer(request)
    key = await _built(settings)
    row = await _row(key, activity_id)
    try:
        made = await service.create_from(key, settings, row, body.kind)
        before, after = await service.set_review(client_for(settings, user), activity_id,
                                                 cfg.R_CREATED, f"New {body.kind} referral",
                                                 user.get("name") or user.get("userName") or "")
    except service.CorrectionRefused as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except EspoError as exc:
        raise _crm_failure("create the referral", exc)
    await _log(user, action="Created", record_id=activity_id,
               mentor_id=row.get("mentorProfileId") or "",
               summary=f"Created an ambassador contact as a new {body.kind} referral",
               before=before, after=after)
    return {"status": "ok", **made}


@router.get("/mentor/{profile_id}")
async def for_mentor(profile_id: str, request: Request) -> dict:
    """A mentor's activities, read-only, for Mentor Administration's tab."""
    user, settings = _reviewer(request, mentor_admin=True)
    key = _key(settings)
    if not await service.available(key):
        return {"available": False, "rows": []}
    try:
        return {"available": True, "rows": await service.for_mentor(key, profile_id)}
    except EspoError as exc:
        raise _crm_failure("read the ambassador activity", exc)
