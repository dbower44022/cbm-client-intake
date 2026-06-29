"""FastAPI app factory — registers forms and serves their frontends.

For each registered form the app exposes ``POST /api/{slug}/intake`` and, when
the form ships a frontend, serves it at ``/{slug}/``. Shared assets (the design
tokens) are served at ``/shared/``. The root lists the available forms.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.sessions import SessionMiddleware

from . import store as store_mod
from .config import Settings, get_settings
from .espo import DryRunEspoClient, EspoApi, EspoClient, EspoError
from .forms import FormSpec
from .store import SubmissionStore
from .submission_log import (
    REASON_HONEYPOT,
    REASON_NORMAL,
    REASON_ORCHESTRATOR_ERROR,
    STATUS_NEW,
    STATUS_PROCESSED,
    log_submission,
)
from .version import __version__

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cbm_intake")

SHARED_DIR = Path(__file__).resolve().parent.parent / "frontend" / "shared"
ASSIGNMENTS_FRONTEND_DIR = (
    Path(__file__).resolve().parent.parent / "assignments" / "frontend"
)
OPS_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "ops" / "frontend"
MENTORADMIN_FRONTEND_DIR = (
    Path(__file__).resolve().parent.parent / "mentoradmin" / "frontend"
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
            submission = spec.submission_model.model_validate(await request.json())
        except ValidationError as exc:
            # exc.errors() can carry a raw exception in ctx (non-serializable);
            # project to a JSON-safe shape.
            detail = [
                {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                for e in exc.errors()
            ]
            return JSONResponse(status_code=422, content={"detail": detail})

        client = _make_client(settings)
        is_honeypot = bool(submission.company_url.strip())

        # V2 Phase 0: durably capture the submission BEFORE any CRM work. This is
        # also the durable idempotency check (replacing the in-memory dict). A
        # repeat token short-circuits here without touching the CRM again.
        captured = None
        if store is not None:
            payload = json.loads(submission.model_dump_json())
            payload["company_url"] = ""  # never persist the honeypot value
            captured = await store.capture(
                spec.slug, submission.submission_token, payload,
                status=store_mod.STATUS_HELD if is_honeypot else store_mod.STATUS_PENDING,
            )
            if not captured.is_new:
                if captured.result is not None:
                    return {"status": "ok", "idempotent": True, **captured.result}
                return {"status": "received", "idempotent": True}

        # Honeypot: acknowledge generically, do not tell a bot it was caught.
        # The submission is held for admin review (written to the CRM as a
        # CIntakeSubmission record, reason=Honeypot, status=New) rather than
        # dropped, so a false positive (e.g. browser autofill, seen 2026-06-12)
        # is recoverable without contacting the submitter.
        if is_honeypot:
            logged = await log_submission(
                client, spec.slug, submission,
                reason=REASON_HONEYPOT, status=STATUS_NEW,
            )
            log.warning(
                "honeypot %s token=%s email=%s logged=%s",
                spec.slug,
                submission.submission_token,
                getattr(submission, "email", "?"),
                logged,
            )
            return {"status": "received"}

        # V2 Phase 1: with async delivery on, return as soon as the submission is
        # durably captured — the background worker delivers it into the CRM. The
        # CIntakeSubmission "Normal" log moves to the worker (on success).
        if captured is not None and settings.async_delivery:
            return {"status": "received", "reference": captured.id}

        # In-memory idempotency only when there is no durable store.
        key = f"{spec.slug}:{submission.submission_token}"
        if store is None and key in processed:
            return {"status": "ok", "idempotent": True, **processed[key]}

        try:
            ids = await spec.orchestrator(submission, client)
        except EspoError as exc:
            # Capture the raw submission for recovery (some records may have been
            # created before the failure). Best-effort, then surface the 502.
            await log_submission(
                client, spec.slug, submission,
                reason=REASON_ORCHESTRATOR_ERROR, status=STATUS_NEW,
            )
            if captured is not None:
                await store.mark_failed(
                    captured.id, status=store_mod.STATUS_NEEDS_ATTENTION, error=str(exc)
                )
            log.error("%s failed token=%s: %s", spec.slug, submission.submission_token, exc)
            raise HTTPException(
                status_code=502,
                detail=(
                    "Your request was received but could not be fully completed in "
                    "the system of record. It has been recorded for completion."
                ),
            )

        # Log the processed submission for audit/analytics, linked to its Contact.
        await log_submission(
            client, spec.slug, submission,
            reason=REASON_NORMAL, status=STATUS_PROCESSED,
            contact_id=ids.get("contactId"),
        )

        if captured is not None:
            await store.mark_completed(captured.id, ids)
        else:
            processed[key] = ids
        log.info("%s ok token=%s ids=%s", spec.slug, submission.submission_token, ids)
        return {"status": "ok", **ids}

    return handler


# Corner-badge styling per environment, matching frontend/shared/wizard.css
# (.cbm-env-badge--*). The index page is server-rendered without that stylesheet,
# so the colors are inlined here to keep the landing page self-contained.
_ENV_BADGE = {
    "production": ("PRODUCTION", "#e7f6ec", "#1b6b38", "#b6e0c4"),
    "test": ("TEST", "#fdf3d8", "#8a6100", "#f0dca0"),
    "dev": ("DEV · DRY-RUN", "#fde4e2", "#a3271c", "#f4bcb6"),
}


def _env_badge_html(environment: str) -> str:
    label, bg, fg, border = _ENV_BADGE.get(
        environment, (environment.upper(), "#eceff3", "#44505f", "#d3dae2")
    )
    return (
        f'<div role="status" title="Environment: {label}" style="position:fixed;'
        "top:0.6rem;right:0.6rem;z-index:1000;padding:0.25rem 0.6rem;"
        "border-radius:999px;font-size:0.72rem;font-weight:700;letter-spacing:0.04em;"
        "line-height:1;white-space:nowrap;font-family:Roboto,Arial,sans-serif;"
        f"background:{bg};color:{fg};border:1px solid {border};"
        f'box-shadow:0 1px 3px rgba(0,0,0,0.18)">{label}</div>'
    )


def _index_html(
    forms: list[FormSpec],
    include_assignments: bool = False,
    environment: str = "",
) -> str:
    items = []
    for f in forms:
        if f.frontend_dir is not None:
            items.append(
                f'<li><a href="/{f.slug}/" target="_blank" rel="noopener">{f.title}</a></li>'
            )
        else:
            items.append(f"<li>{f.title} <em>(API only — UI pending)</em></li>")
    # The mentor assignment dashboard is a staff-only tool, listed separately.
    staff = ""
    if include_assignments:
        staff = (
            "<h2>Staff</h2><ul>"
            '<li><a href="/assignments/" target="_blank" rel="noopener">Client Administration</a> '
            "<em>(staff sign-in required)</em></li>"
            '<li><a href="/ops/" target="_blank" rel="noopener">Submission Operations</a> '
            "<em>(staff sign-in required)</em></li>"
            '<li><a href="/mentoradmin/" target="_blank" rel="noopener">Mentor Administration</a> '
            "<em>(staff sign-in required)</em></li></ul>"
        )
    year = datetime.now(timezone.utc).year
    footer = (
        f"<footer><p>&copy; {year} Cleveland Business Mentors. "
        f"All rights reserved. &middot; v{__version__}</p></footer>"
    )
    badge = _env_badge_html(environment) if environment else ""
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>CBM Intake Forms</title></head><body>"
        + badge
        + "<h1>CBM Intake Forms</h1><ul>" + "".join(items) + "</ul>" + staff + footer
        + "</body></html>"
    )


def create_app(
    forms: list[FormSpec], *, store: Optional[SubmissionStore] = None
) -> FastAPI:
    settings = get_settings()
    # V2 Phase 0: a durable store when DATABASE_URL is set (else None = V1 behavior).
    # Tests inject a fake store directly.
    if store is None:
        store = store_mod.make_store(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if store is not None:
            await store.create_all()  # ensure the submission table exists
        yield

    app = FastAPI(title="CBM Intake Forms", version=__version__, lifespan=lifespan)
    # Exposed to the ops console router (V2 Phase 2).
    app.state.submission_store = store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # Mentor assignment tool: signed-cookie sessions hold each staff user's
    # EspoCRM auth token. Only mounted when a session secret is configured.
    if settings.assignments_active:
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
        and ``/healthz`` are left untouched.
        """
        response = await call_next(request)
        path = request.url.path
        if (
            request.method in ("GET", "HEAD")
            and not path.startswith("/api/")
            and path != "/healthz"
            and path != "/"  # the index sets its own stronger no-store (see index())
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
        if store is not None:
            try:
                await store.ping()
                database = "ok"
            except Exception as exc:  # noqa: BLE001 — report, don't raise
                database = "error"
                response.status_code = 503
                log.warning("healthz: database ping failed: %s", exc)
        return {
            "status": "ok" if database != "error" else "degraded",
            "version": __version__,
            "environment": settings.environment,
            "dryRun": settings.espo_dry_run,
            "forms": [f.slug for f in forms],
            "assignments": settings.assignments_active,
            "durableStore": store is not None,
            "database": database,
        }

    for spec in forms:
        app.add_api_route(
            f"/api/{spec.slug}/intake",
            _make_handler(spec, settings, processed, store),
            methods=["POST"],
            name=f"intake-{spec.slug}",
        )

    # Assignment tool + ops console API routes (registered before the static
    # mounts below so /assignments/api/* and /ops/api/* resolve to the routers).
    # Both reuse the EspoCRM team-auth session, so they need SESSION_SECRET.
    if settings.assignments_active:
        from assignments import api_router as assignments_router
        from mentoradmin import api_router as mentoradmin_router
        from ops import api_router as ops_router

        app.include_router(assignments_router)
        app.include_router(ops_router)
        app.include_router(mentoradmin_router)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        # no-store so a freshly-deployed index is never served stale from a
        # browser/edge cache (the landing page is tiny — nothing to gain caching).
        return HTMLResponse(
            _index_html(
                forms,
                include_assignments=settings.assignments_active,
                environment=settings.environment,
            ),
            headers={"Cache-Control": "no-store"},
        )

    # Static mounts last so the API routes above take precedence.
    for spec in forms:
        if spec.frontend_dir is not None:
            app.mount(
                f"/{spec.slug}",
                StaticFiles(directory=str(spec.frontend_dir), html=True),
                name=f"form-{spec.slug}",
            )
    if settings.assignments_active and ASSIGNMENTS_FRONTEND_DIR.is_dir():
        app.mount(
            "/assignments",
            StaticFiles(directory=str(ASSIGNMENTS_FRONTEND_DIR), html=True),
            name="assignments-frontend",
        )
    if settings.assignments_active and OPS_FRONTEND_DIR.is_dir():
        app.mount(
            "/ops",
            StaticFiles(directory=str(OPS_FRONTEND_DIR), html=True),
            name="ops-frontend",
        )
    if settings.assignments_active and MENTORADMIN_FRONTEND_DIR.is_dir():
        app.mount(
            "/mentoradmin",
            StaticFiles(directory=str(MENTORADMIN_FRONTEND_DIR), html=True),
            name="mentoradmin-frontend",
        )
    app.mount("/shared", StaticFiles(directory=str(SHARED_DIR)), name="shared")

    return app
