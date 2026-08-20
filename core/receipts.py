"""Intake receipts — the CRM as the single source of truth for every arrival.

Doug's redesign (2026-07-27; design record
``prds/intake-receipt-redesign-plan.md``): every arrival — all five web forms
AND every email captured from the shared info@ mailbox — gets ONE
``CIntakeSubmission`` receipt in the CRM, created at capture and UPDATED as it
moves through processing, with the human disposition (who / when / why)
recorded on it. The old ``reason``/``status`` pair is gone; the receipt speaks
one vocabulary:

    Received · Completed · Held-Spam · Held-Email · Error · Discarded

The engine is row-driven: ``expected_fields(row)`` derives the entire desired
receipt from an app-store submission row, and ``sync_row`` converges the CRM
to it — create if missing (first trying to ADOPT an existing receipt by
token, so replays and the historical migration never duplicate), update if
drifted. Every write path (arrival, worker outcome, /ops actions, the
reconciliation sweep, the migration script) goes through this one engine, so
the CRM can never disagree with the app for long: the hourly sweep
(``run_receipt_sweep``) heals anything an opportunistic write missed.

All calls are best-effort at the call sites (``touch_safe``) — a receipt
write failure never breaks a submission or a staff action; the sweep and its
drift alert are the guarantee.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from .config import Settings

log = logging.getLogger("cbm_intake.receipts")

RECEIPT_ENTITY = "CIntakeSubmission"

# The one status vocabulary (exact CRM enum values).
R_RECEIVED = "Received"
R_COMPLETED = "Completed"
R_HELD_SPAM = "Held-Spam"
R_HELD_EMAIL = "Held-Email"
R_HELD_DUPLICATE = "Held-Duplicate"
R_ERROR = "Error"
R_DISCARDED = "Discarded"

# Words added after the original six-word vocabulary shipped. Each is written
# only once the CRM's intakeStatus enum actually offers it (feature-detected in
# ``_gate_status``); until then the receipt falls back to the mapped value below
# and the explanation still rides in intakeMessage, so the app can deploy ahead
# of the CRM build. Handoff: cintake-submission-duplicate-status.md
_GATED_STATUSES = {R_HELD_DUPLICATE: R_RECEIVED}

# App-store machine status -> receipt status. pending/processing/retry are all
# "Received" — the visitor's submission is in hand and being worked; the
# machine's internal gears are not a business state.
_STATUS_MAP = {
    "pending": R_RECEIVED,
    "processing": R_RECEIVED,
    "retry": R_RECEIVED,
    "completed": R_COMPLETED,
    "needs_attention": R_ERROR,
    "held_honeypot": R_HELD_SPAM,
    "held_review": R_HELD_EMAIL,
    "held_duplicate": R_HELD_DUPLICATE,
    "discarded": R_DISCARDED,
}

# CIntakeSubmission.form enum values (the CRM is the source of truth: the
# original three forms use the lowercase slug; partner/sponsor were added
# Title-case; approved info@ emails log as "Email").
_FORM_VALUES = {
    "partner": "Partner",
    "sponsor": "Sponsor",
    "info-email": "Email",
    "event-registration": "Event Registration",
}

# Oversized payload strings (base64 resume uploads, mainly) are summarized so
# the CRM text field stays manageable; the full value is in the app store.
_MAX_FIELD_CHARS = 2000

_MIGRATED_REASON = "migrated — predates disposition reasons"


def receipt_status(store_status: str) -> str:
    return _STATUS_MAP.get(store_status, R_RECEIVED)


def _form_title(slug: str) -> str:
    """The human form name ("Volunteer" etc.) — lazy import to keep core/
    free of a hard dependency on the forms package."""
    try:
        from forms import SPECS_BY_SLUG

        spec = SPECS_BY_SLUG.get(slug)
        if spec is None:
            return slug
        from core.branding import MODE_TEXT, render as render_branding
        from core.config import get_settings

        return render_branding(spec.title, get_settings(), MODE_TEXT)
    except Exception:  # noqa: BLE001 — a display name must never break a write
        return slug


def _redact(value: Any) -> Any:
    if isinstance(value, str) and len(value) > _MAX_FIELD_CHARS:
        return f"<{len(value)} chars omitted>"
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _fmt_dt(value: Any) -> Optional[str]:
    """EspoCRM datetime format (UTC ``YYYY-MM-DD HH:MM:SS``)."""
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _is_email(row: dict[str, Any]) -> bool:
    return (row.get("form_slug") or "") == "info-email"


def payload_text(row: dict[str, Any]) -> str:
    """The receipt's ``payload`` field: the raw form input as submitted, or —
    for an email — the email content itself (a Gmail link is only usable with
    mailbox access and the mailbox copy can be deleted; the CRM carries the
    content). Always contains the submission token, which is the engine's
    adopt-by-token dedup key."""
    payload = row.get("payload") or {}
    if _is_email(row):
        date = payload.get("email_date")
        lines = [
            f"From: {payload.get('first_name', '')} {payload.get('last_name', '')} "
            f"<{payload.get('email', '')}>".replace("  ", " "),
            f"To: {payload.get('mailbox') or '(shared mailbox)'}",
            f"Subject: {payload.get('subject') or '(no subject)'}",
        ]
        if date:
            lines.append(f"Date: {date}")
        lines += ["", (payload.get("message") or "(no text content)"), "",
                  f"Gmail thread: {payload.get('gmail_thread_id') or '?'}",
                  f"Reference token: {row.get('submission_token') or ''}"]
        return "\n".join(lines)
    cleaned = dict(_redact(payload))
    cleaned.pop("company_url", None)  # never persist the honeypot value
    return json.dumps(cleaned, indent=2, sort_keys=True)


def email_link(row: dict[str, Any]) -> Optional[str]:
    """A deep link to the original message in the shared mailbox (email
    receipts only). Convenience — the content itself is in ``payload``."""
    if not _is_email(row):
        return None
    thread = (row.get("payload") or {}).get("gmail_thread_id")
    return f"https://mail.google.com/mail/u/0/#all/{thread}" if thread else None


def spam_message(row: dict[str, Any]) -> str:
    return f"The {_form_title(row.get('form_slug') or '')} spam trap was triggered"


def error_message(row: dict[str, Any]) -> str:
    """The long, specific Error explanation (Doug's requirement: exactly what
    happened and possible fixes)."""
    slug = row.get("form_slug") or ""
    attempts = row.get("attempt_count") or 0
    received = _fmt_dt(row.get("received_at")) or "?"
    err = (row.get("last_error") or "(no error text was recorded)").strip()

    created = sorted((row.get("progress") or {}).keys())
    lines = [
        f"This {_form_title(slug)} submission could NOT be processed into CRM "
        f"records.",
        f"Received {received} UTC; {attempts} delivery attempt(s) were made "
        f"before giving up.",
        "",
        "What went wrong (the CRM's own response / the failure detail):",
        err,
        "",
    ]
    if created:
        lines += [
            "Records created BEFORE the failure (a Re-drive resumes after "
            "these — it never duplicates them):",
            *[f"  - {step}" for step in created],
            "",
        ]
    else:
        lines += ["No CRM records were created before the failure.", ""]

    low = err.lower()
    fixes = []
    if "phonenumber" in low or "phone" in low and "valid" in low:
        fixes.append(
            "The phone number was rejected by the CRM. If the rest looks like "
            "a real inquiry, Re-drive it — invalid phone numbers are dropped "
            "on retry and the lead is kept (the raw value stays in this "
            "payload)."
        )
    if "validationfailure" in low or "not valid" in low or ": valid" in low:
        fixes.append(
            "The CRM rejected a field value (often a dropdown option that no "
            "longer exists). Check the payload below against the CRM's "
            "current options, fix the CRM field options if they drifted, then "
            "Re-drive."
        )
    if "http 5" in low or "transport" in low or "unreachable" in low or "timeout" in low:
        fixes.append(
            "The CRM was unreachable or erroring. Once it is healthy again, "
            "Re-drive — delivery resumes where it stopped."
        )
    if not fixes:
        fixes.append(
            "Review the error above, correct the underlying data or CRM "
            "configuration, then use Re-drive in Submission Admin — delivery "
            "resumes where it stopped and never duplicates records."
        )
    lines += ["Possible fixes:"] + [f"  - {f}" for f in fixes]
    lines += [
        "",
        "If this should not be processed at all, Discard it in Submission "
        "Admin with a reason — the decision is recorded on this receipt.",
    ]
    return "\n".join(lines)


def duplicate_message(row: dict[str, Any]) -> str:
    """Why this arrival was held, and what the reviewer is deciding."""
    original = row.get("duplicate_of")
    lines = [
        "Possible duplicate — held for review, not yet delivered to the CRM.",
        "",
        "The same person already submitted this form a short time earlier, and "
        "that submission was processed normally. Delivering this one as well "
        "would create a second client profile and a second engagement for the "
        "same person.",
    ]
    if original:
        lines.append(f"Earlier submission reference: {original}")
    lines += [
        "",
        "Clients most often re-submit to change or add something — in both "
        "cases seen so far it was to name the mentor they wanted. Compare this "
        "submission's answers with the earlier one before deciding.",
        "",
        "In Submission Admin:",
        "  - Approve — if this really is a separate, genuine request. It is "
        "delivered normally and creates its own records.",
        "  - Discard (with a reason) — if it restates the earlier submission. "
        "Copy anything new from it onto the existing engagement first.",
    ]
    return "\n".join(lines)


def intake_message(row: dict[str, Any]) -> str:
    status = receipt_status(row.get("status") or "")
    if status == R_HELD_SPAM:
        return spam_message(row)
    if status == R_HELD_EMAIL:
        return "All emails need review"
    if status == R_HELD_DUPLICATE:
        return duplicate_message(row)
    if status == R_ERROR:
        return error_message(row)
    # Received / Completed / Discarded carry no processing message (the
    # disposition fields tell the Discarded story).
    return ""


def receipt_name(row: dict[str, Any]) -> str:
    email = (row.get("payload") or {}).get("email") or "(unknown)"
    received = row.get("received_at")
    day = received.strftime("%Y-%m-%d") if isinstance(received, datetime) else ""
    return f"{row.get('form_slug')} — {email} — {day}".strip(" —")


def expected_fields(row: dict[str, Any]) -> dict[str, Any]:
    """The full desired receipt for this app-store row (pure — the single
    source both the live writes and the sweep converge on)."""
    payload = row.get("payload") or {}
    status = receipt_status(row.get("status") or "")
    fields: dict[str, Any] = {
        "name": receipt_name(row),
        "form": _FORM_VALUES.get(row.get("form_slug"), row.get("form_slug")),
        "submitterEmail": str(payload.get("email") or "(unknown)"),
        "intakeStatus": status,
        "intakeMessage": intake_message(row),
        "payload": payload_text(row),
    }
    source = payload.get("how_did_you_hear")
    if source:
        fields["source"] = source
    link = email_link(row)
    if link:
        fields["emailLink"] = link
    contact_id = (row.get("result") or {}).get("contactId")
    if status == R_COMPLETED and contact_id:
        fields["contactId"] = contact_id
    if status == R_DISCARDED:
        # The business decision, from the row's close stamps (store.discard
        # writes them; pre-redesign discards have only acted_by).
        by = row.get("closed_by") or row.get("acted_by")
        if by:
            fields["dispositionedBy"] = by
        at = _fmt_dt(row.get("closed_at"))
        if at:
            fields["dispositionedAt"] = at
        reason = row.get("close_reason")
        note = row.get("close_note")
        fields["dispositionReason"] = (
            f"{reason} — {note}" if reason and note else (reason or _MIGRATED_REASON)
        )
    return fields


# Keys the engine OWNS on an existing receipt: compared on sync, written when
# drifted. name/form/submitterEmail/source are set at create and then left
# alone (an admin may retitle; re-stamping them hourly is churn, not truth).
_SYNC_KEYS = (
    "intakeStatus", "intakeMessage", "payload", "emailLink", "contactId",
    "dispositionedBy", "dispositionedAt", "dispositionReason",
)


async def _prune_dangling_contact(client, fields: dict[str, Any]) -> dict[str, Any]:
    """Drop a ``contactId`` that points at a Contact the CRM no longer has
    (ZZTEST cleanups, hand-deleted records): EspoCRM rejects the WHOLE write
    over a dangling link ("Can't relate with non-existing record"), which
    would leave the receipt permanently failing every sweep. Checking costs
    one GET, and only for writes that carry a contact."""
    contact_id = fields.get("contactId")
    if not contact_id or not hasattr(client, "get"):
        return fields
    try:
        await client.get("Contact", contact_id, select="id")
        return fields
    except Exception:  # noqa: BLE001 — missing OR unreadable: write without the link
        log.info("receipt contact link dropped (Contact %s no longer exists)", contact_id)
        return {k: v for k, v in fields.items() if k != "contactId"}


_status_options_cache: dict[str, Any] = {"options": None}


async def _gate_status(client, fields: dict[str, Any]) -> dict[str, Any]:
    """Downgrade an intakeStatus the CRM's enum doesn't offer yet.

    ``Held-Duplicate`` was added after the six-word vocabulary shipped, so a CRM
    that hasn't had the option built would reject the WHOLE write (EspoCRM 400s
    an out-of-enum value) and the receipt would fail every sweep forever. Until
    the option exists the receipt reads ``Received`` — truthful, since the
    submission IS in hand and undelivered — and ``intakeMessage`` still carries
    the full explanation. Once built, it activates with no deploy.

    Fails OPEN: if the options can't be read, the value is left alone.
    """
    status = fields.get("intakeStatus")
    fallback = _GATED_STATUSES.get(status)
    if fallback is None:
        return fields
    options = _status_options_cache["options"]
    if options is None:
        if not hasattr(client, "metadata_enum_options"):
            return fields
        try:
            options = await client.metadata_enum_options(RECEIPT_ENTITY, "intakeStatus")
        except Exception:  # noqa: BLE001 — unreadable metadata: write as-is
            return fields
        _status_options_cache["options"] = options or []
        options = _status_options_cache["options"]
    if not options or status in options:
        return fields
    log.info(
        "receipt intakeStatus %r not yet a CRM option — writing %r "
        "(build the option to activate it)", status, fallback,
    )
    return {**fields, "intakeStatus": fallback}


_form_options_cache: dict[str, Any] = {"options": None}


async def _gate_form(client, fields: dict[str, Any]) -> dict[str, Any]:
    """Drop a ``form`` value the CRM's enum doesn't offer, instead of losing the
    whole receipt.

    Learned the hard way (2026-08-10): Events registration shipped with the slug
    ``event-registration``, which was not an option on ``CIntakeSubmission.form``.
    EspoCRM 400s an out-of-enum value, so **every** event registration delivered
    into the CRM correctly and then silently got no receipt at all — the
    "a receipt for every arrival" guarantee quietly false for a whole form kind,
    visible only as a WARNING in the worker log.

    A missing classification is a far smaller loss than a missing receipt, so an
    unrecognised form is omitted and everything else is still written. The next
    new form kind therefore gets a receipt before anyone touches the CRM, and
    gains its label the moment the option is built — no deploy.

    Fails OPEN: unreadable metadata leaves the value alone.
    """
    form = fields.get("form")
    if not form:
        return fields
    options = _form_options_cache["options"]
    if options is None:
        if not hasattr(client, "metadata_enum_options"):
            return fields
        try:
            options = await client.metadata_enum_options(RECEIPT_ENTITY, "form")
        except Exception:  # noqa: BLE001 — unreadable metadata: write as-is
            return fields
        _form_options_cache["options"] = options or []
        options = _form_options_cache["options"]
    if not options or form in options:
        return fields
    log.warning(
        "receipt form %r is not a CRM option — writing the receipt without it "
        "(add the option to classify these). Receipt is NOT lost.", form,
    )
    return {k: v for k, v in fields.items() if k != "form"}


async def _find_by_token(client, token: str) -> Optional[str]:
    """Adopt an existing receipt whose stored payload carries this token —
    the dedup guard that makes create idempotent across replays, the
    historical migration, and receipts written before a store row existed."""
    if not token or not hasattr(client, "list"):
        return None
    for attr in ("payload", "description"):
        try:
            env = await client.list(
                RECEIPT_ENTITY,
                where=[{"type": "contains", "attribute": attr, "value": token}],
                select="id",
                max_size=1,
            )
        except Exception:  # noqa: BLE001 — adoption is best-effort; create wins
            return None
        hits = env.get("list") or []
        if hits:
            return hits[0].get("id")
    return None


async def sync_row(
    client,
    store,
    row: dict[str, Any],
    *,
    extra: Optional[dict[str, Any]] = None,
) -> str:
    """Converge this row's CRM receipt to the expected state.

    Returns ``"created"`` / ``"updated"`` / ``"ok"`` (no drift) /
    ``"failed"``. ``extra`` carries action-time-only stamps (the Approve /
    Re-drive dispositionedBy/At, which cannot be derived from the row later)
    and is applied to whichever write happens now.
    """
    expected = expected_fields(row)
    receipt_id = row.get("crm_receipt_id")

    try:
        if receipt_id:
            current = None
            if hasattr(client, "get"):
                try:
                    current = await client.get(
                        RECEIPT_ENTITY, receipt_id,
                        select=",".join(_SYNC_KEYS),
                    )
                except Exception:  # noqa: BLE001 — deleted/unreadable: recreate below
                    current = None
            if current is not None:
                changes = {
                    k: v for k, v in expected.items()
                    if k in _SYNC_KEYS and v is not None and current.get(k) != v
                }
                if extra:
                    changes.update(extra)
                if not changes:
                    return "ok"
                changes = await _prune_dangling_contact(client, changes)
                changes = await _gate_form(client, await _gate_status(client, changes))
                if not changes:
                    return "ok"
                await client.update(RECEIPT_ENTITY, receipt_id, changes)
                return "updated"
            receipt_id = None  # fall through: the linked receipt is gone

        # No linked receipt: adopt an existing one by token, else create.
        adopted = await _find_by_token(client, row.get("submission_token") or "")
        if adopted:
            changes = {k: v for k, v in expected.items()
                       if k in _SYNC_KEYS and v is not None}
            if extra:
                changes.update(extra)
            changes = await _prune_dangling_contact(client, changes)
            changes = await _gate_form(client, await _gate_status(client, changes))
            await client.update(RECEIPT_ENTITY, adopted, changes)
            if store is not None and row.get("id"):
                await store.set_receipt_id(row["id"], adopted)
            return "updated"

        payload = {k: v for k, v in expected.items() if v is not None}
        if extra:
            payload.update(extra)
        payload = await _prune_dangling_contact(client, payload)
        payload = await _gate_form(client, await _gate_status(client, payload))
        created = await client.create(RECEIPT_ENTITY, payload)
        if store is not None and row.get("id") and created.get("id"):
            await store.set_receipt_id(row["id"], created["id"])
        return "created"
    except Exception as exc:  # noqa: BLE001 — receipts never break the caller
        log.warning(
            "receipt sync failed for %s (%s token=%s): %s",
            row.get("id"), row.get("form_slug"), row.get("submission_token"), exc,
        )
        return "failed"


async def touch(client, store, submission_id: str,
                *, extra: Optional[dict[str, Any]] = None) -> str:
    """Sync one submission's receipt right now (the per-action write). Loads
    the row fresh so the receipt reflects the state the action just produced."""
    row = await store.get_submission(submission_id)
    if row is None:
        return "failed"
    return await sync_row(client, store, row, extra=extra)


async def touch_safe(client, store, submission_id: str,
                     *, extra: Optional[dict[str, Any]] = None) -> str:
    """``touch`` that never raises (the call sites are user actions and the
    delivery loop — a receipt hiccup must not break either; the sweep heals)."""
    try:
        return await touch(client, store, submission_id, extra=extra)
    except Exception as exc:  # noqa: BLE001
        log.warning("receipt touch failed for %s: %s", submission_id, exc)
        return "failed"


async def create_direct(client, row_like: dict[str, Any]) -> Optional[str]:
    """Storeless (dev/dry-run) fallback: write a one-shot receipt from a
    synthesized row dict — no store row to link, no sweep to heal."""
    try:
        payload = {k: v for k, v in expected_fields(row_like).items() if v is not None}
        created = await client.create(RECEIPT_ENTITY, payload)
        return created.get("id")
    except Exception as exc:  # noqa: BLE001
        log.warning("direct receipt write failed (%s): %s",
                    row_like.get("form_slug"), exc)
        return None


async def run_receipt_sweep(client, store, settings: Settings,
                            state: Optional[dict] = None) -> dict[str, int]:
    """The reconciliation sweep: converge EVERY app-store row's receipt.
    Missing → adopted-or-created; stale → updated; matching → untouched.
    Idempotent, so it doubles as the manual "sync now" action. Persistent
    failures raise the drift alert (same admin channel as delivery alerts)."""
    stats = {"checked": 0, "created": 0, "updated": 0, "ok": 0, "failed": 0}
    offset = 0
    page = 500
    while True:
        rows = await store.list_all_for_receipts(limit=page, offset=offset)
        if not rows:
            break
        for row in rows:
            outcome = await sync_row(client, store, row)
            stats["checked"] += 1
            stats[outcome] = stats.get(outcome, 0) + 1
        if len(rows) < page:
            break
        offset += page
    if stats["created"] or stats["updated"] or stats["failed"]:
        log.info(
            "receipt sweep: %(checked)s checked, %(created)s created, "
            "%(updated)s updated, %(failed)s failed", stats,
        )
    if stats["failed"] and state is not None:
        from . import monitoring

        now = datetime.now(timezone.utc)
        if monitoring._due(state, "receipt_drift", now, settings.alert_cooldown_seconds):
            await monitoring.send_alert(
                settings,
                f"[cbm-intake {settings.environment}] {stats['failed']} intake "
                f"receipt(s) could not be written to the CRM (of "
                f"{stats['checked']} checked). The CRM's intake-submission "
                "audit trail is incomplete until this clears — check the CRM's "
                "health and the intake API user's edit permission on Intake "
                "Submission. The hourly sweep keeps retrying; 'Sync receipts' "
                "in Submission Admin runs it on demand.",
            )
    return stats
