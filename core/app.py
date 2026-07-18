"""FastAPI app factory — registers forms and serves their frontends.

For each registered form the app exposes ``POST /api/{slug}/intake`` and, when
the form ships a frontend, serves it at ``/{slug}/``. Shared assets (the design
tokens) are served at ``/shared/``. The root lists the available forms.
"""

from __future__ import annotations

import json
import logging
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.sessions import SessionMiddleware

from . import store as store_mod
from .config import Settings, get_settings
from .espo import DryRunEspoClient, EspoApi, EspoClient, EspoError
from .forms import FormSpec
from .logging_setup import setup_logging
from .resumable import ResumableClient
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
        if store is not None:
            payload = json.loads(submission.model_dump_json())
            payload["company_url"] = ""  # never persist the honeypot value
            try:
                captured = await store.capture(
                    spec.slug, submission.submission_token, payload,
                    status=store_mod.STATUS_HELD if is_honeypot else store_mod.STATUS_PENDING,
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
        # The submission is held for admin review (written to the CRM as a
        # CIntakeSubmission record, reason=Honeypot, status=New) rather than
        # dropped, so a false positive (e.g. browser autofill, seen 2026-06-12)
        # is recoverable without contacting the submitter.
        if is_honeypot:
            logged = await log_submission(
                client, spec.slug, submission,
                reason=REASON_HONEYPOT, status=STATUS_NEW,
                payload_stored_durably=captured is not None,
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
            # Capture the raw submission for recovery (some records may have been
            # created before the failure). Best-effort, then surface the 502.
            await log_submission(
                client, spec.slug, submission,
                reason=REASON_ORCHESTRATOR_ERROR, status=STATUS_NEW,
                payload_stored_durably=captured is not None,
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
            payload_stored_durably=captured is not None,
        )

        if captured is not None:
            await store.mark_completed(captured.id, ids)
        else:
            processed[key] = ids
        log.info("%s ok token=%s ids=%s", spec.slug, submission.submission_token, ids)
        return {"status": "ok", **ids}

    return handler


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
    name = _env_name(environment)
    version_label = f"v{__version__}" + (f" ({name})" if name else "")
    footer = (
        f"<footer><p>&copy; {year} Cleveland Business Mentors. "
        f"All rights reserved. &middot; {version_label}</p></footer>"
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>CBM Intake Forms</title>"
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
    setup_logging(settings.log_level)
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
    # Exposed to the portal router (the public-form links on the home page).
    app.state.form_specs = forms
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

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
            "dryRun": settings.espo_dry_run,
            "forms": [f.slug for f in forms],
            "assignments": settings.assignments_active,
            "durableStore": store is not None,
            "database": database,
            "worker": worker_info,
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
        from mentorprofile import api_router as mentorprofile_router
        from ops import api_router as ops_router
        from portal import api_router as portal_router
        from sessions import DOMAINS as SESSION_DOMAINS
        from sessions import make_router as make_sessions_router

        app.include_router(assignments_router)
        app.include_router(ops_router)
        app.include_router(mentoradmin_router)
        app.include_router(mentorprofile_router)
        app.include_router(portal_router)
        # Session Management: one router per domain, all from the same engine.
        for _cfg in SESSION_DOMAINS.values():
            app.include_router(make_sessions_router(_cfg))

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        # With the staff stack on, the root is the authenticated portal (sign in
        # once, see the links your teams allow). Without it (e.g. the dry-run
        # dev app, which has no session support), the public form index remains.
        # no-store so a freshly-deployed page is never served stale from a
        # browser/edge cache (either page is tiny — nothing to gain caching).
        if settings.assignments_active:
            html = (PORTAL_FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
        else:
            html = _index_html(forms, environment=settings.environment)
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
            }
        )
        from sessions import DOMAINS as _SESSION_DOMAINS

        alias_targets.update(
            {slug: f"/{slug}/" for slug in _SESSION_DOMAINS}
        )

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
    if settings.assignments_active and MENTORPROFILE_FRONTEND_DIR.is_dir():
        app.mount(
            "/mentorprofile",
            StaticFiles(directory=str(MENTORPROFILE_FRONTEND_DIR), html=True),
            name="mentorprofile-frontend",
        )
    if settings.assignments_active and PORTAL_FRONTEND_DIR.is_dir():
        # The portal's assets (its index.html is served at "/" above).
        app.mount(
            "/portal",
            StaticFiles(directory=str(PORTAL_FRONTEND_DIR), html=True),
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
            html = (SESSIONS_FRONTEND_DIR / "index.html").read_text(encoding="utf-8")
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
                StaticFiles(directory=str(SESSIONS_FRONTEND_DIR), html=True),
                name=f"sessions-frontend-{_slug}",
            )
    app.mount("/shared", StaticFiles(directory=str(SHARED_DIR)), name="shared")

    return app
