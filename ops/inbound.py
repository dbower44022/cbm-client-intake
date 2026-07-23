"""Inbound info@ mailbox poller (v0.110.0).

Runs in the worker on its own timer (``OPS_INBOUND_SECONDS``, monitoring-check
pattern). Each cycle lists the shared OPS_MAILBOX's inbox (newest ~100
messages) and captures every NEW inbound thread as a **held** ``info-email``
submission in the durable store — the same /ops work queue as the website
forms. Triage-first (Doug's ruling 2026-07-19): no CRM records are created at
capture; staff Approve (redrive → the worker delivers through the info-email
orchestrator, creating Contact / CInformationRequest) or Discard (spam — no
CRM residue).

Dedup is layered and stateless (no cursor to corrupt):
  * the submission token IS the Gmail thread id (``gmail-thread-<id>``), so
    the store's unique (form, token) key makes capture idempotent;
  * ``store.known_gmail_threads`` skips threads already anchored to ANY
    submission — a submitter's REPLY to a conversation staff started from a
    form submission lands in the inbox on that anchored thread and must not
    become a second submission;
  * threads whose first message was written by the shared mailbox itself
    (staff mailing out directly from Gmail) are ignored, as are bounce
    notifications.

A thread that scrolls past the newest-100 window between polls would be
missed; at info@ volumes (worker default: every 5 minutes) that is
theoretical, and the window is a constant below if it ever needs raising.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any

from core.config import Settings
from core.email_clean import clean_email
from core.gmail import GmailClient, looks_like_bounce, parse_message
from core.store import STATUS_HELD_REVIEW, SubmissionStore

log = logging.getLogger("cbm_intake.ops.inbound")

FORM_SLUG = "info-email"
INBOX_QUERY = "in:inbox"
LIST_LIMIT = 100
_TOKEN_PREFIX = "gmail-thread-"
# Delivery-status/bounce senders: replies to our own sends that would only
# clutter the queue. Everything else — including noreply@ marketing — is
# captured and left to staff judgment (Discard costs two clicks).
_BOUNCE_LOCALS = ("mailer-daemon", "postmaster")

# The InfoRequest schema's message cap; the poller clamps rather than letting
# a huge body fail validation at delivery time.
_MESSAGE_MAX = 10_000


def thread_token(thread_id: str) -> str:
    return f"{_TOKEN_PREFIX}{thread_id}"


def _split_name(display: str, address: str) -> tuple[str, str]:
    """Best-effort first/last from the From display name; the address's local
    part when there is none. Staff correct oddities at approval time."""
    parts = " ".join((display or "").replace(",", " ").split()).split()
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    if len(parts) == 1:
        return parts[0], "(unknown)"
    local = address.split("@", 1)[0]
    return (local or "Unknown"), "(unknown)"


async def _capture_thread(
    gmail: GmailClient, store: SubmissionStore, thread_id: str
) -> bool:
    """Capture one thread's originating inbound message as a held submission.
    Returns True when a new row was created."""
    thread = await gmail.get_thread(thread_id)
    origin = None
    for m in thread.get("messages") or []:  # Gmail orders oldest-first
        p = parse_message(m)
        if {"DRAFT", "SPAM", "TRASH"} & set(p.label_ids):
            continue
        if p.from_address == gmail.mailbox:
            # The thread was STARTED by the shared mailbox (staff mailing out
            # directly from Gmail) — outbound-initiated, not an inbound
            # request. Left uncaptured by design.
            return False
        origin = p
        break
    if origin is None:
        return False
    local = origin.from_address.split("@", 1)[0]
    if local in _BOUNCE_LOCALS:
        return False

    first, last = _split_name(origin.from_name, origin.from_address)
    cleaned = clean_email(origin.body_text, origin.body_html or None)
    message = (cleaned.text or origin.snippet or "").strip() or "(no text content)"
    payload: dict[str, Any] = {
        # BaseSubmission's idempotency token doubles as the thread dedup key.
        "submission_token": thread_token(thread_id),
        "first_name": first[:100],
        "last_name": last[:100],
        "email": origin.from_address,
        "subject": (origin.subject or "").strip()[:500] or None,
        "message": message[:_MESSAGE_MAX],
        "gmail_thread_id": thread_id,
        "gmail_message_id": origin.gmail_id,
        "mailbox": gmail.mailbox,
        # When the email actually arrived (received_at is the capture time).
        "email_date": origin.sent_at,
    }
    # Deliberately NOT validated here: a malformed sender (weird spam) must
    # still be captured — never lose an email. If staff approve such a row,
    # the worker's validation routes it to needs_attention with the reason.
    captured = await store.capture(
        FORM_SLUG, thread_token(thread_id), payload, status=STATUS_HELD_REVIEW
    )
    if captured.is_new:
        # Mirror the origin thread into the anchor column so the conversation
        # view and known_gmail_threads see it uniformly.
        await store.add_thread_id(captured.id, thread_id)
        log.info(
            "captured inbound email thread %s as submission %s (from %s)",
            thread_id, captured.id, origin.from_address,
        )
    return captured.is_new


def _newest_message(thread: dict) -> dict | None:
    """The most recent message in a headers-only thread (Gmail internalDate)."""
    newest = None
    for m in thread.get("messages") or []:
        stamp = int(m.get("internalDate") or 0)
        if newest is None or stamp > newest[0]:
            newest = (stamp, m)
    return None if newest is None else {"stamp": newest[0], "msg": newest[1]}


async def _reopen_after_close(
    gmail: GmailClient, store: SubmissionStore, thread_ids: list[str]
) -> int:
    """Auto-reopen (Doug's ruling): a submitter replying on an anchored thread
    of a CLOSED submission brings it back into the open queue. Fires only for a
    message that arrived AFTER the close (else a request closed on an inbound
    message would reopen itself every poll). Best-effort, closed rows only —
    typically none, so this costs one headers-only thread read per closed
    submission touched this poll."""
    if not hasattr(store, "submissions_for_threads"):
        return 0
    rows = await store.submissions_for_threads(thread_ids)
    wanted = set(thread_ids)
    reopened = 0
    for r in rows:
        closed_at = r.get("closed_at")
        if not closed_at:
            continue
        anchored = [t for t in (r.get("thread_ids") or []) if t in wanted]
        newest = None
        for tid in anchored:
            try:
                thread = await gmail.get_thread(tid, headers_only=True)
            except Exception as exc:  # noqa: BLE001 — per-thread best-effort
                log.warning("auto-reopen thread read failed for %s: %s", tid, exc)
                continue
            cand = _newest_message(thread)
            if cand and (newest is None or cand["stamp"] > newest["stamp"]):
                newest = cand
        if newest is None:
            continue
        headers = {
            (h.get("name") or "").lower(): h.get("value") or ""
            for h in (newest["msg"].get("payload") or {}).get("headers") or []
        }
        sender = parseaddr(headers.get("from", ""))[1].lower()
        if not sender or sender == gmail.mailbox:
            continue  # our own message is newest — nothing to reopen for
        if looks_like_bounce(sender, headers.get("subject", "")):
            continue
        arrived = datetime.fromtimestamp(newest["stamp"] / 1000, tz=timezone.utc)
        if arrived <= closed_at:
            continue  # the newest message predates the close
        if await store.reopen_submission(r["id"], acted_by=None):
            reopened += 1
            log.info(
                "auto-reopened submission %s — submitter replied after close", r["id"]
            )
    return reopened


async def run_inbound_cycle(settings: Settings, store: SubmissionStore) -> dict[str, int]:
    """One poll of the shared mailbox. Returns cycle stats (for logs/tests).
    Never raises — the worker loop treats this like the other periodic checks."""
    stats = {"listed": 0, "threads": 0, "captured": 0, "skippedKnown": 0,
             "reopened": 0, "errors": 0}
    if not (settings.gmail_sync and settings.ops_mailbox):
        return stats

    from comms import service as comms_service

    try:
        gmail = await comms_service.gmail_for_shared_mailbox(
            settings, settings.ops_mailbox
        )
    except comms_service.CommsError as exc:
        log.warning("inbound poll skipped: %s", exc)
        return stats
    try:
        listing = await gmail.list_messages(INBOX_QUERY, max_results=LIST_LIMIT)
        msgs = listing.get("messages") or []
        stats["listed"] = len(msgs)
        thread_ids: list[str] = []
        for m in msgs:
            tid = m.get("threadId")
            if tid and tid not in thread_ids:
                thread_ids.append(tid)
        stats["threads"] = len(thread_ids)
        if not thread_ids:
            return stats
        have = await store.existing_tokens(
            FORM_SLUG, [thread_token(t) for t in thread_ids]
        )
        known = await store.known_gmail_threads(thread_ids)
        fresh = [
            t for t in thread_ids
            if thread_token(t) not in have and t not in known
        ]
        stats["skippedKnown"] = len(thread_ids) - len(fresh)
        # Auto-reopen closed submissions whose submitter replied on the thread
        # (best-effort; runs over the anchored/known threads in this poll).
        try:
            stats["reopened"] = await _reopen_after_close(gmail, store, thread_ids)
        except Exception as exc:  # noqa: BLE001 — never crash the poll
            log.warning("auto-reopen pass failed: %s", exc)
        for tid in fresh:
            try:
                if await _capture_thread(gmail, store, tid):
                    stats["captured"] += 1
            except Exception as exc:  # noqa: BLE001 — per-thread best-effort
                stats["errors"] += 1
                log.warning("inbound capture failed for thread %s: %s", tid, exc)
        if stats["captured"] or stats["errors"]:
            log.info(
                "inbound %s: %s new submission(s), %s error(s) "
                "(%s messages, %s threads, %s already tracked)",
                gmail.mailbox, stats["captured"], stats["errors"],
                stats["listed"], stats["threads"], stats["skippedKnown"],
            )
        return stats
    except Exception as exc:  # noqa: BLE001 — the poll must never crash the worker
        stats["errors"] += 1
        log.warning("inbound mailbox poll failed: %s", exc)
        return stats
    finally:
        await gmail.aclose()
