"""Action history + cross-record reporting — the ``record_action`` helper.

Two writes per staff action, from one call (plan: ``prds/action-history-plan.md``):

1. a **Stream note** on the primary record, posted **as the acting user**, so the
   record's own history reads naturally (``core.stream.post_stream_note``); and
2. a **``CActionLog``** row — one per action — written **via the shared API key**
   (not the user's token) so the reporting log never depends on each staff role
   having a Note/create grant. ``actorName``/``actorId`` are stored explicitly, so
   attribution stays exact regardless of who the row is created by. The native
   ``CActionLog`` list view then gives filter/sort/export reporting for free.

Both writes are **best-effort but never silent**: a failure warns with enough to
reconstruct the event and never breaks the operation it documents (the
``post_stream_note`` / ``submission_log`` contract).

``CActionLog`` is **feature-gated**: until the CRM entity exists the log write is
skipped (the stream note still posts), so this ships ahead of the CRM build and
activates automatically once ``CActionLog`` is created — the app's standard
gated-CRM pattern (cf. ``transcript_field_exists``).

Vocabulary (``category`` = small stable enum for report grouping; ``actionType`` =
free-text verb from the constants below, so a NEW action can never be rejected by
an enum — see the plan §4.3). Add new verbs here as new actions are wired.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from .config import get_settings
from .espo import EspoClient
from .stream import post_stream_note

log = logging.getLogger("cbm_intake.action_log")

ACTION_LOG_ENTITY = "CActionLog"

# --- app identities (the `app` enum) ---------------------------------------
APP_CLIENT_ADMIN = "Client Administration"
APP_MENTOR_ADMIN = "Mentor Administration"
APP_MENTOR_PROFILE = "My Mentor Profile"
APP_CLIENT_MGMT = "Client Management"
APP_PARTNER_MGMT = "Partner Management"
APP_FUNDER_MGMT = "Funder Management"
APP_DIRECTORIES = "Directories"
APP_SUBMISSION_ADMIN = "Submission Admin"
APP_COMMUNICATIONS = "Communications"
APP_INTAKE = "Intake"

# --- categories (the `category` enum — small + stable) ----------------------
CAT_ASSIGNMENT = "Assignment"
CAT_STATUS = "Status Change"
CAT_RECORD_EDIT = "Record Edit"
CAT_CONTACT = "Contact & Company"
CAT_SESSION = "Session"
CAT_PROVISIONING = "Provisioning"
CAT_CONTRIBUTION = "Contribution"
CAT_COMMUNICATION = "Communication"
CAT_DOCUMENT = "Document"
CAT_INTAKE = "Intake"
CAT_CONFIG = "Config"

# --- action verbs (`actionType` — free-text over this vocabulary) -----------
ACT_MENTOR_ASSIGNED = "Mentor Assigned"
ACT_MENTOR_REASSIGNED = "Mentor Reassigned"
ACT_ASSIGNMENT_REPAIRED = "Assignment Repaired"
ACT_ENGAGEMENT_ACCEPTED = "Engagement Accepted"
ACT_ENGAGEMENT_ACTIVATED = "Engagement Activated"
ACT_COMENTOR_ADDED = "Co-mentor Added"
ACT_COMENTOR_REMOVED = "Co-mentor Removed"
ACT_STATUS_CHANGED = "Status Changed"
ACT_RECORD_EDITED = "Record Edited"
ACT_NOTES_EDITED = "Notes Edited"
ACT_PHOTO_UPDATED = "Profile Photo Updated"
ACT_SIGNATURE_UPDATED = "Email Signature Updated"
ACT_CONTACT_LINKED = "Contact Linked"
ACT_CONTACT_UNLINKED = "Contact Unlinked"
ACT_CONTACT_CREATED = "Contact Created"
ACT_COMPANY_CREATED = "Company Created"
ACT_CONTACT_EMAIL_ADDED = "Contact Email Added"
ACT_SESSION_RECORDED = "Session Recorded"
ACT_SESSION_EDITED = "Session Edited"
ACT_CAL_EVENT_CREATED = "Calendar Event Created"
ACT_CAL_EVENT_UPDATED = "Calendar Event Updated"
ACT_CAL_EVENT_CANCELLED = "Calendar Event Cancelled"
ACT_MENTOR_APPROVED = "Mentor Approved"
ACT_LOGIN_PROVISIONED = "Login Provisioned"
ACT_MAILBOX_PROVISIONED = "Mailbox Provisioned"
ACT_USER_LINKS_RECONCILED = "User Links Reconciled"
ACT_CONTRIBUTION_RECORDED = "Contribution Recorded"
ACT_CONTRIBUTION_EDITED = "Contribution Edited"
ACT_CONTRIBUTION_CANCELLED = "Contribution Cancelled"
ACT_EMAIL_SENT = "Email Sent"
ACT_CONVERSATION_LINKED = "Conversation Linked"
ACT_CONVERSATION_REMOVED = "Conversation Removed"
ACT_DOCUMENT_UPLOADED = "Document Uploaded"
ACT_DOCUMENT_ARCHIVED = "Document Archived"
ACT_DOCUMENT_RESTORED = "Document Restored"
ACT_ACCESS_GRANTED = "Drive Access Granted"
ACT_ACCESS_REVOKED = "Drive Access Revoked"
ACT_INTEGRATION_CONFIG = "Integration Config Changed"

_NAME_MAX = 250  # CActionLog.name is a varchar — keep the one-liner within it.

# Feature-gate cache: {base_url: (checked_monotonic, exists)}. A True result is
# kept; a False is re-checked after _RECHECK_S so the log activates within a few
# minutes of the CRM entity being created, without a metadata GET per action.
_exists_cache: dict[str, tuple[float, bool]] = {}
_RECHECK_S = 300.0


def _actionlog_client() -> Optional[EspoClient]:
    """The shared-API-key client used to write CActionLog rows (None in dry-run).

    Its own function so tests can monkeypatch it and so the log write never
    borrows the per-user token (that is the whole reliability point)."""
    settings = get_settings()
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    return EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )


async def _entity_available(client: EspoClient) -> bool:
    """Whether the CRM has the CActionLog entity yet (cached, TTL on False)."""
    settings = get_settings()
    key = settings.espo_base_url
    now = time.monotonic()
    cached = _exists_cache.get(key)
    if cached and (cached[1] or now - cached[0] < _RECHECK_S):
        return cached[1]
    try:
        scopes = await client.metadata("scopes")
        exists = isinstance(scopes, dict) and ACTION_LOG_ENTITY in scopes
    except Exception as exc:  # noqa: BLE001 — feature probe: fail closed, retry later
        log.debug("CActionLog probe failed (will retry): %s", exc)
        exists = False
    _exists_cache[key] = (now, exists)
    return exists


def _clip(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def log_action(
    *,
    app: str,
    category: str,
    action: str,
    parent_type: str,
    parent_id: str,
    summary: str,
    actor_id: str = "",
    actor_name: str = "",
    details: Optional[dict[str, Any]] = None,
    outcome: str = "Success",
) -> bool:
    """Write ONE ``CActionLog`` row (the reporting half). Best-effort: returns
    True when stored, False on any skip/failure (dry-run, entity not built yet,
    a rejected write) — never raises. Written via the shared API key."""
    client = _actionlog_client()
    if client is None:
        return False
    try:
        if not await _entity_available(client):
            return False
        payload: dict[str, Any] = {
            "name": _clip(summary, _NAME_MAX),
            "app": app,
            "category": category,
            "actionType": action,
            "actorName": actor_name,
            "summary": summary,
            "details": json.dumps(details, default=str, ensure_ascii=False) if details else None,
            "outcome": outcome,
            "parentType": parent_type,
            "parentId": parent_id,
        }
        if actor_id:
            payload["actorId"] = actor_id
        await client.create(ACTION_LOG_ENTITY, payload)
        return True
    except Exception as exc:  # noqa: BLE001 — reporting side channel: never break the op
        log.warning(
            "action-log write failed (%s on %s/%s by %s): %s",
            action, parent_type, parent_id, actor_name or actor_id or "?", exc,
        )
        return False


def _default_note(app: str, summary: str, actor_name: str) -> str:
    note = f"[{app}] {summary}"
    if actor_name:
        note += f" · by {actor_name}"
    return note


async def record_action(
    user_client: Any,
    *,
    app: str,
    category: str,
    action: str,
    parent_type: str,
    parent_id: str,
    summary: str,
    actor_id: str = "",
    actor_name: str = "",
    details: Optional[dict[str, Any]] = None,
    outcome: str = "Success",
    note: Optional[str] = None,
) -> None:
    """Record a staff action in BOTH places: a stream note on the record (posted
    as the acting user via ``user_client``) AND a ``CActionLog`` row (via the API
    key). Either failing is swallowed (logged) so the operation is never broken.

    ``note`` overrides the stream-note text (for a site whose existing wording we
    keep); otherwise a standard ``[App] <summary> · by <Actor>`` line is posted.
    """
    note_text = note if note is not None else _default_note(app, summary, actor_name)
    try:
        await post_stream_note(user_client, parent_type, parent_id, note_text)
    except Exception as exc:  # noqa: BLE001 — post_stream_note already swallows, belt-and-suspenders
        log.warning("stream note failed (%s/%s): %s", parent_type, parent_id, exc)
    await log_action(
        app=app, category=category, action=action,
        parent_type=parent_type, parent_id=parent_id, summary=summary,
        actor_id=actor_id, actor_name=actor_name, details=details, outcome=outcome,
    )
