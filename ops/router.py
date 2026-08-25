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
from core.espo import EspoError, forbidden_hint, is_forbidden, is_not_found
from core.store import (
    ACT_DISCARDED,
    ACT_REDRIVEN,
    ACT_REOPENED,
    ACT_REPLY_SENT,
    ACT_RESOLVED,
    CLOSE_REASONS,
    base_state,
)

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


async def _activity(store, submission_id: str, **kw) -> None:
    """Best-effort activity-feed write (a store predating the feed just no-ops).
    Activity is context, never load-bearing — it must not fail the action."""
    try:
        await store.add_activity(submission_id, **kw)
    except AttributeError:
        pass
    except Exception as exc:  # noqa: BLE001 — feed write is best-effort
        log.warning("activity write failed on %s: %s", submission_id, exc)


def _actor(user: dict) -> str:
    return user.get("name") or user["userName"]


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
        "opsMailboxName": settings.sender_display_name,
        # The Close-with-reason disposition pick-list (Doug's approved values).
        "closeReasons": list(CLOSE_REASONS),
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
    # The derived conversational state from the row's OWN data (closed / in
    # progress / new). The grid overlays the live reply state (owed / waiting)
    # from /replystates on top of an in-progress base.
    for r in rows:
        r["baseState"] = base_state(r)
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
    user = _require_user(request)
    store = _store(request)
    row = await store.get_submission(submission_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Submission not found.")
    # The collaboration surface: the internal discussion, the activity feed, and
    # who else is looking at this right now (presence). Best-effort — a store
    # without these (older deploy / test fake) just omits them.
    try:
        row["comments"] = await store.list_comments(submission_id)
        row["activity"] = await store.list_activity(submission_id)
        await store.record_presence(
            submission_id, user_name=user["userName"],
            display_name=user.get("name") or user["userName"],
        )
        row["viewers"] = await store.recent_presence(
            submission_id, exclude=user["userName"]
        )
    except AttributeError:  # store predates collaboration
        row.setdefault("comments", [])
        row.setdefault("activity", [])
        row.setdefault("viewers", [])
    row["baseState"] = base_state(row)
    return row


@router.get("/submissions/{submission_id}/presence")
async def submission_presence(submission_id: str, request: Request) -> dict:
    """Poll target for the presence line: record the caller's view and return
    the other admins who looked recently. Cheap enough to poll every ~20s."""
    user = _require_user(request)
    store = _store(request)
    try:
        await store.record_presence(
            submission_id, user_name=user["userName"],
            display_name=user.get("name") or user["userName"],
        )
        viewers = await store.recent_presence(submission_id, exclude=user["userName"])
    except AttributeError:
        viewers = []
    return {"viewers": viewers}


class CommentIn(BaseModel):
    body: str


@router.post("/submissions/{submission_id}/comments")
async def add_comment(submission_id: str, body: CommentIn, request: Request) -> dict:
    """Append an attributed comment to the internal discussion (staff-only —
    never delivered to the CRM or the submitter). Bumps the collision signal
    and writes a ``comment_added`` activity entry."""
    user = _require_user(request)
    text = (body.body or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="A comment can't be empty.")
    store = _store(request)
    comment = await store.add_comment(
        submission_id, author=user["userName"],
        author_name=user.get("name") or user["userName"], body=text,
    )
    if comment is None:
        raise HTTPException(status_code=404, detail="Submission not found.")
    await store.add_activity(
        submission_id, kind="comment_added", actor=user["userName"],
        actor_name=user.get("name") or user["userName"],
        summary="added a comment",
    )
    log.info("comment on %s by %s", submission_id, user["userName"])
    return {"status": "ok", "comment": comment}


class CloseIn(BaseModel):
    reason: str
    note: str = ""


@router.post("/submissions/{submission_id}/close")
async def close_submission(submission_id: str, body: CloseIn, request: Request) -> dict:
    """The single terminal action: close the request with a disposition reason.
    Sets the done-state + the resolved flag + ``request_status="Closed"`` and —
    when the delivery created a CInformationRequest — writes that CRM record's
    Request Status too, so the queue and the CRM never drift."""
    user = _require_user(request)
    if body.reason not in CLOSE_REASONS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown close reason {body.reason!r} "
                f"(expected one of: {', '.join(CLOSE_REASONS)})."
            ),
        )
    store = _store(request)
    row = await store.get_submission(submission_id)
    if row is None or not await store.close_submission(
        submission_id, reason=body.reason, note=(body.note or "").strip(),
        closed_by=user["userName"], closed_by_name=user.get("name") or user["userName"],
    ):
        raise HTTPException(status_code=404, detail="Submission not found.")
    log.info("close %s (%s) by %s", submission_id, body.reason, user["userName"])
    out: dict = {"status": "ok", "closed": True}
    _updated, warning, note = await _writethrough_request_status(row, "Closed", user)
    if warning:
        out["crmWarning"] = warning
    if note:
        out["crmNote"] = note
    return out


@router.post("/submissions/{submission_id}/reopen")
async def reopen_submission(submission_id: str, request: Request) -> dict:
    """Undo Close — the request goes back into the open queue."""
    user = _require_user(request)
    store = _store(request)
    if not await store.reopen_submission(submission_id, acted_by=user["userName"]):
        raise HTTPException(
            status_code=404, detail="Submission not found, or it isn't closed."
        )
    log.info("reopen %s by %s", submission_id, user["userName"])
    return {"status": "ok", "closed": False}


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
    updated, warning, note = await _writethrough_request_status(row, body.status, user)
    if updated:
        out["crmUpdated"] = True
    if warning:
        out["crmWarning"] = warning
    if note:
        out["crmNote"] = note
    return out


async def _writethrough_request_status(
    row: dict, value: str, user: dict
) -> tuple[bool, Optional[str], Optional[str]]:
    """Best-effort mirror of the staff request status onto the delivery's
    CInformationRequest (when it created one).

    Returns ``(updated, warning, note)``; the app-side state is already saved
    either way, and at most one of the two messages is set:

    * ``warning`` — the CRM write FAILED and the two may now disagree. Worth
      alarming about, and worth trying again.
    * ``note`` — the CRM record is GONE (a 404), so there is nothing left to
      keep in step and no retry can change that. Stating it as a failure sent
      staff hunting for a drift that does not exist, so it is reported as the
      plain fact it is. Shared by the request-status endpoint and Close.
    """
    info_id = ((row.get("result") or {}).get("informationRequestId") or "").strip()
    if not info_id:
        return False, None, None
    client = _api_client()
    if client is None:
        return False, None, None
    try:
        await client.update("CInformationRequest", info_id, {"requestStatus": value})
        from core import action_log

        await action_log.record_action(
            client,
            app=action_log.APP_SUBMISSION_ADMIN,
            category=action_log.CAT_STATUS,
            action=action_log.ACT_STATUS_CHANGED,
            parent_type="CInformationRequest",
            parent_id=info_id,
            summary=f"Request status set to {value}",
            actor_name=user.get("name") or user["userName"],
        )
        return True, None, None
    except EspoError as exc:
        if is_not_found(exc):
            # The record this submission's delivery created has since been
            # deleted in the CRM — a test-record sweep, or on crm-test the
            # nightly restore, which puts the CRM back an hour before the app's
            # own tables are cleared. Nothing to update, and nothing to fix.
            log.info(
                "requestStatus write-through skipped: CInformationRequest/%s "
                "no longer exists in the CRM", info_id,
            )
            return False, None, (
                "The linked CRM information-request record no longer exists "
                "(it was deleted in the CRM), so there was nothing to update "
                "there."
            )
        log.warning(
            "requestStatus write-through failed on CInformationRequest/%s: %s",
            info_id, exc,
        )
        return False, (
            "Saved here, but the CRM information-request record couldn't be "
            f"updated — its Request Status may be out of date. ({exc})"
        ), None


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
    await _activity(
        store, submission_id,
        kind=ACT_RESOLVED if body.resolved else ACT_REOPENED,
        actor=user["userName"], actor_name=_actor(user),
        summary="marked this resolved" if body.resolved else "reopened this",
    )
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


def _clean_shared_messages(raw: list, mailbox: str) -> list[dict]:
    """Turn raw Gmail messages from the SHARED mailbox into the conversation
    view's message dicts (shared by the submission conversation + the Other
    correspondence reader). ``sent`` = written by the shared mailbox; a
    delivery bounce on a received message is flagged. Newest first, clamped."""
    from core.email_clean import clean_email
    from core.gmail import looks_like_bounce, parse_message

    out: list[dict] = []
    for r in raw:
        p = parse_message(r)
        if {"DRAFT", "SPAM", "TRASH"} & set(p.label_ids):
            continue
        sent = p.from_address == mailbox
        cleaned = clean_email(p.body_text, p.body_html or None, outbound=sent)
        bounce = (not sent) and looks_like_bounce(p.from_address, p.subject or "")
        out.append({
            "bounce": bounce,
            "id": p.gmail_id,
            "threadId": p.thread_id,
            # Reply threading: the frontend passes these back so the next send
            # stays on this Gmail thread + RFC References chain.
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
    out.sort(key=lambda m: m["date"] or "", reverse=True)
    return out[:_MESSAGES_LIMIT]


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

    if shared:
        messages = _clean_shared_messages(raw, gmail.mailbox)
    else:
        # Legacy per-admin mode: "sent" = not the submitter (no shared identity).
        from core.email_clean import clean_email

        messages = []
        for r in raw:
            p = parse_message(r)
            if {"DRAFT", "SPAM", "TRASH"} & set(p.label_ids):
                continue
            sent = p.from_address != address
            cleaned = clean_email(p.body_text, p.body_html or None, outbound=sent)
            bounce = (not sent) and looks_like_bounce(p.from_address, p.subject or "")
            messages.append({
                "bounce": bounce, "id": p.gmail_id, "threadId": p.thread_id,
                "rfcMessageId": p.rfc_message_id, "references": p.references,
                "direction": "sent" if sent else "received",
                "fromName": p.from_name or p.from_address,
                "fromAddress": p.from_address, "to": ", ".join(p.to_addresses),
                "subject": p.subject or "(no subject)", "date": p.sent_at,
                "snippet": cleaned.snippet or p.snippet, "bodyHtml": cleaned.html,
            })
        messages.sort(key=lambda m: m["date"] or "", reverse=True)
        messages = messages[:_MESSAGES_LIMIT]
    return {
        "messages": messages,
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


# --- Other correspondence (Phase 3, F15) -------------------------------------
# Inbound info@ threads that are NOT tied to a submission — replies to notices
# staff sent as info@ (the poller ignores info@-initiated threads by design, so
# they never enter the work queue). Read + reply live, so Marketing Admin never
# has to watch raw Gmail. Shared-mailbox mode only; nothing stored.

_CORR_LIST_QUERY = "in:inbox"
_CORR_LIST_LIMIT = 80        # newest inbound messages scanned per view
_CORR_THREAD_CAP = 40        # candidate threads fetched to classify


def _corr_ready(settings) -> str | None:
    """The shared mailbox is required — correspondence has no per-admin
    meaning. Returns a readable reason string when unavailable, else None."""
    if not settings.gmail_sync:
        return "Email isn't enabled on this deployment."
    if not settings.ops_mailbox:
        return (
            "Other correspondence needs the shared info@ mailbox "
            "(OPS_MAILBOX) — it isn't configured on this deployment."
        )
    return None


@router.get("/correspondence")
async def correspondence(request: Request) -> dict:
    """Non-submission inbound info@ threads — a reply to a notice staff sent as
    info@, or other mail we've corresponded on that never became a work item.
    Live Gmail read of the shared mailbox: the newest inbound messages, minus
    threads anchored to a submission, keeping those where info@ has both sent
    and received (so it's a conversation, not a brand-new request the poller
    will capture)."""
    _require_user(request)
    store = _store(request)
    settings = get_settings()
    reason = _corr_ready(settings)
    if reason:
        return {"threads": [], "reason": reason}

    from comms import service as comms_service
    from core.gmail import GmailError, looks_like_bounce, parse_message

    try:
        gmail = await comms_service.gmail_for_shared_mailbox(settings, settings.ops_mailbox)
    except comms_service.CommsError as exc:
        return {"threads": [], "reason": str(exc)}
    try:
        listing = await gmail.list_messages(_CORR_LIST_QUERY, max_results=_CORR_LIST_LIMIT)
        thread_ids: list[str] = []
        for m in listing.get("messages") or []:
            tid = m.get("threadId")
            if tid and tid not in thread_ids:
                thread_ids.append(tid)
        anchored = await store.known_gmail_threads(thread_ids)
        candidates = [t for t in thread_ids if t not in anchored]
        capped = len(candidates) > _CORR_THREAD_CAP
        candidates = candidates[:_CORR_THREAD_CAP]
        fetched = await asyncio.gather(
            *(gmail.get_thread(t) for t in candidates), return_exceptions=True
        )
        threads = []
        for tid, t in zip(candidates, fetched):
            if isinstance(t, Exception):
                log.warning("correspondence thread fetch failed (%s): %s", tid, t)
                continue
            parts = [parse_message(m) for m in (t.get("messages") or [])]
            parts = [p for p in parts if not ({"DRAFT", "SPAM", "TRASH"} & set(p.label_ids))]
            if not parts:
                continue
            we_sent = any(p.from_address == gmail.mailbox for p in parts)
            inbound = [p for p in parts if p.from_address != gmail.mailbox]
            # A conversation we took part in (info@ sent AND received), not a
            # brand-new inbound request (the poller captures those). Bounces
            # to our sends never count as the "other party".
            real_inbound = [
                p for p in inbound
                if not looks_like_bounce(p.from_address, p.subject or "")
            ]
            if not (we_sent and real_inbound):
                continue
            newest = max(parts, key=lambda p: p.sent_at or "")
            other = max(real_inbound, key=lambda p: p.sent_at or "")
            threads.append({
                "threadId": tid,
                "subject": newest.subject or "(no subject)",
                "withName": other.from_name or other.from_address,
                "withAddress": other.from_address,
                "lastAt": newest.sent_at,
                # The ball is in our court when the newest message isn't ours.
                "awaitingReply": newest.from_address != gmail.mailbox,
                "messageCount": len(parts),
                "snippet": newest.snippet,
            })
        threads.sort(key=lambda r: r["lastAt"] or "", reverse=True)
        result = {"threads": threads, "mailbox": gmail.mailbox}
        if capped:
            result["capped"] = True
            log.info("correspondence view capped at %s candidate threads", _CORR_THREAD_CAP)
        return result
    except GmailError as exc:
        log.warning("correspondence list failed: %s", exc)
        raise HTTPException(status_code=502, detail="Couldn't read the shared mailbox — try again.")
    finally:
        await gmail.aclose()


@router.get("/correspondence/{thread_id}")
async def correspondence_thread(thread_id: str, request: Request) -> dict:
    """One correspondence thread's messages (cleaned), newest first, with the
    reply-threading fields the compose passes back to stay on the thread."""
    _require_user(request)
    settings = get_settings()
    reason = _corr_ready(settings)
    if reason:
        raise HTTPException(status_code=503, detail=reason)

    from comms import service as comms_service
    from core.gmail import GmailError

    try:
        gmail = await comms_service.gmail_for_shared_mailbox(settings, settings.ops_mailbox)
    except comms_service.CommsError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    try:
        thread = await gmail.get_thread(thread_id)
    except GmailError as exc:
        log.warning("correspondence thread read failed (%s): %s", thread_id, exc)
        raise HTTPException(status_code=502, detail="Couldn't read that conversation — try again.")
    finally:
        await gmail.aclose()
    messages = _clean_shared_messages(thread.get("messages") or [], gmail.mailbox)
    return {"messages": messages, "mailbox": gmail.mailbox}


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
    await _activity(store, submission_id, kind=ACT_REDRIVEN, actor=user["userName"],
                    actor_name=_actor(user), summary="re-queued for delivery")
    # The CRM receipt: back to Received, stamped with WHO approved/re-drove it
    # (an action-time-only fact — the sweep can't derive it later). Best-effort.
    espo = _api_client()
    if espo is not None:
        from core import receipts
        from datetime import datetime, timezone

        await receipts.touch_safe(
            espo, store, submission_id,
            extra={
                "dispositionedBy": _actor(user),
                "dispositionedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            },
        )
    return {"status": "requeued"}


class DiscardIn(BaseModel):
    reason: str = ""
    note: str = ""


@router.post("/submissions/{submission_id}/discard")
async def discard(submission_id: str, body: DiscardIn, request: Request) -> dict:
    user = _require_user(request)
    store = _store(request)
    # A discard is a BUSINESS DECISION (intake-receipt redesign 2026-07-27):
    # it always carries a reason, recorded on the row AND the CRM receipt.
    reason = body.reason.strip()
    if not reason:
        raise HTTPException(
            status_code=422,
            detail="A reason is required to discard a submission.",
        )
    if body.note.strip():
        reason = f"{reason} — {body.note.strip()}"
    if not await store.discard(
        submission_id, acted_by=user["userName"], reason=reason
    ):
        # Either not found, or already completed (which must not be discarded).
        raise HTTPException(
            status_code=404, detail="Submission not found or already completed."
        )
    # Audit: discard is a terminal staff decision — "who discarded this, and
    # why?" must be answerable from the row, the feed, AND the CRM receipt.
    log.info("discard %s by %s (%s)", submission_id, user["userName"], reason)
    await _activity(store, submission_id, kind=ACT_DISCARDED, actor=user["userName"],
                    actor_name=_actor(user),
                    summary=f"discarded this submission — {reason}")
    espo = _api_client()
    if espo is not None:
        from core import receipts

        await receipts.touch_safe(
            espo, store, submission_id, extra={"dispositionedBy": _actor(user)}
        )
    return {"status": "discarded"}


@router.post("/receipts/sync")
async def sync_receipts(request: Request) -> dict:
    """Run the intake-receipt reconciliation NOW (the same sweep the worker
    runs hourly): every submission's CIntakeSubmission receipt is created or
    updated to match reality. Idempotent — safe to press twice."""
    user = _require_user(request)
    store = _store(request)
    espo = _api_client()
    if espo is None:
        raise HTTPException(
            status_code=503,
            detail="No CRM connection on this deployment (dry-run or no API key).",
        )
    from core import receipts

    settings = get_settings()
    stats = await receipts.run_receipt_sweep(espo, store, settings)
    log.info("manual receipt sweep by %s: %s", user["userName"], stats)
    return {"status": "ok", **stats}


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
    """After an /ops reply is sent: anchor its Gmail thread to the submission,
    and log a ``reply_sent`` activity stamped with the admin who sent it — the
    reply goes out as the shared identity, but the feed records the person
    (best-effort; the caller swallows failures)."""
    if not body.submissionId:
        return
    store = getattr(request.app.state, "submission_store", None)
    if store is None:
        return
    thread_id = (result or {}).get("gmailThreadId")
    if thread_id and await store.add_thread_id(body.submissionId, thread_id):
        log.info("anchored gmail thread %s to submission %s", thread_id, body.submissionId)
    user = current_user(request) or {}
    to = ", ".join(getattr(body, "to", None) or []) or "the submitter"
    await _activity(
        store, body.submissionId, kind=ACT_REPLY_SENT,
        actor=user.get("userName", "?"), actor_name=_actor(user) if user else "?",
        summary=f"sent a reply to {to}",
    )


register_quicksend(
    router, _require_user, client_for, _crm_failure,
    shared_mailbox=_ops_shared_mailbox, after_send=_ops_after_send,
)
