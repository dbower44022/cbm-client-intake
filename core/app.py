"""FastAPI app factory — registers forms and serves their frontends.

For each registered form the app exposes ``POST /api/{slug}/intake`` and, when
the form ships a frontend, serves it at ``/{slug}/``. Shared assets (the design
tokens) are served at ``/shared/``. The root lists the available forms.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.sessions import SessionMiddleware

from .config import Settings, get_settings
from .espo import DryRunEspoClient, EspoApi, EspoClient, EspoError
from .forms import FormSpec
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


def _make_client(settings: Settings) -> EspoApi:
    if settings.espo_dry_run:
        return DryRunEspoClient()
    return EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )


def _make_handler(spec: FormSpec, settings: Settings, processed: dict[str, dict]):
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

        # Honeypot: acknowledge generically, do not tell a bot it was caught.
        # The submission is held for admin review (written to the CRM as a
        # CIntakeSubmission record, reason=Honeypot, status=New) rather than
        # dropped, so a false positive (e.g. browser autofill, seen 2026-06-12)
        # is recoverable without contacting the submitter.
        if submission.company_url.strip():
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

        key = f"{spec.slug}:{submission.submission_token}"
        if key in processed:
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

        processed[key] = ids
        log.info("%s ok token=%s ids=%s", spec.slug, submission.submission_token, ids)
        return {"status": "ok", **ids}

    return handler


def _index_html(forms: list[FormSpec]) -> str:
    items = []
    for f in forms:
        if f.frontend_dir is not None:
            items.append(f'<li><a href="/{f.slug}/">{f.title}</a></li>')
        else:
            items.append(f"<li>{f.title} <em>(API only — UI pending)</em></li>")
    year = datetime.now(timezone.utc).year
    footer = (
        f"<footer><p>&copy; {year} Cleveland Business Mentors. "
        f"All rights reserved. &middot; v{__version__}</p></footer>"
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>CBM Intake Forms</title></head><body>"
        "<h1>CBM Intake Forms</h1><ul>" + "".join(items) + "</ul>" + footer
        + "</body></html>"
    )


def create_app(forms: list[FormSpec]) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="CBM Intake Forms", version=__version__)
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
        ):
            response.headers["Cache-Control"] = "no-cache"
        return response

    # Idempotency cache shared across forms (Technical Design §4 wants a durable store).
    processed: dict[str, dict] = {}

    @app.get("/healthz")
    async def healthz() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "dryRun": settings.espo_dry_run,
            "forms": [f.slug for f in forms],
            "assignments": settings.assignments_active,
        }

    for spec in forms:
        app.add_api_route(
            f"/api/{spec.slug}/intake",
            _make_handler(spec, settings, processed),
            methods=["POST"],
            name=f"intake-{spec.slug}",
        )

    # Assignment tool API routes (registered before the static mount below so
    # /assignments/api/* resolves to the router, not the static frontend).
    if settings.assignments_active:
        from assignments import router as assignments_router

        app.include_router(assignments_router)

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return _index_html(forms)

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
    app.mount("/shared", StaticFiles(directory=str(SHARED_DIR)), name="shared")

    return app
