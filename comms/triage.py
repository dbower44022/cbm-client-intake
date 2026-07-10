"""Pre-storage triage: keep automated/marketing mail out of the CRM entirely.

Port of CRM_Extender's free (no-LLM) two-layer filter (``poc/triage.py``):
automated senders, auto-reply subjects, and unsubscribe-marked bodies are
rejected before anything is stored. Runs regardless of the optional AI-summary
flag — it protects the store, not just the summarizer (plan §5.6).
"""

from __future__ import annotations

import re

from core.gmail import ParsedGmailMessage

_AUTOMATED_SENDER = re.compile(
    r"^(?:no-?reply|do-?not-?reply|notifications?|billing|receipts?|"
    r"newsletter|marketing|updates?|alerts?|info|support|mailer-daemon|postmaster)"
    r"[@.+-]",
    re.IGNORECASE,
)

_AUTOMATED_SUBJECT = re.compile(
    r"(?:out\s+of\s+(?:the\s+)?office|auto-?\s?reply|automatic\s+reply|"
    r"undeliverable|delivery\s+(?:status|failure)|read\s+receipt|"
    r"vacation\s+respon)",
    re.IGNORECASE,
)

_MARKETING_BODY = re.compile(
    r"unsubscribe|manage\s+(?:your\s+)?(?:email\s+)?preferences|"
    r"view\s+(?:this\s+email\s+)?in\s+(?:your\s+)?browser",
    re.IGNORECASE,
)


def is_junk(msg: ParsedGmailMessage) -> bool:
    """True when the message should not be stored at all."""
    local = msg.from_address.split("@", 1)[0] + "@"
    if _AUTOMATED_SENDER.match(local):
        return True
    if _AUTOMATED_SUBJECT.search(msg.subject or ""):
        return True
    body = msg.body_text or msg.body_html or ""
    if _MARKETING_BODY.search(body[:5000]):
        return True
    return False
