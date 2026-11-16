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


async def _page_state(request: Request) -> dict[str, Any]:
    """What the Integrations tab reads besides the settings and the last test
    runs: each set-up wizard's progress and what Ask Claude has spent this
    month, from this application's database, never an outside service. Read
    only while the Integrations tab is on; a failure leaves that part empty
    rather than failing the page."""
    if not get_settings().integrations_tab:
        return {}
    out: dict[str, Any] = {"agentSpent": None}
    wizards = _wizard_store(request)
    if wizards is not None:
        try:
            out["wizards"] = await wizards.all()
            out["wizardsStored"] = True
        except Exception as exc:  # noqa: BLE001
            log.warning("wizard progress could not be read: %s", exc)
        try:
            out["agentSpent"] = await wizards.spent_this_month()
        except Exception as exc:  # noqa: BLE001
            log.warning("Ask Claude spending could not be read: %s", exc)
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
    return await page_payload(_store(request), await _test_runs(request), await _page_state(request))


@router.put("/settings/{key}")
async def put_setting(key: str, body: SettingIn, request: Request) -> dict:
    user = _require_admin(request)
    result = await _checked_save(request, user, key, body)
    result["page"] = await page_payload(_store(request), await _test_runs(request),
                                        await _page_state(request))
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
    return {"ok": True, "page": await page_payload(store, await _test_runs(request), await _page_state(request))}


@router.delete("/settings/{key}")
async def delete_setting(key: str, body: ClearIn, request: Request) -> dict:
    user = _require_admin(request)
    await _checked_reset(request, user, key, body.reason)
    store = _store(request)
    return {"ok": True, "page": await page_payload(store, await _test_runs(request), await _page_state(request))}


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
    if result["outcome"] == "ok":
        await _mark_completed(request, key)
    await _log(
        user, action_log.ACT_INTEGRATION_TESTED,
        f"{integ.name} integration test: {result['outcome']}",
        {"integration": key, "outcome": result["outcome"],
         "checks": {c["key"]: c["outcome"] for c in result["checks"]}},
    )
    return {"run": run, "stored": stored}


async def _mark_completed(request: Request, key: str) -> None:
    """A passing test means this integration's setup was completed: a later
    failure reads Fix, never Continue setup (Doug, 11-15-26). Best-effort."""
    from integrations import wizard

    store = _wizard_store(request)
    if store is None or not wizard.screens_for(key):
        return
    try:
        p = dict(wizard.blank(), **(await store.get(key) or {}))
        if not p.get("completed"):
            p["completed"] = True
            await store.put(key, p)
    except Exception as exc:  # noqa: BLE001
        log.warning("the %s setup could not be marked completed: %s", key, exc)


@router.get("/integrations/{key}/test")
async def last_integration_test(key: str, request: Request) -> dict:
    """The last integration test of ``key``, or null."""
    _require_admin(request)
    integ = _testable(key)
    store = _test_store(request)
    if store is None:
        return {"run": None}
    return {"run": await store.latest(integ.key)}


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


# --- what Ask Claude reads (prds/integrations-tab-plan.md § 6.2, ruling W6) ----

def _integration_or_404(key: str):
    from integrations.registry import integration_for

    if not get_settings().integrations_tab:
        raise HTTPException(status_code=404, detail="Not found")
    integ = integration_for(key)
    if integ is None:
        raise HTTPException(status_code=404, detail=f"There is no integration called '{key}'.")
    return integ


async def _snapshot(request: Request, integ: Any, run: dict[str, Any]):
    """What Ask Claude may read, taken now. No secret value."""
    from integrations import diagnosis
    from integrations.events import make_event_store
    from .readiness import readiness_payload

    page = await page_payload(_store(request), await _test_runs(request),
                              await _page_state(request))
    entry = next(i for i in page["integrations"] if i["key"] == integ.key)
    rows = list(entry.get("settings") or [])
    for sec in entry.get("sections") or []:
        rows += sec.get("settings") or []
    readiness: list[dict[str, Any]] = []
    try:
        rd = await readiness_payload(get_settings())
        readiness = [f for f in rd.get("features", []) if f.get("integration") == integ.key]
    except Exception as exc:  # noqa: BLE001 — Claude answers without it
        log.warning("readiness could not be read for Ask Claude about %s: %s", integ.key, exc)
    errors: list[dict[str, Any]] = []
    events = make_event_store(get_settings())
    if events is not None:
        try:
            errors = await events.recent(integ.key)
        except Exception as exc:  # noqa: BLE001
            log.warning("recent errors could not be read for %s: %s", integ.key, exc)
    from integrations.checklist import steps_for

    steps: list[dict[str, Any]] = []
    try:
        steps = [{"id": s.id, "name": s.name} for s in steps_for(integ.key)]
    except Exception as exc:  # noqa: BLE001 — Claude answers without them
        log.warning("guide steps could not be read for %s: %s", integ.key, exc)
    return diagnosis.Snapshot(
        integration=integ.key, name=integ.name,
        test={k: (run or {}).get(k) for k in ("outcome", "checks", "facts", "finishedAt", "trigger")},
        settings=diagnosis.settings_rows(rows), readiness=readiness,
        steps=steps, runbooks=tuple(integ.runbooks), errors=errors,
        doc_sites=tuple(integ.doc_sites),
    )



# --- the setup wizard (prds/integrations-tab-plan.md § 10, rulings W1 to W6) ---

def _wizard_store(request: Request):
    return getattr(request.app.state, "wizard_store", None)


class WizardIn(BaseModel):
    screen: str = ""
    answer: str = ""
    value: str = ""


async def _wizard_context(request: Request, key: str):
    from integrations import wizard

    store = _wizard_store(request)
    if store is None:
        raise HTTPException(status_code=400, detail="No database is attached, so the wizard cannot keep its place.")
    screens = wizard.screens_for(key)
    if not screens:
        raise HTTPException(status_code=404, detail="This integration has no wizard yet.")
    progress = dict(wizard.blank(), **(await store.get(key) or {}))
    return store, screens, progress


@router.post("/integrations/{key}/wizard/{action}")
async def wizard_action(key: str, action: str, body: WizardIn, request: Request) -> dict:
    """One wizard action (W1 to W5): answer, enter, done, back, restart, review, ask.
    A setting is saved through the checked save path as the administrator;
    a screen's test check runs the integration test now."""
    import asyncio
    import uuid

    from integrations import registry, wizard
    from integrations.store import MANUAL
    from integrations.testing import run_integration_test as _run

    user = _require_admin(request)
    integ = _integration_or_404(key)
    store, screens, p = await _wizard_context(request, key)
    ids = [s.id for s in screens]
    by_id = {s.id: s for s in screens}
    actor = _actor(user)
    reason = "set in the setup wizard"

    if "credsAtStart" not in p:
        # The first time this setup is touched: were its credentials all set?
        p["credsAtStart"] = wizard.credentials_set(key, get_settings())

    async def respond() -> dict:
        await store.put(key, p, by=actor)
        return {"page": await page_payload(_store(request), await _test_runs(request),
                                           await _page_state(request))}

    if action == "restart":
        kept = {k: p[k] for k in wizard.KEPT if k in p}
        p.clear()
        p.update(wizard.blank(), **kept)
        return await respond()
    if action == "back":
        if p["history"]:
            p["current"] = p["history"].pop()
            p["finished"], p["ended"], p["failure"] = False, "", None
        else:
            # W5: the screens before the one the wizard opened at were taken
            # as done, and Back revisits them too (phase 11, option A).
            overrides = await _store(request).load() if _store(request) is not None else {}
            settings = get_settings()
            state = wizard.State(settings=settings, overrides=overrides,
                                 test_runs=await _test_runs(request), answers=p["answers"])
            here = wizard.shown(screens, state, p)
            prev = wizard.previous_screen(screens, here, wizard.when_answers(screens, p["answers"], settings)) \
                if here else None
            if prev:
                p["current"] = prev
                p["finished"], p["ended"], p["failure"] = False, "", None
        return await respond()
    if action == "review":
        # Every check passes: open the first screen, so any answer can be
        # seen and changed (phase 11, option A). Answers already saved stay.
        answers = p.get("answers") or {}
        kept = {k: p[k] for k in wizard.KEPT if k in p}
        p.clear()
        p.update(wizard.blank(), **kept)
        p["answers"] = answers
        p["current"] = wizard.first_screen(screens, wizard.when_answers(screens, answers, get_settings()))
        return await respond()

    screen = by_id.get(body.screen)
    if screen is None:
        raise HTTPException(status_code=404, detail=f"There is no screen '{body.screen}' in {integ.name}'s wizard.")

    if action == "ask":
        failure = (p.get("failure") or {}).get("reason") or "Its check did not pass."
        settings = get_settings()
        if not (settings.anthropic_api_key or "").strip() and getattr(request.app.state, "anthropic_client", None) is None:
            raise HTTPException(status_code=409, detail="The Anthropic API key is not set. Set it on the Anthropic sub-tab first.")
        spent = await store.spent_this_month()
        budget = float(settings.integration_agent_monthly_budget or 0)
        if spent >= budget:
            raise HTTPException(status_code=409, detail=(
                f"Claude has spent ${spent:.2f} this month, which reaches the monthly budget of ${budget:.2f}. "
                "Raise the Integration agent monthly budget on the Anthropic sub-tab to ask again."))
        if (p.get("help") or {}).get("status") == "running":
            raise HTTPException(status_code=409, detail="Claude is already answering a question about this wizard.")
        call_id = str(uuid.uuid4())
        snap = await _snapshot(request, integ, (await _test_store(request).latest(key)) if _test_store(request) else {})
        p["help"] = {"status": "running", "screen": screen.id, "id": call_id}
        await store.record_call(call_id=call_id, integration=key, screen=screen.id, status="running", asked_by=actor)
        tasks = getattr(request.app.state, "diagnosis_tasks", None)
        if tasks is None:
            tasks = request.app.state.diagnosis_tasks = set()
        task = asyncio.create_task(_run_ask(request.app, key, call_id, snap, screen.as_dict(), failure, actor))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return await respond()

    if screen.id != p.get("current") and screen.id not in ids:
        raise HTTPException(status_code=409, detail="That screen is not in this wizard.")
    p["failure"], p["help"] = None, None
    then = "next"
    if action == "answer":
        chosen = next((a for a in screen.ask if str(a.get("answer")) == body.answer), None)
        if chosen is None:
            raise HTTPException(status_code=400, detail=f"'{body.answer}' is not an answer to this question.")
        for skey, svalue in (chosen.get("sets") or {}).items():
            try:
                await _checked_save(request, user, skey, SettingIn(value=str(svalue), reason=reason))
            except HTTPException as exc:
                p["current"] = screen.id
                p["failure"] = {"screen": screen.id, "reason": str(exc.detail)}
                return await respond()
        p["answers"][screen.id] = body.answer
        then = str(chosen.get("then") or "next")
    elif action == "enter":
        if not screen.enters:
            raise HTTPException(status_code=400, detail="This screen has no box to fill in.")
        if body.value.strip():
            try:
                res = await _checked_save(request, user, screen.enters, SettingIn(value=body.value.strip(), reason=reason))
            except HTTPException as exc:
                p["current"] = screen.id
                p["failure"] = {"screen": screen.id, "reason": str(exc.detail)}
                return await respond()
            if res.get("reverted"):
                p["current"] = screen.id
                p["failure"] = {"screen": screen.id, "reason": f"Saved, then undone automatically: {res['reverted']}"}
                return await respond()
        for skey, svalue in (screen.sets if body.value.strip() else ()):
            try:
                await _checked_save(request, user, skey, SettingIn(value=svalue, reason=reason))
            except HTTPException as exc:
                p["current"] = screen.id
                p["failure"] = {"screen": screen.id, "reason": f"Saved, but {skey} was refused: {exc.detail}"}
                return await respond()
    elif action == "run":
        # A phase 7 coded action (phase 9): run it, save what it proposes
        # through the checked save path, then the screen's check as usual.
        from integrations import actions as coded

        if not screen.runs:
            raise HTTPException(status_code=400, detail="This screen has no button to run.")
        result = await coded.run(screen.runs, get_settings(), "", dry=False)
        if not result.ok:
            p["current"] = screen.id
            p["failure"] = {"screen": screen.id, "reason": result.summary}
            return await respond()
        for skey, svalue in result.proposes.items():
            try:
                await _checked_save(request, user, skey, SettingIn(value=str(svalue), reason=reason))
            except HTTPException as exc:
                p["current"] = screen.id
                p["failure"] = {"screen": screen.id,
                                "reason": f"{result.summary} But saving {skey} was refused: {exc.detail}"}
                return await respond()
    elif action != "done":
        raise HTTPException(status_code=404, detail=f"There is no wizard action '{action}'.")

    # The screen's check, now.
    if screen.check and then != wizard.END:
        test_runs = {}
        if screen.check.startswith("test:"):
            target = registry.integration_for(screen.check[5:].split("/")[0])
            result = await _run(target, get_settings())
            runs = _test_store(request)
            if runs is not None:
                await runs.record(result, trigger=MANUAL, run_by_id=str(user.get("userId") or ""), run_by=actor)
            test_runs = {target.key: result}
            if target.key == key and result.get("outcome") == "ok":
                p["completed"] = True
        overrides = await _store(request).load() if _store(request) is not None else {}
        state = wizard.State(settings=get_settings(), overrides=overrides, test_runs=test_runs,
                             answers=p["answers"])
        outcome, why = wizard.evaluate(screen, state)
        if outcome != wizard.PASS:
            p["current"] = screen.id
            p["failure"] = {"screen": screen.id, "reason": why}
            return await respond()

    nxt = wizard.next_screen(screens, screen.id,
                             wizard.when_answers(screens, p["answers"], get_settings()), then)
    p["history"].append(screen.id)
    if then == wizard.END:
        p["current"], p["ended"] = None, f"{integ.name} is marked as not used by this chapter."
    elif nxt is None:
        p["current"], p["finished"], p["completed"] = None, True, True
    else:
        p["current"] = nxt
    return await respond()


async def _run_ask(app: Any, key: str, call_id: str, snap: Any, screen: dict[str, Any],
                   failure: str, actor: str) -> None:
    """In the background: Claude's answer about one failed screen. Never raises."""
    from integrations import diagnosis
    from integrations.testing import secret_values

    store = app.state.wizard_store
    settings = get_settings()
    outcome = None
    try:
        factory = getattr(app.state, "anthropic_client", None)
        if factory is None:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, timeout=300.0, max_retries=2)
        else:
            client = factory()
        outcome = await diagnosis.explain(client, snap, screen, failure, model=settings.integration_agent_model,
                                          secrets=secret_values(settings))
    except Exception as exc:  # noqa: BLE001
        log.warning("Ask Claude for %s failed: %s", key, exc)
    answer = (outcome.plan or {}).get("answer", "") if outcome else ""
    error = (outcome.error if outcome else "") or ("" if answer else "Claude could not answer just now.")
    cost = outcome.cost if outcome else 0.0
    try:
        await store.record_call(call_id=call_id, integration=key, screen=screen.get("id", ""),
                                status="answered" if answer else "failed", answer=answer or error,
                                cost=cost, asked_by=actor)
        p = await store.get(key) or {}
        if (p.get("help") or {}).get("id") == call_id:
            p["help"] = {"status": "answered" if answer else "failed", "screen": screen.get("id"),
                         "id": call_id, "text": answer or error, "cost": round(cost, 4)}
            await store.put(key, p, by=actor)
    except Exception as exc:  # noqa: BLE001
        log.warning("Ask Claude answer for %s could not be stored: %s", key, exc)

