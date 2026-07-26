"""Zoom reconciliation for event saves.

One entry point — :func:`sync_event_webinar` — decides what the saved state of a
``CEvent`` implies for Zoom and does it:

===========================  ==========================================
Saved state                  Action
===========================  ==========================================
online, published, no id     **create** the webinar, persist id + URLs
online, published, has id    **patch** it, but only if something material changed
status Cancelled, has id     **cancel** it and clear the stored id
in-person                    skip — nothing to provision
not published                skip, unless the staff action forces it
already-linked id supplied   adopt it (EV-23) rather than creating a second
===========================  ==========================================

**Best-effort by design** (the gcal / mentoradmin-provision precedent): this
module NEVER raises. The event save has already happened; Zoom being down,
misconfigured or slow must not undo it. Every call returns ``{"ok": bool, ...}``
which the router carries back as ``event["zoom"]`` for the UI to show as a
non-blocking notice, and which the worker can retry later.

**Persist-before-invite** (the v0.86.0 calendar lesson): the webinar id is
written to the CRM immediately after creation, before anything else can fail.
If that write fails we delete the webinar we just made rather than leave an
orphan that nobody can find, cancel, or push registrants to.

Inert until ``ZOOM_EVENTS=true`` and the Server-to-Server OAuth credentials are
set, so the feature deploys safely ahead of the Zoom app existing.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from core.zoom import ZoomClient, ZoomError, make_client

from . import config as cfg
from . import service

log = logging.getLogger("cbm_intake.events.zoom")

#: A save only touches an existing webinar when one of these changed. Notes,
#: topic category, capacity and publishing state are ours alone — patching Zoom
#: for them would be pointless traffic and, worse, can trigger Zoom's own
#: "the host updated this event" mail to every registrant.
MATERIAL_FIELDS = ("name", "dateStart", "dateEnd", "duration", "description")


def _duration_minutes(event: dict[str, Any]) -> int:
    """CRM stores seconds (EspoCRM's duration type); Zoom wants minutes."""
    seconds = event.get("duration")
    if not seconds:
        start = service.parse_crm_datetime(event.get("dateStart"))
        end = service.parse_crm_datetime(event.get("dateEnd"))
        seconds = int((end - start).total_seconds()) if (start and end) else 3600
    return max(1, round(int(seconds) / 60))


def is_online(event: dict[str, Any]) -> bool:
    return event.get("format") in cfg.ONLINE_FORMATS


def _material_change(event: dict[str, Any], previous: Optional[dict[str, Any]]) -> bool:
    if previous is None:
        return True  # no baseline to compare against - assume it moved
    return any(event.get(f) != previous.get(f) for f in MATERIAL_FIELDS)


def decide(
    event: dict[str, Any],
    *,
    previous: Optional[dict[str, Any]] = None,
    force: bool = False,
) -> tuple[str, str]:
    """What should happen in Zoom for this event? ``(action, reason)``.

    Pure — no I/O — so the whole matrix is testable without a Zoom account, and
    so the staff app can preview the consequence of a save before making it.
    """
    webinar_id = (event.get("zoomWebinarId") or "").strip()

    if event.get("status") == cfg.STATUS_CANCELLED:
        return ("cancel", "the event is cancelled") if webinar_id else (
            "skip", "the event is cancelled and has no webinar")

    if not is_online(event):
        # An in-person event that USED to be online keeps a stale webinar
        # otherwise - cancel it so registrants aren't sent to a dead room.
        return ("cancel", "the event is no longer online") if webinar_id else (
            "skip", "in-person events have no webinar")

    if not event.get("dateStart"):
        return "skip", "the event has no start time yet"

    if webinar_id:
        if _material_change(event, previous):
            return "patch", "the title, time or description changed"
        return "skip", "nothing material changed"

    if not (event.get("publishToWebsite") or force):
        return "skip", "the event is not published to the website"

    return "create", "the event is published and has no webinar yet"


async def sync_event_webinar(
    settings: Any,
    client: Any,
    event: dict[str, Any],
    *,
    previous: Optional[dict[str, Any]] = None,
    force: bool = False,
    zoom: Optional[ZoomClient] = None,
) -> dict[str, Any]:
    """Reconcile one event's Zoom webinar with its saved state.

    ``client`` is the CRM client used to write the webinar id back. ``zoom`` is
    a test-injection seam. Mutates ``event`` in place on success so the caller's
    response reflects the final record without a re-read.
    """
    try:
        api = zoom or make_client(settings)
        if api is None:
            return {"ok": False, "disabled": True,
                    "reason": "Zoom is not enabled or not configured"}

        host = (getattr(settings, "zoom_host_email", "") or "").strip()
        if not host:
            return {"ok": False, "disabled": True,
                    "reason": "no Zoom host account is configured"}

        action, reason = decide(event, previous=previous, force=force)
        if action == "skip":
            return {"ok": True, "action": "skipped", "reason": reason}
        if action == "create":
            return await _create(settings, client, event, api, host, reason)
        if action == "patch":
            return await _patch(event, api, reason)
        if action == "cancel":
            return await _cancel(client, event, api, reason)
        return {"ok": True, "action": "skipped", "reason": reason}  # pragma: no cover
    except Exception as exc:  # noqa: BLE001 — the event save must stand regardless
        log.warning("Zoom sync failed for event %s: %s", event.get("id"), exc)
        return {"ok": False, "error": str(exc)}


async def _create(
    settings: Any, client: Any, event: dict[str, Any], api: ZoomClient,
    host: str, reason: str,
) -> dict[str, Any]:
    start = service.parse_crm_datetime(event.get("dateStart"))
    if start is None:
        return {"ok": False, "error": "the event start time could not be read"}

    created = await api.create_webinar(
        host,
        topic=event.get("name") or "CBM Workshop",
        start=start,
        duration_minutes=_duration_minutes(event),
        agenda=(event.get("description") or "").strip(),
        timezone_name=cfg.PUBLIC_TIMEZONE,
    )
    webinar_id = str(created.get("id") or "").strip()
    if not webinar_id:
        return {"ok": False, "error": "Zoom did not return a webinar id"}

    updates = {
        "zoomWebinarId": webinar_id,
        "virtualMeetingUrl": created.get("join_url") or "",
        "registrationUrl": created.get("registration_url") or "",
    }
    try:
        await client.update(cfg.EVENT, event["id"], updates)
    except Exception as exc:  # noqa: BLE001
        # Persist-before-anything-else: an unrecorded webinar is invisible to
        # the app forever, so undo it rather than orphan it.
        log.warning(
            "event %s: webinar %s created but the id could not be saved (%s) — "
            "deleting it to avoid an orphan", event.get("id"), webinar_id, exc,
        )
        try:
            await api.delete_webinar(webinar_id, notify_registrants=False)
        except ZoomError as cleanup_exc:
            log.error(
                "event %s: ORPHANED Zoom webinar %s — created but neither saved "
                "nor deleted (%s). Cancel it by hand in Zoom.",
                event.get("id"), webinar_id, cleanup_exc,
            )
            return {"ok": False, "error": str(exc), "orphanedWebinarId": webinar_id}
        return {"ok": False, "error": str(exc)}

    event.update(updates)
    log.info("event %s: created Zoom webinar %s", event.get("id"), webinar_id)
    return {
        "ok": True, "action": "created", "reason": reason,
        "webinarId": webinar_id,
        "joinUrl": updates["virtualMeetingUrl"],
        "registrationUrl": updates["registrationUrl"],
    }


async def _patch(
    event: dict[str, Any], api: ZoomClient, reason: str
) -> dict[str, Any]:
    start = service.parse_crm_datetime(event.get("dateStart"))
    await api.update_webinar(
        event["zoomWebinarId"],
        topic=event.get("name") or None,
        start=start,
        duration_minutes=_duration_minutes(event),
        agenda=(event.get("description") or "").strip(),
    )
    return {"ok": True, "action": "patched", "reason": reason,
            "webinarId": event["zoomWebinarId"]}


async def _cancel(
    client: Any, event: dict[str, Any], api: ZoomClient, reason: str
) -> dict[str, Any]:
    webinar_id = event["zoomWebinarId"]
    await api.delete_webinar(webinar_id, notify_registrants=True)
    # Clear our side so a later re-publish creates a fresh webinar rather than
    # patching one Zoom has already forgotten.
    updates = {"zoomWebinarId": "", "virtualMeetingUrl": "", "registrationUrl": ""}
    try:
        await client.update(cfg.EVENT, event["id"], updates)
        event.update(updates)
    except Exception as exc:  # noqa: BLE001 — the webinar IS cancelled; say so
        log.warning("event %s: webinar %s cancelled but the id could not be "
                    "cleared (%s)", event.get("id"), webinar_id, exc)
        return {"ok": True, "action": "cancelled", "reason": reason,
                "warning": "The webinar was cancelled but the event record still "
                           "shows its id. Saving the event again will clear it."}
    log.info("event %s: cancelled Zoom webinar %s", event.get("id"), webinar_id)
    return {"ok": True, "action": "cancelled", "reason": reason}


async def adopt_existing_webinar(
    settings: Any, client: Any, event: dict[str, Any], webinar_id: str,
    *, zoom: Optional[ZoomClient] = None,
) -> dict[str, Any]:
    """Link an event to a webinar created directly in Zoom (EV-23).

    Also the migration path for anything already scheduled at cutover. Verifies
    the webinar exists before storing the id, so a typo fails loudly here rather
    than silently breaking registration later.
    """
    try:
        api = zoom or make_client(settings)
        if api is None:
            return {"ok": False, "disabled": True,
                    "reason": "Zoom is not enabled or not configured"}
        webinar_id = str(webinar_id).strip().replace(" ", "")
        if not webinar_id:
            return {"ok": False, "error": "No webinar id was supplied."}
        found = await api.get_webinar(webinar_id)
        updates = {
            "zoomWebinarId": str(found.get("id") or webinar_id),
            "virtualMeetingUrl": found.get("join_url") or "",
            "registrationUrl": found.get("registration_url") or "",
        }
        await client.update(cfg.EVENT, event["id"], updates)
        event.update(updates)
        return {"ok": True, "action": "linked", "webinarId": updates["zoomWebinarId"],
                "topic": found.get("topic") or ""}
    except Exception as exc:  # noqa: BLE001
        log.warning("event %s: could not link webinar %s: %s",
                    event.get("id"), webinar_id, exc)
        return {"ok": False, "error": str(exc)}
