"""FastAPI app factory — registers forms and serves their frontends.

For each registered form the app exposes ``POST /api/{slug}/intake`` and, when
the form ships a frontend, serves it at ``/{slug}/``. Shared assets (the design
tokens) are served at ``/shared/``. The root lists the available forms.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .config import Settings, get_settings
from .espo import DryRunEspoClient, EspoApi, EspoClient, EspoError
from .forms import FormSpec

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cbm_intake")

SHARED_DIR = Path(__file__).resolve().parent.parent / "frontend" / "shared"


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
            return JSONResponse(status_code=422, content={"detail": exc.errors()})

        # Honeypot: acknowledge generically, do not tell a bot it was caught.
        if submission.company_url.strip():
            log.warning("honeypot %s token=%s", spec.slug, submission.submission_token)
            return {"status": "received"}

        key = f"{spec.slug}:{submission.submission_token}"
        if key in processed:
            return {"status": "ok", "idempotent": True, **processed[key]}

        try:
            ids = await spec.orchestrator(submission, _make_client(settings))
        except EspoError as exc:
            log.error("%s failed token=%s: %s", spec.slug, submission.submission_token, exc)
            raise HTTPException(
                status_code=502,
                detail=(
                    "Your request was received but could not be fully completed in "
                    "the system of record. It has been recorded for completion."
                ),
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
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>CBM Intake Forms</title></head><body>"
        "<h1>CBM Intake Forms</h1><ul>" + "".join(items) + "</ul></body></html>"
    )


def create_app(forms: list[FormSpec]) -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="CBM Intake Forms", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # Idempotency cache shared across forms (Technical Design §4 wants a durable store).
    processed: dict[str, dict] = {}

    @app.get("/healthz")
    async def healthz() -> dict:
        return {
            "status": "ok",
            "dryRun": settings.espo_dry_run,
            "forms": [f.slug for f in forms],
        }

    for spec in forms:
        app.add_api_route(
            f"/api/{spec.slug}/intake",
            _make_handler(spec, settings, processed),
            methods=["POST"],
            name=f"intake-{spec.slug}",
        )

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
    app.mount("/shared", StaticFiles(directory=str(SHARED_DIR)), name="shared")

    return app
