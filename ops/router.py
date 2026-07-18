"""FastAPI routes for the Submission Admin console (``/ops/api``).

Uses the shared staff session (sign in once at the portal ``/``), gated per
request to the OPS_ALLOWED_TEAMS team ("Marketing Admin Team" by default;
admins always pass). The durable store is read from
``request.app.state.submission_store`` (set by ``create_app``).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from assignments.auth import clear_session, current_user, is_member
from core.config import get_settings

log = logging.getLogger("cbm_intake.ops")

router = APIRouter(prefix="/ops/api", tags=["ops"])


def _require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    settings = get_settings()
    if not is_member(user, settings.ops_allowed_teams_list):
        raise HTTPException(
            status_code=403,
            detail=(
                "Your account is not authorized to use Submission Admin "
                f"(requires the {', '.join(settings.ops_allowed_teams_list) or 'admin'} team)."
            ),
        )
    return user


def _store(request: Request):
    store = getattr(request.app.state, "submission_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Durable store is not configured.")
    return store


@router.post("/logout")
async def logout(request: Request) -> dict:
    clear_session(request)
    return {"status": "ok"}


@router.get("/session")
async def session(request: Request) -> dict:
    user = _require_user(request)
    return {"userName": user["userName"], "name": user["name"], "isAdmin": user["isAdmin"]}


@router.get("/submissions")
async def submissions(
    request: Request,
    status: Optional[str] = Query(default=None),
    form: Optional[str] = Query(default=None),
) -> dict:
    _require_user(request)
    store = _store(request)
    rows = await store.list_submissions(status=status, form=form)
    counts = await store.counts_by_status()
    return {"submissions": rows, "counts": counts}


@router.get("/metrics")
async def metrics(request: Request) -> dict:
    _require_user(request)
    store = _store(request)
    data = await store.metrics()
    # Gmail sync failure visibility (P1-5): mailboxes with messages currently
    # failing ingest (cursor held) or dead-lettered (skipped after repeated
    # failures). Best-effort — absent when comms isn't configured.
    try:
        from comms.store import make_comms_store

        comms = make_comms_store(get_settings())
        if comms is not None:
            try:
                gmail = {
                    s.mailbox: {"failing": s.failed_ids, "deadLetter": s.dead_letter}
                    for s in await comms.all_sync_states()
                    if s.failed_ids or s.dead_letter
                }
                if gmail:
                    data["gmailSync"] = gmail
            finally:
                await comms.dispose()
    except Exception as exc:  # noqa: BLE001 — metrics must never 500 over this
        log.warning("gmail sync metrics unavailable: %s", exc)
    return data


@router.get("/submissions/{submission_id}")
async def submission_detail(submission_id: str, request: Request) -> dict:
    _require_user(request)
    store = _store(request)
    row = await store.get_submission(submission_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Submission not found.")
    return row


@router.post("/submissions/{submission_id}/redrive")
async def redrive(submission_id: str, request: Request) -> dict:
    user = _require_user(request)
    store = _store(request)
    if not await store.redrive(submission_id, acted_by=user["userName"]):
        # Unknown id OR a status the guard refuses (completed = would deliver
        # twice; processing = would race the live worker; pending = already
        # queued). See store.redrive (P1-11).
        raise HTTPException(
            status_code=404,
            detail=(
                "Submission not found, or not in a re-drivable state "
                "(only needs-attention, retry, and held submissions can be re-driven)."
            ),
        )
    # Audit: a redrive re-runs CRM side effects — record who asked for it
    # (also stored durably on the row as acted_by).
    log.info("redrive %s by %s", submission_id, user["userName"])
    return {"status": "requeued"}


@router.post("/submissions/{submission_id}/discard")
async def discard(submission_id: str, request: Request) -> dict:
    user = _require_user(request)
    store = _store(request)
    if not await store.discard(submission_id, acted_by=user["userName"]):
        # Either not found, or already completed (which must not be discarded).
        raise HTTPException(
            status_code=404, detail="Submission not found or already completed."
        )
    # Audit: discard is a terminal staff decision — "who discarded this?"
    # must be answerable from the run logs.
    log.info("discard %s by %s", submission_id, user["userName"])
    return {"status": "discarded"}
