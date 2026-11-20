"""The event feedback survey from Event Administration's Follow-up tab
(decision 3, A; decision 7, 11-20-26).

While ``FEEDBACK_SURVEYS`` is on, the Survey card sends each attendee their
own feedback link from the shared mailbox, with the approved wording, in
place of the ``EventSurvey`` template. It keeps the card's preview-then-send
and returns the result the card already draws (``recipients``, ``skipped``,
``sent``, ``errors``, ``dryRun``, ``warning``).

* **Attendees only** (registrations marked Attended).
* **No marketing opt-in needed** (decision 7): an address the CRM marks as
  opted out of email is still skipped, as is a CBM member.
* **The same moment as the sweep's**: the send key is
  ``event:<event id>:<registration id>``, so a person sent the survey by the
  card is never sent it again by the sweep, nor the other way round.
* **The quiet period does not apply**: a send by hand always goes (BE33).
* The registration's ``followUpsSent`` ledger gains Survey, as the template
  send did, so the Registrants tab's Emails column shows it.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from zoneinfo import ZoneInfo

from . import config as cfg
from .moments import parse_crm
from .sending import Sender, contact_recipient, send, skip_reason, utcnow

log = logging.getLogger("cbm_intake.feedback")


def send_key(event_id: str, registration_id: str) -> str:
    return f"event:{event_id}:{registration_id}"


async def _recipient(client: Any, reg: dict[str, Any]) -> dict[str, Any]:
    who = await contact_recipient(client, reg.get("contactId") or "")
    if (reg.get("email") or "").strip():
        who["email"] = reg["email"].strip()
    who["firstName"] = who.get("firstName") or reg.get("firstName") or ""
    who["name"] = who.get("name") or " ".join(
        p for p in (reg.get("firstName"), reg.get("lastName")) if p)
    return who


async def follow_up_survey(settings: Any, client: Any, event: dict[str, Any], *,
                           store: Any, survey_store: Any, surveys: dict[str, Any],
                           registrations: list[dict[str, Any]], dry_run: bool,
                           created_by: str = "", sender: Optional[Sender] = None,
                           record_sent: Any = None) -> dict[str, Any]:
    """Preview or send the event feedback survey to an event's attendees."""
    now = utcnow()
    result: dict[str, Any] = {
        "kind": "Survey", "template": "(the feedback survey's own email)",
        "eventId": event.get("id"), "recipients": [], "skipped": [], "sent": 0,
        "errors": [], "dryRun": dry_run, "warning": None,
    }
    attended = [r for r in registrations
                if (r.get("attendanceStatus") or "") == cfg.REG_ATTENDED]
    if not attended:
        result["warning"] = ("Nobody is marked Attended on this event yet, so nobody would "
                             "receive the survey. Mark attendance first.")
    if store is None or survey_store is None or not surveys:
        result["errors"].append("Feedback surveys cannot be sent from this server "
                                "(no database or no survey definitions).")
        return result
    tz = ZoneInfo(getattr(settings, "sms_timezone", "") or "America/New_York")
    start = parse_crm(event.get("dateStart"))
    context = {"eventName": event.get("name") or "",
               "eventDate": start.astimezone(tz) if start else None}
    for reg in attended:
        who = await _recipient(client, reg)
        name = who.get("name") or who.get("email") or "(no name)"
        key = send_key(event["id"], reg["id"])
        prior = await store.get(key)
        if prior and prior.get("outcome") == "sent":
            result["skipped"].append({"email": who.get("email"), "name": name,
                                      "reason": "already sent the survey"})
            continue
        reason = await skip_reason(settings, store, who, quiet=False, now=now)
        if reason:
            result["skipped"].append({"email": who.get("email"), "name": name, "reason": reason})
            continue
        result["recipients"].append({"email": who.get("email"), "name": name})
        if dry_run:
            continue
        outcome = await send(
            settings, store=store, survey_store=survey_store, surveys=surveys, send_key=key,
            survey_key=cfg.SURVEY_EVENT, moment=cfg.MOMENT_EVENT, entity_type=cfg.EVENT,
            record_id=event["id"], who=who, data={"event_id": event["id"]},
            display_name=event.get("name") or "", context=context, quiet=False,
            created_by=created_by or "Event Administration", sender=sender, now=now)
        if outcome == "sent":
            result["sent"] += 1
            if record_sent is not None:
                try:
                    await record_sent(client, reg, "Survey")
                except Exception as exc:  # noqa: BLE001 — the send itself stands
                    log.warning("feedback: Survey ledger not written on %s: %s", reg["id"], exc)
        elif outcome != "already":
            result["errors"].append(f"{who.get('email')}: {outcome.replace('skipped:', 'skipped, ')}")
    return result
