"""Zoom reconciliation for event saves — Zoom Webinars and Zoom Meetings.

One entry point — :func:`sync_event_webinar` — decides what the saved state of a
``CEvent`` implies for Zoom and does it. Which Zoom product, if any, is the
event's hosting method (``events/hosting.py``, plan
``prds/events/event-hosting-plan.md``):

===============================  ==========================================
Saved state                      Action
===============================  ==========================================
on a Zoom method, shown, no id   **create** the webinar or meeting, persist id + URLs
on a Zoom method, has id         **patch** it, only if something material changed
moved between the Zoom products  **replace**: cancel the old one, create the new
status Cancelled, has id         **cancel** it and clear the stored id
in-person                        skip — nothing to provision
members-only, not Zoom Meetings  skip — webinars are for Public events (D2)
not shown                        skip, unless the staff action forces it
already-linked id supplied       adopt it (EV-23) rather than creating a second
outside host or other platform,  **cancel** it, keeping a link the same save typed
has id
outside host or other platform,  skip — someone else's platform
no id
===============================  ==========================================

The one id field serves both products (``zoomWebinarId``; handoff
``cevent-hosting-method-crm-handoff.md``). The product an EXISTING id belongs
to is the method the record held before this save (``hosting.stored_product``
of ``previous``), so moving an event from webinars to meetings cancels the
webinar with the webinars client. The editor refuses that move once anyone has
registered (EH4, ``service._refuse_method_change_with_registrants``).

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
from core.branding import abbr

import logging
from datetime import datetime
from typing import Any, Optional

from core.zoom import PRODUCT_MEETING, PRODUCT_WEBINAR, ZoomClient, ZoomError

from . import config as cfg
from . import hosting
from . import visibility
from . import service

log = logging.getLogger("cbm_intake.events.zoom")

#: A save only touches an existing webinar when one of these changed. Notes,
#: topic category, capacity and publishing state are ours alone — patching Zoom
#: for them would be pointless traffic and, worse, can trigger Zoom's own
#: "the host updated this event" mail to every registrant.
MATERIAL_FIELDS = ("name", "dateStart", "dateEnd", "duration", "description")
#: A members-only meeting also changes when "Takes registrations" does: Zoom's
#: registration is switched to match.
MEETING_MATERIAL_FIELDS = MATERIAL_FIELDS + (cfg.TAKES_REGISTRATIONS_FIELD,)


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


def _material_change(
    event: dict[str, Any], previous: Optional[dict[str, Any]], *,
    fields: tuple[str, ...] = MATERIAL_FIELDS,
) -> bool:
    if previous is None:
        return True  # no baseline to compare against - assume it moved
    return any(event.get(f) != previous.get(f) for f in fields)


def existing_product(
    event: dict[str, Any], previous: Optional[dict[str, Any]] = None
) -> str:
    """The product the event's stored Zoom id belongs to, or "" with no id."""
    if not (event.get("zoomWebinarId") or "").strip():
        return ""
    return hosting.stored_product(previous if previous is not None else event)


def decide(
    event: dict[str, Any],
    *,
    previous: Optional[dict[str, Any]] = None,
    force: bool = False,
) -> tuple[str, str]:
    """What should happen in Zoom for this event? ``(action, reason)``.

    Pure — no I/O — so the whole matrix is testable without a Zoom account, and
    so the staff app can preview the consequence of a save before making it.
    Actions: ``create``, ``patch``, ``replace``, ``cancel``, ``skip``.
    """
    webinar_id = (event.get("zoomWebinarId") or "").strip()
    noun = "Zoom event" if webinar_id else "webinar"
    if webinar_id:
        noun = ("meeting" if existing_product(event, previous) == PRODUCT_MEETING
                else "webinar")

    if event.get("status") == cfg.STATUS_CANCELLED:
        return ("cancel", "the event is cancelled") if webinar_id else (
            "skip", f"the event is cancelled and has no {noun}")

    if not hosting.is_online(event):
        # An in-person event that USED to be online keeps a stale webinar
        # otherwise - cancel it so registrants aren't sent to a dead room.
        return ("cancel", "the event is no longer online") if webinar_id else (
            "skip", "in-person events have no webinar")

    method = hosting.method(event)
    # D3-3 and EH3: an event on someone else's platform is never ours to
    # provision. A Zoom event made before the switch is cancelled (the editor
    # refuses the switch while anyone is registered); otherwise nothing to do.
    if method in (hosting.OUTSIDE, hosting.OTHER):
        why = ("the event is run by an outside host" if method == hosting.OUTSIDE
               else "the event is hosted on another platform")
        return ("cancel", why) if webinar_id else ("skip", why)

    product = hosting.zoom_product(event)

    if not event.get("dateStart"):
        return "skip", "the event has no start time yet"

    if webinar_id:
        had = existing_product(event, previous)
        if product and product != had:
            return ("replace",
                    f"the event moved from {hosting.product_name(had)} to "
                    f"{hosting.product_name(product)}")
        fields = MEETING_MATERIAL_FIELDS if had == PRODUCT_MEETING else MATERIAL_FIELDS
        if _material_change(event, previous, fields=fields):
            return "patch", "the title, time or description changed"
        return "skip", "nothing material changed"

    # Doug's ruling D2 (F2/F3 design): webinars are for PUBLIC events only —
    # the account is the public programme's. Even a forced create respects it.
    # Keyed on an audience someone actually SET (``hosting.members_only``): an
    # event from before the field has none, and a staff member forcing a
    # webinar for an unticked draft of the programme keeps the behaviour they
    # had. An existing webinar on an event that later turns Internal is left
    # alone above, so a mistaken audience change cannot cancel real
    # registrants. A members-only event on Zoom Meetings is the exception
    # (Doug, 11-17-26, option B).
    if not product:
        return "skip", ("Zoom webinars are for Public events only; a members-only "
                        "event gets a Zoom event only on Zoom Meetings")

    if not (visibility.is_ticked(event) or force):
        return "skip", "the event is not shown (\u201cShow this event\u201d is off)"

    return "create", (f"the event is shown and has no "
                      f"{'meeting' if product == PRODUCT_MEETING else 'webinar'} yet")


async def sync_event_webinar(
    settings: Any,
    client: Any,
    event: dict[str, Any],
    *,
    previous: Optional[dict[str, Any]] = None,
    force: bool = False,
    zoom: Optional[ZoomClient] = None,
) -> dict[str, Any]:
    """Reconcile one event's Zoom webinar or meeting with its saved state.

    ``client`` is the CRM client used to write the id back. ``zoom`` is a
    test-injection seam that serves both products. Mutates ``event`` in place
    on success so the caller's response reflects the final record without a
    re-read.
    """
    try:
        action, reason = decide(event, previous=previous, force=force)
        had = existing_product(event, previous)
        product = hosting.zoom_product(event)
        # The product this save talks to first: the existing id's, else the
        # one a create needs. None at all: nothing of Zoom's is involved.
        first = had or product
        if not first:
            return {"ok": True, "action": "skipped", "reason": reason}

        def api_for(p: str) -> Any:
            return zoom or hosting.zoom_client(settings, p)

        api = api_for(first)
        if api is None:
            return {"ok": False, "disabled": True, "product": first,
                    "reason": hosting.not_ready_reason(first)}
        host = hosting.zoom_host(settings, product or first)
        if action in ("create", "replace") and not host:
            return {"ok": False, "disabled": True, "product": product,
                    "reason": "no Zoom host account is configured"}

        if action == "skip":
            return {"ok": True, "action": "skipped", "reason": reason}
        if action == "create":
            return await _create(settings, client, event, api, host, reason, product)
        if action == "patch":
            return await _patch(event, api, reason, had)
        if action == "cancel":
            return await _cancel(client, event, api, reason, had, previous)
        if action == "replace":
            new_api = api_for(product)
            if new_api is None:
                return {"ok": False, "disabled": True, "product": product,
                        "reason": hosting.not_ready_reason(product)}
            cancelled = await _cancel(client, event, api, reason, had, previous)
            if not cancelled.get("ok") or (event.get("zoomWebinarId") or "").strip():
                return {**cancelled, "action": "cancelled",
                        "warning": "The old Zoom event was cancelled but its id is still "
                                   "on the record, so no new one was made. Save the "
                                   "event again."}
            created = await _create(settings, client, event, new_api, host, reason, product)
            return {**created, "replaced": had}
        return {"ok": True, "action": "skipped", "reason": reason}  # pragma: no cover
    except Exception as exc:  # noqa: BLE001 — the event save must stand regardless
        log.warning("Zoom sync failed for event %s: %s", event.get("id"), exc)
        return {"ok": False, "error": str(exc)}


async def _create(
    settings: Any, client: Any, event: dict[str, Any], api: ZoomClient,
    host: str, reason: str, product: str = PRODUCT_WEBINAR,
) -> dict[str, Any]:
    start = service.parse_crm_datetime(event.get("dateStart"))
    if start is None:
        return {"ok": False, "error": "the event start time could not be read"}

    meeting = product == PRODUCT_MEETING
    common = dict(
        topic=event.get("name") or f"{abbr()} Workshop",
        start=start,
        duration_minutes=_duration_minutes(event),
        agenda=(event.get("description") or "").strip(),
        timezone_name=cfg.PUBLIC_TIMEZONE,
    )
    if meeting:
        created = await api.create_meeting(
            host, registration=hosting.zoom_registration(event), **common)
    else:
        created = await api.create_webinar(host, **common)
    webinar_id = str(created.get("id") or "").strip()
    if not webinar_id:
        return {"ok": False,
                "error": f"Zoom did not return a {'meeting' if meeting else 'webinar'} id"}

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
            if meeting:
                await api.delete_meeting(webinar_id, notify_registrants=False)
            else:
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
    log.info("event %s: created Zoom %s %s", event.get("id"),
             "meeting" if meeting else "webinar", webinar_id)
    return {
        "ok": True, "action": "created", "reason": reason, "product": product,
        "webinarId": webinar_id,
        "joinUrl": updates["virtualMeetingUrl"],
        "registrationUrl": updates["registrationUrl"],
    }


async def _patch(
    event: dict[str, Any], api: ZoomClient, reason: str,
    product: str = PRODUCT_WEBINAR,
) -> dict[str, Any]:
    start = service.parse_crm_datetime(event.get("dateStart"))
    common = dict(
        topic=event.get("name") or None,
        start=start,
        duration_minutes=_duration_minutes(event),
        agenda=(event.get("description") or "").strip(),
    )
    if product == PRODUCT_MEETING:
        await api.update_meeting(event["zoomWebinarId"],
                                 registration=hosting.zoom_registration(event), **common)
    else:
        await api.update_webinar(event["zoomWebinarId"], **common)
    return {"ok": True, "action": "patched", "reason": reason, "product": product,
            "webinarId": event["zoomWebinarId"]}


async def _cancel(
    client: Any, event: dict[str, Any], api: ZoomClient, reason: str,
    product: str = PRODUCT_WEBINAR, previous: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    webinar_id = event["zoomWebinarId"]
    if product == PRODUCT_MEETING:
        await api.delete_meeting(webinar_id, notify_registrants=True)
    else:
        await api.delete_webinar(webinar_id, notify_registrants=True)
    # Clear our side so a later re-publish creates a fresh webinar rather than
    # patching one Zoom has already forgotten. An Outside host's link is the
    # host's, and an Other platform's the shared one, saved a moment ago by
    # the same edit: never ours to clear (D3-3, EH3) — unless the save left it
    # exactly as it was, when it is still Zoom's link to the event just
    # cancelled.
    updates = {"zoomWebinarId": "", "virtualMeetingUrl": "", "registrationUrl": ""}
    if hosting.method(event) in (hosting.OUTSIDE, hosting.OTHER):
        typed = (event.get("virtualMeetingUrl") or "").strip()
        unchanged = previous is not None and typed == (
            previous.get("virtualMeetingUrl") or "").strip()
        if typed and not unchanged:
            del updates["virtualMeetingUrl"]
    try:
        await client.update(cfg.EVENT, event["id"], updates)
        event.update(updates)
    except Exception as exc:  # noqa: BLE001 — the webinar IS cancelled; say so
        log.warning("event %s: webinar %s cancelled but the id could not be "
                    "cleared (%s)", event.get("id"), webinar_id, exc)
        return {"ok": True, "action": "cancelled", "reason": reason,
                "warning": "The webinar was cancelled but the event record still "
                           "shows its id. Saving the event again will clear it."}
    log.info("event %s: cancelled Zoom %s %s", event.get("id"),
             "meeting" if product == PRODUCT_MEETING else "webinar", webinar_id)
    return {"ok": True, "action": "cancelled", "reason": reason, "product": product}


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
        # The event's own method says which product the id is (a members-only
        # event not on Zoom Meetings adopts a webinar, as before).
        product = hosting.zoom_product(event) or PRODUCT_WEBINAR
        api = zoom or hosting.zoom_client(settings, product)
        if api is None:
            return {"ok": False, "disabled": True,
                    "reason": hosting.not_ready_reason(product)}
        webinar_id = str(webinar_id).strip().replace(" ", "")
        if not webinar_id:
            return {"ok": False, "error": "No webinar id was supplied."}
        if product == PRODUCT_MEETING:
            found = await api.get_meeting(webinar_id)
        else:
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
