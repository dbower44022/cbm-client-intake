"""Phase 6b — event follow-up email (EV-60…EV-64).

Five sends: **reminder**, **recording available**, **no-show re-engagement**,
**mentor-connection CTA** and **feedback survey**. All go out as the shared
info@ identity (EV-60) and are rendered from EspoCRM email templates, so staff
change the wording without a deploy.

Three rules with teeth:

* **Once per registrant, per event, per kind (EV-62).** The ledger is
  ``CEventRegistration.followUpsSent``, a multiEnum on the row itself — so a
  retry, a redrive, a second click or a worker restart cannot produce a second
  copy. The ledger is written **after** a successful send: a crash between
  sending and recording risks one duplicate, which is far better than the
  reverse, where the ledger says sent and nobody ever received it.
* **Cancelled and opted-out are excluded (EV-63).** A cancelled registration
  gets nothing. Marketing-flavoured sends (mentor CTA, survey) additionally
  require the Contact's marketing opt-in; the operational ones (reminder,
  recording, no-show) do not — they are about a thing the person signed up for.
* **Nothing sends without a template.** A missing EspoCRM template is a skip
  with a clear reason, never an improvised email in CBM's name.

Inert unless Events, Gmail sync and a shared mailbox are all configured.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core.config import Settings
from core.espo import EspoApi, EspoError

from . import config as cfg
from . import service

log = logging.getLogger("cbm_intake.events.notify")

#: Ledger values — these MUST match the CEventRegistration.followUpsSent enum.
#: An out-of-enum value 400s the whole update (the trap that lost every event
#: registration's receipt in v0.192.3), so `send_follow_up` verifies the option
#: exists before writing.
KIND_REMINDER = "Reminder"
KIND_RECORDING = "Recording"
KIND_NO_SHOW = "No Show"
KIND_MENTOR_CTA = "Mentor CTA"
KIND_SURVEY = "Survey"


@dataclass(frozen=True)
class FollowUp:
    kind: str
    #: EspoCRM EmailTemplate name. Staff own the wording; we own the trigger.
    template: str
    #: Which attendance states the send is for.
    statuses: tuple[str, ...]
    #: Marketing-flavoured sends need the Contact's opt-in; operational ones don't.
    needs_opt_in: bool = False
    description: str = ""


FOLLOW_UPS: tuple[FollowUp, ...] = (
    FollowUp(KIND_REMINDER, "EventReminder", (cfg.REG_REGISTERED,),
             description="Before the event, carrying the join link."),
    FollowUp(KIND_RECORDING, "EventRecordingAvailable",
             (cfg.REG_ATTENDED, cfg.REG_NO_SHOW, cfg.REG_REGISTERED),
             description="After the recording is published."),
    FollowUp(KIND_NO_SHOW, "EventNoShow", (cfg.REG_NO_SHOW,),
             description="Re-engagement for people who registered but didn't come."),
    FollowUp(KIND_MENTOR_CTA, "EventMentorCTA", (cfg.REG_ATTENDED,),
             needs_opt_in=True,
             description="Invitation to explore mentoring. Opt-in only."),
    FollowUp(KIND_SURVEY, "EventSurvey", (cfg.REG_ATTENDED,),
             needs_opt_in=True,
             description="Feedback survey. Opt-in only."),
)

BY_KIND = {f.kind: f for f in FOLLOW_UPS}


def notify_active(settings: Settings) -> bool:
    """Every piece must be present: the feature, the send stack, the identity."""
    return bool(
        settings.events_active
        and settings.gmail_sync
        and settings.ops_mailbox
        and not settings.espo_dry_run
    )


def already_sent(registration: dict[str, Any], kind: str) -> bool:
    return kind in (registration.get("followUpsSent") or [])


def skip_reason(
    follow_up: FollowUp, registration: dict[str, Any], contact: Optional[dict[str, Any]]
) -> str:
    """Why this registrant should NOT get this send — "" means send it.

    Returns a human sentence, because the manual trigger shows staff exactly who
    was skipped and why (EV-64); a silent skip looks like a bug.
    """
    status = registration.get("attendanceStatus") or ""
    if status == cfg.REG_CANCELLED:
        return "registration cancelled"
    if already_sent(registration, follow_up.kind):
        return "already sent"
    if status not in follow_up.statuses:
        return f"status is {status or 'unset'}"
    if not (registration.get("email") or "").strip():
        return "no email address"
    if follow_up.needs_opt_in:
        opted_in = bool(
            registration.get("marketingOptIn")
            or (contact or {}).get("cMarketingOptIn")
        )
        if not opted_in:
            return "no marketing opt-in"
    return ""


def plan_sends(
    follow_up: FollowUp,
    registrations: list[dict[str, Any]],
    contacts: Optional[dict[str, dict[str, Any]]] = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Split a roster into (recipients, [{email, reason} skipped]). Pure."""
    contacts = contacts or {}
    send: list[dict[str, Any]] = []
    skip: list[dict[str, str]] = []
    for reg in registrations:
        reason = skip_reason(follow_up, reg, contacts.get(reg.get("contactId") or ""))
        if reason:
            skip.append({
                "email": reg.get("email") or "(no address)",
                "name": f"{reg.get('firstName') or ''} {reg.get('lastName') or ''}".strip(),
                "reason": reason,
            })
        else:
            send.append(reg)
    return send, skip


async def _ledger_options(client: EspoApi) -> Optional[list[str]]:
    try:
        return await client.metadata_enum_options(cfg.REGISTRATION, "followUpsSent")
    except Exception as exc:  # noqa: BLE001 — unverifiable: proceed, write may fail
        log.debug("follow-ups: could not read the ledger enum: %s", exc)
        return None


async def record_sent(client: EspoApi, registration: dict[str, Any], kind: str) -> bool:
    """Append ``kind`` to the row's ledger. Returns False if it could not be
    recorded — the caller logs loudly, because an unrecorded send is the one way
    a duplicate can happen."""
    current = list(registration.get("followUpsSent") or [])
    if kind in current:
        return True
    options = await _ledger_options(client)
    if options is not None and kind not in options:
        log.warning(
            "follow-ups: %r is not an option on %s.followUpsSent — not recording "
            "(add the option, or the send will repeat)", kind, cfg.REGISTRATION,
        )
        return False
    try:
        await client.update(
            cfg.REGISTRATION, registration["id"], {"followUpsSent": current + [kind]}
        )
        return True
    except EspoError as exc:
        log.warning(
            "follow-ups: could not record %r on registration %s: %s",
            kind, registration.get("id"), exc,
        )
        return False


async def send_follow_up(
    settings: Settings,
    client: EspoApi,
    event: dict[str, Any],
    follow_up: FollowUp,
    *,
    registrations: Optional[list[dict[str, Any]]] = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Send one kind to everyone on an event who should get it.

    ``dry_run`` returns exactly who would receive it and who would be skipped,
    which is what the admin preview shows (EV-64).
    """
    if registrations is None:
        registrations = await service.list_registrations(client, event["id"])
    recipients, skipped = plan_sends(follow_up, registrations)
    result: dict[str, Any] = {
        "kind": follow_up.kind,
        "template": follow_up.template,
        "eventId": event.get("id"),
        "recipients": [
            {"email": r.get("email"),
             "name": f"{r.get('firstName') or ''} {r.get('lastName') or ''}".strip()}
            for r in recipients
        ],
        "skipped": skipped,
        "sent": 0,
        "errors": [],
        "dryRun": dry_run,
    }
    if dry_run or not recipients:
        return result
    if not notify_active(settings):
        result["errors"].append(
            "Follow-up email is not configured (needs Events, Gmail sync and the "
            "shared mailbox)."
        )
        return result

    from comms import service as comms_service
    from comms import templates as comms_templates

    try:
        found = await comms_templates.list_templates(client, follow_up.template)
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"Could not read templates: {exc}")
        return result
    # `list_templates` is a CONTAINS search, so match the name exactly — a
    # template called "EventReminder (old)" must not be picked up by accident.
    template = next(
        (row for row in found.get("templates", [])
         if (row.get("name") or "").strip() == follow_up.template),
        None,
    )
    if not template:
        # EV-60: staff own the wording. No template, no improvised email.
        result["errors"].append(
            f"No EspoCRM email template named {follow_up.template!r}. Create it, "
            "then send again — nothing was sent."
        )
        return result

    gmail = await comms_service.gmail_for_shared_mailbox(settings, settings.ops_mailbox)
    try:
        for reg in recipients:
            try:
                rendered = await comms_templates.parse_template(
                    client, template["id"],
                    parent_type=cfg.EVENT, parent_id=event["id"],
                    email_address=reg.get("email"),
                )
                await comms_service.send_quick_message(
                    gmail=gmail,
                    to=[reg["email"]],
                    subject=rendered.get("subject") or (event.get("name") or "CBM event"),
                    body_html=rendered.get("bodyHtml") or "",
                    sender_name=settings.ops_mailbox_name,
                )
            except Exception as exc:  # noqa: BLE001 — one recipient never stops the rest
                result["errors"].append(f"{reg.get('email')}: {exc}")
                continue
            result["sent"] += 1
            if not await record_sent(client, reg, follow_up.kind):
                result["errors"].append(
                    f"{reg.get('email')}: sent, but the ledger could not be updated "
                    "— this one may send again."
                )
    finally:
        await gmail.aclose()
    return result


# --- the reminder timer ------------------------------------------------------


async def due_reminders(
    client: EspoApi, settings: Settings, *, now: Optional[datetime] = None
) -> list[dict[str, Any]]:
    """Published, non-cancelled events starting inside the reminder lead time.

    Bounded below by the event start: once an event has begun a reminder is
    noise, so a worker that was down through the window simply misses it rather
    than emailing people about something already under way.
    """
    moment = now or datetime.now(timezone.utc)
    horizon = moment + timedelta(hours=max(1, settings.events_reminder_lead_hours))
    rows = await service._all_events(
        client,
        select=cfg.PUBLIC_SELECT,
        where=[
            {"type": "after", "attribute": "dateStart",
             "value": service.to_crm_datetime(moment)},
            {"type": "before", "attribute": "dateStart",
             "value": service.to_crm_datetime(horizon)},
        ],
        order_by="dateStart",
        limit=100,
    )
    return [r for r in rows if r.get("status") != cfg.STATUS_CANCELLED]


async def run_reminder_cycle(
    settings: Settings, *, client: Optional[EspoApi] = None
) -> dict[str, int]:
    """The worker's timer body. Best-effort: never raises."""
    totals = {"events": 0, "sent": 0, "skipped": 0, "errors": 0}
    if not notify_active(settings) or not settings.events_reminders:
        return totals
    if client is None:
        from core.espo import EspoClient

        client = EspoClient(
            settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
        )
    try:
        events = await due_reminders(client, settings)
    except EspoError as exc:
        log.warning("reminders: could not list due events: %s", exc)
        return {**totals, "errors": 1}
    totals["events"] = len(events)
    for event in events:
        try:
            result = await send_follow_up(
                settings, client, event, BY_KIND[KIND_REMINDER]
            )
        except Exception as exc:  # noqa: BLE001 — one event never stops the rest
            totals["errors"] += 1
            log.warning("reminders: failed for event %s: %s", event.get("id"), exc)
            continue
        totals["sent"] += result["sent"]
        totals["skipped"] += len(result["skipped"])
        totals["errors"] += len(result["errors"])
    if totals["events"]:
        log.info("event reminder pass: %s", totals)
    return totals


def catalogue() -> list[dict[str, Any]]:
    """What the Follow-up tab offers (EV-64)."""
    return [
        {"kind": f.kind, "template": f.template, "description": f.description,
         "needsOptIn": f.needs_opt_in, "statuses": list(f.statuses)}
        for f in FOLLOW_UPS
    ]
