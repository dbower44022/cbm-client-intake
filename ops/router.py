"""FastAPI routes for the Submission Admin console (``/ops/api``).

Uses the shared staff session (sign in once at the portal ``/``), gated per
request to the OPS_ALLOWED_TEAMS team ("Marketing Admin Team" by default;
admins always pass). The durable store is read from
``request.app.state.submission_store`` (set by ``create_app``).

Rebuilt 2026-07-19 (Doug's spec): staff triage NOTES per submission (the
store's ``notes`` column, migration 0011) and a Communications view — the
conversation with the SUBMITTER read live from the signed-in admin's own
Gmail mailbox (a ``from:X OR to:X`` search; nothing is stored), with
sending via the shared quick-compose (``register_quicksend`` — the admin's
own ``@cbmentors.org`` mailbox, templates + signature included). Both email
features need the Gmail integration on AND the admin's login linked to a
profile with a ``cbmEmail``; without them the tab degrades to a readable
message and the compose falls back to ``mailto:``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from assignments import auth
from assignments.auth import clear_session, current_user, is_member
from assignments.espo_user import client_for
from core.config import get_settings
from core.espo import EspoError, forbidden_hint, is_forbidden

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


def _crm_failure(request: Request, exc: EspoError, message: str) -> HTTPException:
    """Per-user CRM errors → readable HTTP (the assignments pattern): expired
    token = 401 re-login; CRM 403 = name the missing grant; else 502."""
    if auth.session_expired(exc):
        clear_session(request)
        return HTTPException(
            status_code=401, detail="Your session has expired — please sign in again."
        )
    actor = (current_user(request) or {}).get("userName", "?")
    log.warning("%s (user=%s): %s", message, actor, exc)
    if is_forbidden(exc):
        hint = forbidden_hint(exc)
        return HTTPException(
            status_code=403,
            detail=(
                f"{message}: your CRM role is missing {hint} — ask CBM staff to grant it."
                if hint else
                f"{message}: your account doesn't have permission to do this in the CRM."
            ),
        )
    return HTTPException(status_code=502, detail=f"{message}: {exc}")


@router.post("/logout")
async def logout(request: Request) -> dict:
    clear_session(request)
    return {"status": "ok"}


@router.get("/session")
async def session(request: Request) -> dict:
    user = _require_user(request)
    settings = get_settings()
    return {
        "userName": user["userName"],
        "name": user["name"],
        "isAdmin": user["isAdmin"],
        # The deploy's CRM base URL, so the Details tab can link the records a
        # delivery created (result ids) straight into EspoCRM.
        "crmUrl": settings.espo_base_url,
        # True => the Communications tab talks to the real endpoints below;
        # false => it explains that email isn't enabled on this deployment.
        "commsEnabled": settings.gmail_sync,
        # EspoCRM email template pre-applied when starting a NEW conversation
        # on an info-request (Doug's canned reply; blank compose if missing).
        "replyTemplate": settings.ops_reply_template,
    }


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


class NotesIn(BaseModel):
    notes: str = ""


class ResolvedIn(BaseModel):
    resolved: bool = True


@router.put("/submissions/{submission_id}/resolved")
async def save_resolved(submission_id: str, body: ResolvedIn, request: Request) -> dict:
    """Mark a submission resolved / reopen it — the staff workflow marker
    ("is anyone still waiting on us?"), independent of the delivery status."""
    user = _require_user(request)
    store = _store(request)
    if not await store.set_resolved(
        submission_id, body.resolved, acted_by=user["userName"]
    ):
        raise HTTPException(status_code=404, detail="Submission not found.")
    log.info("%s %s by %s", "resolved" if body.resolved else "reopened",
             submission_id, user["userName"])
    return {"status": "ok", "resolved": body.resolved}


@router.put("/submissions/{submission_id}/notes")
async def save_notes(submission_id: str, body: NotesIn, request: Request) -> dict:
    """Staff triage notes (free text, staff-only — never delivered to the CRM)."""
    user = _require_user(request)
    store = _store(request)
    if not await store.set_notes(
        submission_id, body.notes, acted_by=user["userName"]
    ):
        raise HTTPException(status_code=404, detail="Submission not found.")
    log.info("notes saved on %s by %s", submission_id, user["userName"])
    return {"status": "ok"}


# How many matched messages the conversation view fetches in full. A triage
# conversation is short; a submitter address that matches hundreds of messages
# (a colleague!) is clamped rather than hammering Gmail.
_MESSAGES_LIMIT = 25


@router.get("/submissions/{submission_id}/messages")
async def submission_messages(submission_id: str, request: Request) -> dict:
    """The email conversation with the SUBMITTER — a live Gmail search of the
    signed-in admin's OWN mailbox (``from:X OR to:X``), newest first. Nothing
    is stored; each admin sees the thread from their own mailbox. Degrades to
    a readable reason (no Gmail integration / no linked CBM mailbox / no
    submitter email) instead of failing the page."""
    user = _require_user(request)
    store = _store(request)
    row = await store.get_submission(submission_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Submission not found.")
    address = ((row.get("payload") or {}).get("email") or "").strip().lower()
    if not address:
        return {"messages": [], "address": None,
                "reason": "This submission has no submitter email address."}
    settings = get_settings()
    if not settings.gmail_sync:
        return {"messages": [], "address": address,
                "reason": "Email isn't enabled on this deployment."}

    from comms import service as comms_service
    from core.gmail import GmailError, parse_message

    client = client_for(settings, user)
    try:
        gmail = await comms_service.gmail_for_user(settings, client, user)
    except comms_service.CommsError as exc:
        # No linked profile / no cbmEmail — a readable reason, not an error.
        return {"messages": [], "address": address, "reason": str(exc)}
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not look up your mailbox")

    try:
        listing = await gmail.list_messages(
            f"from:{address} OR to:{address}", max_results=_MESSAGES_LIMIT
        )
        ids = [m["id"] for m in listing.get("messages") or []]
        raw = await asyncio.gather(*(gmail.get_message(i) for i in ids[:_MESSAGES_LIMIT]))
    except GmailError as exc:
        log.warning("ops mailbox search failed for %s: %s", user.get("userName"), exc)
        raise HTTPException(
            status_code=502, detail="Couldn't read your mailbox — try again."
        )

    from core.email_clean import clean_email

    messages = []
    for r in raw:
        p = parse_message(r)
        if {"DRAFT", "SPAM", "TRASH"} & set(p.label_ids):
            continue
        cleaned = clean_email(p.body_text, p.body_html or None)
        messages.append({
            "id": p.gmail_id,
            "threadId": p.thread_id,
            # For reply threading: the frontend passes these back so the next
            # send stays on this Gmail thread + RFC References chain.
            "rfcMessageId": p.rfc_message_id,
            "references": p.references,
            "direction": "sent" if p.from_address != address else "received",
            "fromName": p.from_name or p.from_address,
            "fromAddress": p.from_address,
            "to": ", ".join(p.to_addresses),
            "subject": p.subject or "(no subject)",
            "date": p.sent_at,
            "snippet": cleaned.snippet or p.snippet,
            "bodyHtml": cleaned.html,
        })
    messages.sort(key=lambda m: m["date"] or "", reverse=True)
    return {"messages": messages, "address": address, "mailbox": gmail.mailbox}


class ReplyStatesIn(BaseModel):
    ids: list[str] = []


# Reply-state checks per grid load are capped: 2 Gmail calls per row, and the
# open-request work queue is small by nature.
_REPLY_STATE_LIMIT = 30


@router.post("/replystates")
async def reply_states(body: ReplyStatesIn, request: Request) -> dict:
    """Who spoke last, per submission — the grid's awaiting-reply column.

    For each id: one Gmail search (newest message with the submitter) + one
    headers-only fetch. States: ``owed`` (their message is newest — we owe a
    reply), ``waiting`` (ours is newest — waiting on them), ``none`` (no
    conversation). Best-effort per id; an empty map when email is off or the
    admin has no linked mailbox."""
    user = _require_user(request)
    store = _store(request)
    settings = get_settings()
    if not settings.gmail_sync:
        return {"states": {}}

    from email.utils import parseaddr

    from comms import service as comms_service
    from core.gmail import GmailError

    client = client_for(settings, user)
    try:
        gmail = await comms_service.gmail_for_user(settings, client, user)
    except comms_service.CommsError:
        return {"states": {}}
    except EspoError as exc:
        raise _crm_failure(request, exc, "Could not look up your mailbox")

    async def one(sid: str):
        try:
            row = await store.get_submission(sid)
            address = ((row or {}).get("payload") or {}).get("email")
            address = (address or "").strip().lower()
            if not address:
                return sid, {"state": "none"}
            listing = await gmail.list_messages(
                f"from:{address} OR to:{address}", max_results=1
            )
            msgs = listing.get("messages") or []
            if not msgs:
                return sid, {"state": "none"}
            meta = await gmail.get_message_headers(msgs[0]["id"])
            headers = {
                (h.get("name") or "").lower(): h.get("value") or ""
                for h in (meta.get("payload") or {}).get("headers") or []
            }
            sender = parseaddr(headers.get("from", ""))[1].lower()
            return sid, {
                "state": "owed" if sender == address else "waiting",
                "date": headers.get("date", ""),
            }
        except (GmailError, Exception):  # noqa: BLE001 — per-id best-effort
            return sid, {"state": "unknown"}

    ids = body.ids[:_REPLY_STATE_LIMIT]
    results = await asyncio.gather(*(one(s) for s in ids))
    return {"states": dict(results)}


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


# Quick-send email (compose to the submitter, templates + signature included):
# GET /mailbox + POST /sendmail + the template endpoints, behind this app's own
# gate. See comms/quicksend.py.
from comms.quicksend import register_quicksend  # noqa: E402  (needs router + helpers above)

register_quicksend(router, _require_user, client_for, _crm_failure)
