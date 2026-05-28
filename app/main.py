"""FastAPI application — the intake proxy (Technical Design §2, §3).

Exposes the single public write endpoint ``POST /api/intake``, a ``/healthz``
probe, and serves the static wizard frontend. It is the only component that
holds EspoCRM credentials.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .espo import DryRunEspoClient, EspoApi, EspoClient, EspoError
from .orchestrator import submit_intake
from .schemas import IntakeSubmission

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cbm_intake")

settings = get_settings()
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="CBM Client Intake", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# In-memory idempotency cache. Technical Design §4 calls for a durable store;
# this is sufficient for the scaffold and a single process.
_processed: dict[str, dict[str, str]] = {}


def _make_client() -> EspoApi:
    if settings.espo_dry_run:
        return DryRunEspoClient()
    return EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "dryRun": settings.espo_dry_run}


@app.post("/api/intake")
async def intake(submission: IntakeSubmission) -> dict:
    # Honeypot: a filled hidden field marks a bot. Return a generic acknowledgement
    # rather than an error so the bot is not told it was detected.
    if submission.company_url.strip():
        log.warning("honeypot triggered; dropping token=%s", submission.submission_token)
        return {"status": "received"}

    # Idempotency: a repeated token (double-submit, retry) returns the prior result.
    if submission.submission_token in _processed:
        return {"status": "ok", "idempotent": True, **_processed[submission.submission_token]}

    try:
        ids = await submit_intake(submission, _make_client())
    except EspoError as exc:
        log.error("intake failed token=%s: %s", submission.submission_token, exc)
        raise HTTPException(
            status_code=502,
            detail=(
                "Your request was received but could not be fully completed in the "
                "system of record. It has been recorded for completion."
            ),
        )

    _processed[submission.submission_token] = ids
    log.info("intake ok token=%s ids=%s", submission.submission_token, ids)
    return {"status": "ok", **ids}


# Serve the static wizard frontend at the root. Mounted last so the API routes
# above take precedence.
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
