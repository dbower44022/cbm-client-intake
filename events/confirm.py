"""The registration confirmation — CBM's own, the only email a registrant gets (D3).

Three single-recipient sends, siblings of the five fan-out follow-ups in
:mod:`events.notify` (the render and ledger halves carry over; the fan-out does
not, which is why this is not a reuse of ``send_follow_up``):

* **Confirmation** — the ticket. Sent at delivery to a registrant who holds a
  seat. For an online public event it carries the person's OWN Zoom join link
  (``CEventRegistration.zoomJoinUrl``, returned when the registrant is pushed to
  Zoom); for an in-person event the venue; for an Internal event that takes
  registrations the event's Join URL (the member rule, Portal Calendar design
  D2). Zoom's own registrant emails are switched off (ruling D3-2), so this
  send is the thing the registrant depends on — which is why a public online
  registration **without a personal join link yet is not confirmed at all**:
  the send is skipped with a reason, and the next delivery attempt (a redrive)
  pushes to Zoom again and then confirms.
* **Waitlisted** — the same moment, for a registrant the capacity put on the
  waiting list. No join link; a seat is not theirs.
* **Seat Offered** — when a cancellation promotes the longest-waiting person,
  after they have been pushed to Zoom. From then on they are an ordinary
  registrant.

Rulings behind this module (`CBM_Events_Finalization_Plan.md`, D3): CBM sends
its own confirmation (08-17-26); the confirmation is the ticket and a public
online event is never offered without its webinar (D3-1, 10-22-26); one email,
ours, Zoom's confirmations off (D3-2, 10-22-26).

Rules with teeth, the same three as the follow-ups: once per registration
(``confirmationSentAt`` for the first two kinds, the ``followUpsSent`` ledger
for Seat Offered — written AFTER a successful send); cancelled registrations
get nothing; nothing sends without the EspoCRM template, and nothing is
improvised in CBM's name.

**App tokens.** EspoCRM renders its own ``{Contact.firstName}`` / ``{CEvent.name}``
placeholders; the values only this application knows — the personal join link,
the cancel link, the event's page, the time in the chapter's own zone — ride as
``{{token}}`` placeholders substituted AFTER EspoCRM's render, HTML-escaped in
the body. The set is :data:`TOKEN_NAMES`; ``scripts/seed_event_templates.py``
writes default wording that uses them, and the staff guide lists them.

Dark behind ``EVENTS_CONFIRMATIONS`` (off) on top of the follow-ups' own
``notify_active`` conditions (Events, Gmail sync, the shared mailbox).
"""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from core.config import Settings
from core.espo import EspoApi, EspoError

from . import config as cfg
from . import ics as ics_mod
from . import notify
from . import service
from . import visibility
from .tokens import cancel_url as make_cancel_url

log = logging.getLogger("cbm_intake.events.confirm")

KIND_CONFIRMATION = "Confirmation"
KIND_WAITLISTED = "Waitlisted"
KIND_SEAT_OFFERED = "Seat Offered"

#: EspoCRM EmailTemplate names, exact. Staff own the wording; we own the trigger.
TEMPLATES: dict[str, str] = {
    KIND_CONFIRMATION: "EventConfirmation",
    KIND_WAITLISTED: "EventWaitlisted",
    KIND_SEAT_OFFERED: "EventSeatOffered",
}

#: Where the first two kinds are ledgered: a datetime on the registration.
LEDGER_FIELD = "confirmationSentAt"

#: The ``{{token}}`` placeholders a template may use, in every event email.
TOKEN_NAMES = (
    "firstName", "lastName", "eventName", "when", "where", "joinUrl", "joinBlock",
    "cancelUrl", "eventUrl", "recordingUrl", "orgName", "orgAbbr",
)

_APP_TOKEN = re.compile(r"\{\{\s*([A-Za-z][A-Za-z0-9]*)\s*\}\}")


def active(settings: Settings) -> bool:
    """The follow-ups' send stack AND this feature's own switch."""
    return bool(getattr(settings, "events_confirmations", False)) and notify.notify_active(settings)


# --- what goes into the email -----------------------------------------------

def join_url_for(event: dict[str, Any], registration: dict[str, Any]) -> str:
    """The link THIS registrant joins by.

    The personal Zoom link first. Failing that, only an Internal event lends its
    shared Join URL (members registered for it see it on the member page, so the
    email may carry it too). A Public online event's shared link is never sent:
    the personal one is the ticket, and if it is missing the send waits.
    """
    personal = (registration.get("zoomJoinUrl") or "").strip()
    if personal:
        return personal
    if visibility.effective_audience(event) == cfg.AUDIENCE_INTERNAL:
        return (event.get("virtualMeetingUrl") or "").strip()
    return ""


def when_text(event: dict[str, Any]) -> str:
    """``Wednesday, October 21, 2026, 12:00 PM – 1:15 PM`` in the chapter's zone."""
    start = service.parse_crm_datetime(event.get("dateStart"))
    if start is None:
        return ""
    local = service.to_local(start)
    text = local.strftime("%A, %B %-d, %Y, %-I:%M %p")
    end = service.parse_crm_datetime(event.get("dateEnd"))
    if end is not None:
        text += " – " + service.to_local(end).strftime("%-I:%M %p")
    return text


def where_text(event: dict[str, Any]) -> str:
    location = (event.get("location") or "").strip()
    if location:
        return location
    return "Online" if (event.get("format") or "") in cfg.ONLINE_FORMATS else ""


def event_url(settings: Settings, event: dict[str, Any]) -> str:
    slug = (event.get("slug") or "").strip()
    if not slug:
        return ""
    base = (getattr(settings, "events_public_base_url", "") or "").strip()
    if not base:
        app = (getattr(settings, "app_base_url", "") or "").strip().rstrip("/")
        base = f"{app}/webinars" if app else ""
    return f"{base.rstrip('/')}/{slug}" if base else ""


def app_tokens(
    settings: Settings, event: dict[str, Any], registration: dict[str, Any], *, kind: str
) -> dict[str, str]:
    """Every ``{{token}}`` value for one registrant on one event."""
    from core import branding

    join = join_url_for(event, registration) if kind != KIND_WAITLISTED else ""
    cancel = ""
    secret = getattr(settings, "session_secret", "") or ""
    base = (getattr(settings, "app_base_url", "") or "").strip()
    if registration.get("id") and secret and base:
        cancel = make_cancel_url(registration["id"], secret, base) or ""
    return {
        "firstName": registration.get("firstName") or "",
        "lastName": registration.get("lastName") or "",
        "eventName": event.get("name") or "",
        "when": when_text(event),
        "where": where_text(event),
        "joinUrl": join,
        "joinBlock": (
            f'<p>Join online: <a href="{html.escape(join, quote=True)}">'
            f"{html.escape(join)}</a></p>" if join else ""
        ),
        "cancelUrl": cancel,
        "eventUrl": event_url(settings, event),
        "recordingUrl": (event.get("recordingUrl") or "").strip(),
        "orgName": getattr(settings, "organization_name", "") or "",
        "orgAbbr": branding.abbr(settings),
    }


def apply_app_tokens(text: str, tokens: dict[str, str], *, as_html: bool) -> str:
    """Substitute ``{{token}}`` placeholders. ``joinBlock`` is already HTML and
    is placed as-is; every other value is escaped in an HTML body. An unknown
    token stays literal, like EspoCRM's own unresolved ones."""
    def one(match: "re.Match[str]") -> str:
        name = match.group(1)
        if name not in tokens:
            return match.group(0)
        value = tokens[name] or ""
        if as_html and name != "joinBlock":
            return html.escape(value)
        return value
    return _APP_TOKEN.sub(one, text or "")


def calendar_attachment(
    settings: Settings, event: dict[str, Any], registration: dict[str, Any], *, join: str,
    now: Optional[datetime] = None,
) -> Optional[dict[str, Any]]:
    start = service.parse_crm_datetime(event.get("dateStart"))
    if start is None:
        return None
    end = service.parse_crm_datetime(event.get("dateEnd"))
    description = (event.get("description") or "").strip()
    if join:
        description = (description + "\n\n" if description else "") + f"Join online: {join}"
    text = ics_mod.build_ics(
        uid=f"{event.get('id')}-{registration.get('id')}@cbm-client-intake",
        summary=event.get("name") or "Event",
        start=start, end=end,
        description=description,
        location=(event.get("location") or "").strip() or join,
        url=event_url(settings, event),
        organizer_name=getattr(settings, "sender_display_name", "") or "",
        organizer_email=getattr(settings, "ops_mailbox", "") or "",
        now=now,
    )
    return ics_mod.attachment(text)


# --- deciding whether to send -------------------------------------------------

def kind_for_status(status: Optional[str]) -> Optional[str]:
    if status == cfg.REG_REGISTERED:
        return KIND_CONFIRMATION
    if status == cfg.REG_WAITLISTED:
        return KIND_WAITLISTED
    return None


def already_sent(registration: dict[str, Any], kind: str) -> bool:
    if kind == KIND_SEAT_OFFERED:
        return notify.already_sent(registration, KIND_SEAT_OFFERED)
    return bool((registration.get(LEDGER_FIELD) or "").strip()) if isinstance(
        registration.get(LEDGER_FIELD), str) else bool(registration.get(LEDGER_FIELD))


def skip_reason(
    settings: Settings, event: dict[str, Any], registration: dict[str, Any], kind: str
) -> Optional[str]:
    """Why this registrant does NOT get this kind right now; None means send."""
    if not active(settings):
        return "confirmation email is not switched on"
    if not (registration.get("email") or "").strip():
        return "no email address"
    if registration.get("attendanceStatus") == cfg.REG_CANCELLED:
        return "registration cancelled"
    if already_sent(registration, kind):
        return "already sent"
    if kind in (KIND_CONFIRMATION, KIND_SEAT_OFFERED) and visibility.effective_audience(
            event) == cfg.AUDIENCE_PUBLIC and (event.get("format") or "") in cfg.ONLINE_FORMATS:
        if not (registration.get("zoomJoinUrl") or "").strip():
            # D3-2: ours is the only email, so a ticket without a way in is
            # worse than a late ticket. The redrive pushes to Zoom and retries.
            return "no personal join link yet"
    return None


# --- sending -------------------------------------------------------------------

async def _find_template(client: EspoApi, name: str) -> Optional[dict[str, Any]]:
    from comms import templates as comms_templates

    found = await comms_templates.list_templates(client, name)
    return next(
        (row for row in found.get("templates", [])
         if (row.get("name") or "").strip() == name),
        None,
    )


async def _render(
    client: EspoApi, template_id: str, event: dict[str, Any], email: str
) -> dict[str, Any]:
    from comms import templates as comms_templates

    return await comms_templates.parse_template(
        client, template_id, parent_type=cfg.EVENT, parent_id=event["id"],
        email_address=email,
    )


async def _send(
    settings: Settings, *, to: str, subject: str, body_html: str,
    attachments: Optional[list[dict[str, Any]]],
) -> None:
    from comms import service as comms_service

    gmail = await comms_service.gmail_for_shared_mailbox(settings, settings.ops_mailbox)
    try:
        await comms_service.send_quick_message(
            gmail=gmail, to=[to], subject=subject, body_html=body_html,
            sender_name=settings.sender_display_name, attachments=attachments or None,
        )
    finally:
        await gmail.aclose()


async def _record(
    client: EspoApi, registration: dict[str, Any], kind: str, now: datetime
) -> bool:
    if kind == KIND_SEAT_OFFERED:
        return await notify.record_sent(client, registration, KIND_SEAT_OFFERED)
    try:
        stamp = service.to_crm_datetime(now)
        await client.update(cfg.REGISTRATION, registration["id"], {LEDGER_FIELD: stamp})
        registration[LEDGER_FIELD] = stamp
        return True
    except EspoError as exc:
        log.warning("registration %s: %s sent but the ledger was refused: %s",
                    registration.get("id"), kind, exc)
        return False


async def send_registration_email(
    settings: Settings, client: EspoApi, event: dict[str, Any],
    registration: dict[str, Any], kind: str, *,
    now: Optional[datetime] = None, dry_run: bool = False,
) -> dict[str, Any]:
    """Send one kind to one registrant, or say exactly why not.

    Returns ``{"kind", "ok", "skipped"|"error", "template", "to"}``. Never
    raises: a registration is complete before this runs, and the caller's save
    must not fail over an email.
    """
    moment = now or datetime.now(timezone.utc)
    template_name = TEMPLATES[kind]
    out: dict[str, Any] = {"kind": kind, "template": template_name,
                           "to": registration.get("email"), "ok": False}
    reason = skip_reason(settings, event, registration, kind)
    if reason:
        out["skipped"] = reason
        return out
    try:
        template = await _find_template(client, template_name)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"could not read templates: {exc}"
        return out
    if not template:
        out["error"] = (f"no EspoCRM email template named {template_name!r} — "
                        "create it; nothing was sent")
        return out
    tokens = app_tokens(settings, event, registration, kind=kind)
    try:
        rendered = await _render(client, template["id"], event, registration["email"])
        subject = apply_app_tokens(
            rendered.get("subject") or (event.get("name") or "Your registration"),
            tokens, as_html=False)
        body = apply_app_tokens(rendered.get("bodyHtml") or "", tokens, as_html=True)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"render failed: {exc}"
        return out
    attachments: list[dict[str, Any]] = []
    if kind != KIND_WAITLISTED:
        ics = calendar_attachment(settings, event, registration, join=tokens["joinUrl"], now=moment)
        if ics:
            attachments.append(ics)
    out.update({"subject": subject, "attachments": [a["filename"] for a in attachments]})
    if dry_run:
        out["ok"] = True
        out["dryRun"] = True
        return out
    try:
        await _send(settings, to=registration["email"], subject=subject,
                    body_html=body, attachments=attachments)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"send failed: {exc}"
        return out
    out["ok"] = True
    if not await _record(client, registration, kind, moment):
        out["ledger"] = "not recorded — this one may send again"
    return out


async def after_registration(
    settings: Optional[Settings], client: EspoApi, event: dict[str, Any],
    registration_id: str, status: Optional[str], *, now: Optional[datetime] = None,
) -> dict[str, Any]:
    """The delivery-time hook: confirm a seat, or acknowledge the waiting list.

    Best-effort by construction — every failure is a dict, never an exception.
    """
    kind = kind_for_status(status)
    if settings is None or kind is None:
        return {"ok": False, "skipped": "no kind for this status"}
    if not active(settings):
        return {"ok": False, "skipped": "confirmation email is not switched on"}
    try:
        registration = await client.get(cfg.REGISTRATION, registration_id)
    except EspoError as exc:
        return {"ok": False, "error": f"could not read the registration: {exc}"}
    if not registration:
        return {"ok": False, "error": "registration not found"}
    return await send_registration_email(settings, client, event, registration, kind, now=now)


async def after_promotion(
    settings: Optional[Settings], client: EspoApi, event: dict[str, Any],
    registration: dict[str, Any], *, now: Optional[datetime] = None,
) -> dict[str, Any]:
    """The waitlist hook: the promoted person's seat, with their own join link."""
    if settings is None or not active(settings):
        return {"ok": False, "skipped": "confirmation email is not switched on"}
    return await send_registration_email(
        settings, client, event, registration, KIND_SEAT_OFFERED, now=now)


def catalogue() -> list[dict[str, str]]:
    """For the staff guide and the readiness panel: kind → template."""
    return [{"kind": k, "template": v} for k, v in TEMPLATES.items()]
