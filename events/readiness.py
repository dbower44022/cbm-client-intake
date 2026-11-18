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
#: (events/email_templates.py holds their wording and creates missing ones).
from .email_templates import NAMES as TEMPLATE_NAMES  # noqa: E402

#: Zoom's value for "Who can share?" set to Host Only. ``"all"`` is
#: documented; ``"host"`` is the expected counterpart, not yet confirmed
#: against Zoom's reference, so any other value reads as unknown, never ready.
SHARE_HOST = "host"
SHARE_ALL = "all"


def _row(label: str, ok: Optional[bool], detail: str,
         fix: Optional[dict[str, str]] = None) -> dict[str, Any]:
    row = {"kind": "hosting", "label": label, "ok": ok, "detail": detail}
    if fix:
        row["fix"] = fix
    return row


#: The fix buttons (item 3, ruling R2): each names exactly what it changes and
#: acts only on a second click. ``confirm`` is what the first click shows.
FIX_TEMPLATES = "templates"
FIX_ZOOM_SHARING = "zoom_sharing"


def _templates_fix(missing: list[str]) -> dict[str, str]:
    return {
        "action": FIX_TEMPLATES,
        "button": "Create the missing templates",
        "confirm": (f"Creates {len(missing)} email template(s) in the CRM with default "
                    f"wording: {', '.join(missing)}. Templates that exist are not touched. "
                    "Click again to create them."),
    }


def _zoom_fix(host: str) -> dict[str, str]:
    return {
        "action": FIX_ZOOM_SHARING,
        "button": "Set host-only sharing and co-host",
        "confirm": (f"Changes the Zoom user {host}: screen sharing on, Who can share? set "
                    "to Host Only, co-host on. This applies to every meeting that Zoom user "
                    "hosts, not only events. Click again to change it."),
    }


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
                "kinds refuses until they exist.", _templates_fix(missing))


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
                         "share.", _zoom_fix(account_host)))
    elif who == SHARE_HOST:
        rows.append(_row("Screen sharing", True, "host only"))
    elif who == SHARE_ALL:
        rows.append(_row("Screen sharing", False,
                         "all participants: any attendee can share their screen (ruling "
                         "EH11 wants host only).", _zoom_fix(account_host)))
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
                         "can share", _zoom_fix(account_host)))
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


# --- the fixes (item 3, ruling R2) -------------------------------------------------

#: Zoom's error when the app lacks a permission names it; this is what to add.
ZOOM_UPDATE_SCOPE = "user:update:settings:admin"


async def fix(action: str, settings: Any, *, admin_factory: Any = None,
              zoom: Any = None) -> dict[str, Any]:
    """Run one fix. ``{"ok": bool, "message": str}`` in words; never raises.
    Called only after the administrator's second click."""
    try:
        if action == FIX_TEMPLATES:
            return await _fix_templates(settings, admin_factory)
        if action == FIX_ZOOM_SHARING:
            return await _fix_zoom_sharing(settings, zoom)
        return {"ok": False, "message": f"There is no fix called {action!r}."}
    except Exception as exc:  # noqa: BLE001 — the page shows the reason, never a 500
        log.warning("readiness fix %s failed: %s", action, exc)
        return {"ok": False, "message": f"The fix failed: {exc}"}


async def _fix_templates(settings: Any, admin_factory: Any) -> dict[str, Any]:
    from core.admin_client import admin_client_factory

    from . import email_templates

    factory = admin_factory or admin_client_factory(settings)
    if factory is None:
        return {"ok": False, "message": (
            "Creating email templates needs a CRM administrator, and this deployment "
            "has no provisioning administrator (ESPO_PROVISION_USERNAME and "
            "ESPO_PROVISION_PASSWORD). Run scripts/seed_templates.sh instead.")}
    admin = await factory()
    result = await email_templates.create_missing(admin)
    if not result["created"]:
        return {"ok": True, "message": "All 8 templates were already there; nothing was created."}
    return {"ok": True, "message": (f"Created {len(result['created'])}: "
                                    f"{', '.join(result['created'])}. Edit their wording in "
                                    "the CRM under Email Templates.")}


async def _fix_zoom_sharing(settings: Any, zoom: Any) -> dict[str, Any]:
    from core.zoom import ZoomError

    host = hosting.zoom_host(settings, PRODUCT_MEETING)
    api = zoom or hosting.zoom_client(settings, PRODUCT_MEETING)
    if api is None or not host:
        return {"ok": False, "message": "Zoom Meetings is not switched on or not set up."}
    body = {"in_meeting": {"screen_sharing": True, "who_can_share_screen": SHARE_HOST,
                           "co_host": True}}
    try:
        await api.update_user_settings(host, body)
    except ZoomError as exc:
        text = str(exc)
        if exc.status_code in (400, 401, 403) and "scope" in text.lower():
            return {"ok": False, "message": (
                f"Zoom refused: the Zoom Meetings app lacks the permission "
                f"{ZOOM_UPDATE_SCOPE}. Add it on the app's Scopes page in Zoom's App "
                "Marketplace (Add Scopes), then click the button again.")}
        return {"ok": False, "message": f"Zoom refused the change: {text[:300]}"}
    after = (await api.get_user_settings(host) or {}).get("in_meeting") or {}
    if after.get("who_can_share_screen") == SHARE_HOST and after.get("co_host") is True \
            and after.get("screen_sharing") is not False:
        return {"ok": True, "message": (f"Done: {host} now has host-only screen sharing and "
                                        "co-host on, read back from Zoom.")}
    return {"ok": False, "message": (
        f"Zoom accepted the change but still reports who can share as "
        f"{after.get('who_can_share_screen')!r} and co-host as {after.get('co_host')!r}. "
        "The account's own settings may lock them: an account owner can change them in "
        "Zoom under Account Settings.")}
