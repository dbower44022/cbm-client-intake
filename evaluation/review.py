"""Review and approval of a Business Evaluation (plan § 3 steps 5 and 6;
rulings BE17 and BE18). Phase 4.

Doug's choices at stopping point (a), 11-14-26, all as recommended:

* **Every reviewer edits ``reviewedReport``**, before and after approval.
  A saved change to an Approved report **withdraws the approval**: the status
  goes back to Draft Ready and ``approvedAt`` / ``approvedBy`` are cleared, so
  the text phase 5 releases is always the text the mentor approved.
* The draft is shown beside the editor, read-only. This module never reads
  or writes the draft (BE17): it is written once, by the analysis.
* No images in the report: the client version is emailed and filed, and its
  readers cannot reach the application's image proxy.
* The review session is either an upcoming session already scheduled on the
  engagement, or a new one made in the session editor; either way it is
  linked to every record of the round (``reviewSession``).

Rules kept here:

* **Writes run as the user**, so the CRM's own access decides who may edit:
  a co-mentor carries the engagement's ``assignedUsers`` stamp, and the
  Mentor Role edits ``own`` (BE18). Only a link a role cannot set
  (``approvedBy`` naming a User, ``reviewSession`` naming a session) is
  retried under the org-wide key, on a 403 alone.
* **Only the engagement's mentor approves** (BE17): the login on the
  engagement's mentor profile. A co-mentor is told why, by name; the button
  is never hidden. Administrators get no exemption.
* **A save made over someone else's newer save is refused**, naming who
  saved and when, so two reviewers never overwrite each other unseen.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Callable, Optional

from core.espo import EspoError, is_forbidden

from . import service
from .service import ENGAGEMENT

log = logging.getLogger("cbm_intake.evaluation")

STATUS_DRAFT_READY = "Draft Ready"
STATUS_APPROVED = "Approved"
#: The statuses whose reviewed report can be edited.
EDITABLE = (STATUS_DRAFT_READY, STATUS_APPROVED)
#: Statuses that still owe a draft or an approval: a round with any of them is
#: not ready for its review session.
NOT_READY = (service.STATUS_SUBMITTED, "Analysis Failed", STATUS_DRAFT_READY)

MENTOR_PROFILE = "CMentorProfile"
SESSION = "CSession"
#: CEngagement's link to its sessions, and CSession's link to the engagement.
ENGAGEMENT_SESSIONS_LINK = "engagementSessions"
SESSION_ENGAGEMENT_ATTR = "engagementId"

#: The report's reviewers-only section, which phase 5's client version drops.
INTERNAL_MARKER = "data-internal"


class ReviewError(Exception):
    """A request that cannot be done, with the words to show (400)."""


class NotTheMentor(ReviewError):
    """Approve pressed by someone other than the engagement's mentor (403)."""


class Conflict(ReviewError):
    """Someone else saved the report after this reviewer opened it (409)."""


def _same(a: Optional[str], b: Optional[str]) -> bool:
    """Compare report HTML as a reader would: the CRM reads an empty value
    back as null and may normalise whitespace (``core/receipts._same``)."""
    def norm(x: Optional[str]) -> str:
        return re.sub(r"\s+", " ", x or "").strip()
    return norm(a) == norm(b)


def _text(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "")


def marker_lost(before: str, after: str) -> bool:
    """True when a save dropped the reviewers-only marker but kept the
    section's heading: the client version would then carry it."""
    return (INTERNAL_MARKER in (before or "") and INTERNAL_MARKER not in (after or "")
            and "points to check" in _text(after).lower())


MARKER_WARNING = (
    "The \"Points to check\" section lost its reviewers-only marker in this save, "
    "so it would go to the client with the report. Delete the section if it is no "
    "longer wanted; to restore the marker, ask {abbr} staff.")


def marker_warning() -> str:
    from core.branding import abbr

    return MARKER_WARNING.format(abbr=abbr())


async def _record(client: Any, engagement_id: str, record_id: str,
                  select: str) -> dict[str, Any]:
    rec = await client.get(service.ENTITY, record_id, select="id,engagementId," + select)
    if rec.get("engagementId") != engagement_id:
        raise ReviewError("That evaluation is not on this engagement.")
    return rec


async def _update(client: Any, escalate: Optional[Callable[[], Any]],
                  entity: str, record_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Write as the user; retry under the org-wide key only on a refusal."""
    try:
        return await client.update(entity, record_id, payload) or {}
    except EspoError as exc:
        key = escalate() if escalate and is_forbidden(exc) else None
        if key is None:
            raise
        log.info("evaluation: %s/%s update refused as the user (%s); under the org-wide key",
                 entity, record_id, exc)
        return await key.update(entity, record_id, payload) or {}


# --- the engagement's mentor ---------------------------------------------------

async def engagement_mentor(client: Any, engagement_id: str,
                            reader: Optional[Any] = None) -> dict[str, Any]:
    """The engagement's mentor: profile id, name and whether a given user is
    them is answered by :func:`is_mentor`. ``reader`` (the org-wide key, when
    there is one) reads the mentor profile, which a co-mentor may not."""
    eng = await client.get(ENGAGEMENT, engagement_id, select="mentorProfileId,mentorProfileName")
    profile_id = eng.get("mentorProfileId") or ""
    profile: dict[str, Any] = {}
    if profile_id:
        for who in (reader, client):
            if who is None:
                continue
            try:
                profile = await who.get(MENTOR_PROFILE, profile_id,
                                        select="assignedUserId,assignedUsersIds")
                break
            except EspoError as exc:
                log.warning("evaluation: mentor profile %s not read: %s", profile_id, exc)
    return {"profileId": profile_id, "name": eng.get("mentorProfileName") or "",
            "profile": profile}


def is_mentor(mentor: dict[str, Any], user_id: str) -> bool:
    from assignments.service import is_assigned_to

    return bool(mentor.get("profile")) and is_assigned_to(mentor["profile"], user_id)


# --- Save the reviewed report (BE17, BE18) ---------------------------------------

async def save_report(client: Any, engagement_id: str, record_id: str, *, html: str,
                      base: Optional[str]) -> dict[str, Any]:
    """Write the reviewed report as the user. ``base`` is the reviewed report
    the reviewer opened; a different stored one is someone else's newer save,
    and the write is refused. A change to an Approved report withdraws the
    approval. Returns what changed, for the action log, and a warning when
    the reviewers-only marker was lost."""
    rec = await _record(client, engagement_id, record_id, (
        "evaluationArea,evaluationRound,status,reviewedReport,approvedAt,approvedById,"
        "approvedByName,modifiedAt,modifiedByName"))
    status = rec.get("status") or ""
    if status not in EDITABLE:
        raise ReviewError(
            f"This report cannot be edited while the evaluation is {status or 'without a status'}: "
            "a report is edited once its draft is ready.")
    stored = rec.get("reviewedReport") or ""
    if base is not None and not _same(base, stored):
        who = rec.get("modifiedByName") or "Another reviewer"
        raise Conflict(
            f"{who} saved this report after you opened it, so your save was not made. "
            "Your text is still in the editor: copy what you need, then close and reopen "
            "the report to see their version.")
    if _same(html, stored):
        return {"changed": False, "area": rec.get("evaluationArea") or "",
                "status": status, "fields": {}, "warning": None, "stored": stored}
    payload: dict[str, Any] = {"reviewedReport": html}
    fields: dict[str, Any] = {"reviewed report": {
        "from": f"{len(_text(stored).split())} words",
        "to": f"{len(_text(html).split())} words"}}
    withdrawn = status == STATUS_APPROVED
    if withdrawn:
        payload.update(status=STATUS_DRAFT_READY, approvedAt=None, approvedById=None)
        fields["status"] = {"from": STATUS_APPROVED, "to": STATUS_DRAFT_READY}
        fields["approved by"] = {"from": rec.get("approvedByName") or "", "to": ""}
    saved = await client.update(service.ENTITY, record_id, payload) or {}
    after = saved.get("reviewedReport") if "reviewedReport" in saved else html
    lost = marker_lost(stored, after or "")
    return {"changed": True, "area": rec.get("evaluationArea") or "",
            "round": rec.get("evaluationRound"), "stored": after or "",
            "status": STATUS_DRAFT_READY if withdrawn else status,
            "approvalWithdrawn": withdrawn, "fields": fields,
            "warning": marker_warning() if lost else None}


# --- Approve (BE17) ----------------------------------------------------------------

async def approve(client: Any, engagement_id: str, record_id: str, *, user_id: str,
                  escalate: Optional[Callable[[], Any]] = None,
                  now: Optional[datetime] = None) -> dict[str, Any]:
    """Approve as the engagement's mentor: status Approved, ``approvedAt``,
    ``approvedBy``. Raises ``NotTheMentor`` for anyone else, naming the
    mentor, and ``ReviewError`` when the report is not ready to approve."""
    rec = await _record(client, engagement_id, record_id,
                        "evaluationArea,evaluationRound,status,approvedAt,approvedByName")
    area = rec.get("evaluationArea") or "This evaluation"
    mentor = await engagement_mentor(client, engagement_id,
                                     reader=escalate() if escalate else None)
    if not is_mentor(mentor, user_id):
        name = mentor["name"] or "the engagement's mentor"
        raise NotTheMentor(
            f"Only the engagement's mentor, {name}, can approve a report. You can still "
            f"edit it; {name} approves it once the reviewers are done.")
    status = rec.get("status") or ""
    if status == STATUS_APPROVED:
        raise ReviewError(f"{area} is already approved"
                          + (f" by {rec['approvedByName']}." if rec.get("approvedByName") else "."))
    if status != STATUS_DRAFT_READY:
        raise ReviewError(f"There is no report to approve yet: {area} is "
                          f"{status or 'without a status'}.")
    now = now or service.utcnow()
    await _update(client, escalate, service.ENTITY, record_id, {
        "status": STATUS_APPROVED, "approvedAt": service.crm_stamp(now),
        "approvedById": user_id})
    return {"id": record_id, "area": rec.get("evaluationArea") or "",
            "round": rec.get("evaluationRound"), "approvedAt": service.crm_stamp(now),
            "fields": {"status": {"from": status, "to": STATUS_APPROVED},
                       "approved at": {"from": "", "to": service.crm_stamp(now)}}}


# --- The review session (plan § 3 step 6) ---------------------------------------------

async def _round_records(client: Any, engagement_id: str, round_no: int) -> list[dict[str, Any]]:
    from .sending import list_records

    return [r for r in await list_records(client, engagement_id)
            if (r.get("evaluationRound") or 0) == round_no]


def readiness(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Whether a round is ready for its review session: every area with a
    draft (or one still being written) Approved, and at least one Approved.
    Areas the client never submitted are left out."""
    waiting = sorted(r.get("evaluationArea") or "" for r in records
                     if (r.get("status") or "") in NOT_READY)
    approved = sorted(r.get("evaluationArea") or "" for r in records
                      if (r.get("status") or "") == STATUS_APPROVED)
    if waiting:
        message = ("Approve every report in this round before scheduling its review "
                   f"session. Still waiting: {', '.join(waiting)}.")
    elif not approved:
        message = "No report in this round is approved yet, so there is nothing to review with the client."
    else:
        message = ""
    return {"ready": not message, "waiting": waiting, "approved": approved, "message": message}


async def upcoming_sessions(client: Any, engagement_id: str,
                            now: Optional[datetime] = None) -> list[dict[str, Any]]:
    """The engagement's Scheduled sessions that have not started, soonest first."""
    now_stamp = service.crm_stamp(now or service.utcnow())
    page = await client.list_related(ENGAGEMENT, engagement_id, ENGAGEMENT_SESSIONS_LINK,
                                     select="id,name,status,dateStart", max_size=200)
    rows = [s for s in page.get("list", []) or []
            if s.get("status") == "Scheduled" and (s.get("dateStart") or "") >= now_stamp]
    rows.sort(key=lambda s: s.get("dateStart") or "")
    return [{"id": s["id"], "name": s.get("name") or "", "dateStart": s.get("dateStart")}
            for s in rows]


async def review_session_view(client: Any, engagement_id: str, round_no: int) -> dict[str, Any]:
    """What the Schedule review session dialog needs: readiness, the session
    already linked (if any) and the upcoming sessions to pick from."""
    records = await _round_records(client, engagement_id, round_no)
    if not records:
        raise ReviewError(f"There is no round {round_no} on this engagement.")
    current = next((r for r in records if r.get("reviewSessionId")), None)
    try:
        upcoming = await upcoming_sessions(client, engagement_id)
    except EspoError as exc:
        log.warning("evaluation: sessions of %s not read: %s", engagement_id, exc)
        upcoming = []
    return {"round": round_no, **readiness(records),
            "current": ({"id": current["reviewSessionId"],
                         "name": current.get("reviewSessionName") or ""} if current else None),
            "upcoming": upcoming}


async def link_review_session(client: Any, engagement_id: str, round_no: int, session_id: str,
                              *, escalate: Optional[Callable[[], Any]] = None) -> dict[str, Any]:
    """Link a session of this engagement to every record of the round. Refused
    while the round is not ready, or for a session of another engagement."""
    records = await _round_records(client, engagement_id, round_no)
    if not records:
        raise ReviewError(f"There is no round {round_no} on this engagement.")
    ready = readiness(records)
    if not ready["ready"]:
        raise ReviewError(ready["message"])
    sess = await client.get(SESSION, session_id, select=f"id,name,{SESSION_ENGAGEMENT_ATTR}")
    if sess.get(SESSION_ENGAGEMENT_ATTR) != engagement_id:
        raise ReviewError("That session is not on this engagement.")
    before = next((r.get("reviewSessionName") or r.get("reviewSessionId")
                   for r in records if r.get("reviewSessionId")), "")
    linked = []
    for r in records:
        if r.get("reviewSessionId") == session_id:
            continue
        await _update(client, escalate, service.ENTITY, r["id"], {"reviewSessionId": session_id})
        linked.append(r["id"])
    return {"round": round_no, "session": {"id": session_id, "name": sess.get("name") or ""},
            "records": linked,
            "fields": {"review session": {"from": before, "to": sess.get("name") or session_id}}}
