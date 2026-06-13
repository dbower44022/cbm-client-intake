"""Hold honeypot-tripped submissions for admin review instead of dropping them.

A honeypot hit returns a generic success and creates nothing (see
``core/app.py``). That is correct for bots, but a false positive (e.g. a
browser that autofills the hidden field) would silently lose a real
submission. To make those recoverable, a held submission is emailed to an
admin address so a human can review it and, if valid, reprocess it.

The submission reaches here only after passing full schema validation, so the
held payload is always well-formed — the review queue is small and meaningful,
not a flood of malformed spam.

Transport is plain SMTP configured entirely via env vars. When SMTP is not
configured the feature is a no-op (the app still boots with zero env vars),
and the caller falls back to logging.
"""

from __future__ import annotations

import asyncio
import json
import logging
import smtplib
from email.message import EmailMessage
from typing import Any

from .config import Settings
from .forms import BaseSubmission

log = logging.getLogger("cbm_intake.quarantine")

# Strings longer than this (base64 résumé uploads, mainly) are redacted from
# the email so it stays small enough to send.
_MAX_FIELD_CHARS = 2000


def _redact(value: Any) -> Any:
    """Recursively replace oversized strings with a short placeholder."""
    if isinstance(value, str) and len(value) > _MAX_FIELD_CHARS:
        return f"<{len(value)} chars omitted>"
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def build_quarantine_message(
    slug: str, submission: BaseSubmission, *, mail_from: str, mail_to: str
) -> EmailMessage:
    """Build the review email for a held submission (pure; no I/O).

    The JSON block is reprocess-ready: the honeypot field is emptied so an
    admin can re-POST it verbatim to ``/api/{slug}/intake`` to create the
    records (honeypot hits never populate the idempotency cache, so the
    original token still processes).
    """
    payload = _redact(json.loads(submission.model_dump_json()))
    held_honeypot = payload.get("company_url", "")
    payload["company_url"] = ""  # clear so the block is ready to resubmit
    pretty = json.dumps(payload, indent=2, sort_keys=True)

    email = getattr(submission, "email", "(unknown)")
    msg = EmailMessage()
    msg["Subject"] = f"[CBM intake — review] held {slug} submission from {email}"
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg.set_content(
        "A submission to the CBM "
        f"{slug} form was held because it tripped the spam honeypot.\n"
        "It passed all other validation. If it looks like a real person rather\n"
        "than a bot, you can process it without contacting the submitter.\n\n"
        f"Submitter email: {email}\n"
        f"Honeypot value that was caught: {held_honeypot!r}\n\n"
        "To process it: POST the JSON below (the honeypot field is already\n"
        f"cleared) to  /api/{slug}/intake  with Content-Type: application/json.\n\n"
        "----- submission payload -----\n"
        f"{pretty}\n"
    )
    return msg


def _send_smtp(settings: Settings, msg: EmailMessage) -> None:
    """Blocking SMTP send (run off the event loop via ``asyncio.to_thread``)."""
    if settings.smtp_ssl:
        server: smtplib.SMTP = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port, timeout=15
        )
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
    with server:
        if settings.smtp_starttls and not settings.smtp_ssl:
            server.starttls()
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


async def quarantine_submission(
    settings: Settings, slug: str, submission: BaseSubmission
) -> bool:
    """Email a held submission for review. Returns True if an email was sent.

    Best-effort: never raises. When SMTP is unconfigured this is a no-op
    (returns False). On a send failure the full payload is logged at WARNING
    so the submission is still recoverable from the run logs.
    """
    if not settings.quarantine_enabled:
        return False
    msg = build_quarantine_message(
        slug,
        submission,
        mail_from=settings.quarantine_email_from,
        mail_to=settings.quarantine_email_to,
    )
    try:
        await asyncio.to_thread(_send_smtp, settings, msg)
        return True
    except Exception as exc:  # noqa: BLE001 — best-effort; log everything
        log.warning(
            "quarantine email failed for %s (%s); payload=%s",
            slug,
            exc,
            _redact(json.loads(submission.model_dump_json())),
        )
        return False
