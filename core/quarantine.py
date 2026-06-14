"""Hold honeypot-tripped submissions for admin review instead of dropping them.

A honeypot hit returns a generic success and creates nothing (see
``core/app.py``). That is correct for bots, but a false positive (e.g. a
browser that autofills the hidden field) would silently lose a real
submission. To make those recoverable, a held submission is written to the
CRM as a ``CIntakeSubmission`` record so it is visible to every admin and the
CRM can alert on it (assignment / workflow-on-create) — no app-side mail
credentials, no separate review surface.

The submission reaches here only after passing full schema validation, so the
held payload is always well-formed — the review queue is small and meaningful,
not a flood of malformed spam.

CRM dependency (owned by the CRM team — see ``cintake-submission-entity.md``):
the ``CIntakeSubmission`` entity and the intake API user's *create* grant must
exist. Until they do, ``client.create`` fails and this falls back to logging
the full payload at WARNING — so deploying the app never blocks on the CRM
build, and nothing is silently lost in the meantime.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from .espo import EspoApi
from .forms import BaseSubmission

log = logging.getLogger("cbm_intake.quarantine")

# The CRM holding entity and its fields (reconciled to the spec the CRM team
# builds to — see cintake-submission-entity.md). Field names mirror the
# orchestrators' hardcoded-constant style.
QUARANTINE_ENTITY = "CIntakeSubmission"
Q_FORM = "cForm"                # enum: client-intake / volunteer / info-request
Q_REASON = "cReason"            # enum: Honeypot / OrchestratorError
Q_SUBMITTER_EMAIL = "cSubmitterEmail"  # varchar
Q_STATUS = "cStatus"           # enum: New / Approved / Rejected / Processed

REASON_HONEYPOT = "Honeypot"
STATUS_NEW = "New"

# Strings longer than this (base64 résumé uploads, mainly) are redacted from
# the stored payload so the CRM text field stays manageable.
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


def _description(slug: str, submission: BaseSubmission, email: str) -> str:
    """Human-readable note + reprocess-ready JSON for the CRM record.

    The JSON block has the honeypot field cleared so an admin who deems the
    submission valid can re-POST it verbatim to ``/api/{slug}/intake`` to
    create the records (honeypot hits never populate the idempotency cache,
    so the original token still processes).
    """
    payload = _redact(json.loads(submission.model_dump_json()))
    held_honeypot = payload.get("company_url", "")
    payload["company_url"] = ""  # clear so the block is ready to resubmit
    pretty = json.dumps(payload, indent=2, sort_keys=True)
    return (
        f"Held by the intake app: this {slug} submission tripped the spam "
        "honeypot.\nIt passed all other validation. If it looks like a real "
        "person rather than\na bot, you can process it without contacting the "
        "submitter.\n\n"
        f"Submitter email: {email}\n"
        f"Honeypot value that was caught: {held_honeypot!r}\n\n"
        "To process it: POST the JSON below (honeypot field already cleared) "
        f"to\n/api/{slug}/intake  with Content-Type: application/json.\n\n"
        "----- submission payload -----\n"
        f"{pretty}"
    )


def build_quarantine_payload(slug: str, submission: BaseSubmission) -> dict[str, Any]:
    """Build the ``CIntakeSubmission`` record body (pure; no I/O)."""
    email = getattr(submission, "email", None) or "(unknown)"
    return {
        "name": f"{slug} — {email} — {datetime.now(timezone.utc):%Y-%m-%d}",
        Q_FORM: slug,
        Q_REASON: REASON_HONEYPOT,
        Q_SUBMITTER_EMAIL: str(email),
        Q_STATUS: STATUS_NEW,
        "description": _description(slug, submission, str(email)),
    }


async def quarantine_submission(
    client: EspoApi, slug: str, submission: BaseSubmission
) -> bool:
    """Write a held submission to the CRM for review. Returns True on success.

    Best-effort: never raises. If the CRM create fails (e.g. the
    CIntakeSubmission entity or the API user's create grant is not in place
    yet) the full payload is logged at WARNING so the submission is still
    recoverable from the run logs.
    """
    payload = build_quarantine_payload(slug, submission)
    try:
        created = await client.create(QUARANTINE_ENTITY, payload)
        log.info("quarantined %s submission to %s/%s", slug, QUARANTINE_ENTITY, created["id"])
        return True
    except Exception as exc:  # noqa: BLE001 — best-effort; log everything
        log.warning(
            "quarantine to CRM failed for %s (%s); payload=%s",
            slug,
            exc,
            payload,
        )
        return False
