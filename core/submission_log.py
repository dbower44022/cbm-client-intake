"""Log every intake submission to the CRM as a ``CIntakeSubmission`` record.

A record is written for every submission, with a ``reason`` that says why:

  - ``Normal``           — processed into CRM records (status ``Processed``)
  - ``Honeypot``         — held: tripped the spam honeypot (status ``New``)
  - ``OrchestratorError``— the CRM orchestration failed partway (status ``New``)

This gives admins an audit trail of exactly what was submitted (the processed
Account/Contact/profile records are transformed — phone normalized, multi-selects
collapsed, fields dropped) and a basis for inbound-form analytics (volume by
``form`` and ``source`` over the native ``createdAt``, plus conversion via the
``contact`` link). The ``New``-status records (Honeypot / OrchestratorError) are
the review queue; ``Normal`` records are the log.

All writes are best-effort: a CRM-write failure never breaks the submission
(the user already has their response), and the full payload is logged at
WARNING so nothing is lost. Writes are create-only — the record is written
*after* the outcome is known, so no later update (and no edit grant) is needed.

CRM dependency (CRM team — see ``cintake-submission-entity.md``): the
``CIntakeSubmission`` entity with the ``form``/``reason``/``status``/
``submitterEmail``/``source``/``description`` fields, the ``contact`` link, and
the API user's *create* grant. Until they exist the create fails and this falls
back to logging.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from .espo import EspoApi
from .forms import BaseSubmission

log = logging.getLogger("cbm_intake.submission_log")

SUBMISSION_ENTITY = "CIntakeSubmission"
S_FORM = "form"                # enum: client-intake / volunteer / info-request
S_REASON = "reason"            # enum: Normal / Honeypot / OrchestratorError
S_SUBMITTER_EMAIL = "submitterEmail"  # varchar (EspoCRM type email)
S_STATUS = "status"            # enum: New / Approved / Rejected / Processed
S_SOURCE = "source"            # varchar: how the submitter heard about CBM
S_DESCRIPTION = "description"  # native text field: the raw submission JSON
S_CONTACT_ID = "contactId"     # belongsTo Contact (the record this produced)

REASON_NORMAL = "Normal"
REASON_HONEYPOT = "Honeypot"
REASON_ORCHESTRATOR_ERROR = "OrchestratorError"
STATUS_NEW = "New"
STATUS_PROCESSED = "Processed"

# The CIntakeSubmission.form enum value per form. The CRM is the source of truth:
# the original three use the lowercase slug, but partner/sponsor were added to the
# enum as Title-case, so the app logs exactly that (else the enum rejects it and
# the audit write falls back to a WARNING).
_FORM_VALUES = {"partner": "Partner", "sponsor": "Sponsor"}

# Strings longer than this (base64 résumé uploads, mainly) are redacted from
# the stored payload so the CRM text field stays manageable.
_MAX_FIELD_CHARS = 2000

_HEADERS = {
    REASON_HONEYPOT: (
        "Held by the intake app: this {slug} submission tripped the spam "
        "honeypot.\nIt passed all other validation. If it looks like a real "
        "person rather than\na bot, process it without contacting the submitter "
        "(see below)."
    ),
    REASON_ORCHESTRATOR_ERROR: (
        "The CRM orchestration for this {slug} submission FAILED partway — some "
        "records\nmay be missing or orphaned. The full submission is preserved "
        "below for recovery."
    ),
    REASON_NORMAL: (
        "Logged for audit/analytics: this {slug} submission was processed into "
        "CRM records.\nThis is the raw input exactly as submitted (the processed "
        "records are transformed)."
    ),
}


def _redact(value: Any) -> Any:
    """Recursively replace oversized strings with a short placeholder."""
    if isinstance(value, str) and len(value) > _MAX_FIELD_CHARS:
        return f"<{len(value)} chars omitted>"
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _description(slug: str, submission: BaseSubmission, reason: str) -> str:
    """Human-readable note + the raw submission JSON for the CRM record.

    The JSON has the honeypot field cleared, so for a held record (Honeypot /
    OrchestratorError) an admin can re-POST it verbatim to ``/api/{slug}/intake``
    to create the records — honeypot hits never populate the idempotency cache,
    so the original token still processes.
    """
    payload = _redact(json.loads(submission.model_dump_json()))
    held = payload.get("company_url", "")
    payload["company_url"] = ""
    pretty = json.dumps(payload, indent=2, sort_keys=True)

    parts = [_HEADERS[reason].format(slug=slug), ""]
    if reason == REASON_HONEYPOT:
        parts.append(f"Honeypot value that was caught: {held!r}")
    if reason in (REASON_HONEYPOT, REASON_ORCHESTRATOR_ERROR):
        parts.append(
            "To process it: POST the JSON below (honeypot field already cleared) "
            f"to /api/{slug}/intake with Content-Type: application/json."
        )
    parts += ["", "----- submission payload -----", pretty]
    return "\n".join(parts)


def build_submission_payload(
    slug: str,
    submission: BaseSubmission,
    *,
    reason: str,
    status: str,
    contact_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build the ``CIntakeSubmission`` record body (pure; no I/O)."""
    raw_email = getattr(submission, "email", None)
    email = str(raw_email) if raw_email else "(unknown)"
    payload: dict[str, Any] = {
        "name": f"{slug} — {email} — {datetime.now(timezone.utc):%Y-%m-%d}",
        S_FORM: _FORM_VALUES.get(slug, slug),
        S_REASON: reason,
        S_STATUS: status,
        S_DESCRIPTION: _description(slug, submission, reason),
    }
    # ``submitterEmail`` is an EspoCRM **email-type** field — a bare string is
    # silently dropped on create (real records came back with a null
    # submitterEmail), so set it via the ``<field>Data`` array the way EspoCRM's
    # own UI does. The plain string is kept alongside for readability/back-compat.
    # (Every form requires email, so the guard only covers the degenerate case.)
    if raw_email:
        payload[S_SUBMITTER_EMAIL] = email
        payload[f"{S_SUBMITTER_EMAIL}Data"] = [
            {"emailAddress": email, "primary": True, "optOut": False, "invalid": False}
        ]
    source = getattr(submission, "how_did_you_hear", None)
    if source:
        payload[S_SOURCE] = source
    if contact_id:
        payload[S_CONTACT_ID] = contact_id
    return payload


async def log_submission(
    client: EspoApi,
    slug: str,
    submission: BaseSubmission,
    *,
    reason: str,
    status: str,
    contact_id: Optional[str] = None,
) -> bool:
    """Write a CIntakeSubmission record for this submission. Returns True on success.

    Best-effort: never raises. On failure the full payload is logged at WARNING.
    """
    payload = build_submission_payload(
        slug, submission, reason=reason, status=status, contact_id=contact_id
    )
    try:
        created = await client.create(SUBMISSION_ENTITY, payload)
        log.info("logged %s submission (%s) to %s/%s", slug, reason, SUBMISSION_ENTITY, created["id"])
        return True
    except Exception as exc:  # noqa: BLE001 — best-effort; log everything
        log.warning("submission log to CRM failed for %s (%s); payload=%s", slug, exc, payload)
        return False
