"""The Business Evaluation's mentor side (plan § 3 steps 1 and 2; rulings BE3,
BE5, BE10, BE12, BE14): what the engagement's Evaluations tab shows, and the
one Send path that both the Send Evaluation button and
``scripts/evaluation_make_link.py`` use.

Rules kept here:

* **The tab is feature-detected.** A CRM without ``CBusinessEvaluation``
  answers ``available: false`` with the reason, never an error.
* **Reads run as the signed-in user**, so the CRM's own access rules decide
  what a mentor sees (the Mentor Role reads ``own``: every record carrying
  the mentor in ``assignedUsers``).
* **Records are created as the user, stamped with the engagement's
  ``assignedUsers``.** The Mentor Role's Assignment Permission is ``team``, so
  a stamp naming someone outside the mentor's teams is refused; only that
  refusal is retried under the org-wide key (the ``_link_or_escalate``
  pattern), so the send never fails over who else is on the engagement.
* **More than three areas is advised against and still sent** (BE10).
* **The link is a random token** (BE12), made in the application database
  after the records exist, and it reaches the client only through the email.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Callable, Optional

from core.espo import EspoError, is_forbidden
from surveys.answers import readable_html

from . import service
from .service import ENGAGEMENT, link_data
from .surveys import PROFILE_KEY, Survey, latest

log = logging.getLogger("cbm_intake.evaluation")

STATUS_SENT = "Sent"
STATUS_EXPIRED = "Expired"
STATUS_DECLINED = "Declined"
#: Statuses a client can still act on: Expire and Record a decline apply to these.
OPEN_STATUSES = (STATUS_SENT, service.STATUS_IN_PROGRESS)

#: BE10: the Send dialog advises two or three areas per round.
ADVISED_MAX = 3

UNAVAILABLE_REASON = (
    "Business Evaluations are not available yet: this CRM does not have the "
    "Business Evaluation record type. An administrator applies "
    "business-evaluation-crm-handoff.md to add it."
)

RECORD_SELECT = ("id,name,evaluationArea,evaluationRound,status,sentAt,submittedAt,"
                 "engagementId,surveyVersion")


class SendError(Exception):
    """A send the application refuses, with a message the mentor can act on."""


async def entity_available(client: Any) -> bool:
    """True when the CRM has the Business Evaluation entity. A metadata read
    that fails counts as absent: the tab says so rather than breaking."""
    try:
        meta = await client.metadata(f"entityDefs.{service.ENTITY}")
    except EspoError as exc:
        log.warning("evaluation: metadata read failed: %s", exc)
        return False
    return isinstance(meta, dict) and bool(meta.get("fields"))


def area_surveys(surveys: dict[str, Survey]) -> list[Survey]:
    """The latest version of every area survey (never the business profile),
    in title order: what the Send dialog offers."""
    keys = sorted({s.key for s in surveys.values() if s.key != PROFILE_KEY})
    found = [latest(surveys, k) for k in keys]
    return sorted((s for s in found if s is not None), key=lambda s: s.title)


def area_choices(surveys: dict[str, Survey]) -> list[dict[str, str]]:
    return [{"key": s.key, "title": s.title} for s in area_surveys(surveys)]


def choose_areas(surveys: dict[str, Survey], keys: list[str]) -> list[Survey]:
    """The surveys for the chosen area keys, in the order given, once each.
    Raises ``SendError`` naming an unknown key, or when none is chosen."""
    chosen: list[Survey] = []
    for key in dict.fromkeys(k for k in keys if k):
        survey = latest(surveys, key)
        if survey is None or key == PROFILE_KEY:
            known = ", ".join(s.title for s in area_surveys(surveys))
            raise SendError(f"'{key}' is not an evaluation area. The areas are: {known}.")
        chosen.append(survey)
    if not chosen:
        raise SendError("Choose at least one evaluation area to send.")
    return chosen


def advice(count: int) -> Optional[str]:
    """The warning above three areas (BE10); None at three or fewer."""
    if count <= ADVISED_MAX:
        return None
    return (f"You chose {count} areas. Clients finish two or three at a time far "
            "more often than more. You can still send all of them.")


async def engagement_context(client: Any, engagement_id: str) -> dict[str, Any]:
    """What a send needs from the CRM, read as the user: the engagement, its
    client profile, the company name, whether the business profile is still
    owed (BE8), and the primary contact."""
    eng = await client.get(ENGAGEMENT, engagement_id, select=(
        "name,engagementClientId,clientOrganizationName,assignedUsersIds,"
        "primaryEngagementContactId,primaryEngagementContactName"))
    profile_id = eng.get("engagementClientId")
    if not profile_id:
        raise SendError("This engagement has no client business profile, so an "
                        "evaluation cannot be sent. Ask Client Administration to link one.")
    prof = await client.get(service.CLIENT_PROFILE, profile_id,
                            select="name,linkedCompanyName,evaluationProfile")
    company = (eng.get("clientOrganizationName") or prof.get("linkedCompanyName")
               or prof.get("name") or "")
    return {
        "engagement": eng,
        "profileId": profile_id,
        "company": company,
        "profileNeeded": not (prof.get("evaluationProfile") or "").strip(),
        "assignedUsersIds": list(eng.get("assignedUsersIds") or []),
        "contactId": eng.get("primaryEngagementContactId") or "",
        "contactName": eng.get("primaryEngagementContactName") or "",
    }


async def list_records(client: Any, engagement_id: str) -> list[dict[str, Any]]:
    """Every Business Evaluation record on the engagement the user can read.
    Pages at 200, the CRM's ceiling."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = await client.list(service.ENTITY, where=[
            {"type": "equals", "attribute": "engagementId", "value": engagement_id}],
            select=RECORD_SELECT, max_size=200, offset=offset,
            order_by="createdAt", order="asc")
        batch = page.get("list", []) or []
        rows += batch
        offset += len(batch)
        if not batch or offset >= (page.get("total") or 0):
            return rows


def next_round(records: list[dict[str, Any]]) -> int:
    return 1 + max([r.get("evaluationRound") or 0 for r in records] or [0])


async def _create(client: Any, escalate: Optional[Callable[[], Any]],
                  payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Create as the user; retry under the org-wide key only on a refusal.
    Returns the record and whether it was escalated."""
    try:
        return await client.create(service.ENTITY, payload), False
    except EspoError as exc:
        key = escalate() if escalate and is_forbidden(exc) else None
        if key is None:
            raise
        log.info("evaluation: create refused as the user (%s); writing under the org-wide key", exc)
        return await key.create(service.ENTITY, payload), True


async def send(client: Any, store: Any, *, engagement_id: str, area_keys: list[str],
               surveys: dict[str, Survey], created_by: str, days: int,
               escalate: Optional[Callable[[], Any]] = None,
               now: Optional[datetime] = None) -> dict[str, Any]:
    """Send Evaluation: one Business Evaluation record per area (status Sent,
    the engagement's assigned users, the next round) and one link opening
    them, plus the business profile when it is still owed.

    ``escalate`` returns the org-wide-key client (or None). A record created
    before a later refusal stays: the next send is a new round, and the
    mentor can Expire the partial one."""
    chosen = choose_areas(surveys, area_keys)
    if store is None:
        raise SendError("Evaluations need the application database, which is not "
                        "configured here.")
    ctx = await engagement_context(client, engagement_id)
    round_no = next_round(await list_records(client, engagement_id))
    now = now or service.utcnow()
    made: list[dict[str, Any]] = []
    for survey in chosen:
        rec, escalated = await _create(client, escalate, {
            "name": f"{survey.area} — {ctx['company']}" if ctx["company"] else survey.area,
            "engagementId": engagement_id,
            "clientProfileId": ctx["profileId"],
            "evaluationArea": survey.area,
            "evaluationRound": round_no,
            "status": STATUS_SENT,
            "sentAt": service.crm_stamp(now),
            "surveyVersion": survey.ref,
            "assignedUsersIds": ctx["assignedUsersIds"],
        })
        made.append({"id": rec["id"], "key": survey.key, "ref": survey.ref,
                     "area": survey.area, "title": survey.title, "escalated": escalated})
    profile = latest(surveys, PROFILE_KEY)
    rows = ([(PROFILE_KEY, profile.ref, None)] if ctx["profileNeeded"] and profile else [])
    rows += [(m["key"], m["ref"], m["id"]) for m in made]
    link = await store.create_link(
        purpose=service.PURPOSE, entity_type=ENGAGEMENT, record_id=engagement_id,
        data={"client_profile_id": ctx["profileId"], "round": round_no,
              "area_keys": [s.key for s in chosen], "profile_needed": ctx["profileNeeded"]},
        display_name=ctx["company"], created_by=created_by, days=days, surveys=rows, now=now)
    return {
        "round": round_no,
        "records": made,
        "link": link,
        "company": ctx["company"],
        "profileNeeded": ctx["profileNeeded"],
        "contactId": ctx["contactId"],
        "contactName": ctx["contactName"],
        "warning": advice(len(chosen)),
    }


# --- the tab -----------------------------------------------------------------

def link_state(link: Optional[dict[str, Any]], now: datetime) -> str:
    """``open``, ``ended`` (replaced or expired by the mentor) or ``expired``."""
    if not link:
        return "none"
    if link.get("replaced_at"):
        return "ended"
    return "open" if now < link["expires_at"] else "expired"


def _iso(at: Optional[datetime]) -> Optional[str]:
    return at.isoformat() if at else None


async def rounds_view(client: Any, store: Any, engagement_id: str,
                      now: Optional[datetime] = None) -> list[dict[str, Any]]:
    """The tab's rows, newest round first: each round's records (area,
    status, sent and submitted dates) and the state of its current link.
    The link's token is never part of it."""
    now = now or service.utcnow()
    records = await list_records(client, engagement_id)
    links: list[dict[str, Any]] = []
    if store is not None:
        try:
            links = await links_for_engagement(store, engagement_id)
        except Exception as exc:  # noqa: BLE001 — the CRM rows still show
            log.warning("evaluation: links for %s not read: %s", engagement_id, exc)
    by_round: dict[int, list[dict[str, Any]]] = {}
    for r in records:
        by_round.setdefault(r.get("evaluationRound") or 0, []).append({
            "id": r.get("id"), "area": r.get("evaluationArea") or "",
            "status": r.get("status") or "", "sentAt": r.get("sentAt"),
            "submittedAt": r.get("submittedAt"),
        })
    out = []
    for round_no in sorted(by_round, reverse=True):
        current = current_link(links, round_no)
        out.append({
            "round": round_no,
            "records": sorted(by_round[round_no], key=lambda x: x["area"]),
            "link": {
                "state": link_state(current, now),
                "sentAt": _iso(current["created_at"]) if current else None,
                "expiresAt": _iso(current["expires_at"]) if current else None,
                "endedAt": _iso(current.get("replaced_at")) if current else None,
            },
        })
    return out


def _profile_html(raw: str, surveys: dict[str, Survey]) -> Optional[str]:
    """The business profile's answers as reviewer text, from the client
    profile's JSON. None when there is none or it cannot be read."""
    if not (raw or "").strip():
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    ref = data.get("survey") if isinstance(data, dict) else None
    survey = surveys.get(ref or "") or latest(surveys, PROFILE_KEY)
    answers = data.get("answers") if isinstance(data, dict) else None
    if survey is None or not isinstance(answers, dict):
        return None
    return readable_html(survey, answers)


async def answers_view(client: Any, engagement_id: str, record_id: str,
                       surveys: dict[str, Survey]) -> Optional[dict[str, Any]]:
    """One record's answers, read-only, with the business profile. None when
    the record is not this engagement's (the caller answers 404)."""
    rec = await client.get(service.ENTITY, record_id, select=(
        "id,name,evaluationArea,evaluationRound,status,sentAt,submittedAt,"
        "engagementId,clientProfileId,answersReadable"))
    if rec.get("engagementId") != engagement_id:
        return None
    profile_html: Optional[str] = None
    profile_note = ""
    if rec.get("clientProfileId"):
        try:
            prof = await client.get(service.CLIENT_PROFILE, rec["clientProfileId"],
                                    select="evaluationProfile,evaluationProfileAt")
            profile_html = _profile_html(prof.get("evaluationProfile") or "", surveys)
            if profile_html is None:
                profile_note = "The client has not answered the business profile yet."
        except EspoError as exc:
            log.warning("evaluation %s: business profile not read: %s", record_id, exc)
            profile_note = "The business profile could not be read with your access."
    return {
        "id": rec.get("id"), "area": rec.get("evaluationArea") or "",
        "round": rec.get("evaluationRound"), "status": rec.get("status") or "",
        "sentAt": rec.get("sentAt"), "submittedAt": rec.get("submittedAt"),
        "answersHtml": rec.get("answersReadable") or "",
        "profileHtml": profile_html, "profileNote": profile_note,
    }


# --- the email (step 4) ----------------------------------------------------------

def link_url(base: str, token: str) -> str:
    return f"{(base or '').rstrip('/')}/survey/{token}"


async def recipient(client: Any, contact_id: str) -> dict[str, str]:
    """The engagement's primary contact as an email recipient: address, first
    name and name. Empty values when there is none or it cannot be read; the
    composer then names the missing recipient when the mentor presses Send."""
    if not contact_id:
        return {"email": "", "firstName": "", "name": ""}
    try:
        c = await client.get("Contact", contact_id, select="name,firstName,emailAddress")
    except EspoError as exc:
        log.warning("evaluation: primary contact %s not read: %s", contact_id, exc)
        return {"email": "", "firstName": "", "name": ""}
    return {"email": c.get("emailAddress") or "", "firstName": c.get("firstName") or "",
            "name": c.get("name") or ""}


async def compose_email(client: Any, *, org: str, base_url: str, link: dict[str, Any],
                        contact_id: str, surveys: dict[str, Survey]) -> dict[str, str]:
    """What the composer opens with: the recipient, the subject and the body,
    the link inside it."""
    from . import email as eval_email

    who = await recipient(client, contact_id)
    titles = []
    for key in link_data(link).get("area_keys") or []:
        survey = latest(surveys, key)
        titles.append(survey.title if survey else key)
    filled = eval_email.invitation(
        org=org, first_name=who["firstName"], area_titles=titles,
        link_url=link_url(base_url, link["token"]), expires_at=link["expires_at"],
        profile_needed=bool(link_data(link).get("profile_needed")))
    return {"to": who["email"], "toName": who["name"], **filled}


# --- Resend, Expire, Record a decline (step 5) ----------------------------------

async def links_for_engagement(store: Any, engagement_id: str) -> list[dict[str, Any]]:
    """Every Business Evaluation link made for one engagement, oldest first."""
    return await store.links_for_record(service.PURPOSE, ENGAGEMENT, engagement_id)


def current_link(links: list[dict[str, Any]], round_no: int) -> Optional[dict[str, Any]]:
    """The round's newest link."""
    return max((l for l in links if link_data(l).get("round") == round_no),
               key=lambda l: l["created_at"], default=None)


async def _round(client: Any, store: Any, engagement_id: str, round_no: int
                 ) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]]]:
    if store is None:
        raise SendError("Evaluations need the application database, which is not "
                        "configured here.")
    records = [r for r in await list_records(client, engagement_id)
               if (r.get("evaluationRound") or 0) == round_no]
    if not records:
        raise SendError(f"Round {round_no} is not on this engagement.")
    link = current_link(await links_for_engagement(store, engagement_id), round_no)
    return records, link


async def resend(client: Any, store: Any, *, engagement_id: str, round_no: int,
                 created_by: str, days: int, now: Optional[datetime] = None) -> dict[str, Any]:
    """A new link for the round that ends the old one (BE12). The client's
    saved answers and consent move with it. Refused when the client has
    nothing left to answer in the round."""
    records, old = await _round(client, store, engagement_id, round_no)
    if old is None:
        raise SendError(f"Round {round_no} has no link to resend. Use Send Evaluation.")
    if not any(r.get("status") in OPEN_STATUSES + (STATUS_EXPIRED,) for r in records):
        raise SendError(f"Nothing in round {round_no} is left for the client to answer.")
    now = now or service.utcnow()
    new = await store.replace_link(old, created_by=created_by, days=days, now=now)
    started = {row.get("crm_record_id") for row in await store.answers_for(new["id"])
               if row.get("answers")}
    reopened = []
    for r in records:
        if r.get("status") == STATUS_EXPIRED:
            # An expired area is open again on the new link: In Progress when
            # the client had begun it, else Sent.
            to = service.STATUS_IN_PROGRESS if r["id"] in started else STATUS_SENT
            await client.update(service.ENTITY, r["id"], {"status": to})
            reopened.append({"id": r["id"], "area": r.get("evaluationArea") or "",
                             "status": {"from": STATUS_EXPIRED, "to": to}})
    return {"round": round_no, "link": new, "previousLink": old, "changed": reopened}


async def _set_status(client: Any, records: list[dict[str, Any]], applies: tuple[str, ...],
                      to: str) -> list[dict[str, Any]]:
    changed = []
    for r in records:
        if r.get("status") in applies:
            await client.update(service.ENTITY, r["id"], {"status": to})
            changed.append({"id": r["id"], "area": r.get("evaluationArea") or "",
                            "status": {"from": r.get("status"), "to": to}})
    return changed


async def expire(client: Any, store: Any, *, engagement_id: str, round_no: int,
                 now: Optional[datetime] = None) -> dict[str, Any]:
    """End the round's link and set its open records to Expired."""
    records, link = await _round(client, store, engagement_id, round_no)
    ended = bool(link) and await store.end_link(link["id"], now or service.utcnow())
    changed = await _set_status(client, records, OPEN_STATUSES, STATUS_EXPIRED)
    return {"round": round_no, "linkEnded": ended, "changed": changed}


async def decline(client: Any, store: Any, *, engagement_id: str, round_no: int,
                  now: Optional[datetime] = None) -> dict[str, Any]:
    """Record a decline (BE14): Declined on every record of the round not yet
    submitted, and the link ended, since nothing is left to answer."""
    records, link = await _round(client, store, engagement_id, round_no)
    changed = await _set_status(client, records, OPEN_STATUSES + (STATUS_EXPIRED,),
                                STATUS_DECLINED)
    ended = bool(link) and await store.end_link(link["id"], now or service.utcnow())
    return {"round": round_no, "linkEnded": ended, "changed": changed}


def status_fields(changed: list[dict[str, Any]]) -> dict[str, Any]:
    """``CActionLog.details["fields"]`` for a round's status change (ruling
    Q5.4): the old values as they stood, the new value."""
    if not changed:
        return {}
    olds = sorted({c["status"]["from"] for c in changed if c["status"].get("from")})
    return {"status": {"from": ", ".join(olds), "to": changed[0]["status"]["to"]}}
