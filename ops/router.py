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
        # The shared send/read mailbox (info@ model, v0.110.0); null = the
        # legacy per-admin-mailbox mode.
        "opsMailbox": settings.ops_mailbox or None,
        "opsMailboxName": settings.ops_mailbox_name,
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


# The staff request-status vocabulary — deliberately the same values as the
# CRM's CInformationRequest.requestStatus enum so the write-through below keeps
# both in step ("Responded" doubles as the response marker, Doug's ruling
# 2026-07-22).
REQUEST_STATUSES = ("New", "In Progress", "Responded", "Closed")


class RequestStatusIn(BaseModel):
    status: str


def _api_client():
    """The shared API-key EspoCRM client for the requestStatus write-through
    (None in dry-run / keyless deploys). Its own function so tests can
    monkeypatch it; the per-user token is deliberately NOT used — ops admins
    have no CInformationRequest grant, and the API role does."""
    from core.espo import EspoClient

    settings = get_settings()
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    return EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )


@router.put("/submissions/{submission_id}/requeststatus")
async def save_request_status(
    submission_id: str, body: RequestStatusIn, request: Request
) -> dict:
    """Set the submission's request status (New / In Progress / Responded /
    Closed) — the staff work state of the request itself, distinct from the
    machine-managed delivery status. Best-effort write-through: when this
    submission's delivery created a CInformationRequest, the same value is
    written to that CRM record's ``requestStatus`` so the CRM worklist stays
    in step (a CRM failure never loses the app-side save)."""
    user = _require_user(request)
    if body.status not in REQUEST_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown request status {body.status!r} "
                f"(expected one of: {', '.join(REQUEST_STATUSES)})."
            ),
        )
    store = _store(request)
    row = await store.get_submission(submission_id)
    if row is None or not await store.set_request_status(
        submission_id, body.status, acted_by=user["userName"]
    ):
        raise HTTPException(status_code=404, detail="Submission not found.")
    log.info("request status %s on %s by %s", body.status, submission_id, user["userName"])
    out: dict = {"status": "ok", "requestStatus": body.status}
    info_id = ((row.get("result") or {}).get("informationRequestId") or "").strip()
    if info_id:
        client = _api_client()
        if client is not None:
            try:
                await client.update(
                    "CInformationRequest", info_id, {"requestStatus": body.status}
                )
                out["crmUpdated"] = True
                from core import action_log

                await action_log.record_action(
                    client,
                    app=action_log.APP_SUBMISSION_ADMIN,
                    category=action_log.CAT_STATUS,
                    action=action_log.ACT_STATUS_CHANGED,
                    parent_type="CInformationRequest",
                    parent_id=info_id,
                    summary=f"Request status set to {body.status}",
                    actor_name=user.get("name") or user["userName"],
                )
            except EspoError as exc:
                log.warning(
                    "requestStatus write-through failed on CInformationRequest/%s: %s",
                    info_id, exc,
                )
                out["crmWarning"] = (
                    "Saved here, but the CRM information-request record "
                    "couldn't be updated — its Request Status may be out of "
                    f"date. ({exc})"
                )
    return out


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


# How many messages the conversation view fetches in full. A triage
# conversation is short; a runaway match set is clamped rather than hammering
# Gmail.
_MESSAGES_LIMIT = 25


def submission_thread_ids(row: dict) -> list[str]:
    """The Gmail threads anchored to a submission: the inbound origin thread
    (email-originated submissions carry it in the payload) + every thread a
    staff reply started (recorded by the send hook in ``thread_ids``)."""
    threads = [t for t in (row.get("thread_ids") or []) if t]
    origin = ((row.get("payload") or {}).get("gmail_thread_id") or "").strip()
    if origin and origin not in threads:
        threads.insert(0, origin)
    return threads


def _lifetime_query(address: str, row: dict) -> str:
    """The legacy per-admin address search, time-boxed to the submission's
    lifetime (``after:`` received, ``before:`` resolved + 2 days grace) so a
    submitter's unrelated history/later mail stays out. Used only when no
    shared OPS_MAILBOX is configured."""
    q = f"from:{address} OR to:{address}"
    received = row.get("received_at")
    if received is not None:
        q = f"({q}) after:{int(received.timestamp())}"
    resolved = row.get("resolved_at")
    if resolved is not None:
        q = f"{q} before:{int(resolved.timestamp()) + 2 * 86400}"
    return q


@router.get("/submissions/{submission_id}/messages")
async def submission_messages(submission_id: str, request: Request) -> dict:
    """The email conversation belonging to this submission, newest first.

    With a shared **OPS_MAILBOX** configured (the info@ model, v0.110.0) this
    reads exactly the submission's ANCHORED Gmail threads from that one
    mailbox — the inbound thread that created an email submission, plus every
    thread staff started from here. Every admin sees the same conversation,
    and a submitter's unrelated mail can never appear (the old ``from:X OR
    to:X`` search polluted volunteer submissions especially).

    Without OPS_MAILBOX it falls back to the per-admin mailbox search, now
    time-boxed to the submission's lifetime. Nothing is stored either way;
    degrades to a readable reason instead of failing the page."""
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
    from core.gmail import GmailError, looks_like_bounce, parse_message

    shared = bool(settings.ops_mailbox)
    if shared:
        try:
            gmail = await comms_service.gmail_for_shared_mailbox(
                settings, settings.ops_mailbox
            )
        except comms_service.CommsError as exc:
            return {"messages": [], "address": address, "reason": str(exc)}
        thread_ids = submission_thread_ids(row)
        if not thread_ids:
            return {
                "messages": [], "address": address, "mailbox": gmail.mailbox,
                "reason": ("No conversation for this submission yet — use "
                           "“Email the submitter” to start one from "
                           f"{gmail.mailbox}."),
            }
        try:
            threads = await asyncio.gather(
                *(gmail.get_thread(t) for t in thread_ids), return_exceptions=True
            )
        except GmailError as exc:  # auth-level failure before any fetch
            log.warning("ops shared-mailbox read failed: %s", exc)
            raise HTTPException(
                status_code=502, detail="Couldn't read the shared mailbox — try again."
            )
        raw = []
        for t in threads:
            if isinstance(t, Exception):
                # A single deleted/inaccessible thread shouldn't kill the view.
                log.warning("ops thread fetch failed: %s", t)
                continue
            raw.extend(t.get("messages") or [])
    else:
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
                _lifetime_query(address, row), max_results=_MESSAGES_LIMIT
            )
            ids = [m["id"] for m in listing.get("messages") or []]
            raw = await asyncio.gather(
                *(gmail.get_message(i) for i in ids[:_MESSAGES_LIMIT])
            )
        except GmailError as exc:
            log.warning(
                "ops mailbox search failed for %s: %s", user.get("userName"), exc
            )
            raise HTTPException(
                status_code=502, detail="Couldn't read your mailbox — try again."
            )

    from core.email_clean import clean_email

    messages = []
    for r in raw:
        p = parse_message(r)
        if {"DRAFT", "SPAM", "TRASH"} & set(p.label_ids):
            continue
        # Shared mode: "sent" = written by the shared mailbox; legacy mode
        # keeps the old submitter comparison.
        sent = (p.from_address == gmail.mailbox) if shared else (p.from_address != address)
        cleaned = clean_email(p.body_text, p.body_html or None, outbound=sent)
        # Delivery failures thread with the original send — mark them so the
        # UI shows "delivery failed" instead of an ordinary received message.
        bounce = (not sent) and looks_like_bounce(p.from_address, p.subject or "")
        messages.append({
            "bounce": bounce,
            "id": p.gmail_id,
            "threadId": p.thread_id,
            # For reply threading: the frontend passes these back so the next
            # send stays on this Gmail thread + RFC References chain.
            "rfcMessageId": p.rfc_message_id,
            "references": p.references,
            "direction": "sent" if sent else "received",
            "fromName": p.from_name or p.from_address,
            "fromAddress": p.from_address,
            "to": ", ".join(p.to_addresses),
            "subject": p.subject or "(no subject)",
            "date": p.sent_at,
            "snippet": cleaned.snippet or p.snippet,
            "bodyHtml": cleaned.html,
        })
    messages.sort(key=lambda m: m["date"] or "", reverse=True)
    return {
        "messages": messages[:_MESSAGES_LIMIT],
        "address": address,
        "mailbox": gmail.mailbox,
    }


class ReplyStatesIn(BaseModel):
    ids: list[str] = []


# Reply-state checks per grid load are capped: 2 Gmail calls per row, and the
# open-request work queue is small by nature.
_REPLY_STATE_LIMIT = 30


@router.post("/replystates")
async def reply_states(body: ReplyStatesIn, request: Request) -> dict:
    """Who spoke last, per submission — the grid's awaiting-reply column.

    Shared-mailbox mode (OPS_MAILBOX set): reads only the submission's
    anchored threads (headers-only), so the state reflects THIS conversation
    — never the submitter's unrelated mail. ``owed`` = the newest message
    wasn't ours; ``waiting`` = ours is newest; ``none`` = no conversation.
    Legacy mode searches the admin's own mailbox, time-boxed to the
    submission's lifetime. Best-effort per id; an empty map when email is
    off or no mailbox resolves."""
    user = _require_user(request)
    store = _store(request)
    settings = get_settings()
    if not settings.gmail_sync:
        return {"states": {}}

    from email.utils import parseaddr

    from comms import service as comms_service
    from core.gmail import GmailError, looks_like_bounce

    shared = bool(settings.ops_mailbox)
    if shared:
        try:
            gmail = await comms_service.gmail_for_shared_mailbox(
                settings, settings.ops_mailbox
            )
        except comms_service.CommsError:
            return {"states": {}}
    else:
        client = client_for(settings, user)
        try:
            gmail = await comms_service.gmail_for_user(settings, client, user)
        except comms_service.CommsError:
            return {"states": {}}
        except EspoError as exc:
            raise _crm_failure(request, exc, "Could not look up your mailbox")

    def _headers(meta: dict) -> dict:
        return {
            (h.get("name") or "").lower(): h.get("value") or ""
            for h in (meta.get("payload") or {}).get("headers") or []
        }

    async def one(sid: str):
        try:
            row = await store.get_submission(sid)
            address = ((row or {}).get("payload") or {}).get("email")
            address = (address or "").strip().lower()
            if not address:
                return sid, {"state": "none"}
            if shared:
                thread_ids = submission_thread_ids(row)
                if not thread_ids:
                    return sid, {"state": "none"}
                newest = None  # (internalDate, headers)
                for tid in thread_ids:
                    thread = await gmail.get_thread(tid, headers_only=True)
                    for m in thread.get("messages") or []:
                        stamp = int(m.get("internalDate") or 0)
                        if newest is None or stamp > newest[0]:
                            newest = (stamp, _headers(m))
                if newest is None:
                    return sid, {"state": "none"}
                headers = newest[1]
                sender = parseaddr(headers.get("from", ""))[1].lower()
                # A bounce as the newest message = our reply did NOT arrive —
                # its own state, else it reads as "they replied" (owed).
                if looks_like_bounce(sender, headers.get("subject", "")):
                    return sid, {"state": "bounced", "date": headers.get("date", "")}
                return sid, {
                    "state": "waiting" if sender == gmail.mailbox else "owed",
                    "date": headers.get("date", ""),
                }
            listing = await gmail.list_messages(
                _lifetime_query(address, row), max_results=1
            )
            msgs = listing.get("messages") or []
            if not msgs:
                return sid, {"state": "none"}
            headers = _headers(await gmail.get_message_headers(msgs[0]["id"]))
            sender = parseaddr(headers.get("from", ""))[1].lower()
            if looks_like_bounce(sender, headers.get("subject", "")):
                return sid, {"state": "bounced", "date": headers.get("date", "")}
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


# Quick-send email (compose to the submitter, templates included), behind this
# app's own gate. See comms/quicksend.py. With OPS_MAILBOX configured the
# compose sends as the SHARED info@ mailbox under the generic display name
# (Doug's ruling 2026-07-19) and the sent message's Gmail thread is anchored
# to the submission, which is what the conversation view reads.
from comms.quicksend import (  # noqa: E402  (needs router + helpers above)
    register_quicksend,
    shared_staff_mailbox as _ops_shared_mailbox,
)


async def _ops_after_send(request: Request, body, result: dict) -> None:
    """Anchor the sent message's Gmail thread to the submission it was
    composed from (best-effort — the caller swallows failures)."""
    thread_id = (result or {}).get("gmailThreadId")
    if not body.submissionId or not thread_id:
        return
    store = getattr(request.app.state, "submission_store", None)
    if store is None:
        return
    if await store.add_thread_id(body.submissionId, thread_id):
        log.info("anchored gmail thread %s to submission %s", thread_id, body.submissionId)


register_quicksend(
    router, _require_user, client_for, _crm_failure,
    shared_mailbox=_ops_shared_mailbox, after_send=_ops_after_send,
)
