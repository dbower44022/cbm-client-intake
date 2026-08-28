"""FastAPI app factory — registers forms and serves their frontends.

For each registered form the app exposes ``POST /api/{slug}/intake`` and, when
the form ships a frontend, serves it at ``/{slug}/``. Shared assets (the design
tokens) are served at ``/shared/``. The root lists the available forms.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time  # noqa: F401 — the TTL + rate-limit middlewares both use it
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from html import escape as html_escape
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.sessions import SessionMiddleware

from . import boot_overrides
from . import network_standard as _network_standard
from . import receipts
from . import store as store_mod
from .branding import BrandedStaticFiles, render_page as render_branding
from .config import Settings, get_settings, override_values, overrides_version
from .espo import DryRunEspoClient, EspoApi, EspoClient, EspoError
from .forms import BaseSubmission, FormSpec
from .logging_setup import setup_logging
from .resumable import ResumableClient
from .store import SubmissionStore
from .version import __version__

# Shared format for both processes (level/name/seconds — see the module doc);
# re-applied with the configured LOG_LEVEL in create_app once settings load.
setup_logging()
log = logging.getLogger("cbm_intake")

SHARED_DIR = Path(__file__).resolve().parent.parent / "frontend" / "shared"
ASSIGNMENTS_FRONTEND_DIR = (
    Path(__file__).resolve().parent.parent / "assignments" / "frontend"
)
OPS_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "ops" / "frontend"
MENTORPROFILE_FRONTEND_DIR = (
    Path(__file__).resolve().parent.parent / "mentorprofile" / "frontend"
)
MENTORADMIN_FRONTEND_DIR = (
    Path(__file__).resolve().parent.parent / "mentoradmin" / "frontend"
)
PORTAL_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "portal" / "frontend"
# One shared frontend served at all three Session Management routes; the JS reads
# the domain from its own URL path (see sessions/frontend/app.js).
SESSIONS_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "sessions" / "frontend"
# One shared frontend served at all Workspace Directory routes
# (/directory/{companies,contacts,mentors}); the JS reads the kind from its URL.
DIRECTORY_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "directory" / "frontend"
MYEMAIL_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "myemail" / "frontend"
EVENTS_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "events" / "frontend"
ANALYTICS_FRONTEND_DIR = (
    Path(__file__).resolve().parent.parent / "analytics" / "frontend"
)
SETUP_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "setup" / "frontend"
# The WordPress plugin's own assets, served so the website preview
# (/events/preview.html) can exercise the EXACT renderer that will ship rather
# than a copy of it that can drift.
EVENTS_PLUGIN_ASSETS_DIR = (
    Path(__file__).resolve().parent.parent / "wp-plugin" / "cbm-events" / "assets"
)


def _make_client(settings: Settings) -> EspoApi:
    if settings.espo_dry_run:
        return DryRunEspoClient()
    return EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )


def _make_handler(
    spec: FormSpec,
    settings: Settings,
    processed: dict[str, dict],
    store: Optional[SubmissionStore],
):
    async def handler(request: Request):
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 — malformed/truncated JSON is caller data
            # Previously a raw 500; a bad body is a 422 like any invalid input.
            return JSONResponse(
                status_code=422,
                content={"detail": "The request body is not valid JSON."},
            )
        return await _process_submission(spec, settings, processed, store, body)

    return handler


def _receipt_row_like(
    spec: FormSpec, submission: Any, status: str,
    *, result: Optional[dict] = None, error: Optional[str] = None,
) -> dict:
    """A synthesized store-row for the STORELESS (dev/dry-run) receipt write —
    core.receipts is row-driven, and without a database there is no row."""
    payload = json.loads(submission.model_dump_json())
    payload["company_url"] = ""
    return {
        "form_slug": spec.slug,
        "submission_token": submission.submission_token,
        "status": status,
        "payload": payload,
        "result": result,
        "last_error": error,
        "attempt_count": 1 if error else 0,
        "received_at": datetime.now(timezone.utc),
    }


async def _recent_duplicate_id(
    store: SubmissionStore,
    settings: Settings,
    spec: FormSpec,
    submission: BaseSubmission,
) -> Optional[str]:
    """The id of a recent prior submission of this form from this email, or None.

    Best-effort by design: this guard exists to save staff cleanup work, so a
    store hiccup must never cost us the submission. On any failure we log and
    return None — the submission delivers exactly as it did before the guard
    existed.
    """
    window = settings.duplicate_hold_seconds
    email = str(getattr(submission, "email", "") or "").strip()
    if window <= 0 or not email:
        return None
    try:
        prior = await store.find_recent_duplicate(spec.slug, email, within_seconds=window)
    except Exception as exc:  # noqa: BLE001 — never block a submission over this
        log.warning("duplicate check failed for %s (%s) — delivering: %s",
                    spec.slug, email, exc)
        return None
    if not prior:
        return None
    log.info(
        "%s duplicate hold: %s re-submitted (prior=%s received %s)",
        spec.slug, email, prior.get("id"), prior.get("received_at"),
    )
    return prior.get("id")


async def _process_submission(
    spec: FormSpec,
    settings: Settings,
    processed: dict[str, dict],
    store: Optional[SubmissionStore],
    body: Any,
):
    """Validate, capture and deliver one submission.

    Split out of :func:`_make_handler` so a form can also be reached through a
    purpose-built route — the Events register endpoint takes the event slug from
    the URL path and merges it into the body — WITHOUT reimplementing durable
    capture, idempotency, the honeypot, async hand-off, or the audit log.
    """
    try:
        submission = spec.submission_model.model_validate(body)
    except ValidationError as exc:
        # exc.errors() can carry a raw exception in ctx (non-serializable);
        # project to a JSON-safe shape.
        errors = [
            {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
            for e in exc.errors()
        ]
        # ``detail`` is a human-readable string naming each failing field
        # and why — the frontends display it verbatim, so the user (and
        # whoever they screenshot it to) sees the exact reason, never a
        # generic "check your entries". The structured list rides along
        # as ``errors`` for programmatic clients.
        detail = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'submission'}: {e['msg']}"
            for e in errors
        )
        # Log it too — otherwise a validation failure (e.g. a form/schema
        # mismatch after CRM enum drift) is invisible in the run logs.
        log.warning("%s validation failed: %s", spec.slug, detail)
        return JSONResponse(
            status_code=422, content={"detail": detail, "errors": errors}
        )

    client = _make_client(settings)
    is_honeypot = bool(submission.company_url.strip())

    # V2 Phase 0: durably capture the submission BEFORE any CRM work. This is
    # also the durable idempotency check (replacing the in-memory dict). A
    # repeat token short-circuits here without touching the CRM again.
    captured = None
    duplicate_of = None
    if store is not None:
        payload = json.loads(submission.model_dump_json())
        payload["company_url"] = ""  # never persist the honeypot value
        # Near-duplicate hold: a client who re-fills the whole form (to add a
        # mentor request, fix a typo) would otherwise create a SECOND client
        # profile + engagement — and, because CClientProfile.linkedCompany is a
        # hasOne, silently strip those links off the first one. Held for staff
        # review instead. Spam wins over duplicate: a honeypot hit stays spam.
        if not is_honeypot:
            duplicate_of = await _recent_duplicate_id(store, settings, spec, submission)
        if is_honeypot:
            capture_status = store_mod.STATUS_HELD
        elif duplicate_of:
            capture_status = store_mod.STATUS_HELD_DUPLICATE
        else:
            capture_status = store_mod.STATUS_PENDING
        try:
            captured = await store.capture(
                spec.slug, submission.submission_token, payload,
                status=capture_status, duplicate_of=duplicate_of,
            )
        except Exception as exc:  # noqa: BLE001 — DB outage at accept (P2)
            # The log line is the submission's ONLY copy right now
            # (storeless-style dump), and the user gets a controlled
            # please-retry instead of a raw 500.
            log.error(
                "durable capture FAILED for %s token=%s (%s); payload=%s",
                spec.slug, submission.submission_token, exc, payload,
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    "We couldn't record your submission just now — please "
                    "try again in a moment. Nothing was saved."
                ),
            )
        if not captured.is_new:
            if captured.result is not None:
                return {"status": "ok", "idempotent": True, **captured.result}
            return {"status": "received", "idempotent": True}

    # Honeypot: acknowledge generically, do not tell a bot it was caught.
    # The submission is held for admin review — and its CRM receipt is written
    # immediately (intakeStatus=Held-Spam) so the CRM sees the arrival — so a
    # false positive (e.g. browser autofill, seen 2026-06-12) is recoverable
    # without contacting the submitter.
    if is_honeypot:
        if captured is not None:
            written = await receipts.touch_safe(client, store, captured.id)
        else:
            written = await receipts.create_direct(
                client, _receipt_row_like(spec, submission, store_mod.STATUS_HELD)
            )
        log.warning(
            "honeypot %s token=%s email=%s receipt=%s",
            spec.slug,
            submission.submission_token,
            getattr(submission, "email", "?"),
            written,
        )
        return {"status": "received"}

    # Near-duplicate: captured, acknowledged to the visitor exactly like any
    # other submission (from their side nothing is wrong — they submitted a
    # form and we have it), and NOT delivered. It waits in Submission Admin
    # for a human to Approve or Discard. Deliberately placed before the
    # async/sync delivery split so it holds in BOTH modes.
    if duplicate_of and captured is not None:
        await receipts.touch_safe(client, store, captured.id)
        log.info(
            "%s held as possible duplicate token=%s reference=%s (of %s)",
            spec.slug, submission.submission_token, captured.id, duplicate_of,
        )
        return {"status": "received", "reference": captured.id}

    # V2 Phase 1: with async delivery on, return as soon as the submission is
    # durably captured — the background worker delivers it into the CRM. The
    # CRM receipt (intakeStatus=Received) is written in the background so the
    # visitor's instant acknowledgment never waits on the CRM; a failed write
    # is healed by the worker's outcome touch or the reconciliation sweep.
    if captured is not None and settings.async_delivery:
        asyncio.create_task(receipts.touch_safe(client, store, captured.id))
        # The accept-side end of the trace: the worker logs the same slug +
        # token on claim/delivered/retry, so one submission is followable
        # across both processes by token (reliability review, correlation).
        log.info(
            "%s received token=%s reference=%s (async)",
            spec.slug, submission.submission_token, captured.id,
        )
        return {"status": "received", "reference": captured.id}

    # In-memory idempotency only when there is no durable store.
    key = f"{spec.slug}:{submission.submission_token}"
    if store is None and key in processed:
        return {"status": "ok", "idempotent": True, **processed[key]}

    # P1-8: with a store, the sync path records per-record progress like
    # the worker does — a partial failure marked needs_attention then
    # carries its progress, so an /ops redrive RESUMES instead of
    # re-running the whole chain and duplicating the plain creates.
    delivery_client: EspoApi = client
    if captured is not None:

        async def _save_progress(progress: dict) -> None:
            await store.save_progress(captured.id, progress)

        delivery_client = ResumableClient(client, None, _save_progress)

    try:
        ids = await spec.orchestrator(submission, delivery_client)
    except EspoError as exc:
        # Record the failure on the CRM receipt (intakeStatus=Error with the
        # what-happened-and-how-to-fix message). Best-effort, then the 502.
        if captured is not None:
            await store.mark_failed(
                captured.id, status=store_mod.STATUS_NEEDS_ATTENTION, error=str(exc)
            )
            await receipts.touch_safe(client, store, captured.id)
        else:
            await receipts.create_direct(
                client,
                _receipt_row_like(
                    spec, submission, store_mod.STATUS_NEEDS_ATTENTION, error=str(exc)
                ),
            )
        log.error("%s failed token=%s: %s", spec.slug, submission.submission_token, exc)
        raise HTTPException(
            status_code=502,
            detail=(
                "Your request was received but could not be fully completed in "
                "the system of record. It has been recorded for completion."
            ),
        )

    if captured is not None:
        # Record-creating forms auto-close on delivery (Doug's ruling): the
        # downstream admin team handles them — nothing for /ops to do.
        await store.mark_completed(
            captured.id, ids, auto_close_reason=store_mod.autoclose_reason(spec.slug)
        )
        # The receipt reaches Completed (+ the Contact link) — the same event
        # the CRM's intakeStatus and Submission Admin now both call by name.
        await receipts.touch_safe(client, store, captured.id)
    else:
        processed[key] = ids
        await receipts.create_direct(
            client,
            _receipt_row_like(
                spec, submission, store_mod.STATUS_COMPLETED, result=ids
            ),
        )
    log.info("%s ok token=%s ids=%s", spec.slug, submission.submission_token, ids)
    return {"status": "ok", **ids}


# Canonical environment key -> display name shown after the version in the footer
# (e.g. "v0.18.0 (Production)"). Mirrors frontend/shared/footer.js.
_ENV_NAMES = {"production": "Production", "test": "Test", "dev": "Dev"}


def _env_name(environment: str) -> str:
    if not environment:
        return ""
    return _ENV_NAMES.get(environment, environment.capitalize())


def _index_html(
    forms: list[FormSpec],
    environment: str = "",
    organization: str = "Cleveland Business Mentors",
) -> str:
    """The PUBLIC form index — served at ``/`` only when the staff stack is off
    (no ``SESSION_SECRET``, e.g. the dry-run dev app). With the staff stack on,
    the root serves the authenticated portal instead (``portal/frontend``)."""
    # Each entry shows its shortcut path (the normalized alias the /{alias}
    # redirect accepts — no dashes or caps to remember; see form_alias).
    def shortcut(slug: str) -> str:
        alias = re.sub(r"[^a-z0-9]", "", slug)
        return f' <code class="shortcut">/{alias}</code>'

    items = []
    for f in forms:
        if f.frontend_dir is not None:
            items.append(
                f'<li><a href="/{f.slug}/" target="_blank" rel="noopener">{f.title}</a>'
                f"{shortcut(f.slug)}</li>"
            )
        else:
            items.append(f"<li>{f.title} <em>(API only — UI pending)</em></li>")
    year = datetime.now(timezone.utc).year
    org = html_escape(organization)
    name = _env_name(environment)
    version_label = f"v{__version__}" + (f" ({name})" if name else "")
    footer = (
        f"<footer><p>&copy; {year} {org}. "
        f"All rights reserved. &middot; {version_label}</p></footer>"
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{org} — Intake Forms</title>"
        "<style>.shortcut{background:#f0f2f5;border:1px solid #d7dce2;"
        "border-radius:4px;padding:0.05em 0.4em;font-size:0.85em;color:#556}"
        "li{margin:0.3em 0}</style></head><body>"
        + "<h1>CBM Intake Forms</h1><ul>" + "".join(items) + "</ul>" + footer
        + "</body></html>"
    )


def create_app(
    forms: list[FormSpec], *, store: Optional[SubmissionStore] = None
) -> FastAPI:
    settings = get_settings()
    # Install stored overrides BEFORE anything below reads a setting. Router
    # mounting, middleware and logging are all decided in this function, so an
    # override for one of those keys used to never apply at all — not even after
    # a redeploy, because the redeploy re-ran this first. Doug's ruling of
    # 2026-08-28 is that every setting belongs on the Settings page, which
    # requires "takes effect on restart" to be TRUE rather than a promise. This
    # is what makes it true. Never raises, and degrades to the deployment's own
    # values rather than to code defaults. See core/boot_overrides.
    boot_overrides.load_at_boot(settings)
    setup_logging(settings.log_level)
    # Fail-fast on contradictory config (Phase 6, reliability review
    # 2026-07-17): these combinations used to boot fine and fail at runtime —
    # live mode without an API key 401'd every CRM call; async delivery
    # without a store silently fell back to synchronous.
    if not settings.espo_dry_run and not settings.espo_api_key:
        raise RuntimeError(
            "ESPO_DRY_RUN=false requires ESPO_API_KEY — refusing to boot into "
            "silent 401s on every CRM call."
        )
    if settings.async_delivery and not settings.database_url and store is None:
        raise RuntimeError(
            "ASYNC_DELIVERY=true requires DATABASE_URL (the durable store the "
            "worker claims from) — refusing to boot into silent sync mode."
        )
    # V2 Phase 0: a durable store when DATABASE_URL is set (else None = V1 behavior).
    # Tests inject a fake store directly.
    if store is None:
        store = store_mod.make_store(settings)

    # Effective-mode banner (the worker has had one since Phase 1 of V2; the
    # web tier booted silently — a degraded mode like "no store" was invisible
    # until something failed).
    log.info(
        "intake app starting: environment=%s dryRun=%s durableStore=%s "
        "asyncDelivery=%s staffStack=%s gmailSync=%s gcalEvents=%s "
        "gdriveDocs=%s(identity=%s) provisioning=%s forms=%s",
        settings.environment, settings.espo_dry_run, store is not None,
        settings.async_delivery, settings.assignments_active,
        settings.gmail_sync, settings.gcal_events,
        settings.gdrive_docs, settings.gdrive_identity,
        settings.mentor_provision_users, [f.slug for f in forms],
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # NOTE deliberately no store.create_all() here (Phase 6): the schema
        # authority is Alembic (the PRE_DEPLOY migrate job in production;
        # `uv run alembic upgrade head` locally). Building tables at boot left
        # a fresh environment WITHOUT an alembic_version stamp, wedging every
        # later `upgrade head`. Missing tables now surface as visible capture
        # 503s / worker cycle errors instead of a silently forked schema.
        #
        # Worker-liveness watch (2026-07-23): the web process — which survives
        # a dead worker — periodically checks the heartbeat row and alerts
        # when it goes stale. Only meaningful when a worker is expected
        # (async delivery) and a store exists to read the heartbeat from.
        liveness_task = None
        if (
            store is not None
            and settings.async_delivery
            and settings.worker_liveness_check_seconds > 0
        ):
            import asyncio as _asyncio

            from core import monitoring as _monitoring

            async def _liveness_loop() -> None:
                state: dict = {}
                while True:
                    await _asyncio.sleep(settings.worker_liveness_check_seconds)
                    try:
                        await _monitoring.run_worker_liveness_check(
                            store, settings, state
                        )
                    except Exception:  # noqa: BLE001 — the watch must survive
                        log.exception("worker liveness check failed")

            liveness_task = _asyncio.create_task(_liveness_loop())
            log.info(
                "worker liveness watch enabled (every %ss, stale after %ss)",
                settings.worker_liveness_check_seconds,
                settings.worker_heartbeat_alert_seconds,
            )
        # System Settings — the runtime override layer. Each process re-reads
        # `app_setting` on a timer; this is the lag between an admin toggling
        # something here and the WORKER (a separate container) acting on it, and
        # it is what /healthz reports as `settingsVersion`. Refreshing here also
        # means the very first request after boot already sees the overrides.
        settings_task = None
        settings_store = getattr(_app.state, "settings_store", None)
        if settings_store is not None and settings.settings_overrides:
            import asyncio as _asyncio

            from core.settings_store import refresh_into_config as _refresh
            from core.settings_store import sweep_reverts as _sweep_reverts

            await _refresh(settings_store, settings)

            async def _settings_loop() -> None:
                while True:
                    await _asyncio.sleep(max(5, settings.setup_refresh_seconds))
                    try:
                        # Undo any change nobody confirmed in time BEFORE
                        # re-reading, so the refresh installs the restored value
                        # in the same pass. This is what rescues an admin who
                        # locked themselves out: it is a background task, so it
                        # keeps running even when no request can reach the page.
                        await _sweep_reverts(settings_store)
                        await _refresh(settings_store, get_settings())
                    except Exception:  # noqa: BLE001 — must never take the app down
                        log.exception("settings override refresh failed")

            settings_task = _asyncio.create_task(_settings_loop())
            log.info(
                "settings overrides enabled (refresh every %ss)",
                settings.setup_refresh_seconds,
            )
        # Stamp B — the CRM's configuration version, cached for /healthz. Its
        # own task rather than a line in the settings loop above, because that
        # one only runs when a database is configured and this has nothing to
        # do with a database. Ships dark: 0 disables, and 0 is the default.
        # /healthz reads the cache, never the CRM (see core/network_standard).
        crm_config_task = None
        if settings.crm_config_refresh_seconds > 0 and not settings.espo_dry_run:
            import asyncio as _asyncio

            from core import network_standard as _ns

            async def _crm_config_loop() -> None:
                while True:
                    try:
                        await _ns.refresh(_make_client(get_settings()))
                    except Exception:  # noqa: BLE001 — must never take the app down
                        log.exception("crmConfig refresh failed")
                    await _asyncio.sleep(
                        max(30, get_settings().crm_config_refresh_seconds)
                    )

            crm_config_task = _asyncio.create_task(_crm_config_loop())
            log.info(
                "crmConfig probe enabled (refresh every %ss)",
                settings.crm_config_refresh_seconds,
            )
        try:
            yield
        finally:
            if crm_config_task is not None:
                crm_config_task.cancel()
            if liveness_task is not None:
                liveness_task.cancel()
            if settings_task is not None:
                settings_task.cancel()

    app = FastAPI(title="CBM Intake Forms", version=__version__, lifespan=lifespan)
    # Exposed to the ops console router (V2 Phase 2).
    app.state.submission_store = store
    # Exposed to the analytics router — the cached-metric store (None => the app
    # runs live-only, recomputing each view). Independent of the submission store.
    if settings.analytics_active:
        from analytics import make_analytics_store

        app.state.analytics_store = make_analytics_store(settings)
    else:
        app.state.analytics_store = None
    # Exposed to the public Events API — the API-key CRM client (no session).
    # A factory rather than a client so tests can substitute a fake, and so the
    # client is built per request like the intake handlers do.
    app.state.events_client_factory = lambda: _make_client(settings)
    # Exposed to the portal router (the public-form links on the home page).
    app.state.form_specs = forms
    # System Settings (prds/system-settings-plan.md). The override store is
    # created whenever a database is attached — even with the /setup page off —
    # because the override layer and the page are separate concerns: an existing
    # override must keep applying if the page is later switched off.
    from core.settings_store import make_settings_store

    app.state.settings_store = make_settings_store(settings)
    if settings.setup_active:
        from setup.jobs import make_job_store

        app.state.job_store = make_job_store(settings)
    else:
        app.state.job_store = None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # --- public intake POST limits (Phase 6, decision D3: 2 MB / 30 per
    # 10 min per IP). Before this the DO edge passed >=60 MB bodies into
    # `await request.json()` and a token-varying bot could write unbounded
    # rows/CRM records — the honeypot + idempotency only stop dumb repeats.
    _mb = 1024 * 1024
    _intake_caps = {
        # The volunteer form carries its resume as base64 INSIDE the JSON
        # (MAX_RESUME_B64_CHARS = 7,000,000 ≈ a 5 MB file) — its cap must
        # clear that; every other form is plain text fields.
        f"/api/{spec.slug}/intake": (
            8 * _mb if spec.slug == "volunteer"
            else settings.intake_max_body_mb * _mb
        )
        for spec in forms
    }
    # Per-IP sliding window, in-memory and per app instance (the worker is
    # a separate process; the web tier runs a single instance).
    _rate_hits: dict[str, list[float]] = {}

    def _client_ip(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "?"

    def _body_cap(path: str) -> Optional[int]:
        """The body cap for a public write path, or None if it isn't one.

        Event registration lives at a DYNAMIC path (the event slug is in the
        URL), so it can't be looked up in the exact-match table — without this
        it would be the one public POST with no size cap and no rate limit.
        """
        cap = _intake_caps.get(path)
        if cap is not None:
            return cap
        if path.startswith("/api/events/") and path.endswith(
            ("/register", "/cancel")
        ):
            return settings.intake_max_body_mb * _mb
        return None

    @app.middleware("http")
    async def _intake_limits(request: Request, call_next):
        cap = _body_cap(request.url.path)
        if cap is not None and request.method == "POST":
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > cap:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            f"The submission is too large (limit "
                            f"{cap // _mb} MB)."
                        )
                    },
                )
            if settings.intake_rate_limit > 0:
                now = time.time()
                window = settings.intake_rate_window_seconds
                ip = _client_ip(request)
                hits = [t for t in _rate_hits.get(ip, []) if now - t < window]
                if len(hits) >= settings.intake_rate_limit:
                    log.warning("intake rate limit hit for %s (%s)", ip, request.url.path)
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": (
                                "Too many submissions from your network — "
                                "please wait a few minutes and try again."
                            )
                        },
                        headers={"Retry-After": str(window)},
                    )
                hits.append(now)
                _rate_hits[ip] = hits
        return await call_next(request)

    # Mentor assignment tool: signed-cookie sessions hold each staff user's
    # EspoCRM auth token. Only mounted when a session secret is configured.
    if settings.assignments_active:

        @app.middleware("http")
        async def _membership_ttl(request: Request, call_next):
            """Staff-gate membership TTL (P1-12, reliability review 2026-07-17).

            The signed cookie caches team membership at login; without this, a
            staffer removed from a team kept their entitlements until the CRM
            token died (which can be never — /ops makes no CRM calls at all).
            On staff API requests, when the session's membership stamp is older
            than MEMBERSHIP_REFRESH_SECONDS, re-read membership from the CRM as
            the user and re-save the session; a dead token clears the session so
            the app gate answers 401. Registered BEFORE SessionMiddleware in
            code so it runs INSIDE it (request.session live, rewrites saved).
            The portal is excluded — its session restore already refreshes.
            """
            path = request.url.path
            if "/api/" in path and not path.startswith("/api/portal"):
                from assignments import auth as staff_auth

                sess = staff_auth.current_user(request)
                stale = sess is not None and (
                    time.time() - (sess.get("refreshedAt") or 0)
                    >= settings.membership_refresh_seconds
                )
                if stale:
                    try:
                        updated = await staff_auth.refresh_membership(settings, sess)
                        staff_auth.set_session(request, updated)
                    except staff_auth.AuthError:
                        # Token dead/revoked — drop the session; the gate 401s
                        # and the frontend sends the user back to the portal.
                        staff_auth.clear_session(request)
            return await call_next(request)

        app.add_middleware(
            SessionMiddleware,
            secret_key=settings.session_secret,
            session_cookie="cbm_assign_session",
            https_only=settings.session_cookie_secure,
            same_site="lax",
        )

    @app.middleware("http")
    async def _revalidate_frontend(request: Request, call_next):
        """Make the frontend always revalidate so deploys take effect at once.

        Without this, browsers (and DO's edge) may serve a stale cached
        ``app.js``/``wizard.css`` after a deploy, so a fix only appears after a
        hard refresh. ``no-cache`` lets the asset stay cached but forces a
        conditional request; StaticFiles answers with a cheap ``304`` when the
        ETag is unchanged, and full fresh content when it is not. The JSON API
        and ``/healthz`` are left untouched, as is any route that set its own
        Cache-Control (the index and the record pages use a stronger no-store).
        """
        response = await call_next(request)
        path = request.url.path
        if (
            request.method in ("GET", "HEAD")
            and not path.startswith("/api/")
            and path != "/healthz"
            and "cache-control" not in response.headers
        ):
            response.headers["Cache-Control"] = "no-cache"
        return response

    # Idempotency cache shared across forms (Technical Design §4 wants a durable store).
    processed: dict[str, dict] = {}

    @app.get("/healthz")
    async def healthz(response: Response) -> dict:
        # Verify the durable store is actually reachable — if it's configured but
        # down, capture would fail, so the app is genuinely unhealthy (503).
        # The CRM is deliberately NOT pinged: a CRM outage must not take the web
        # tier down, since durable capture + the async worker exist precisely to
        # ride it out.
        database = None
        worker_info = None
        if store is not None:
            try:
                await store.ping()
                database = "ok"
            except Exception as exc:  # noqa: BLE001 — report, don't raise
                database = "error"
                response.status_code = 503
                log.warning("healthz: database ping failed: %s", exc)
            # Worker liveness + backlog (P1-6): the in-worker alerter cannot
            # alert on its own death, so an external uptime check watches these
            # fields instead. Best-effort — a failed read reports null fields
            # and NEVER degrades /healthz (decision D1: only the DB ping 503s).
            if database == "ok":
                try:
                    m = await store.metrics()
                    worker_info = {
                        "lastHeartbeatAgeSeconds": m.get("workerHeartbeatAgeSeconds"),
                        "backlog": m.get("backlog"),
                        "oldestPendingAgeSeconds": m.get("oldestPendingAgeSeconds"),
                        "stranded": m.get("stranded"),
                    }
                except Exception as exc:  # noqa: BLE001 — never fail healthz for this
                    log.warning("healthz: metrics read failed: %s", exc)
        return {
            "status": "ok" if database != "error" else "degraded",
            "version": __version__,
            "environment": settings.environment,
            # Whose deployment this is. Public, like the version — and the name
            # is on every page of the app anyway. The fleet console (plan
            # phase 5) reads it to label an instance.
            "organization": settings.organization_name,
            "dryRun": settings.espo_dry_run,
            # The release train's two version stamps (prds/chapter-network).
            # `version` says what CODE this is; `releaseTag` says what
            # PROMOTION it is, and after a hotfix rebuild the two differ. Null
            # on an untagged build rather than guessing. `crmConfig` is the
            # configuration version of the CRM behind this deployment, served
            # from a cache — /healthz never pings the CRM.
            "releaseTag": settings.release_tag or None,
            "crmConfig": _network_standard.current().as_health(),
            "forms": [f.slug for f in forms],
            "assignments": settings.assignments_active,
            "durableStore": store is not None,
            "database": database,
            "worker": worker_info,
            # The override layer. `settingsVersion` bumps every time a process
            # picks up a change, so comparing web's number with the worker's is
            # how you see whether the worker has caught up yet — they are
            # separate containers on separate refresh timers.
            "settings": {
                "page": settings.setup_active,
                "overridesActive": settings.overrides_active,
                "overrideCount": len(override_values()),
                "settingsVersion": overrides_version(),
            },
        }

    for spec in forms:
        app.add_api_route(
            f"/api/{spec.slug}/intake",
            _make_handler(spec, settings, processed, store),
            methods=["POST"],
            name=f"intake-{spec.slug}",
        )
        # The client-intake form's optional "preferred mentor" dropdown needs a
        # live roster (2026-07-27). Registered per-form so no other deploy —
        # and no other form — exposes it.
        if spec.slug == "client-intake":
            from forms.client_intake.router import make_router as make_roster_router

            app.include_router(make_roster_router(lambda: _make_client(settings)))

    # Assignment tool + ops console API routes (registered before the static
    # mounts below so /assignments/api/* and /ops/api/* resolve to the routers).
    # Both reuse the EspoCRM team-auth session, so they need SESSION_SECRET.
    if settings.assignments_active:
        from assignments import api_router as assignments_router
        from mentoradmin import api_router as mentoradmin_router
        from mentorprofile import api_router as mentorprofile_router
        from ops import api_router as ops_router
        from directory import DIRECTORIES as DIRECTORY_KINDS
        from directory import make_router as make_directory_router
        from myemail import api_router as myemail_router
        from portal import api_router as portal_router
        from sessions import DOMAINS as SESSION_DOMAINS
        from sessions import make_router as make_sessions_router

        app.include_router(myemail_router)
        app.include_router(assignments_router)
        app.include_router(ops_router)
        app.include_router(mentoradmin_router)
        app.include_router(mentorprofile_router)
        app.include_router(portal_router)
        # Analytics app (prds/analytics-app-plan.md) — mounted only when enabled.
        if settings.analytics_active:
            from analytics import api_router as analytics_router

            app.include_router(analytics_router)
        # System Settings — admin-only (not team-gated); mounted only when the
        # feature is on AND there is a database to hold the overrides.
        if settings.setup_active:
            from setup import api_router as setup_router

            app.include_router(setup_router)
        # Event Administration — the staff app; team-gated like the others.
        if settings.events_active:
            from events.router import api_router as events_admin_router

            app.include_router(events_admin_router)
        # Session Management: one router per domain, all from the same engine.
        for _cfg in SESSION_DOMAINS.values():
            app.include_router(make_sessions_router(_cfg))
        # Workspace Directories: one router per kind, all from the same engine.
        for _dcfg in DIRECTORY_KINDS.values():
            app.include_router(make_directory_router(_dcfg))

    # The peer-facing settings snapshot for the environment diff. Outside the
    # staff-stack block on purpose: the caller is the other deployment, not a
    # person, and it authenticates with the shared token. Mounted only when a
    # token is configured, so an unconfigured deploy exposes nothing at all.
    if settings.setup_peer_token:
        from setup import peer_router as setup_peer_router

        app.include_router(setup_peer_router)

    # Events & Webinars: the public read API for the website. Mounted only when
    # switched on, so an unconfigured deploy exposes nothing. Deliberately
    # outside the staff-stack block — it is unauthenticated by design.
    if settings.events_public_active:
        from events import api_router as events_public_router
        from events.public import make_registration_routes
        from forms import event_registration as _event_registration

        app.include_router(events_public_router)
        # Registration rides the SAME durable pipeline as the intake forms —
        # capture before any external call, idempotency, retries, /ops
        # visibility — with the event slug taken from the URL.
        app.include_router(
            make_registration_routes(
                lambda body: _process_submission(
                    _event_registration.SPEC, settings, processed, store, body
                )
            )
        )

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        # With the staff stack on, the root is the authenticated portal (sign in
        # once, see the links your teams allow). Without it (e.g. the dry-run
        # dev app, which has no session support), the public form index remains.
        # no-store so a freshly-deployed page is never served stale from a
        # browser/edge cache (either page is tiny — nothing to gain caching).
        if settings.assignments_active:
            # Read directly rather than through the mount, so the branding
            # substitution the mount would have done has to happen here too.
            html = render_branding(
                (PORTAL_FRONTEND_DIR / "index.html").read_text(encoding="utf-8"),
                settings,
            )
        else:
            html = _index_html(
                forms,
                environment=settings.environment,
                organization=settings.organization_name,
            )
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    # Friendly URL aliases — a typed shortcut like /clientintake (or
    # /Client-Intake, /client_intake, …) goes straight to the form without
    # showing the index. Any single-segment path is normalized (lowercase,
    # alphanumerics only) and, if it matches a form slug or staff tool,
    # redirected to the canonical /{slug}/; anything else is a plain 404.
    # Registered BEFORE the static mounts: an exact /{slug} (no trailing
    # slash) now hits this route and redirects to /{slug}/ — same landing
    # place as the StaticFiles redirect it replaces.
    alias_targets = {
        re.sub(r"[^a-z0-9]", "", spec.slug): f"/{spec.slug}/"
        for spec in forms
        if spec.frontend_dir is not None
    }
    if settings.assignments_active:
        alias_targets.update(
            {
                "assignments": "/assignments/",
                "ops": "/ops/",
                "mentoradmin": "/mentoradmin/",
                "mentorprofile": "/mentorprofile/",
                "myprofile": "/mentorprofile/",
                "myemail": "/myemail/",
                "email": "/myemail/",
            }
        )
        if settings.analytics_active:
            alias_targets["analytics"] = "/analytics/"
        if settings.events_active:
            alias_targets["events"] = "/events/"
            alias_targets["eventadmin"] = "/events/"
        if settings.setup_active:
            alias_targets["setup"] = "/setup/"
            alias_targets["settings"] = "/setup/"
        from sessions import DOMAINS as _SESSION_DOMAINS

        alias_targets.update(
            {slug: f"/{slug}/" for slug in _SESSION_DOMAINS}
        )
        # Workspace + its directories (a bare /directory lands on Companies).
        alias_targets["directory"] = "/directory/companies/"
        alias_targets["workspace"] = "/directory/companies/"

    @app.get("/{alias}", include_in_schema=False)
    async def form_alias(alias: str) -> RedirectResponse:
        dest = alias_targets.get(re.sub(r"[^a-z0-9]", "", alias.lower()))
        if dest is None:
            raise HTTPException(status_code=404, detail="Not found")
        # 307 (not 308/301): permanent redirects get cached hard by browsers,
        # which would outlive a future change to where an alias points.
        return RedirectResponse(dest, status_code=307)

    # Static mounts last so the API routes above take precedence.
    for spec in forms:
        if spec.frontend_dir is not None:
            app.mount(
                f"/{spec.slug}",
                BrandedStaticFiles(directory=str(spec.frontend_dir), html=True),
                name=f"form-{spec.slug}",
            )
    if settings.assignments_active and ASSIGNMENTS_FRONTEND_DIR.is_dir():
        app.mount(
            "/assignments",
            BrandedStaticFiles(directory=str(ASSIGNMENTS_FRONTEND_DIR), html=True),
            name="assignments-frontend",
        )
    if settings.events_active and EVENTS_PLUGIN_ASSETS_DIR.is_dir():
        # Its own top-level path, not under /events, so it cannot be shadowed by
        # the events frontend mount registered below.
        app.mount(
            "/events-plugin",
            StaticFiles(directory=str(EVENTS_PLUGIN_ASSETS_DIR)),
            name="events-plugin-assets",
        )
    if settings.events_active and EVENTS_FRONTEND_DIR.is_dir():
        app.mount(
            "/events",
            BrandedStaticFiles(directory=str(EVENTS_FRONTEND_DIR), html=True),
            name="events-frontend",
        )
    if settings.assignments_active and OPS_FRONTEND_DIR.is_dir():
        app.mount(
            "/ops",
            BrandedStaticFiles(directory=str(OPS_FRONTEND_DIR), html=True),
            name="ops-frontend",
        )
    if settings.assignments_active and MENTORADMIN_FRONTEND_DIR.is_dir():
        app.mount(
            "/mentoradmin",
            BrandedStaticFiles(directory=str(MENTORADMIN_FRONTEND_DIR), html=True),
            name="mentoradmin-frontend",
        )
    if settings.assignments_active and MENTORPROFILE_FRONTEND_DIR.is_dir():
        app.mount(
            "/mentorprofile",
            BrandedStaticFiles(directory=str(MENTORPROFILE_FRONTEND_DIR), html=True),
            name="mentorprofile-frontend",
        )
    if settings.assignments_active and MYEMAIL_FRONTEND_DIR.is_dir():
        app.mount(
            "/myemail",
            BrandedStaticFiles(directory=str(MYEMAIL_FRONTEND_DIR), html=True),
            name="myemail-frontend",
        )
    if settings.analytics_active and ANALYTICS_FRONTEND_DIR.is_dir():
        app.mount(
            "/analytics",
            BrandedStaticFiles(directory=str(ANALYTICS_FRONTEND_DIR), html=True),
            name="analytics-frontend",
        )
    if settings.setup_active and SETUP_FRONTEND_DIR.is_dir():
        app.mount(
            "/setup",
            BrandedStaticFiles(directory=str(SETUP_FRONTEND_DIR), html=True),
            name="setup-frontend",
        )
    if settings.assignments_active and PORTAL_FRONTEND_DIR.is_dir():
        # The portal's assets (its index.html is served at "/" above).
        app.mount(
            "/portal",
            BrandedStaticFiles(directory=str(PORTAL_FRONTEND_DIR), html=True),
            name="portal-frontend",
        )
    if settings.assignments_active and SESSIONS_FRONTEND_DIR.is_dir():
        # One shared frontend, mounted at each domain's route. The JS derives its
        # domain (and API base) from the first path segment of its own URL.
        from sessions import DOMAINS as _SESSION_DOMAINS

        def _record_page(slug: str) -> HTMLResponse:
            """The dedicated RECORD page (/{slug}/record/{id}) — the same built
            frontend, booted straight into one record (the JS reads the id from
            the path; no list, no back-to-list). A <base> tag makes the page's
            relative assets resolve against /{slug}/ from the nested path."""
            html = render_branding(
                (SESSIONS_FRONTEND_DIR / "index.html").read_text(encoding="utf-8"),
                settings,
            )
            html = html.replace("<head>", f'<head><base href="/{slug}/">', 1)
            return HTMLResponse(html, headers={"Cache-Control": "no-store"})

        for _slug in _SESSION_DOMAINS:
            app.add_api_route(
                f"/{_slug}/record/{{record_id}}",
                (lambda _s: (lambda record_id: _record_page(_s)))(_slug),
                methods=["GET"],
                response_class=HTMLResponse,
                include_in_schema=False,
            )
            app.mount(
                f"/{_slug}",
                BrandedStaticFiles(directory=str(SESSIONS_FRONTEND_DIR), html=True),
                name=f"sessions-frontend-{_slug}",
            )
    if settings.assignments_active and DIRECTORY_FRONTEND_DIR.is_dir():
        # One shared frontend, mounted at each directory kind's route. The JS
        # derives its kind (and API base) from the second path segment
        # (/directory/{kind}/…).
        from directory import DIRECTORIES as _DIRECTORY_KINDS

        def _directory_record_page(kind: str, html_file: str) -> HTMLResponse:
            """A dedicated /directory/{kind}/record/{id} page — the View Contact
            page (record.html) for contact kinds, or the rich mentor profile
            page (mentor.html) for the Mentors kind — booted straight into one
            record (the JS reads the id from the path). A <base> tag makes
            relative assets resolve against /directory/{kind}/ from the nested
            path."""
            html = render_branding(
                (DIRECTORY_FRONTEND_DIR / html_file).read_text(encoding="utf-8"),
                settings,
            )
            html = html.replace("<head>", f'<head><base href="/directory/{kind}/">', 1)
            return HTMLResponse(html, headers={"Cache-Control": "no-store"})

        for _kind, _dcfg in _DIRECTORY_KINDS.items():
            _record_html = (
                "record.html" if getattr(_dcfg, "contact_page", False)
                or getattr(_dcfg, "company_page", False)
                else "mentor.html" if getattr(_dcfg, "mentor_page", False)
                else None
            )
            if _record_html:
                app.add_api_route(
                    f"/directory/{_kind}/record/{{record_id}}",
                    (lambda _k, _h: (lambda record_id: _directory_record_page(_k, _h)))(_kind, _record_html),
                    methods=["GET"],
                    response_class=HTMLResponse,
                    include_in_schema=False,
                )
            app.mount(
                f"/directory/{_kind}",
                BrandedStaticFiles(directory=str(DIRECTORY_FRONTEND_DIR), html=True),
                name=f"directory-frontend-{_kind}",
            )
    app.mount(
        "/shared",
        # Branded: legal-links.js carries the policy-document URLs as tokens.
        # Files without tokens (and anything vendored) fall through to the
        # normal streamed response.
        BrandedStaticFiles(directory=str(SHARED_DIR)),
        name="shared",
    )

    return app
