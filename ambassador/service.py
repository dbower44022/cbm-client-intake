"""Reading and changing Ambassador Activity records (PRD § 3.5, § 5).

* **My activity** reads AS THE MENTOR: the Mentor Role reads its own records
  only, so a mentor can never list anyone else's. What it returns leaves out
  what the delivery found (match state, where a contact was recorded): the
  page never says who is a client (AM3 item 3).
* **A mentor's correction** is a save as the mentor, of the date, the
  activity and the note only, inside ``AMBASSADOR_EDIT_DAYS``.
* **The review list** and its actions are the program team's. Every one of
  its writes runs under the organization-wide key and is read back
  (:func:`write_checked`): a staff member who is also in the Mentor Team
  carries the Mentor Role's field rules, which silently drop the follow-up
  and review fields. The staff member is named on the record and in the
  action log, written by the router.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core.espo import EspoError

from . import config as cfg
from . import delivery
from . import email as am_email
from . import notify, referrals

log = logging.getLogger("cbm_intake.ambassador")

ACTIVITY_SELECT = (
    "id,name,activityDate,activityType,mentorProfileId,mentorProfileName,contactId,contactName,"
    "companyId,companyName,personKind,enteredName,enteredEmail,enteredOrganization,enteredTitle,"
    "enteredPhone,corrections,matchStatus,routedTo,marketingAgreed,note,followUpRequested,"
    "followUpDone,followUpDoneAt,followUpNote,followUpBy,reviewOutcome,reviewNote,reviewedBy,"
    "reviewedAt,referralOutcome,receivedAt,submissionReference,createdAt")
#: What the mentor's own list reads: nothing the delivery found.
MINE_SELECT = ("id,activityDate,activityType,enteredName,contactName,personKind,note,"
               "followUpRequested,followUpDone,followUpNote,referralOutcome,receivedAt,"
               "submissionReference")
EDITABLE = ("activityDate", "activityType", "note")


def key_client(settings: Any):
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    from core.espo import EspoClient

    return EspoClient(settings.espo_base_url, settings.espo_api_key,
                      settings.request_timeout_seconds)


_available: dict[str, Any] = {"ok": None, "at": 0.0}


async def available(client: Any) -> bool:
    """Whether the CRM has the Ambassador Activity record type; remembered for
    a minute so a page load is not a metadata read per request."""
    if client is None:
        return False
    if _available["ok"] is not None and time.monotonic() - _available["at"] < 60:
        return bool(_available["ok"])
    ok = await referrals.activity_available(client)
    _available.update(ok=ok, at=time.monotonic())
    return ok


def _parse(stamp: Any) -> Optional[datetime]:
    if not stamp:
        return None
    try:
        return datetime.strptime(str(stamp)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def editable_until(row: dict[str, Any], days: int) -> Optional[datetime]:
    got = _parse(row.get("receivedAt"))
    return got + timedelta(days=max(0, days)) if got else None


def mine_view(row: dict[str, Any], days: int, now: Optional[datetime] = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    until = editable_until(row, days)
    follow = ""
    if row.get("followUpRequested"):
        follow = "Done" if row.get("followUpDone") else "Requested"
    return {
        "id": row.get("id"),
        "activityDate": row.get("activityDate") or "",
        "activityType": row.get("activityType") or "",
        "contact": row.get("contactName") or row.get("enteredName") or "",
        "note": row.get("note") or "",
        "followUp": follow,
        "followUpNote": (row.get("followUpNote") or "") if row.get("followUpDone") else "",
        "outcome": row.get("referralOutcome") or "",
        "reference": row.get("submissionReference") or "",
        "editableUntil": until.strftime("%Y-%m-%d") if until else "",
        "editable": bool(until and now <= until),
        "saving": False,
    }


def saving_view(report: dict[str, Any]) -> dict[str, Any]:
    """A report still being recorded, shown at the top of My activity."""
    p = report.get("payload") or {}
    return {"id": "", "activityDate": p.get("activityDate") or "",
            "activityType": p.get("activityType") or "",
            "contact": delivery.person_name(p.get("contact") or {}),
            "note": p.get("note") or "", "followUp": "Requested" if p.get("followUp") else "",
            "followUpNote": "", "outcome": "", "reference": report.get("reference") or "",
            "editableUntil": "", "editable": False, "saving": True,
            "failed": report.get("status") == "failed"}


async def my_activity(user_client: Any, mentor_profile_id: str, days: int) -> list[dict[str, Any]]:
    page = await user_client.list(cfg.ACTIVITY, where=[
        {"type": "equals", "attribute": "mentorProfileId", "value": mentor_profile_id}],
        select=MINE_SELECT, max_size=200, order_by="activityDate", order="desc")
    return [mine_view(r, days) for r in page.get("list", [])]


class CorrectionRefused(Exception):
    pass


async def correct(user_client: Any, activity_id: str, changes: dict[str, Any], days: int,
                  now: Optional[datetime] = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Save a mentor's correction as the mentor; ``(before, after)`` of the
    changed fields. Raises CorrectionRefused with the words to show."""
    row = await user_client.get(cfg.ACTIVITY, activity_id, select=MINE_SELECT)
    until = editable_until(row, days)
    if not until or (now or datetime.now(timezone.utc)) > until:
        raise CorrectionRefused(
            f"This report can no longer be changed: corrections are open for {days} days "
            "after a report is saved. Ask the program team to change it.")
    update: dict[str, Any] = {}
    for key in EDITABLE:
        if key in changes:
            value = (changes[key] or "").strip() if isinstance(changes[key], str) else changes[key]
            if key == "activityType" and value not in cfg.ACTIVITY_TYPES:
                raise CorrectionRefused("Choose one of the six activities.")
            if key == "activityDate" and not value:
                raise CorrectionRefused("Enter the date you did it.")
            if (row.get(key) or "") != (value or ""):
                update[key] = value or None
    if not update:
        return {}, {}
    await user_client.update(cfg.ACTIVITY, activity_id, update)
    return {k: row.get(k) for k in update}, update


# --- the review list (PRD § 5.2) --------------------------------------------------

def review_kind(row: dict[str, Any]) -> list[str]:
    kinds = []
    if row.get("followUpRequested") and not row.get("followUpDone"):
        kinds.append("follow-up")
    if not row.get("reviewOutcome"):
        if row.get("matchStatus") in cfg.NEEDS_REVIEW:
            kinds.append("contact")
        elif row.get("corrections"):
            kinds.append("correction")
    return kinds


def review_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "kinds": review_kind(row),
        "activityDate": row.get("activityDate") or "",
        "activityType": row.get("activityType") or "",
        "ambassador": row.get("mentorProfileName") or "",
        "mentorProfileId": row.get("mentorProfileId") or "",
        "personKind": row.get("personKind") or "",
        "name": row.get("enteredName") or "",
        "email": row.get("enteredEmail") or "",
        "organization": row.get("enteredOrganization") or "",
        "title": row.get("enteredTitle") or "",
        "phone": row.get("enteredPhone") or "",
        "contactId": row.get("contactId") or "",
        "contactName": row.get("contactName") or "",
        "matchStatus": row.get("matchStatus") or "",
        "corrections": row.get("corrections") or "",
        "routedTo": row.get("routedTo") or "",
        "note": row.get("note") or "",
        "followUpRequested": bool(row.get("followUpRequested")),
        "followUpDone": bool(row.get("followUpDone")),
        "followUpNote": row.get("followUpNote") or "",
        "followUpBy": row.get("followUpBy") or "",
        "reviewOutcome": row.get("reviewOutcome") or "",
        "reviewNote": row.get("reviewNote") or "",
        "referralOutcome": row.get("referralOutcome") or "",
        "receivedAt": row.get("receivedAt") or "",
        "reference": row.get("submissionReference") or "",
    }


async def review_rows(client: Any) -> list[dict[str, Any]]:
    """The program team's open rows, oldest first: open follow-ups, contacts
    to place, and corrections not yet seen."""
    queries = [
        [{"type": "isTrue", "attribute": "followUpRequested"},
         {"type": "isFalse", "attribute": "followUpDone"}],
        [{"type": "in", "attribute": "matchStatus", "value": sorted(cfg.NEEDS_REVIEW)},
         {"type": "or", "value": [{"type": "isNull", "attribute": "reviewOutcome"},
                                  {"type": "equals", "attribute": "reviewOutcome", "value": ""}]}],
        [{"type": "isNotNull", "attribute": "corrections"},
         {"type": "or", "value": [{"type": "isNull", "attribute": "reviewOutcome"},
                                  {"type": "equals", "attribute": "reviewOutcome", "value": ""}]}],
    ]
    found: dict[str, dict[str, Any]] = {}
    for where in queries:
        page = await client.list(cfg.ACTIVITY, where=where, select=ACTIVITY_SELECT,
                                 max_size=200, order_by="createdAt", order="asc")
        for r in page.get("list", []):
            found[r["id"]] = r
    rows = [review_view(r) for r in found.values()]
    rows = [r for r in rows if r["kinds"]]
    return sorted(rows, key=lambda r: r["receivedAt"])


async def open_follow_ups(client: Any) -> int:
    page = await client.list(cfg.ACTIVITY, where=[
        {"type": "isTrue", "attribute": "followUpRequested"},
        {"type": "isFalse", "attribute": "followUpDone"}], select="id", max_size=1)
    return int(page.get("total") or 0)


async def oldest_follow_up(client: Any) -> Optional[dict[str, Any]]:
    page = await client.list(cfg.ACTIVITY, where=[
        {"type": "isTrue", "attribute": "followUpRequested"},
        {"type": "isFalse", "attribute": "followUpDone"}],
        select="id,name,mentorProfileName,enteredName,createdAt", max_size=1,
        order_by="createdAt", order="asc")
    rows = page.get("list", [])
    return {**rows[0], "total": int(page.get("total") or 0)} if rows else None


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class WriteDropped(CorrectionRefused):
    """The CRM answered 200 but did not store a field: a field-level rule."""


async def write_checked(client: Any, activity_id: str, values: dict[str, Any]) -> None:
    """Update the activity and read it back. The CRM drops a field a role's
    field rule forbids and still answers 200; a staff member who is also in
    the Mentor Team carries the Mentor Role's rules, which is how Mark done
    and the review outcome were silently lost on the Association (11-21-26).
    The program team's writes therefore run under the org-wide key, and a
    field that still did not store raises ``WriteDropped``."""
    await client.update(cfg.ACTIVITY, activity_id, values)
    got = await client.get(cfg.ACTIVITY, activity_id, select=",".join(values))
    dropped = [k for k, v in values.items()
               if v not in (None, "") and (got.get(k) if not isinstance(v, bool) else bool(got.get(k))) != v]
    if dropped:
        raise WriteDropped("The CRM did not store " + ", ".join(dropped)
                           + ". The application's role is missing an edit grant on these fields.")


async def mark_done(staff_client: Any, key: Any, settings: Any, activity_id: str, note: str,
                    staff_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Mark a follow-up done and tell the mentor (PRD § 14 item 5).
    ``staff_client`` is the org-wide key (see :func:`write_checked`); the
    staff member is named in ``followUpBy`` and in the action log.
    ``(before, after)`` for the action log."""
    note = (note or "").strip()
    if not note:
        raise CorrectionRefused("Write a note saying what was done before marking it done.")
    row = await staff_client.get(cfg.ACTIVITY, activity_id, select=ACTIVITY_SELECT)
    after = {"followUpDone": True, "followUpNote": note, "followUpDoneAt": _stamp(),
             "followUpBy": staff_name or ""}
    await write_checked(staff_client, activity_id, after)
    before = {k: row.get(k) for k in after}
    if key is not None:
        address, _n, first = await notify.profile_mailbox(key, row.get("mentorProfileId") or "")
        if address:
            filled = am_email.follow_up_done(
                org=settings.organization_name, first_name=first,
                activity=row.get("activityType") or "", date=row.get("activityDate") or "",
                note=note, done_by=staff_name)
            await notify.send(settings, [address], filled, what="follow-up-done")
    return before, after


async def set_review(staff_client: Any, activity_id: str, outcome: str, note: str,
                     staff_name: str, extra: Optional[dict[str, Any]] = None
                     ) -> tuple[dict[str, Any], dict[str, Any]]:
    row = await staff_client.get(cfg.ACTIVITY, activity_id, select=ACTIVITY_SELECT)
    after = {"reviewOutcome": outcome, "reviewNote": (note or "").strip() or None,
             "reviewedBy": staff_name or "", "reviewedAt": _stamp(), **(extra or {})}
    await write_checked(staff_client, activity_id, after)
    return {k: row.get(k) for k in after}, after


def report_from_activity(row: dict[str, Any]) -> dict[str, Any]:
    """A report shaped as the delivery expects, rebuilt from an activity, for
    the review list's Link and Create."""
    first, _, last = (row.get("enteredName") or "").partition(" ")
    return {
        "reference": row.get("submissionReference") or row.get("id"),
        "user_name": row.get("mentorProfileName") or "",
        "user_id": "",
        "mentor_profile_id": row.get("mentorProfileId") or "",
        "payload": {
            "activityType": row.get("activityType") or "",
            "activityDate": row.get("activityDate") or "",
            "note": row.get("note") or "",
            "personKind": row.get("personKind") or "",
            "marketingAgreed": bool(row.get("marketingAgreed")),
            "contact": {"firstName": first, "lastName": last,
                        "email": row.get("enteredEmail") or "",
                        "organization": row.get("enteredOrganization") or "",
                        "phone": row.get("enteredPhone") or "",
                        "title": row.get("enteredTitle") or ""},
        },
    }


TARGETS = {
    "partner": (cfg.PARTNER, cfg.PARTNER_SESSION_FK, cfg.PARTNER_MANAGER, "partnersessions",
                "the partner record"),
    "funder": (cfg.SPONSOR, cfg.SPONSOR_SESSION_FK, cfg.SPONSOR_MANAGER, "sponsorsessions",
               "the funder record"),
    "client": (cfg.ENGAGEMENT, cfg.ENGAGEMENT_SESSION_FK, "mentorProfileId", "mentorsessions",
               "the client's engagement"),
}


async def search_targets(key: Any, kind: str, query: str) -> list[dict[str, Any]]:
    """Records the program team may link a contact to, by name."""
    if kind not in TARGETS or len((query or "").strip()) < 2:
        return []
    entity = TARGETS[kind][0]
    page = await key.list(entity, where=[{"type": "contains", "attribute": "name",
                                          "value": query.strip()}],
                          select="id,name", max_size=20, order_by="name", order="asc")
    return [{"id": r["id"], "name": r.get("name") or ""} for r in page.get("list", [])]


async def link_to(key: Any, settings: Any, row: dict[str, Any], kind: str,
                  record_id: str) -> str:
    """Record the activity's contact on an existing partner, funder or client:
    the session and the email, as the delivery would have."""
    entity, fk, manager_attr, slug, words = TARGETS[kind]
    rec = await key.get(entity, record_id,
                        select=f"id,name,{manager_attr},assignedUsersIds,teamsIds")
    report = report_from_activity(row)
    contact = {"id": row.get("contactId") or "", "name": row.get("enteredName") or "",
               "accountName": row.get("enteredOrganization") or ""}
    if not contact["id"]:
        # The contact is not in the CRM yet: it is made on that record now.
        entered = report["payload"]["contact"]
        if not entered.get("email"):
            raise CorrectionRefused("This contact has no email address, so it cannot be "
                                    "added to the CRM. Create it in the record first.")
        from core.crm_upsert import find_create_or_fill
        payload = {"firstName": entered.get("firstName") or None,
                   "lastName": entered.get("lastName") or "(not given)",
                   "emailAddress": entered["email"]}
        cid, _ = await find_create_or_fill(key, cfg.CONTACT, match_attr="emailAddress",
                                           match_value=entered["email"],
                                           create_payload={k: v for k, v in payload.items() if v})
        contact["id"] = cid
    target = {"kind": kind, "entity": entity, "record": rec, "fk": fk,
              "manager": rec.get(manager_attr), "slug": slug, "words": words}
    line = await delivery.record_contact(key, settings, target, report=report, contact=contact,
                                         step="review-link")
    await key.update(cfg.ACTIVITY, row["id"], {"contactId": contact["id"],
                                               "matchStatus": cfg.M_MATCHED,
                                               "routedTo": ((row.get("routedTo") or "") + "\n" + line).strip()})
    return line


async def create_from(key: Any, settings: Any, row: dict[str, Any], kind: str) -> dict[str, Any]:
    """Create the activity's contact as a new referral of ``kind``."""
    person_kind = {"client": cfg.POTENTIAL_CLIENT, "partner": cfg.POTENTIAL_PARTNER,
                   "funder": cfg.POTENTIAL_FUNDER}.get(kind)
    if person_kind is None:
        raise CorrectionRefused("Choose client, partner or funder.")
    report = report_from_activity(row)
    entered = report["payload"]["contact"]
    if not entered.get("email"):
        raise CorrectionRefused("This contact has no email address. A new referral needs one, "
                                "so that it is found again when the person applies.")
    made = await referrals.create_referral(
        key, settings, kind=person_kind, entered=entered,
        mentor_profile_id=row.get("mentorProfileId") or "", user_id="",
        marketing_agreed=bool(row.get("marketingAgreed")))
    await key.update(cfg.ACTIVITY, row["id"], {
        "contactId": made["contactId"], "companyId": made.get("companyId") or None,
        "matchStatus": cfg.M_CREATED, "personKind": person_kind,
        "referralOutcome": cfg.O_NOT_YET if row.get("activityType") == cfg.REFERRED else "",
        "routedTo": ((row.get("routedTo") or "") + f"\nNew {kind} referral from review").strip()})
    return made


async def for_mentor(key: Any, mentor_profile_id: str) -> list[dict[str, Any]]:
    """A mentor's activities for staff (Mentor Administration's tab)."""
    page = await key.list(cfg.ACTIVITY, where=[
        {"type": "equals", "attribute": "mentorProfileId", "value": mentor_profile_id}],
        select=ACTIVITY_SELECT, max_size=200, order_by="activityDate", order="desc")
    return [review_view(r) for r in page.get("list", [])]
