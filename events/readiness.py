"""Can event hosting work here? The live checks behind the Event hosting card on
System Settings → Feature readiness (prds/events/event-hosting-plan.md § 8,
item 2; ruling R1, Doug 11-18-26: a card on Feature readiness).

Every failure the step 6 live check met on the Business Mentors Association's
system (11-17/18-26) was readable before anyone registered: the worker's
Events switch, the missing email templates, the Zoom host letting attendees
share. This module reads each of them and says so in words.

**Read-only.** It never writes to the CRM or to Zoom. A fix is a separate,
confirmed action (item 3, ruling R2).

Each check is ``{"kind", "label", "ok", "detail"}``, the shape every Feature
readiness row already has: ``ok`` True (ready), False (not ready, ``detail``
says why and what to do) or None (could not be read, or does not apply).
A failure to read is never an error page.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

from core.zoom import PRODUCT_MEETING

from . import config as cfg
from . import hosting

log = logging.getLogger("cbm_intake.events.readiness")

#: The eight EspoCRM email templates every event email is sent from
#: (scripts/seed_event_templates.py creates any that are missing).
TEMPLATE_NAMES: tuple[str, ...] = (
    "EventConfirmation", "EventWaitlisted", "EventSeatOffered", "EventReminder",
    "EventRecordingAvailable", "EventNoShow", "EventMentorCTA", "EventSurvey",
)

#: Zoom's value for "Who can share?" set to Host Only. ``"all"`` is
#: documented; ``"host"`` is the expected counterpart, not yet confirmed
#: against Zoom's reference, so any other value reads as unknown, never ready.
SHARE_HOST = "host"
SHARE_ALL = "all"


def _row(label: str, ok: Optional[bool], detail: str) -> dict[str, Any]:
    return {"kind": "hosting", "label": label, "ok": ok, "detail": detail}


# --- the worker ----------------------------------------------------------------

def worker_rows(worker: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    """From the worker's own report (core/worker_switches.py): Events on, and
    everything the confirmation needs. ``worker`` is ``store.worker_report()``."""
    switches = (worker or {}).get("switches")
    if not switches:
        why = ("the worker has not reported its switches yet; it does on its first "
               "beat after this version is deployed")
        return [_row("Events, for the worker", None, why),
                _row("Confirmation email, for the worker", None, why)]
    rows = []
    if switches.get("events_enabled"):
        rows.append(_row("Events, for the worker", True, "on"))
    else:
        rows.append(_row(
            "Events, for the worker", False,
            "off: the worker delivers registrations but sends no confirmation, reminder "
            "or follow-up and pulls no attendance. Set EVENTS_ENABLED on the worker "
            "component, or save Events & Webinars as On here to override it."))
    missing = [label for key, label in (
        ("events_confirmations", "Registration confirmation emails"),
        ("gmail_sync", "Gmail conversation sync"),
        ("ops_mailbox", "the shared mailbox"),
    ) if not switches.get(key)]
    if switches.get("espo_dry_run"):
        missing.append("a real CRM (the worker is in dry run)")
    if missing:
        rows.append(_row("Confirmation email, for the worker", False,
                         "cannot be sent: off or missing for the worker: " + ", ".join(missing)))
    else:
        rows.append(_row("Confirmation email, for the worker", True,
                         "switched on, with Gmail sync and the shared mailbox"))
    return rows


# --- the CRM -------------------------------------------------------------------

async def template_row(crm: Any) -> dict[str, Any]:
    """The eight event email templates, read by name."""
    label = "Event email templates"
    if crm is None:
        return _row(label, None, "the CRM could not be read")
    try:
        data = await crm.list(
            "EmailTemplate", select="id,name", max_size=200,
            where=[{"type": "in", "attribute": "name", "value": list(TEMPLATE_NAMES)}],
        )
    except Exception as exc:  # noqa: BLE001 — a read failure is unknown, never an error
        log.info("readiness: email templates unreadable: %s", exc)
        return _row(label, None, "could not be read")
    present = {str(r.get("name") or "").strip() for r in (data or {}).get("list", [])}
    missing = [n for n in TEMPLATE_NAMES if n not in present]
    if not missing:
        return _row(label, True, "all 8 present")
    return _row(label, False,
                f"{len(missing)} of 8 missing ({', '.join(missing)}): every send of those "
                "kinds refuses until they exist. Create them with "
                "scripts/seed_templates.sh, or in the CRM under Email Templates.")


async def option_rows(crm: Any) -> list[dict[str, Any]]:
    """The hosting method's options and the portal's registration source."""
    rows = []
    if crm is None:
        return [_row("Hosting method options", None, "the CRM could not be read"),
                _row("Members register from the portal", None, "the CRM could not be read")]
    try:
        methods = await crm.metadata_enum_options(cfg.EVENT, cfg.HOSTED_BY_FIELD)
    except Exception:  # noqa: BLE001
        methods = None
    if methods is None:
        rows.append(_row("Hosting method options", False,
                         "the CRM has no Hosted by field on events, so every online event "
                         "is a Zoom webinar (cevent-hostedby-crm-handoff.md)"))
    else:
        lacking = [hosting.label(v) for v in (hosting.MEETINGS, hosting.OTHER)
                   if v not in methods]
        if lacking:
            rows.append(_row("Hosting method options", False,
                             "the CRM does not offer " + " or ".join(lacking)
                             + " (cevent-hosting-method-crm-handoff.md)"))
        else:
            rows.append(_row("Hosting method options", True,
                             ", ".join(hosting.label(v) for v in methods)))
    try:
        sources = await crm.metadata_enum_options(cfg.REGISTRATION, "registrationSource")
    except Exception:  # noqa: BLE001
        sources = None
    if sources is None:
        rows.append(_row("Members register from the portal", None, "could not be read"))
    elif cfg.SOURCE_PORTAL in sources:
        rows.append(_row("Members register from the portal", True,
                         f"the registration source {cfg.SOURCE_PORTAL} exists"))
    else:
        rows.append(_row("Members register from the portal", False,
                         f"the CRM lacks the registration source {cfg.SOURCE_PORTAL}, so "
                         "a member's Register button is refused"))
    return rows


# --- Zoom Meetings ----------------------------------------------------------------

async def zoom_rows(settings: Any, zoom: Any = None) -> list[dict[str, Any]]:
    """The event host user's settings that decide what an attendee may do
    (ruling EH11): screen sharing for the host only, and co-host on so a
    co-presenter can share. Only while Zoom Meetings is switched on."""
    if not getattr(settings, "zoom_meetings_events", False):
        return [_row("Zoom Meetings", None, "not switched on, so not checked")]
    account_host = hosting.zoom_host(settings, PRODUCT_MEETING)
    api = zoom or hosting.zoom_client(settings, PRODUCT_MEETING)
    if api is None or not account_host:
        return [_row("Zoom Meetings", False,
                     "switched on but not set up: the app's credentials or the event host "
                     "user are missing (Integrations, Zoom Meetings)")]
    try:
        user_settings = await api.get_user_settings(account_host) or {}
    except Exception as exc:  # noqa: BLE001
        log.info("readiness: Zoom host settings unreadable: %s", exc)
        return [_row("Zoom event host user", None,
                     f"the settings of {account_host} could not be read from Zoom")]
    rows = [_row("Zoom event host user", True, account_host)]
    meeting = user_settings.get("in_meeting") or {}

    who = meeting.get("who_can_share_screen")
    sharing_on = meeting.get("screen_sharing")
    if sharing_on is False:
        rows.append(_row("Screen sharing", False,
                         "off for the event host user, so not even a co-presenter can "
                         "share. Turn it on with Who can share? set to Host Only."))
    elif who == SHARE_HOST:
        rows.append(_row("Screen sharing", True, "host only"))
    elif who == SHARE_ALL:
        rows.append(_row("Screen sharing", False,
                         "all participants: any attendee can share their screen. Set Who "
                         "can share? to Host Only for the event host user (ruling EH11)."))
    else:
        rows.append(_row("Screen sharing", None,
                         f"Zoom reported who can share as {who!r}, which this check does "
                         "not recognise" if who else "Zoom did not report who can share"))

    co_host = meeting.get("co_host")
    if co_host is True:
        rows.append(_row("Co-host", True,
                         "on, so a co-presenter made co-host in the meeting can share"))
    elif co_host is False:
        rows.append(_row("Co-host", False,
                         "off: a co-presenter cannot be made co-host, so only the host "
                         "can share"))
    else:
        rows.append(_row("Co-host", None, "Zoom did not report it"))
    return rows


# --- the card ---------------------------------------------------------------------

async def checks(
    settings: Any,
    *,
    worker: Optional[dict[str, Any]] = None,
    crm_factory: Optional[Callable[[], Any]] = None,
    zoom: Any = None,
) -> list[dict[str, Any]]:
    """Every check on the Event hosting card, in the order staff act on them."""
    crm = None
    if crm_factory is not None and not getattr(settings, "espo_dry_run", False):
        try:
            crm = crm_factory()
        except Exception as exc:  # noqa: BLE001
            log.info("readiness: no CRM client: %s", exc)
    rows = worker_rows(worker)
    rows.append(await template_row(crm))
    rows.extend(await option_rows(crm))
    rows.extend(await zoom_rows(settings, zoom))
    return rows
