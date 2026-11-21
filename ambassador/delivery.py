"""Recording one ambassador report in the CRM (PRD § 4.1, § 4.2).

The report was captured in ``ambassador_report`` first. This chain runs under
the organization-wide key through ``core/resumable.ResumableClient``: every
create is remembered in the row's progress and every side effect is a named
step, so a retry after a failure finishes the chain without duplicating a
record or an email.

The chain:

1. create the activity record, linked to the mentor and assigned to their
   login so the Mentor Role's "own" grant lets them read and correct it;
2. classify the contact: a CBM member, a known Contact (by email, else the
   Contact the lookup picked), several Contacts with one email, or nobody;
3. route (§ 4.2's table): an "Ambassador Contact" session on every partner,
   funder and current engagement the Contact belongs to, each manager or
   mentor emailed; a referral of someone unknown created (referrals.py); a
   known person referred is credited if no one was before; anything the
   chain cannot place is left for the program team's review;
4. the follow-up request, if any, emailed to the program team;
5. the activity updated with what was found and done.

The mentor's own browser never sees what this chain found (AM3 item 3).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape
from typing import Any, Optional

from core.espo import EspoError
from core.resumable import ResumableClient, run_step_once

from . import config as cfg
from . import email as am_email
from . import notify, referrals
from .lookup import is_member_address

log = logging.getLogger("cbm_intake.ambassador")


def _now_crm() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def person_name(entered: dict[str, Any]) -> str:
    return " ".join(x for x in ((entered.get("firstName") or "").strip(),
                                (entered.get("lastName") or "").strip()) if x)


def activity_name(payload: dict[str, Any], mentor_name: str) -> str:
    return f"{payload.get('activityType') or ''} — {mentor_name or 'ambassador'} — " \
           f"{payload.get('activityDate') or ''}"[:255]


def readable_corrections(corrections: list[dict[str, Any]]) -> str:
    lines = []
    for c in corrections or []:
        field = (c.get("field") or "").strip()
        if field:
            lines.append(f"{field}: our records said \"{c.get('ours') or ''}\"; "
                         f"the ambassador entered \"{c.get('theirs') or ''}\"")
    return "\n".join(lines)


def activity_payload(report: dict[str, Any]) -> dict[str, Any]:
    """The activity record as first written, before routing."""
    p = report["payload"]
    entered = p.get("contact") or {}
    corrections = readable_corrections(p.get("corrections") or [])
    kind = p.get("personKind") or ""
    body: dict[str, Any] = {
        "name": activity_name(p, report.get("user_name") or ""),
        "activityDate": p.get("activityDate"),
        "activityType": p.get("activityType"),
        "mentorProfileId": report["mentor_profile_id"],
        "assignedUsersIds": [report["user_id"]],
        "personKind": kind or None,
        "enteredName": person_name(entered) or None,
        "enteredEmail": (entered.get("email") or "").strip() or None,
        "enteredOrganization": (entered.get("organization") or "").strip() or None,
        "enteredTitle": (entered.get("title") or "").strip() or None,
        "enteredPhone": (entered.get("phone") or "").strip() or None,
        "corrections": corrections or None,
        "matchStatus": cfg.M_PENDING,
        "marketingAgreed": bool(p.get("marketingAgreed")),
        "note": (p.get("note") or "").strip() or None,
        "followUpRequested": bool(p.get("followUp")),
        "followUpDone": False,
        "referralOutcome": cfg.O_NOT_YET if p.get("activityType") == cfg.REFERRED
        and kind in cfg.REFERRAL_KINDS else cfg.O_NONE,
        "receivedAt": report["created_at"].astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(report.get("created_at"), datetime) else _now_crm(),
        "submissionReference": report["reference"],
    }
    return {k: v for k, v in body.items() if v is not None}


# --- classifying the contact ----------------------------------------------------------

async def classify(client: Any, settings: Any, entered: dict[str, Any]) -> dict[str, Any]:
    """``{"state": member|many|known|unknown|none, "contact": {...}}``."""
    email = (entered.get("email") or "").strip()
    picked = (entered.get("contactId") or "").strip()
    if not (email or picked or person_name(entered)):
        return {"state": "none"}
    if email and is_member_address(settings, email):
        return {"state": "member"}
    select = f"id,name,firstName,lastName,emailAddress,accountId,accountName,cContactType," \
             f"{cfg.CONTACT_REFERRED_BY}Id"
    contact = None
    if email:
        page = await client.list(cfg.CONTACT, where=[
            {"type": "equals", "attribute": "emailAddress", "value": email}],
            select=select.replace(f",{cfg.CONTACT_REFERRED_BY}Id", ""), max_size=3)
        rows = page.get("list", [])
        if len(rows) > 1:
            return {"state": "many"}
        contact = rows[0] if rows else None
    if contact is None and picked:
        try:
            contact = await client.get(cfg.CONTACT, picked, select=select.replace(
                f",{cfg.CONTACT_REFERRED_BY}Id", ""))
        except EspoError:
            contact = None
    if contact is None:
        return {"state": "unknown"}
    if is_member_address(settings, contact.get("emailAddress") or "", contact.get("cContactType")):
        return {"state": "member"}
    if await referrals.has_link(client, cfg.CONTACT, cfg.CONTACT_REFERRED_BY):
        try:
            contact = await client.get(cfg.CONTACT, contact["id"], select=select)
        except EspoError:
            pass
    return {"state": "known", "contact": contact}


async def _linked(client: Any, entity: str, contacts_link: str, primary: str,
                  contact_id: str, select: str) -> list[dict[str, Any]]:
    """Records of ``entity`` whose contacts include, or whose primary contact
    is, the Contact."""
    found: dict[str, dict[str, Any]] = {}
    for where in ([{"type": "linkedWith", "attribute": contacts_link, "value": [contact_id]}],
                  [{"type": "equals", "attribute": primary, "value": contact_id}]):
        try:
            page = await client.list(entity, where=where, select=select, max_size=20)
        except EspoError as exc:
            log.warning("ambassador: %s for contact %s not read: %s", entity, contact_id, exc)
            continue
        for r in page.get("list", []):
            found[r["id"]] = r
    return list(found.values())


def current_engagement(rows: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The client's current engagement: the newest in an active status, else
    the newest of any."""
    if not rows:
        return None
    by_new = sorted(rows, key=lambda r: r.get("createdAt") or "", reverse=True)
    for r in by_new:
        if r.get("engagementStatus") in cfg.CURRENT_ENGAGEMENT_STATUSES:
            return r
    return by_new[0]


async def find_targets(client: Any, contact_id: str) -> list[dict[str, Any]]:
    """Every record an ambassador contact with this person is recorded on:
    each partner and funder profile, and the current engagement."""
    targets: list[dict[str, Any]] = []
    for r in await _linked(client, cfg.PARTNER, cfg.PARTNER_CONTACTS, cfg.PARTNER_PRIMARY,
                           contact_id, f"id,name,{cfg.PARTNER_MANAGER},assignedUsersIds,teamsIds"):
        targets.append({"kind": "partner", "entity": cfg.PARTNER, "record": r,
                        "fk": cfg.PARTNER_SESSION_FK, "manager": r.get(cfg.PARTNER_MANAGER),
                        "slug": "partnersessions", "words": "the partner record"})
    for r in await _linked(client, cfg.SPONSOR, cfg.SPONSOR_CONTACTS, cfg.SPONSOR_PRIMARY,
                           contact_id, f"id,name,{cfg.SPONSOR_MANAGER},assignedUsersIds,teamsIds"):
        targets.append({"kind": "funder", "entity": cfg.SPONSOR, "record": r,
                        "fk": cfg.SPONSOR_SESSION_FK, "manager": r.get(cfg.SPONSOR_MANAGER),
                        "slug": "sponsorsessions", "words": "the funder record"})
    eng = current_engagement(await _linked(
        client, cfg.ENGAGEMENT, cfg.ENGAGEMENT_CONTACTS, "primaryEngagementContactId", contact_id,
        "id,name,engagementStatus,mentorProfileId,assignedUsersIds,teamsIds,createdAt"))
    if eng:
        targets.append({"kind": "client", "entity": cfg.ENGAGEMENT, "record": eng,
                        "fk": cfg.ENGAGEMENT_SESSION_FK, "manager": eng.get("mentorProfileId"),
                        "slug": "mentorsessions", "words": "the client's engagement"})
    return targets


# --- the session and its email ---------------------------------------------------------

def session_payload(target: dict[str, Any], *, mentor_name: str, date: str, activity: str,
                    note: str, contact_name: str) -> dict[str, Any]:
    rec = target["record"]
    notes = f"<p>{escape(activity)} — reported by {escape(mentor_name)}, an ambassador.</p>"
    if note:
        notes += "<p>" + escape(note).replace("\n", "<br>") + "</p>"
    payload: dict[str, Any] = {
        "name": f"Ambassador contact by {mentor_name}"[:255],
        "sessionType": cfg.AMBASSADOR_SESSION_TYPE,
        "status": "Completed",
        "dateStart": f"{date} 12:00:00",
        "dateEnd": f"{date} 12:30:00",
        "sessionNotes": notes,
        target["fk"]: rec["id"],
    }
    if rec.get("assignedUsersIds"):
        payload["assignedUsersIds"] = list(rec["assignedUsersIds"])
    if rec.get("teamsIds"):
        payload["teamsIds"] = list(rec["teamsIds"])
    return payload


async def record_contact(client: Any, settings: Any, target: dict[str, Any], *,
                         report: dict[str, Any], contact: dict[str, Any], step: str) -> str:
    """Write the ambassador contact session on one record and email its
    manager or mentor. Returns a line for the activity's ``routedTo``."""
    p = report["payload"]
    mentor_name = report.get("user_name") or "an ambassador"
    contact_name = contact.get("name") or person_name(p.get("contact") or {})
    created = await client.create(cfg.SESSION, session_payload(
        target, mentor_name=mentor_name, date=p.get("activityDate") or "",
        activity=p.get("activityType") or "", note=(p.get("note") or "").strip(),
        contact_name=contact_name))

    async def _attendee() -> None:
        try:
            await client.relate(cfg.SESSION, created["id"], cfg.ATTENDEE_LINK, contact["id"])
        except EspoError as exc:
            log.warning("ambassador: attendee not linked on session %s: %s", created["id"], exc)

    await run_step_once(client, f"{step}:attendee", _attendee)

    async def _email() -> None:
        address, _n, _f = await notify.profile_mailbox(client, target.get("manager") or "")
        if not address:
            log.info("ambassador: %s %s has no manager with a CBM address; no email",
                     target["kind"], target["record"]["id"])
            return
        filled = am_email.contact_met(
            org=settings.organization_name, ambassador=mentor_name, contact=contact_name,
            organization=contact.get("accountName") or "",
            activity=p.get("activityType") or "", date=p.get("activityDate") or "",
            note=(p.get("note") or "").strip(),
            record_words=f"{target['words']}, {target['record'].get('name') or ''}",
            link_url=f"{notify.base_url(settings)}/{target['slug']}/record/"
                     f"{target['record']['id']}?tab=sessions")
        await notify.send(settings, [address], filled, what=f"{target['kind']}-contact")

    await run_step_once(client, f"{step}:email", _email)
    return f"Ambassador contact session on {target['kind']} {target['record'].get('name') or ''} " \
           f"({target['record']['id']})"


# --- the follow-up request (AM4) -----------------------------------------------------

async def alert_follow_up(client: Any, settings: Any, report: dict[str, Any]) -> str:
    p = report["payload"]
    to = await notify.team_mailboxes(client, settings.ambassador_review_teams_list)
    if not to:
        to = list(getattr(settings, "alert_email_to_list", None) or [])
        log.warning("ambassador follow-up %s: the program team has no members with an "
                    "address; sent to the alert address instead", report["reference"])
    filled = am_email.follow_up_requested(
        org=settings.organization_name, ambassador=report.get("user_name") or "an ambassador",
        activity=p.get("activityType") or "", date=p.get("activityDate") or "",
        contact=person_name(p.get("contact") or {}), note=(p.get("note") or "").strip(),
        link_url=f"{notify.base_url(settings)}/ambassador/review/")
    return await notify.send(settings, to, filled, what="follow-up")


async def _referral_email(client: Any, settings: Any, report: dict[str, Any], kind: str,
                          made: dict[str, Any]) -> None:
    """Partner or Funder Management's team hears of a referred organisation."""
    p = report["payload"]
    entered = p.get("contact") or {}
    team = settings.partner_team_name if kind == cfg.POTENTIAL_PARTNER else settings.sponsor_team_name
    slug = "partnersessions" if kind == cfg.POTENTIAL_PARTNER else "sponsorsessions"
    to = await notify.team_mailboxes(client, [team])
    filled = am_email.referral_received(
        org=settings.organization_name, ambassador=report.get("user_name") or "an ambassador",
        person=person_name(entered), organization=entered.get("organization") or "",
        kind_words=referrals.KIND_WORDS.get(kind, ""), note=(p.get("note") or "").strip(),
        link_url=f"{notify.base_url(settings)}/{slug}/record/{made.get('profileId')}")
    await notify.send(settings, to, filled, what="referral-received")


# --- the chain --------------------------------------------------------------------

async def deliver(client: ResumableClient, settings: Any, report: dict[str, Any]) -> str:
    """Run the chain for one report; returns the activity id. Raises on a CRM
    failure the caller should retry."""
    p = report["payload"]
    created = await client.create(cfg.ACTIVITY, activity_payload(report))
    activity_id = created["id"]
    entered = p.get("contact") or {}
    kind = p.get("personKind") or ""
    result: dict[str, Any] = {"matchStatus": cfg.M_NO_CONTACT}
    routed: list[str] = []

    if p.get("activityType") not in cfg.NO_CONTACT:
        found = await classify(client, settings, entered)
        state = found["state"]
        if state == "member":
            result["matchStatus"] = cfg.M_MEMBER
        elif state == "many":
            result["matchStatus"] = cfg.M_MANY
        elif state == "known":
            contact = found["contact"]
            result.update({"contactId": contact["id"], "companyId": contact.get("accountId") or None})
            targets = await find_targets(client, contact["id"])
            for i, target in enumerate(targets):
                routed.append(await record_contact(client, settings, target, report=report,
                                                   contact=contact, step=f"route{i}"))
            if kind in cfg.REFERRAL_KINDS:
                async def _credit() -> None:
                    if await referrals.credit_contact(client, contact, report["mentor_profile_id"]):
                        routed.append("Referred by set on the contact")
                await run_step_once(client, "credit", _credit)
                wanted = {cfg.POTENTIAL_PARTNER: "partner", cfg.POTENTIAL_FUNDER: "funder"}.get(kind)
                if wanted and not any(t["kind"] == wanted for t in targets):
                    made = await referrals.create_referral(
                        client, settings, kind=kind, entered={**entered, "contactId": contact["id"],
                                                              "email": contact.get("emailAddress") or entered.get("email"),
                                                              "companyId": contact.get("accountId") or entered.get("companyId")},
                        mentor_profile_id=report["mentor_profile_id"], user_id=report["user_id"],
                        marketing_agreed=bool(p.get("marketingAgreed")))
                    routed.append(f"Starting {wanted} record {made.get('profileId')}")
                    await run_step_once(client, "referral-email",
                                        lambda: _referral_email(client, settings, report, kind, made))
            if targets or kind in cfg.REFERRAL_KINDS or kind != cfg.EXISTING_ORG:
                result["matchStatus"] = cfg.M_MATCHED
            else:
                result["matchStatus"] = cfg.M_NOT_MATCHED
        elif state == "unknown":
            if kind in cfg.REFERRAL_KINDS and (entered.get("email") or "").strip():
                made = await referrals.create_referral(
                    client, settings, kind=kind, entered=entered,
                    mentor_profile_id=report["mentor_profile_id"], user_id=report["user_id"],
                    marketing_agreed=bool(p.get("marketingAgreed")))
                result.update({"matchStatus": cfg.M_CREATED, "contactId": made["contactId"],
                               "companyId": made.get("companyId") or None})
                routed.append(f"New contact {made['contactId']}"
                              + (f", starting record {made['profileId']}" if made.get("profileId") else ""))
                if made.get("profileId"):
                    await run_step_once(client, "referral-email",
                                        lambda: _referral_email(client, settings, report, kind, made))
            else:
                result["matchStatus"] = cfg.M_NOT_MATCHED
                # Someone else, met and named, with nothing to follow up: the
                # report stands on its own and needs no review (PRD § 4.2).
                if kind == cfg.SOMEONE_ELSE and not p.get("followUp"):
                    result["reviewOutcome"] = cfg.R_SEEN

    if p.get("followUp"):
        async def _alert() -> None:
            outcome = await alert_follow_up(client, settings, report)
            if outcome == "failed":
                raise EspoError("the follow-up alert could not be sent")
        try:
            await run_step_once(client, "follow-up-alert", _alert)
        except EspoError as exc:
            # The report is recorded; the alert is retried with the delivery.
            log.warning("ambassador %s: %s", report["reference"], exc)
            raise

    if routed:
        result["routedTo"] = "\n".join(routed)
    await client.update(cfg.ACTIVITY, activity_id, {k: v for k, v in result.items() if v is not None})
    return activity_id
