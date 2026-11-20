"""Sending a feedback survey: the recipient, the quiet period, the link and
the email (rulings BE30, BE33; decisions 3, 5 and 7, 11-20-26).

One function, ``send``, serves every send: the four automatic moments (from
the sweep, ``moments.py``) and a staff member's on-demand send. It:

1. claims the moment in ``feedback_send`` (never twice);
2. skips, recording why, a person with no address, a CBM member, an address
   the CRM marks as opted out of email, or (for an automatic send other than
   the closing survey) an address sent any feedback survey in the quiet
   period;
3. makes the person's own link in the survey engine's store;
4. emails it from the shared mailbox (``OPS_MAILBOX``).

A mentor's on-demand send (``prepare_for_composer``) makes the link and the
``feedback_send`` row the same way, and returns the email for the mentor's
composer instead of sending it: the mentor sends it from their own mailbox.

Nothing here raises to a caller that must not fail: ``send`` returns one
word saying what happened.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from core.espo import EspoError

from . import config as cfg
from . import email as fb_email
from .store import FAILED, SENT, SKIPPED, norm_email

log = logging.getLogger("cbm_intake.feedback")

CREATED_BY_SWEEP = "feedback sweep"

Sender = Callable[[Any, list[str], str, str], Awaitable[None]]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def link_url(base: str, token: str) -> str:
    return f"{(base or '').rstrip('/')}/survey/{token}"


async def send_shared(settings: Any, to: list[str], subject: str, body_html: str) -> None:
    """Send from the shared mailbox, as the intake survey does."""
    from comms import service as comms_service

    gmail = await comms_service.gmail_for_shared_mailbox(settings, settings.ops_mailbox)
    try:
        await comms_service.send_quick_message(
            gmail=gmail, to=to, subject=subject, body_html=body_html,
            sender_name=settings.sender_display_name)
    finally:
        await gmail.aclose()


# --- the recipient ----------------------------------------------------------------

async def contact_recipient(client: Any, contact_id: str) -> dict[str, Any]:
    """A Contact as a recipient: address, first name, name, whether the CRM
    marks the address as opted out, and the contact's types. Empty values
    when it cannot be read."""
    blank = {"contactId": contact_id or "", "email": "", "firstName": "", "name": "",
             "optedOut": False, "types": []}
    if not contact_id:
        return blank
    try:
        c = await client.get(cfg.CONTACT, contact_id, select=(
            "name,firstName,emailAddress,emailAddressIsOptedOut,cContactType"))
    except EspoError as exc:
        log.warning("feedback: contact %s not read: %s", contact_id, exc)
        return blank
    types = c.get("cContactType") or []
    return {"contactId": contact_id, "email": c.get("emailAddress") or "",
            "firstName": c.get("firstName") or "", "name": c.get("name") or "",
            "optedOut": bool(c.get("emailAddressIsOptedOut")),
            "types": types if isinstance(types, list) else [types]}


def is_member(settings: Any, who: dict[str, Any]) -> bool:
    """A CBM member is never surveyed (decision 7): a Mentor-typed contact, or
    an address on the organization's own mail domain."""
    if "Mentor" in (who.get("types") or []):
        return True
    domain = (getattr(settings, "mentor_email_domain", "") or "").strip().lower()
    return bool(domain) and norm_email(who.get("email") or "").endswith("@" + domain)


async def engagement_recipient(client: Any, engagement_id: str,
                               settings: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """The engagement, and its survey recipient (decision 7): the primary
    client contact, else the first client contact with an address. A CBM
    member is passed over. Raises ``EspoError`` when the engagement cannot
    be read."""
    eng = await client.get(cfg.ENGAGEMENT, engagement_id, select=(
        "name,engagementStatus,clientOrganizationName,mentorProfileId,mentorProfileName,"
        "assignedUsersIds,primaryEngagementContactId,engagementClientId"))
    who = await contact_recipient(client, eng.get("primaryEngagementContactId") or "")
    if who["email"] and not is_member(settings, who):
        return eng, who
    try:
        related = await client.list_related(cfg.ENGAGEMENT, engagement_id, "engagementContacts",
                                            select="id", max_size=50)
    except EspoError as exc:
        log.warning("feedback: contacts of engagement %s not read: %s", engagement_id, exc)
        related = {}
    for row in related.get("list", []):
        if row.get("id") == eng.get("primaryEngagementContactId"):
            continue
        other = await contact_recipient(client, row["id"])
        if other["email"] and not is_member(settings, other):
            return eng, other
    return eng, who


def mentor_first_name(eng: dict[str, Any]) -> str:
    return ((eng.get("mentorProfileName") or "").strip().split(" ") or [""])[0]


# --- the quiet period (BE33) ------------------------------------------------------

async def in_quiet_period(store: Any, settings: Any, email: str,
                          now: Optional[datetime] = None) -> bool:
    days = int(getattr(settings, "feedback_quiet_days", 0) or 0)
    if days <= 0 or not email:
        return False
    since = (now or utcnow()) - timedelta(days=days)
    return await store.recently_sent(email, since)


# --- one send ---------------------------------------------------------------------

def _wording(settings: Any, *, survey_key: str, moment: str, who: dict[str, Any],
             context: dict[str, Any], url: str) -> dict[str, str]:
    org = settings.organization_name
    first = who.get("firstName") or ""
    if survey_key == cfg.SURVEY_EVENT:
        return fb_email.event(org=org, first_name=first, event_name=context.get("eventName", ""),
                              event_date=context.get("eventDate"), link_url=url)
    if survey_key == cfg.SURVEY_EVALUATION:
        return fb_email.evaluation_released(org=org, first_name=first,
                                            mentor_first=context.get("mentorFirst", ""),
                                            link_url=url)
    if moment == cfg.MOMENT_CLOSED:
        return fb_email.engagement_closed(org=org, first_name=first,
                                          mentor_first=context.get("mentorFirst", ""),
                                          company=context.get("company", ""), link_url=url)
    return fb_email.session_milestone(org=org, first_name=first,
                                      mentor_first=context.get("mentorFirst", ""),
                                      company=context.get("company", ""), link_url=url,
                                      on_demand=moment == cfg.MOMENT_ON_DEMAND)


async def _make_link(settings: Any, survey_store: Any, surveys: dict[str, Any], *,
                     survey_key: str, moment: str, entity_type: str, record_id: str,
                     who: dict[str, Any], data: dict[str, Any], display_name: str,
                     created_by: str, now: datetime) -> dict[str, Any]:
    from surveys.definitions import latest

    survey = latest(surveys, survey_key)
    if survey is None:
        raise LookupError(f"no {survey_key} survey definition")
    link_data = {**data, "survey_key": survey_key, "moment": moment,
                 "contact_id": who.get("contactId") or "", "email": who.get("email") or "",
                 "name": who.get("name") or ""}
    return await survey_store.create_link(
        purpose=cfg.PURPOSE, entity_type=entity_type, record_id=record_id, data=link_data,
        display_name=display_name, created_by=created_by,
        days=int(getattr(settings, "feedback_link_days", 30) or 30),
        surveys=[(survey_key, survey.ref, None)], now=now)


async def send(settings: Any, *, store: Any, survey_store: Any, surveys: dict[str, Any],
               send_key: str, survey_key: str, moment: str, entity_type: str, record_id: str,
               who: dict[str, Any], data: dict[str, Any], display_name: str,
               context: dict[str, Any], quiet: bool, created_by: str = CREATED_BY_SWEEP,
               sender: Optional[Sender] = None, now: Optional[datetime] = None) -> str:
    """One survey to one person for one moment, from the shared mailbox.
    Returns ``sent``, ``already`` (claimed before), ``skipped:<why>`` or
    ``failed``. Never raises."""
    now = now or utcnow()
    try:
        claimed = await store.claim(
            send_key, moment=moment, survey_key=survey_key, entity_type=entity_type,
            record_id=record_id, email=who.get("email") or "",
            contact_id=who.get("contactId") or None, created_by=created_by, now=now)
    except Exception as exc:  # noqa: BLE001 — the next pass tries again
        log.warning("feedback %s: not claimed: %s", send_key, exc)
        return "failed"
    if not claimed:
        return "already"
    reason = await skip_reason(settings, store, who, quiet=quiet, now=now)
    if reason:
        await store.finish(send_key, SKIPPED, reason=reason, now=now)
        log.info("feedback %s: skipped (%s)", send_key, reason)
        return f"skipped:{reason}"
    try:
        link = await _make_link(settings, survey_store, surveys, survey_key=survey_key,
                                moment=moment, entity_type=entity_type, record_id=record_id,
                                who=who, data=data, display_name=display_name,
                                created_by=created_by, now=now)
        filled = _wording(settings, survey_key=survey_key, moment=moment, who=who,
                          context=context, url=link_url(settings.app_base_url, link["token"]))
        await (sender or send_shared)(settings, [who["email"]], filled["subject"],
                                      filled["bodyHtml"])
    except Exception as exc:  # noqa: BLE001 — recorded; the next pass tries again
        await store.finish(send_key, FAILED, reason=str(exc)[:500], now=now)
        log.warning("feedback %s: send failed: %s", send_key, exc)
        return "failed"
    await store.finish(send_key, SENT, link_id=link["id"], now=now)
    log.info("feedback %s: %s sent (%s, link %s)", send_key, survey_key, moment, link["id"])
    return "sent"


async def skip_reason(settings: Any, store: Any, who: dict[str, Any], *, quiet: bool,
                      now: datetime) -> Optional[str]:
    """Why this person is not sent a survey, in words; None to send."""
    if not (who.get("email") or "").strip():
        return "no email address"
    if is_member(settings, who):
        return "a member of the organization"
    if who.get("optedOut"):
        return "the address is opted out of email"
    if quiet and await in_quiet_period(store, settings, who["email"], now):
        return "quiet period"
    if not (getattr(settings, "ops_mailbox", "") or "").strip():
        return "no shared mailbox"
    return None


def on_demand_key() -> str:
    return f"ondemand:{uuid.uuid4().hex}"


async def prepare_for_composer(settings: Any, *, store: Any, survey_store: Any,
                               surveys: dict[str, Any], engagement_id: str,
                               who: dict[str, Any], eng: dict[str, Any], created_by: str,
                               now: Optional[datetime] = None) -> dict[str, Any]:
    """A mentor's on-demand mentoring survey (decision 3): the link and the
    ``feedback_send`` row, then the email for the mentor's composer. Raises
    ``ValueError`` with a message for the mentor."""
    now = now or utcnow()
    if not (who.get("email") or "").strip():
        raise ValueError("That contact has no email address, so no survey was made.")
    if is_member(settings, who):
        raise ValueError("That contact is a member of the organization. Feedback surveys "
                         "go to clients only.")
    key = on_demand_key()
    await store.claim(key, moment=cfg.MOMENT_ON_DEMAND, survey_key=cfg.SURVEY_MENTORING,
                      entity_type=cfg.ENGAGEMENT, record_id=engagement_id,
                      email=who["email"], contact_id=who.get("contactId") or None,
                      created_by=created_by, now=now)
    link = await _make_link(
        settings, survey_store, surveys, survey_key=cfg.SURVEY_MENTORING,
        moment=cfg.MOMENT_ON_DEMAND, entity_type=cfg.ENGAGEMENT, record_id=engagement_id,
        who=who, data={"engagement_id": engagement_id,
                       "mentor_profile_id": eng.get("mentorProfileId") or ""},
        display_name=eng.get("clientOrganizationName") or eng.get("name") or "",
        created_by=created_by, now=now)
    await store.finish(key, SENT, link_id=link["id"], now=now)
    filled = fb_email.mentor_on_demand(
        org=settings.organization_name, first_name=who.get("firstName") or "",
        company=eng.get("clientOrganizationName") or "",
        link_url=link_url(settings.app_base_url, link["token"]))
    return {"to": who["email"], "toName": who.get("name") or "", **filled,
            "expiresAt": link["expires_at"].isoformat()}
