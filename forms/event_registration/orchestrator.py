"""Event registration → EspoCRM (and Zoom).

Turns a website sign-up into:

1. a **Contact** — found by email, created as a Prospect if new, null-filled if
   existing (the info-request pattern);
2. a **CEventRegistration** linked to that Contact and the event;
3. a **Zoom registrant**, so Zoom emails the person their unique join link.

This is the step that ends the lead leak: today every registrant lands in Zoom
and a Google Sheet, and the CRM never hears about them.

Rules that are easy to get wrong, so they are stated here and tested:

* **An existing Contact keeps its type** (D-09). A client, mentor or partner who
  attends a webinar must not be relabelled "Prospect". Only brand-new Contacts
  get a type at all — ``cContactType`` is excluded from the null-fill.
* **Consent is only ever written as true** (D-19/EV-12). The opt-in keys are
  omitted entirely when the box wasn't ticked, so a previous opt-out is never
  flipped by a registration.
* **One registration per person per event** (EV-13). A repeat submit updates the
  existing row and re-issues the join link rather than creating a duplicate.
* **Capacity is evaluated at delivery**, not at accept (EV-15) — the seat may
  have gone while the submission sat in the queue. Over capacity ⇒ Waitlisted
  and NOT pushed to Zoom.
* **Zoom is best-effort.** A Zoom failure leaves a complete CRM record and is
  retried by the redrive path; it never loses the registration.

Delivery runs through the durable pipeline (capture → worker → here), so every
create is guarded by a named resumable step and a retry converges on one clean
set of records rather than duplicating them.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from core.crm_upsert import find_create_or_fill
from core.espo import EspoApi, EspoError
from core.phone import e164_or_none
from core.resumable import run_step_once
from events import config as cfg
from events import service as events_service

from .schemas import EventRegistration

log = logging.getLogger("cbm_intake.events.registration")

CONTACT = "Contact"

# Contact fields (custom fields on a native entity carry the ``c`` prefix).
C_CONTACT_TYPE = "cContactType"
C_MARKETING_OPT_IN = "cMarketingOptIn"
C_TERMS_ACCEPTED = "cTermsOfUseAccepted"
C_PRIVACY_ACCEPTED = "cPrivacyPolicyAccepted"
C_CODE_OF_CONDUCT = "cCodeOfConductAccepted"

PROSPECT = "Prospect"

#: Fields that may be null-filled on an EXISTING Contact. Deliberately excludes
#: ``cContactType`` (D-09 — never relabel someone for attending a webinar) and
#: the match key.
_CONTACT_FILL_KEYS = (
    "firstName", "lastName", "phoneNumber", "addressPostalCode",
    C_MARKETING_OPT_IN, C_TERMS_ACCEPTED, C_PRIVACY_ACCEPTED, C_CODE_OF_CONDUCT,
)


class RegistrationRefused(Exception):
    """A business refusal, not a system failure — the event is gone, cancelled,
    or closed. Surfaced to the visitor as a readable message; never retried."""


async def _find_event(client: EspoApi, slug: str) -> Optional[dict[str, Any]]:
    data = await client.list(
        cfg.EVENT,
        select=cfg.PUBLIC_SELECT,
        where=[{"type": "equals", "attribute": "slug", "value": slug}],
        max_size=1,
    )
    rows = data.get("list", [])
    return rows[0] if rows else None


async def check_open(client: EspoApi, slug: str) -> dict[str, Any]:
    """Pre-flight for the register endpoint: resolve the event and refuse
    plainly if it can't take a registration.

    Runs BEFORE durable capture so the visitor gets a real answer — with async
    delivery on, the HTTP response is sent long before the orchestrator runs, so
    a refusal raised at delivery time would never reach them.
    """
    event = await _find_event(client, slug)
    if event is None or not event.get("publishToWebsite"):
        raise RegistrationRefused("That event could not be found.")
    if event.get("status") == cfg.STATUS_CANCELLED:
        raise RegistrationRefused("That event has been cancelled.")
    if not events_service.registration_open(event):
        raise RegistrationRefused(
            "Registration for that event has closed. Please check the calendar "
            "for upcoming sessions."
        )
    return event


async def _existing_registration(
    client: EspoApi, event_id: str, email: str
) -> Optional[dict[str, Any]]:
    """The person's existing registration for this event, if any (EV-13)."""
    data = await client.list(
        cfg.REGISTRATION,
        select=cfg.REGISTRATION_SELECT,
        where=[
            {"type": "equals", "attribute": "eventId", "value": event_id},
            {"type": "equals", "attribute": "email", "value": email},
        ],
        max_size=1,
    )
    rows = data.get("list", [])
    return rows[0] if rows else None


async def _seat_status(
    client: EspoApi, event: dict[str, Any], *, excluding_id: Optional[str] = None
) -> str:
    """``Registered`` or ``Waitlisted``, decided against live seat usage.

    Evaluated here rather than at accept time because the queue can be minutes
    behind on a busy launch — the last seat may already be gone.
    """
    capacity = event.get("venueCapacity")
    if not capacity or capacity <= 0:
        return cfg.REG_REGISTERED
    rows = await events_service.list_registrations(client, event["id"])
    taken = sum(
        1 for r in rows
        if r.get("attendanceStatus") in cfg.SEAT_TAKING and r.get("id") != excluding_id
    )
    return cfg.REG_REGISTERED if taken < capacity else cfg.REG_WAITLISTED


def _contact_payload(sub: EventRegistration, *, is_new: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "firstName": sub.first_name,
        "lastName": sub.last_name or "",
        "emailAddress": str(sub.email),
    }
    if is_new:
        # Only a brand-new Contact gets a type. An existing one keeps whatever
        # it already is (D-09).
        payload[C_CONTACT_TYPE] = [PROSPECT]
    phone = e164_or_none(sub.phone)
    if phone:
        payload["phoneNumber"] = phone
    if sub.zip_code:
        payload["addressPostalCode"] = sub.zip_code
    if sub.consent:
        # Written as true only — omitted entirely when unticked, so a prior
        # opt-out is never flipped (EV-12).
        payload[C_MARKETING_OPT_IN] = True
        payload[C_TERMS_ACCEPTED] = True
        payload[C_PRIVACY_ACCEPTED] = True
        payload[C_CODE_OF_CONDUCT] = True
    return payload


async def _push_to_zoom(
    settings: Any, client: EspoApi, event: dict[str, Any],
    registration_id: str, sub: EventRegistration,
) -> dict[str, Any]:
    """Register the person with Zoom so Zoom emails them the join link.

    Best-effort: a failure leaves a complete CRM record, logs, and is picked up
    by a redrive. Nothing about the registration depends on it succeeding.
    """
    webinar_id = (event.get("zoomWebinarId") or "").strip()
    if not webinar_id:
        return {"ok": False, "reason": "the event has no Zoom webinar"}
    try:
        from core.zoom import make_client

        api = make_client(settings)
        if api is None:
            return {"ok": False, "reason": "Zoom is not enabled"}
        result = await api.add_registrant(
            webinar_id,
            email=str(sub.email),
            first_name=sub.first_name,
            last_name=sub.last_name or "",
            phone=e164_or_none(sub.phone) or "",
            zip_code=sub.zip_code or "",
        )
        updates = {
            "zoomRegistrantId": str(result.get("registrant_id") or ""),
            "zoomJoinUrl": result.get("join_url") or "",
        }
        await client.update(cfg.REGISTRATION, registration_id, updates)
        return {"ok": True, **updates}
    except Exception as exc:  # noqa: BLE001 — never lose a registration to Zoom
        log.warning("registration %s: Zoom push failed: %s", registration_id, exc)
        return {"ok": False, "error": str(exc)}


async def deliver(
    sub: EventRegistration, client: EspoApi, *, settings: Any = None
) -> dict[str, Any]:
    """Create the Contact + registration, then push to Zoom."""
    event = await _find_event(client, sub.event_slug)
    if event is None:
        # Permanent: no retry will conjure the event. Surfaces in /ops as
        # needs_attention with this message.
        raise RegistrationRefused(
            f"No event exists with the slug {sub.event_slug!r}."
        )

    email = str(sub.email)
    existing_contact = await client.find_one(
        CONTACT, "emailAddress", email, select="id"
    )
    contact_id, action = await find_create_or_fill(
        client, CONTACT,
        match_attr="emailAddress", match_value=email,
        create_payload=_contact_payload(sub, is_new=existing_contact is None),
        fill_keys=_CONTACT_FILL_KEYS,
    )

    existing = await _existing_registration(client, event["id"], email)
    status = await _seat_status(
        client, event, excluding_id=existing.get("id") if existing else None
    )

    name = f"{event.get('name') or 'Event'} — {sub.first_name} {sub.last_name or ''}".strip()
    payload: dict[str, Any] = {
        "name": name[:255],
        "eventId": event["id"],
        "contactId": contact_id,
        "email": email,
        "firstName": sub.first_name,
        "lastName": sub.last_name or "",
        "registrationSource": cfg.SOURCE_ONLINE,
        "marketingOptIn": bool(sub.consent),
    }

    if existing:
        registration_id = existing["id"]
        updates = dict(payload)
        # A cancelled registrant who signs up again is reinstated; anyone
        # already attended/no-showed keeps that history.
        if existing.get("attendanceStatus") in (None, "", cfg.REG_REGISTERED,
                                                cfg.REG_WAITLISTED, cfg.REG_CANCELLED):
            updates["attendanceStatus"] = status
        await run_step_once(
            client, "update-registration",
            lambda: client.update(cfg.REGISTRATION, registration_id, updates),
        )
        outcome = "updated"
    else:
        payload["attendanceStatus"] = status
        payload["registrationDate"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        created = await client.create(cfg.REGISTRATION, payload)
        registration_id = created["id"]
        outcome = "created"

    ids: dict[str, Any] = {
        "contactId": contact_id,
        "contactAction": action,
        "eventId": event["id"],
        "eventRegistrationId": registration_id,
        "registrationStatus": status,
        "outcome": outcome,
    }

    if status == cfg.REG_REGISTERED:
        zoom_result = await _push_to_zoom(
            settings, client, event, registration_id, sub
        )
        ids["zoom"] = zoom_result
    else:
        # A waitlisted person must NOT get a Zoom join link — they have no seat.
        ids["zoom"] = {"ok": False, "reason": "waitlisted"}

    log.info(
        "event registration %s for event %s (%s, %s)",
        registration_id, event["id"], status, outcome,
    )
    return ids


async def orchestrate(sub: EventRegistration, client: EspoApi) -> dict[str, Any]:
    """The registry entry point (settings come from the process config)."""
    from core.config import get_settings

    return await deliver(sub, client, settings=get_settings())
