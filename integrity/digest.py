"""The integrity digest — mentor login integrity plan § 4.2, step 4b.

Named the *integrity digest* everywhere (code, settings, log lines): the
worker already sends a different "daily email digest" (``comms/digest.py``).

After each daily run, with ``INTEGRITY_DIGEST`` on, one email lists every open
fault nobody has acknowledged, new ones marked, and repeats each day while any
is open. A fault is *new* until it has appeared in one digest
(``notified_at``). Acknowledged faults leave the email and stay in Mentor
Administration's fault list. Nothing open and unacknowledged: no email.

Recipients: ``INTEGRITY_DIGEST_TO``, else ``ALERT_EMAIL_TO``
(``Settings.integrity_recipients``). Sent through the alert mailer.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Optional

from core.branding import abbr
from core.config import Settings

from .check import CONDITIONS, DAILY

log = logging.getLogger("cbm_intake.integrity")

#: ``send(to, subject, text)``; tests inject one.
Send = Callable[[list[str], str, str], Awaitable[None]]


def mentor_url(settings: Settings, mentor_id: str) -> str:
    base = (settings.app_base_url or "").strip().rstrip("/")
    return f"{base}/mentoradmin/?mentor={mentor_id}" if base else ""


def faults_url(settings: Settings) -> str:
    base = (settings.app_base_url or "").strip().rstrip("/")
    return f"{base}/mentoradmin/?faults=1" if base else "the Login faults list in Mentor Administration"


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def digest_body(settings: Settings, rows: list[dict[str, Any]], *, acknowledged: int,
                fixed: int) -> tuple[str, str]:
    """(subject, text) for the open, unacknowledged ``rows``."""
    new = sum(1 for r in rows if not r.get("notified_at"))
    head = f"Login integrity: {_plural(len(rows), 'open fault', 'open faults')}"
    if new:
        head += f", {new} new"
    lines = [
        head + ".",
        "",
        "Each line is a mentor login that disagrees with its mentor profile. Fix it,",
        "or acknowledge it in Mentor Administration (\"known — being handled\") to take",
        "it off this email. A fault the daily check no longer finds closes itself.",
        "",
    ]
    for cond in (*DAILY, 7):
        group = [r for r in rows if r["condition"] == cond]
        if not group:
            continue
        lines.append(f"{CONDITIONS[cond]} ({len(group)})")
        for r in group:
            lines.append(f"  {'NEW · ' if not r.get('notified_at') else ''}{r['summary']}")
            for m in r.get("mentors") or []:
                link = mentor_url(settings, m["id"])
                if link:
                    lines.append(f"      {m['name']}: {link}")
        lines.append("")
    if acknowledged:
        lines.append(f"Acknowledged and not listed: {acknowledged}.")
    if fixed:
        lines.append(f"Fixed since the last check: {fixed}.")
    lines.append(f"Fault list: {faults_url(settings)}")
    lines.append(f"Environment: {settings.environment}.")
    subject = f"[{abbr()} — {settings.environment}] {head}"
    return subject, "\n".join(lines)


async def _default_send(settings: Settings) -> Send:
    from core.monitoring import _email_alert

    async def send(to: list[str], subject: str, text: str) -> None:
        await _email_alert(settings, text, to=to, subject=subject,
                           sender_name=f"{abbr()} Login Integrity")

    return send


async def send_integrity_digest(settings: Settings, store: Any, result: dict[str, Any], *,
                                send: Optional[Send] = None) -> bool:
    """Send today's digest. True when an email went out."""
    open_rows = result["open"]
    rows = [r for r in open_rows if not r.get("ack_at")]
    if not rows:
        log.info("integrity digest: nothing open and unacknowledged, no email")
        return False
    to = settings.integrity_recipients
    if not to:
        log.warning("integrity digest: %d open fault(s) but no recipients — set "
                    "INTEGRITY_DIGEST_TO or ALERT_EMAIL_TO", len(rows))
        return False
    fixed = sum(1 for r in result.get("closed", []) if r["condition"] in DAILY)
    subject, text = digest_body(settings, rows, acknowledged=len(open_rows) - len(rows),
                                fixed=fixed)
    send = send or await _default_send(settings)
    await send(to, subject, text)
    try:
        await store.mark_notified([r["id"] for r in rows if not r.get("notified_at")])
    except Exception as exc:  # noqa: BLE001 — the email did go; say so
        log.warning("integrity digest sent, but its faults could not be marked as "
                    "emailed (tomorrow's digest will call them new again): %s", exc)
    log.info("integrity digest sent to %s: %d open, %d new", ", ".join(to), len(rows),
             sum(1 for r in rows if not r.get("notified_at")))
    return True
