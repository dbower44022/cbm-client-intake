"""What the screens show (decisions 3 and 4, 11-20-26): the responses about an
engagement (the mentor's Feedback tab in Client Management), about a mentor
(Mentor Administration's Feedback tab), about an event (Event
Administration), one response's answers, and Mark follow-up done.

Every read runs **as the signed-in user**, so the CRM decides who sees what:
a mentor reads only responses stamped with them (Mentor Role, read own);
Mentor Administration and Marketing Admin staff read every response.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from core.branding import render_text
from core.espo import EspoError

from . import config as cfg
from .service import answers_of

LIST_SELECT = ("id,name,surveyKey,moment,recommendScore,needsFollowUp,followUpDone,"
               "followUpNote,followUpDoneAt,submittedAt,contactId,contactName,engagementId,"
               "engagementName,eventId,eventName,mentorProfileId,mentorProfileName")
DETAIL_SELECT = LIST_SELECT + ",answers,surveyVersion"

UNAVAILABLE = ("The CRM does not have the Survey Response record type yet, so there is "
               "no feedback to show. An administrator applies "
               "crm-plans/survey-response.json (survey-response-crm-handoff.md).")


class FollowUpError(Exception):
    """A Mark follow-up done the person can correct (shown as given)."""


def row_view(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r.get("id"),
        "survey": cfg.survey_title(r.get("surveyKey") or ""),
        "surveyKey": r.get("surveyKey") or "",
        "moment": r.get("moment") or "",
        "score": r.get("recommendScore"),
        "needsFollowUp": bool(r.get("needsFollowUp")),
        "followUpDone": bool(r.get("followUpDone")),
        "followUpNote": r.get("followUpNote") or "",
        "followUpDoneAt": r.get("followUpDoneAt"),
        "submittedAt": r.get("submittedAt"),
        "contactName": r.get("contactName") or "",
        "engagementId": r.get("engagementId") or "",
        "engagementName": r.get("engagementName") or "",
        "eventId": r.get("eventId") or "",
        "eventName": r.get("eventName") or "",
        "mentorName": r.get("mentorProfileName") or "",
    }


async def list_responses(client: Any, attribute: str, value: str) -> list[dict[str, Any]]:
    """The responses whose link ``attribute`` (engagementId, mentorProfileId
    or eventId) is ``value``, newest first, as the user."""
    page = await client.list(cfg.ENTITY, where=[
        {"type": "equals", "attribute": attribute, "value": value}],
        select=LIST_SELECT, max_size=200)
    rows = [row_view(r) for r in page.get("list", [])]
    rows.sort(key=lambda r: str(r.get("submittedAt") or ""), reverse=True)
    return rows


async def open_follow_ups(client: Any) -> int:
    """How many responses need follow-up and are not done, as the user (the
    home page's *Feedback to follow up* row). Uses the list total."""
    page = await client.list(cfg.ENTITY, where=[
        {"type": "isTrue", "attribute": "needsFollowUp"},
        {"type": "isFalse", "attribute": "followUpDone"},
    ], select="id", max_size=1)
    return int(page.get("total") or len(page.get("list") or []))


async def oldest_open(client: Any, survey_keys: tuple[str, ...]) -> tuple[int, Optional[dict[str, Any]]]:
    """How many responses of these surveys need follow-up and are not done,
    and the oldest of them (the home page's row opens it), as the user."""
    page = await client.list(cfg.ENTITY, where=[
        {"type": "isTrue", "attribute": "needsFollowUp"},
        {"type": "isFalse", "attribute": "followUpDone"},
        {"type": "in", "attribute": "surveyKey", "value": list(survey_keys)},
    ], select="id,surveyKey,eventId,mentorProfileId,submittedAt", order_by="submittedAt",
        order="asc", max_size=1)
    rows = page.get("list") or []
    return int(page.get("total") or len(rows)), (rows[0] if rows else None)


def _sections(survey_ref: str, raw_answers: str) -> list[dict[str, Any]]:
    """The answers as sections of questions and answers (answers stand out
    from questions, Doug 11-16-26), the labels with the organization's name."""
    from surveys.answers import answer_sections
    from surveys.definitions import latest

    from .purpose import surveys

    loaded = surveys() or {}
    data: dict[str, Any] = {}
    try:
        data = json.loads(raw_answers or "") or {}
    except ValueError:
        pass
    ref = (data.get("survey") if isinstance(data, dict) else None) or survey_ref or ""
    survey = loaded.get(ref) or latest(loaded, ref.split(".v")[0])
    if survey is None:
        return []
    sections = answer_sections(survey, answers_of(raw_answers))
    for sec in sections:
        sec["title"] = render_text(sec["title"])
        for item in sec["items"]:
            item["label"] = render_text(item["label"])
    return sections


async def detail(client: Any, response_id: str) -> dict[str, Any]:
    r = await client.get(cfg.ENTITY, response_id, select=DETAIL_SELECT)
    view = row_view(r)
    view["sections"] = _sections(r.get("surveyVersion") or "", r.get("answers") or "")
    view["reasons"] = cfg.follow_up_reasons(answers_of(r.get("answers") or ""))
    return view


def _stamp(at: datetime) -> str:
    return at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def mark_done(client: Any, response_id: str, note: str,
                    now: Optional[datetime] = None) -> dict[str, Any]:
    """Mark a follow-up done with its note (decision 4), as the user. Returns
    the response and the fields changed, old and new, for the action log."""
    note = (note or "").strip()
    if not note:
        raise FollowUpError("Say what was done in the note, then mark the follow-up done.")
    before = await client.get(cfg.ENTITY, response_id, select=DETAIL_SELECT)
    if not before.get("needsFollowUp"):
        raise FollowUpError("This response was not flagged for follow-up.")
    if before.get("followUpDone"):
        raise FollowUpError("This follow-up is already marked done.")
    at = _stamp(now or datetime.now(timezone.utc))
    changes = {"followUpDone": True, "followUpNote": note, "followUpDoneAt": at}
    await client.update(cfg.ENTITY, response_id, changes)
    fields = {k: {"from": before.get(k), "to": v} for k, v in changes.items()}
    return {"response": row_view({**before, **changes}), "fields": fields,
            "name": before.get("name") or ""}


async def engagement_contacts(client: Any, engagement_id: str) -> list[dict[str, Any]]:
    """The engagement's client contacts a mentor may send the survey to: the
    primary contact first. Read as the user."""
    eng = await client.get(cfg.ENGAGEMENT, engagement_id,
                           select="primaryEngagementContactId,primaryEngagementContactName")
    out: list[dict[str, Any]] = []
    primary = eng.get("primaryEngagementContactId") or ""
    if primary:
        out.append({"id": primary, "name": eng.get("primaryEngagementContactName") or "",
                    "primary": True})
    try:
        related = await client.list_related(cfg.ENGAGEMENT, engagement_id, "engagementContacts",
                                            select="id,name,emailAddress", max_size=50)
    except EspoError:
        related = {}
    for row in related.get("list", []):
        if row.get("id") and row["id"] != primary:
            out.append({"id": row["id"], "name": row.get("name") or "", "primary": False})
    return out
