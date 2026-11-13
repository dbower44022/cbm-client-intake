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
from core import config as config_module
from core.settings_store import (
    SettingsError,
    SettingsStore,
    refresh_into_config,
    scoped_overrides,
)
from integrations import guard as integration_guard
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
    # The page is switched off per REQUEST, not only at boot. ``setup_enabled``
    # is a lockout key with a confirm-or-revert countdown; that countdown only
    # guards something real if switching the page off actually takes effect
    # before a restart. Read live (the override refresh mutates the one
    # Settings object in place), and answer 404 exactly as an unmounted page
    # would — a switched-off page is absent, not forbidden.
    if not get_settings().setup_active:
        raise HTTPException(status_code=404, detail="Not Found")
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


def _test_store(request: Request):
    return getattr(request.app.state, "integration_test_store", None)


async def _test_runs(request: Request) -> dict[str, dict[str, Any]]:
    """The last integration test of each integration, for the status lines.
    Read only while the Integrations tab is on; a database failure leaves the
    lines at "Not tested yet" rather than failing the page."""
    store = _test_store(request)
    if store is None or not get_settings().integrations_tab:
        return {}
    try:
        return await store.latest_all()
    except Exception as exc:  # noqa: BLE001
        log.warning("integration test runs could not be read: %s", exc)
        return {}


def _tick_store(request: Request):
    return getattr(request.app.state, "integration_tick_store", None)


async def _checklist_state(request: Request) -> dict[str, Any]:
    """What the setup checklists read besides the settings and the last test
    runs: the hand ticks, the mailing connection and the stored Email Setup —
    all from this application's database, never an outside service. Read only
    while the Integrations tab is on; a failure leaves that part unknown or
    empty rather than failing the page."""
    if not get_settings().integrations_tab:
        return {}
    out: dict[str, Any] = {"ticks": {}, "mailingConnected": None, "storedGoogle": {},
                           "ticksStored": False, "fixPlans": {}, "agentSpent": None}
    plans = getattr(request.app.state, "fix_plan_store", None)
    if plans is not None:
        try:
            out["fixPlans"] = await plans.latest_all()
            out["setupPlans"] = await plans.latest_all(kind="setup")
            out["agentSpent"] = await plans.spent_this_month()
        except Exception as exc:  # noqa: BLE001
            log.warning("fix plans could not be read: %s", exc)
    ticks = _tick_store(request)
    if ticks is not None:
        try:
            out["ticks"] = await ticks.current()
            out["ticksStored"] = True
        except Exception as exc:  # noqa: BLE001
            log.warning("setup checklist ticks could not be read: %s", exc)
    mailing = getattr(request.app.state, "mailing_store", None)
    if mailing is not None:
        try:
            conn = await mailing.get()
            out["mailingConnected"] = bool(conn and conn.usable)
        except Exception as exc:  # noqa: BLE001
            log.warning("mailing connection could not be read for the checklist: %s", exc)
    else:
        out["mailingConnected"] = False
    try:
        from core.app_config import make_app_config_store

        cfg_store = make_app_config_store(get_settings())
        stored = (await cfg_store.get_google_config()) if cfg_store is not None else None
        stored = stored or {}
        out["storedGoogle"] = {
            "google_service_account_json": bool(stored.get("service_account_json")),
            "google_delegated_admin": bool((stored.get("delegated_admin") or "").strip()),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("stored Email Setup could not be read for the checklist: %s", exc)
    return out


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


def _refuse_if_guarded(key: str, value: Any, settings: Any) -> None:
    """The two "in use" refusals (rulings I5, I13), in the save path itself."""
    why = integration_guard.refusal(key, value, settings, scoped_overrides())
    if why:
        raise HTTPException(status_code=409, detail=why)


@router.get("/settings")
async def get_settings_page(request: Request) -> dict:
    _require_admin(request)
    return await page_payload(_store(request), await _test_runs(request), await _checklist_state(request))


@router.put("/settings/{key}")
async def put_setting(key: str, body: SettingIn, request: Request) -> dict:
    user = _require_admin(request)
    result = await _checked_save(request, user, key, body)
    result["page"] = await page_payload(_store(request), await _test_runs(request),
                                        await _checklist_state(request))
    return result


async def _checked_save(request: Request, user: dict[str, Any], key: str,
                        body: SettingIn) -> dict[str, Any]:
    """The checked save path: pre-flight, store, post-apply with its automatic
    revert, confirm-or-undo, the action log. Every change a person makes on
    the page and every setting change a fix plan carries out goes through
    here (the build orchestrator's rule). Raises HTTPException on a refusal."""
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
    _refuse_if_guarded(key, body.value, settings)
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
    return {"ok": True, "page": await page_payload(store, await _test_runs(request), await _checklist_state(request))}


@router.delete("/settings/{key}")
async def delete_setting(key: str, body: ClearIn, request: Request) -> dict:
    user = _require_admin(request)
    await _checked_reset(request, user, key, body.reason)
    store = _store(request)
    return {"ok": True, "page": await page_payload(store, await _test_runs(request), await _checklist_state(request))}


async def _checked_reset(request: Request, user: dict[str, Any], key: str, reason: str) -> None:
    """Back to the deployment's own value: the page's Reset to deployment
    value, and a plan's setting reset. Raises HTTPException on a refusal."""
    store = _store(request)
    if store is None:
        raise HTTPException(status_code=503, detail="No database is attached.")
    # A reset returns the setting to its deployment value, which can switch a
    # feature on just as a save can.
    _refuse_if_guarded(key, config_module.env_values().get(key), get_settings())
    cleared = await store.clear(key, actor=_actor(user), reason=reason)
    if not cleared:
        raise HTTPException(status_code=404, detail=f"'{key}' was not overridden.")
    await refresh_into_config(store, get_settings())
    await _log(
        user,
        action_log.ACT_SETTING_CLEARED,
        f"{key} reset to its deployment value",
        {"key": key, "reason": reason},
    )


@router.get("/history")
async def get_history(
    request: Request, key: str = Query(default=""), limit: int = Query(default=50, le=200)
) -> dict:
    _require_admin(request)
    store = _store(request)
    rows = await store.history(key, limit) if store is not None else []
    # The setup checklists' hand ticks join the History tab (plan § 4), each
    # with who ticked it and when, under the key "checklist <step>".
    ticks = _tick_store(request)
    if ticks is not None and get_settings().integrations_tab and (
            not key or key.startswith("checklist")):
        try:
            for tk in await ticks.history(limit):
                rows.append({
                    "key": f"checklist {tk['stepId']}",
                    "oldValue": None,
                    "newValue": "ticked" if tk["ticked"] else "not ticked",
                    "action": "tick" if tk["ticked"] else "untick",
                    "reason": f"Setup checklist, {tk['integration']} sub-tab",
                    "actor": tk["by"],
                    "at": tk["at"],
                })
            rows.sort(key=lambda r: r.get("at") or "", reverse=True)
            rows = rows[:limit]
        except Exception as exc:  # noqa: BLE001
            log.warning("setup checklist ticks could not be read for history: %s", exc)
    return {"history": rows}


# --- Website images (prds/chapter-website-plan.md, decision 4.3) -------------
# The logo and header graphic the chapter website shows. Uploaded here, stored
# in the application database, served publicly at /api/website/images/{name}
# while WEBSITE_API is on. The preview below is admin-only and works with the
# switch off, so the images can be set before the website is connected.


class ImageIn(BaseModel):
    # A base64 string or a data: address. About 2.7 MB of text for a 2 MB file.
    data: str = Field(default="", max_length=3_000_000)
    reason: str = Field(default="", max_length=2000)


def _website_store(request: Request):
    return getattr(request.app.state, "website_store", None)


async def _images_payload(request: Request) -> dict:
    from website.images import IMAGE_NAMES

    store = _website_store(request)
    meta = await store.image_meta() if store is not None else {}
    return {
        "available": store is not None,
        "images": [
            {"name": name, "label": label, "set": name in meta, **(meta.get(name) or {})}
            for name, label in IMAGE_NAMES.items()
        ],
    }


def _image_name(name: str) -> str:
    from website.images import IMAGE_NAMES

    if name not in IMAGE_NAMES:
        raise HTTPException(status_code=404, detail=f"There is no Website image called '{name}'.")
    return name


@router.get("/website/images")
async def get_website_images(request: Request) -> dict:
    _require_admin(request)
    return await _images_payload(request)


@router.get("/website/images/{name}")
async def preview_website_image(name: str, request: Request) -> Response:
    _require_admin(request)
    store = _website_store(request)
    image = await store.get_image(_image_name(name)) if store is not None else None
    if image is None:
        raise HTTPException(status_code=404, detail="No image has been uploaded.")
    return Response(content=image["data"], media_type=image["contentType"],
                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.put("/website/images/{name}")
async def put_website_image(name: str, body: ImageIn, request: Request) -> dict:
    from website.images import IMAGE_NAMES, ImageError, decode

    user = _require_admin(request)
    name = _image_name(name)
    store = _website_store(request)
    if store is None:
        raise HTTPException(status_code=409, detail="Images need a database, and this deployment has none.")
    try:
        data, content_type = decode(body.data)
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    meta = await store.put_image(name, data, content_type, actor=_actor(user))
    await _log(user, "Website image uploaded",
               f"{IMAGE_NAMES[name]} uploaded for the chapter website",
               {"image": name, "contentType": content_type, "size": meta["size"],
                "sha256": meta["sha256"], "reason": body.reason})
    return await _images_payload(request)


@router.delete("/website/images/{name}")
async def delete_website_image(name: str, request: Request, body: Optional[ClearIn] = None) -> dict:
    from website.images import IMAGE_NAMES

    user = _require_admin(request)
    name = _image_name(name)
    store = _website_store(request)
    if store is None:
        raise HTTPException(status_code=409, detail="Images need a database, and this deployment has none.")
    if await store.delete_image(name):
        await _log(user, "Website image removed",
                   f"{IMAGE_NAMES[name]} removed from the chapter website",
                   {"image": name, "reason": (body.reason if body else "")})
    return await _images_payload(request)


# --- the integration test (prds/integrations-tab-plan.md § 3, part 2) -------

def _testable(key: str):
    """The integration ``key``, when the tab is on and its test is built."""
    from integrations.registry import integration_for

    if not get_settings().integrations_tab:
        # Built dark: with the switch off the endpoints are absent.
        raise HTTPException(status_code=404, detail="Not Found")
    integ = integration_for(key)
    if integ is None:
        raise HTTPException(status_code=404, detail=f"There is no integration called '{key}'.")
    if not integ.testable:
        raise HTTPException(
            status_code=409,
            detail=f"{integ.name}'s integration test comes with phase {integ.test_phase} "
                   "of the Integrations tab build.",
        )
    return integ


@router.post("/integrations/{key}/test")
async def run_integration_test(key: str, request: Request) -> dict:
    """Run one integration's test now. Every call it makes is a read; nothing
    is written to any outside service. The run is stored and recorded."""
    from integrations.store import MANUAL
    from integrations.testing import AlreadyRunning, run_integration_test as _run

    user = _require_admin(request)
    integ = _testable(key)
    try:
        result = await _run(integ, get_settings())
    except AlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    run = dict(result, trigger=MANUAL, runBy=_actor(user))
    stored = False
    store = _test_store(request)
    if store is not None:
        try:
            run = await store.record(result, trigger=MANUAL,
                                     run_by_id=str(user.get("userId") or ""),
                                     run_by=_actor(user))
            stored = True
        except Exception as exc:  # noqa: BLE001 — the result is still shown
            log.warning("integration test of %s could not be stored: %s", key, exc)
    await _log(
        user, action_log.ACT_INTEGRATION_TESTED,
        f"{integ.name} integration test: {result['outcome']}",
        {"integration": key, "outcome": result["outcome"],
         "checks": {c["key"]: c["outcome"] for c in result["checks"]}},
    )
    return {"run": run, "stored": stored}


@router.get("/integrations/{key}/test")
async def last_integration_test(key: str, request: Request) -> dict:
    """The last integration test of ``key``, or null."""
    _require_admin(request)
    integ = _testable(key)
    store = _test_store(request)
    if store is None:
        return {"run": None}
    return {"run": await store.latest(integ.key)}


class TickIn(BaseModel):
    ticked: bool = True


@router.post("/integrations/{key}/checklist/{step_id}")
async def tick_checklist_step(key: str, step_id: str, body: TickIn, request: Request) -> dict:
    """Tick, or untick, a manual step of an integration's setup checklist
    (plan § 4). An automatic step is refused: it ticks itself from its check."""
    from integrations import checklist as checklist_mod
    from integrations.registry import integration_for

    user = _require_admin(request)
    if not get_settings().integrations_tab:
        raise HTTPException(status_code=404, detail="Not found")
    integ = integration_for(key)
    if integ is None:
        raise HTTPException(status_code=404, detail=f"There is no integration called '{key}'.")
    step = next((s for s in checklist_mod.steps_for(key) if s.id == step_id), None)
    if step is None:
        if step_id in (checklist_mod.DECIDE_ID, checklist_mod.TEST_ID):
            raise HTTPException(status_code=409, detail=(
                "This step ticks itself from its check and cannot be ticked by hand."))
        raise HTTPException(status_code=404, detail=(
            f"Step {step_id} is not on {integ.name}'s setup checklist."))
    if not step.manual:
        raise HTTPException(status_code=409, detail=(
            f"Step {step_id} ticks itself from its check and cannot be ticked by hand."))
    store = _tick_store(request)
    if store is None:
        raise HTTPException(status_code=400, detail=(
            "No database is attached, so a tick cannot be kept."))
    tick = await store.record(step_id, key, body.ticked,
                              actor_id=str(user.get("userId") or ""), actor=_actor(user))
    await _log(
        user,
        action_log.ACT_CHECKLIST_TICKED if body.ticked else action_log.ACT_CHECKLIST_UNTICKED,
        f"{integ.name} setup checklist: step {step_id} {'ticked' if body.ticked else 'unticked'}",
        {"integration": key, "step": step_id, "ticked": body.ticked},
    )
    return {"tick": tick,
            "page": await page_payload(_store(request), await _test_runs(request),
                                       await _checklist_state(request))}


@router.get("/readiness")
async def get_readiness(request: Request) -> dict:
    _require_admin(request)
    return await readiness_mod.readiness_payload(
        get_settings(),
        getattr(request.app.state, "submission_store", None),
        getattr(request.app.state, "mailing_store", None),
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


# --- the diagnosis agent and fix plans (prds/integrations-tab-plan.md § 6) ----

def _plan_store(request: Request):
    return getattr(request.app.state, "fix_plan_store", None)


def _integration_or_404(key: str):
    from integrations.registry import integration_for

    if not get_settings().integrations_tab:
        raise HTTPException(status_code=404, detail="Not found")
    integ = integration_for(key)
    if integ is None:
        raise HTTPException(status_code=404, detail=f"There is no integration called '{key}'.")
    return integ


async def _snapshot(request: Request, integ: Any, run: dict[str, Any]):
    """What the diagnosis agent may read, taken now. No secret value."""
    from integrations import diagnosis
    from integrations.events import make_event_store
    from .readiness import readiness_payload

    page = await page_payload(_store(request), await _test_runs(request),
                              await _checklist_state(request))
    entry = next(i for i in page["integrations"] if i["key"] == integ.key)
    rows = list(entry.get("settings") or [])
    for sec in entry.get("sections") or []:
        rows += sec.get("settings") or []
    readiness: list[dict[str, Any]] = []
    try:
        rd = await readiness_payload(get_settings())
        readiness = [f for f in rd.get("features", []) if f.get("integration") == integ.key]
    except Exception as exc:  # noqa: BLE001 — the agent works without it
        log.warning("readiness could not be read for the diagnosis of %s: %s", integ.key, exc)
    errors: list[dict[str, Any]] = []
    events = make_event_store(get_settings())
    if events is not None:
        try:
            errors = await events.recent(integ.key)
        except Exception as exc:  # noqa: BLE001
            log.warning("recent errors could not be read for %s: %s", integ.key, exc)
    checklist_rows = [{k: r.get(k) for k in ("id", "name", "state", "reason", "automatic")}
                      for r in (entry.get("checklist") or {}).get("rows", [])]
    from integrations.actions import for_integration

    return diagnosis.Snapshot(
        integration=integ.key, name=integ.name,
        test={k: (run or {}).get(k) for k in ("outcome", "checks", "facts", "finishedAt", "trigger")},
        actions=tuple((a.name, a.label, a.description, a.input_label) for a in for_integration(integ.key)),
        settings=diagnosis.settings_rows(rows), readiness=readiness,
        checklist=checklist_rows, runbooks=tuple(integ.runbooks), errors=errors,
        doc_sites=tuple(integ.doc_sites),
    )


async def _run_diagnosis(app: Any, plan_id: str, snap: Any, user: dict[str, Any], mode: str = "fix") -> None:
    """In the background: the agent's call, then the plan stored. Never raises."""
    from integrations import diagnosis, fixplans
    from integrations.testing import secret_values

    store = app.state.fix_plan_store
    settings = get_settings()
    outcome = None
    try:
        factory = getattr(app.state, "anthropic_client", None)
        if factory is None:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key,
                                              timeout=300.0, max_retries=2)
        else:
            client = factory()
        outcome = await diagnosis.diagnose(client, snap, model=settings.integration_agent_model,
                                           secrets=secret_values(settings), mode=mode)
        plan = outcome.plan
        await store.complete(
            plan_id, status=fixplans.PROPOSED if plan else fixplans.NO_PLAN,
            diagnosis=(plan or {}).get("diagnosis", ""), confidence=(plan or {}).get("confidence", ""),
            steps=(plan or {}).get("steps", []), model=outcome.model, cost=outcome.cost,
            usage=outcome.usage, error=outcome.error)
    except Exception as exc:  # noqa: BLE001
        log.warning("diagnosis of %s failed: %s", snap.integration, exc)
        try:
            await store.complete(plan_id, status=fixplans.NO_PLAN,
                                 error=f"The diagnosis could not be completed: {type(exc).__name__}.",
                                 cost=outcome.cost if outcome else 0.0)
        except Exception:  # noqa: BLE001
            pass
    await _log(user, fixplans.ACT_SETUP_ASKED if mode == "setup" else fixplans.ACT_DIAGNOSED,
               f"{snap.name}: {'setup plan written' if mode == 'setup' else 'diagnosed'} with Claude"
               + (f" (${outcome.cost:.2f})" if outcome else ""),
               {"integration": snap.integration, "plan": plan_id,
                "outcome": "plan" if outcome and outcome.plan else "no plan"})


@router.post("/integrations/{key}/diagnose")
async def diagnose_integration(key: str, request: Request) -> dict:
    """Start a diagnosis of ``key``'s last failed test (ruling I7). Runs in
    the background; the page reads the plan when it is ready."""
    return await _start_agent(request, key, "fix")


@router.post("/integrations/{key}/setup")
async def setup_integration(key: str, request: Request) -> dict:
    """Ask the setup assistant for a setup plan of ``key``'s open setup
    checklist steps (plan § 6.5, ruling I11). Runs in the background."""
    return await _start_agent(request, key, "setup")


async def _start_agent(request: Request, key: str, mode: str) -> dict:
    import asyncio

    from integrations import checklist as checklist_mod
    from integrations import fixplans

    user = _require_admin(request)
    integ = _integration_or_404(key)
    settings = get_settings()
    plans, runs = _plan_store(request), _test_store(request)
    word = "setup plan" if mode == "setup" else "fix plan"
    if plans is None or runs is None:
        raise HTTPException(status_code=400, detail=f"No database is attached, so a {word} cannot be kept.")
    if not (settings.anthropic_api_key or "").strip() and getattr(request.app.state, "anthropic_client", None) is None:
        raise HTTPException(status_code=409, detail=(
            "The Anthropic API key is not set. Set it on the Anthropic sub-tab first."))
    run = await runs.latest(integ.key)
    if mode == "fix" and (not run or run.get("outcome") == "ok"):
        raise HTTPException(status_code=409, detail=(
            f"{integ.name}'s last integration test did not fail, so there is nothing to diagnose. "
            "Run the test first."))
    latest = await plans.latest(integ.key, kind=mode)
    if latest and latest["status"] == fixplans.DIAGNOSING:
        raise HTTPException(status_code=409, detail=(
            f"Claude is already writing a {word} for {integ.name}."))
    spent = await plans.spent_this_month()
    budget = float(settings.integration_agent_monthly_budget or 0)
    if spent >= budget:
        raise HTTPException(status_code=409, detail=(
            f"Claude has spent ${spent:.2f} this month on diagnoses and setup plans, which reaches the "
            f"monthly budget of ${budget:.2f}. Raise the Integration agent monthly budget on the "
            "Anthropic sub-tab to ask again."))
    snap = await _snapshot(request, integ, run or {})
    if mode == "setup" and all(r.get("state") == checklist_mod.DONE for r in snap.checklist):
        raise HTTPException(status_code=409, detail=(
            f"Every step of {integ.name}'s setup checklist is done, so there is nothing to set up."))
    plan = await plans.create(integration=integ.key, kind=mode, test_run_id=(run or {}).get("id") or "",
                              status=fixplans.DIAGNOSING, created_by=_actor(user))
    tasks = getattr(request.app.state, "diagnosis_tasks", None)
    if tasks is None:
        tasks = request.app.state.diagnosis_tasks = set()
    task = asyncio.create_task(_run_diagnosis(request.app, plan["id"], snap, user, mode))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return {"plan": plan}


@router.get("/integrations/{key}/setupplan")
async def get_setup_plan(key: str, request: Request) -> dict:
    _require_admin(request)
    integ = _integration_or_404(key)
    plans = _plan_store(request)
    return {"plan": await plans.latest(integ.key, kind="setup") if plans is not None else None}


@router.get("/integrations/{key}/fixplan")
async def get_fix_plan(key: str, request: Request) -> dict:
    _require_admin(request)
    integ = _integration_or_404(key)
    plans = _plan_store(request)
    return {"plan": await plans.latest(integ.key) if plans is not None else None}


class ApplyIn(BaseModel):
    fingerprint: str


async def _execute_step(request: Request, user: dict[str, Any], plan: dict[str, Any],
                        step: dict[str, Any]) -> bool:
    """Carry out one step as ``user``; record its outcome on ``step``. True
    when it is done. Never raises for a refusal: the reason goes on the step."""
    from integrations import actions, fixplans, registry
    from integrations.store import MANUAL
    from integrations.testing import run_integration_test as _run

    now = datetime.now(timezone.utc).isoformat()
    reason = f"applied from a {plan.get('kind') or 'fix'} plan ({plan['id'][:8]})"

    def done(detail: str, **extra: Any) -> bool:
        step.update(state="done", doneBy=_actor(user), doneAt=now, detail=detail, **extra)
        return True

    def refused(detail: str) -> bool:
        step.update(detail=detail)
        return False

    kind = step["kind"]
    if kind == fixplans.SETTING_CHANGE:
        try:
            res = await _checked_save(request, user, step["key"], SettingIn(value=step["value"], reason=reason))
        except HTTPException as exc:
            return refused(str(exc.detail))
        if res.get("reverted"):
            return refused(f"Reverted automatically: {res['reverted']}")
        return done("Applied. Confirm it within 10 minutes on the Settings tab, or it undoes itself."
                    if res.get("confirmBy") else "Applied.")
    if kind == fixplans.SETTING_RESET:
        try:
            await _checked_reset(request, user, step["key"], reason)
        except HTTPException as exc:
            if exc.status_code == 404:
                return done("It already has the deployment's own value.")
            return refused(str(exc.detail))
        return done("Reset to the deployment's own value.")
    if kind == fixplans.CODED_ACTION:
        result = await actions.run(step["name"], get_settings(), step.get("input") or "", dry=False)
        if not result.ok:
            return refused(result.summary)
        for key, value in result.proposes.items():
            try:
                res = await _checked_save(request, user, key, SettingIn(value=value, reason=reason))
            except HTTPException as exc:
                return refused(f"{result.summary} But saving {key} was refused: {exc.detail}")
            if res.get("reverted"):
                return refused(f"{result.summary} But {key} was reverted automatically: {res['reverted']}")
        return done(result.summary)
    if kind == fixplans.MANUAL_STEP:
        linked = step.get("checklistStep") or ""
        if linked:
            page = await page_payload(_store(request), await _test_runs(request), await _checklist_state(request))
            entry = next((i for i in page.get("integrations") or [] if i["key"] == plan["integration"]), {})
            row = next((r for r in (entry.get("checklist") or {}).get("rows", []) if r["id"] == linked), None)
            if row is not None and row.get("automatic") and row.get("state") != "done":
                return refused(f"Not done yet: {row.get('reason') or 'its check does not pass.'} "
                               "Finish the step and confirm again, or ask Claude to diagnose it.")
        return done("Confirmed.")
    if kind == fixplans.RETEST:
        integ = registry.integration_for(plan["integration"])
        try:
            result = await _run(integ, get_settings())
        except Exception as exc:  # noqa: BLE001
            return refused(f"The re-test could not run: {exc}")
        runs = _test_store(request)
        if runs is not None:
            await runs.record(result, trigger=MANUAL, run_by_id=str(user.get("userId") or ""),
                              run_by=_actor(user))
        return done({"ok": "The integration test passes.",
                     "failed": "The integration test still fails. Diagnose it."}.get(
                         result["outcome"], "The integration test could not be completed."),
                    outcome=result["outcome"])
    return refused(f"Unknown step kind {kind}.")


async def _carry_out(request: Request, user: dict[str, Any], plan: dict[str, Any], *,
                     confirm: Optional[int] = None) -> dict[str, Any]:
    """Carry out the plan's steps in order (ruling I10).

    A **fix plan** runs its automatic steps straight through, pauses at a
    manual step, and stops at the first failure (ruling I12). A **setup plan**
    waits for confirmation at every step: ``confirm`` names the step a person
    has just confirmed; a coded action shows its dry run while it waits; a
    step that fails stays open with the reason (plan § 2)."""
    from integrations import actions, fixplans

    plans = _plan_store(request)
    steps = plan["steps"]
    setup = plan.get("kind") == fixplans.SETUP
    status = fixplans.APPLYING
    for step in steps:
        if step["state"] == "done":
            continue
        if setup:
            if confirm != step["n"]:
                if step["kind"] == fixplans.CODED_ACTION and "dryRun" not in step:
                    res = await actions.run(step["name"], get_settings(), step.get("input") or "", dry=True)
                    step["dryRun"] = res.as_dict()
                status = fixplans.WAITING
                break
            confirm = None
            if not await _execute_step(request, user, plan, step):
                status = fixplans.WAITING
                break
            if step["kind"] == fixplans.RETEST:
                status = fixplans.APPLIED
            continue
        if step["kind"] == fixplans.MANUAL_STEP:
            status = fixplans.WAITING
            break
        if not await _execute_step(request, user, plan, step):
            step["state"] = "failed"
            status = fixplans.STOPPED
            break
        if step["kind"] == fixplans.RETEST:
            status = fixplans.APPLIED
    if all(s["state"] == "done" for s in steps):
        status = fixplans.APPLIED
    finished = status in (fixplans.APPLIED, fixplans.STOPPED)
    await plans.update(plan["id"], status=status, steps=steps,
                       finished_at=datetime.now(timezone.utc) if finished else None)
    return await plans.get(plan["id"])


@router.post("/integrations/{key}/fixplan/{plan_id}/apply")
async def apply_fix_plan(key: str, plan_id: str, body: ApplyIn, request: Request) -> dict:
    """Approve and apply that exact plan (ruling I7): refused if it changed."""
    from integrations import fixplans

    user = _require_admin(request)
    integ = _integration_or_404(key)
    plans = _plan_store(request)
    plan = await plans.get(plan_id) if plans is not None else None
    if plan is None or plan["integration"] != integ.key:
        raise HTTPException(status_code=404, detail="There is no such fix plan.")
    if plan["status"] != fixplans.PROPOSED:
        raise HTTPException(status_code=409, detail=f"This fix plan is {plan['status']}, not waiting for approval.")
    if body.fingerprint != plan["fingerprint"] or \
            fixplans.fingerprint(plan["diagnosis"], plan["steps"]) != plan["fingerprint"]:
        raise HTTPException(status_code=409, detail=(
            "This fix plan changed after it was shown. Reload the page and read it again."))
    now = datetime.now(timezone.utc)
    await plans.update(plan_id, status=fixplans.APPLYING, approved_by=_actor(user), approved_at=now)
    plan.update(approvedBy=_actor(user))
    await _log(user, fixplans.ACT_PLAN_APPLIED, f"{integ.name}: {plan.get('kind', 'fix')} plan approved",
               {"integration": key, "plan": plan_id, "steps": len(plan["steps"])})
    result = await _carry_out(request, user, plan)
    return {"plan": result, "page": await page_payload(_store(request), await _test_runs(request),
                                                       await _checklist_state(request))}


@router.post("/integrations/{key}/fixplan/{plan_id}/steps/{n}/done")
async def confirm_fix_plan_step(key: str, plan_id: str, n: int, request: Request) -> dict:
    """A person confirms the manual step the plan is waiting at; the plan then
    carries on."""
    from integrations import fixplans

    user = _require_admin(request)
    integ = _integration_or_404(key)
    plans = _plan_store(request)
    plan = await plans.get(plan_id) if plans is not None else None
    if plan is None or plan["integration"] != integ.key:
        raise HTTPException(status_code=404, detail="There is no such fix plan.")
    if plan["status"] != fixplans.WAITING:
        raise HTTPException(status_code=409, detail="This plan is not waiting at a step.")
    waiting = next((s for s in plan["steps"] if s["state"] != "done"), None)
    setup = plan.get("kind") == fixplans.SETUP
    if waiting is None or waiting["n"] != n or (not setup and waiting["kind"] != fixplans.MANUAL_STEP):
        raise HTTPException(status_code=409, detail=f"Step {n} is not the step this plan is waiting at.")
    await _log(user, fixplans.ACT_PLAN_STEP, f"{integ.name}: {plan.get('kind', 'fix')} plan step {n} confirmed",
               {"integration": key, "plan": plan_id, "step": n, "kind": waiting["kind"]})
    if setup:
        result = await _carry_out(request, user, plan, confirm=n)
    else:
        waiting.update(state="done", doneBy=_actor(user), doneAt=datetime.now(timezone.utc).isoformat())
        result = await _carry_out(request, user, plan)
    return {"plan": result, "page": await page_payload(_store(request), await _test_runs(request),
                                                       await _checklist_state(request))}


@router.post("/integrations/{key}/fixplan/{plan_id}/discard")
async def discard_fix_plan(key: str, plan_id: str, request: Request) -> dict:
    from integrations import fixplans

    user = _require_admin(request)
    integ = _integration_or_404(key)
    plans = _plan_store(request)
    plan = await plans.get(plan_id) if plans is not None else None
    if plan is None or plan["integration"] != integ.key:
        raise HTTPException(status_code=404, detail="There is no such fix plan.")
    if plan["status"] not in (fixplans.PROPOSED, fixplans.WAITING):
        raise HTTPException(status_code=409, detail=f"This fix plan is {plan['status']} and cannot be discarded.")
    await plans.update(plan_id, status=fixplans.DISCARDED, finished_at=datetime.now(timezone.utc))
    await _log(user, fixplans.ACT_PLAN_DISCARDED, f"{integ.name}: fix plan discarded",
               {"integration": key, "plan": plan_id})
    return {"plan": await plans.get(plan_id)}
