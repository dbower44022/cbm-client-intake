"""System Settings API (``/setup/api``) — admin-only (ruling 1).

The gate is the CRM user's own admin flag, already carried on the shared staff
session and re-read on every session restore. No new team to create, and the
smallest possible blast radius for a page that can reconfigure the platform.

One endpoint deliberately sits outside the session: ``GET /api/setup/snapshot``
is how the peer deployment reads this one for the environment diff. It is
authorised by a shared token, returns no secret values, and is closed unless a
token is configured.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from assignments.auth import current_user
from core import action_log
from core.config import get_settings
from core.settings_registry import LOCKOUT_KEYS, VERIFIED_KEYS, spec_for
from core.settings_store import (
    SettingsError,
    SettingsStore,
    refresh_into_config,
)
from core.config import get_settings as _get_settings

from . import jobs as jobs_mod
from . import verify
from . import readiness as readiness_mod
from . import snapshot as snapshot_mod
from .service import describe_change, page_payload

log = logging.getLogger("cbm_intake.setup")

router = APIRouter(prefix="/setup/api", tags=["setup"])
# The peer-facing snapshot lives on its own prefix: it is machine-to-machine and
# must not look like part of the authenticated app.
peer_router = APIRouter(prefix="/api/setup", tags=["setup"])


def _require_admin(request: Request) -> dict[str, Any]:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    if not user.get("isAdmin"):
        raise HTTPException(
            status_code=403,
            detail="System Settings is restricted to EspoCRM administrators.",
        )
    return user


def _store(request: Request) -> Optional[SettingsStore]:
    return getattr(request.app.state, "settings_store", None)


def _job_store(request: Request):
    return getattr(request.app.state, "job_store", None)


def _actor(user: dict[str, Any]) -> str:
    return str(user.get("userName") or user.get("name") or "")


async def _log(user: dict[str, Any], action: str, summary: str, details: dict) -> None:
    """Record the change. There is no CRM record to hang a stream note on, so
    this writes the reporting row only."""
    await action_log.log_action(
        app=action_log.APP_SETUP,
        category=action_log.CAT_CONFIG,
        action=action,
        parent_type="",
        parent_id="",
        summary=summary,
        actor_id=str(user.get("userId") or ""),
        actor_name=_actor(user),
        details=details,
    )


class SettingIn(BaseModel):
    value: str = Field(default="")
    reason: str = Field(default="", max_length=2000)
    temporary: bool = False
    reviewAt: Optional[datetime] = None
    scopeTeams: list[str] = Field(default_factory=list)
    scopeUsers: list[str] = Field(default_factory=list)


class ClearIn(BaseModel):
    reason: str = Field(default="", max_length=2000)


class JobIn(BaseModel):
    reason: str = Field(default="", max_length=2000)
    planId: str = ""


# How long an admin has to confirm a lockout-capable change before it undoes
# itself. Long enough to sign out, sign back in and look around; short enough
# that an admin who HAS locked themselves out is not stuck for an afternoon.
CONFIRM_WINDOW_MINUTES = 10


def _revert_deadline(key: str) -> Optional[datetime]:
    """When this change must undo itself unless confirmed, or None.

    Only for settings that can lock the admin out of this page. Neither the
    pre-flight probe nor the post-apply health check can catch that case — the
    application would be working perfectly and simply refusing to let anyone
    back in — so the countdown is the only mechanism that survives it. It is
    deliberately NOT applied to merely-dangerous settings: an unattended change
    undoing itself is disruptive, and it should only happen where the
    alternative is being locked out.
    """
    if key not in LOCKOUT_KEYS:
        return None
    return datetime.now(timezone.utc) + timedelta(minutes=CONFIRM_WINDOW_MINUTES)


@router.get("/settings")
async def get_settings_page(request: Request) -> dict:
    _require_admin(request)
    return await page_payload(_store(request))


@router.put("/settings/{key}")
async def put_setting(key: str, body: SettingIn, request: Request) -> dict:
    user = _require_admin(request)
    store = _store(request)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="No database is attached, so settings cannot be overridden here.",
        )
    settings = get_settings()
    if not settings.settings_overrides:
        raise HTTPException(
            status_code=409,
            detail="The override layer is switched off (SETTINGS_OVERRIDES=false), so "
                   "a change saved here would not take effect.",
        )
    spec = spec_for(key)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"'{key}' is not an editable setting.")
    # Scoping only works where there is a user in context — the web process.
    # Refuse rather than store a scope the worker can never evaluate (plan §5).
    if (body.scopeTeams or body.scopeUsers) and spec.component != "web":
        raise HTTPException(
            status_code=400,
            detail=(
                f"{spec.label} is read by the {spec.component} process, which has no "
                "signed-in user, so it cannot be scoped to a team or person. Set it "
                "for the whole environment instead."
            ),
        )
    if body.temporary and body.reviewAt is None:
        raise HTTPException(
            status_code=400,
            detail="A temporary change needs a review date — that is the whole point "
                   "of marking it temporary.",
        )
    # 1. PRE-FLIGHT. Try the value for real before storing it. A CRM key the
    #    CRM rejects, or an address that is not a CRM this application can use,
    #    is refused HERE with the actual error — never accepted and left to fail
    #    on every later call. A probe that cannot REACH the thing it tests
    #    returns "unknown" and does not block: an admin fixing configuration
    #    during an outage must not be blocked by the outage.
    checked = await verify.probe(key, body.value)
    if checked.blocks_save:
        raise HTTPException(
            status_code=400,
            detail=f"{spec.label} was not saved — {checked.detail}",
        )

    deadline = _revert_deadline(key)
    try:
        record = await store.set(
            key,
            body.value,
            actor=_actor(user),
            reason=body.reason,
            temporary=body.temporary,
            review_at=body.reviewAt,
            scope_teams=body.scopeTeams,
            scope_users=body.scopeUsers,
            revert_at=deadline,
        )
    except SettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await refresh_into_config(store, get_settings())

    # 2. POST-APPLY. With the change actually installed, is the system still
    #    working? A failure here reverts immediately rather than leaving a
    #    broken configuration in place for someone to discover.
    reverted = None
    if key in VERIFIED_KEYS and not spec.restart:
        health = await verify.still_functional()
        if health.outcome == verify.FAILED:
            await store.revert(
                key, actor="system",
                reason=f"reverted automatically: {health.detail}",
            )
            await refresh_into_config(store, get_settings())
            reverted = health.detail
            await _log(
                user, action_log.ACT_SETTING_CLEARED,
                f"{key} reverted automatically — the system stopped working",
                {"key": key, "detail": health.detail},
            )
    await _log(
        user,
        action_log.ACT_SETTING_CHANGED,
        describe_change(key, body.value),
        {
            "key": key,
            "temporary": body.temporary,
            "scoped": record.scoped,
            "reason": body.reason,
        },
    )
    return {
        "ok": reverted is None,
        "restart": spec.restart,
        "verification": checked.as_dict(),
        # Set when the change was applied and then undone because the system
        # stopped working. The page says so instead of reporting a success.
        "reverted": reverted,
        # Set when the change is live but will undo itself unless confirmed.
        "confirmBy": deadline.isoformat() if deadline and reverted is None else None,
        "setting": record.as_dict(),
        "page": await page_payload(store),
    }


@router.post("/settings/{key}/confirm")
async def confirm_setting(key: str, request: Request) -> dict:
    """A human says the system still works. Cancels the countdown.

    Reaching this endpoint at all is the proof: it needs an authenticated admin
    session on this page, which is precisely what a lockout would prevent.
    """
    user = _require_admin(request)
    store = _store(request)
    if store is None:
        raise HTTPException(status_code=503, detail="No database is attached.")
    if not await store.confirm(key, actor=_actor(user)):
        raise HTTPException(
            status_code=404, detail=f"'{key}' has no change awaiting confirmation."
        )
    await _log(
        user, action_log.ACT_SETTING_CHANGED,
        f"{key} confirmed working — the automatic revert is cancelled",
        {"key": key},
    )
    return {"ok": True, "page": await page_payload(store)}


@router.delete("/settings/{key}")
async def delete_setting(key: str, body: ClearIn, request: Request) -> dict:
    user = _require_admin(request)
    store = _store(request)
    if store is None:
        raise HTTPException(status_code=503, detail="No database is attached.")
    cleared = await store.clear(key, actor=_actor(user), reason=body.reason)
    if not cleared:
        raise HTTPException(status_code=404, detail=f"'{key}' was not overridden.")
    await refresh_into_config(store, get_settings())
    await _log(
        user,
        action_log.ACT_SETTING_CLEARED,
        f"{key} reset to its deployment value",
        {"key": key, "reason": body.reason},
    )
    return {"ok": True, "page": await page_payload(store)}


@router.get("/history")
async def get_history(
    request: Request, key: str = Query(default=""), limit: int = Query(default=50, le=200)
) -> dict:
    _require_admin(request)
    store = _store(request)
    if store is None:
        return {"history": []}
    return {"history": await store.history(key, limit)}


@router.get("/readiness")
async def get_readiness(request: Request) -> dict:
    _require_admin(request)
    return await readiness_mod.readiness_payload(
        get_settings(), getattr(request.app.state, "submission_store", None)
    )


@router.get("/diff")
async def get_diff(request: Request) -> dict:
    _require_admin(request)
    return await snapshot_mod.diff_payload(get_settings(), _store(request))


@router.get("/jobs")
async def get_jobs(request: Request) -> dict:
    _require_admin(request)
    store = _job_store(request)
    recent = await store.recent() if store is not None else []
    return {
        "jobs": jobs_mod.catalogue(),
        "recent": [jobs_mod.job_row(r) for r in recent],
        "available": store is not None,
    }


async def _run_job(request: Request, key: str, body: JobIn, *, apply: bool) -> dict:
    user = _require_admin(request)
    store = _job_store(request)
    if store is None:
        raise HTTPException(status_code=503, detail="No database is attached.")
    spec = jobs_mod.BY_KEY.get(key)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown job '{key}'.")
    if not spec.runnable:
        raise HTTPException(
            status_code=409,
            detail=spec.unavailable_reason or "That job cannot be run from here.",
        )
    if apply and spec.mutating and not body.reason.strip():
        raise HTTPException(
            status_code=422,
            detail="Applying a change needs a reason — it is recorded with the run.",
        )
    settings = get_settings()
    if apply:
        result = await jobs_mod.run_apply(
            store, spec, settings, plan_id=body.planId,
            actor=_actor(user), reason=body.reason,
        )
        if result.get("status") == jobs_mod.STATUS_DONE:
            await _log(
                user, action_log.ACT_JOB_APPLIED,
                f"Ran maintenance job: {spec.name}",
                {"job": key, "reason": body.reason, "planOf": body.planId},
            )
    else:
        result = await jobs_mod.run_dry_run(
            store, spec, settings, actor=_actor(user), reason=body.reason
        )
        await _log(
            user, action_log.ACT_JOB_DRY_RUN,
            f"Dry-ran maintenance job: {spec.name}",
            {"job": key},
        )
    return result


@router.post("/jobs/{key}/dry-run")
async def post_job_dry_run(key: str, body: JobIn, request: Request) -> dict:
    return await _run_job(request, key, body, apply=False)


@router.post("/jobs/{key}/apply")
async def post_job_apply(key: str, body: JobIn, request: Request) -> dict:
    return await _run_job(request, key, body, apply=True)


@peer_router.get("/snapshot")
async def get_snapshot(request: Request, response: Response) -> dict:
    """The read-only, non-secret settings snapshot the peer deployment reads.

    Token-authorised rather than session-authorised: the caller is the other
    app, not a person. Closed when no token is configured.
    """
    settings = _get_settings()
    presented = request.headers.get(snapshot_mod.TOKEN_HEADER, "")
    if not snapshot_mod.token_matches(settings, presented):
        raise HTTPException(status_code=401, detail="Invalid or missing setup token.")
    response.headers["Cache-Control"] = "no-store"
    store = getattr(request.app.state, "settings_store", None)
    overrides = await store.load() if store is not None else {}
    return snapshot_mod.build_snapshot(settings, overrides)
