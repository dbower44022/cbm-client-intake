"""A submitted feedback survey becomes a Survey Response record in the CRM
(ruling BE31; decision 1, 11-20-26), and a response that needs follow-up
alerts staff (BE32).

A feedback link's ``data`` holds ``survey_key``, ``moment``, ``contact_id``,
``email``, ``name`` and what the survey is about: ``engagement_id`` and
``mentor_profile_id`` (the engagement's mentor when it was sent), or
``event_id``, and for evaluation feedback ``business_evaluation_id``. Its
``record_id`` is the engagement or the event; its ``display_name`` the company
or the event's name.

Rules kept here:

* **The write runs under the org-wide key** (the API role creates; no other
  role does). A refusal (``EspoError``) keeps the answers and the engine's
  worker pass retries.
* **Replay-safe**: before creating, a response with the same survey, contact
  and submit time is looked for; a retry after a create that landed reuses it.
* **A response about an engagement carries the engagement's
  ``assignedUsers``** (read at submit, so a co-mentor added since sees it),
  which is how its mentor reads it (Mentor Role: read own). Event feedback
  carries none, so no mentor reads it (BE32).
* **The follow-up flag** is set for a score of 6 or below, and for a yes to
  "contact me" or "talk with a mentor" (decision 2); the alert follows,
  once, best-effort.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from core.branding import render_text
from core.config import get_settings
from core.espo import EspoError
from surveys.answers import answers_json, readable_html
from surveys.registry import SubmitContext

from . import config as cfg

log = logging.getLogger("cbm_intake.feedback")


def crm_stamp(at: datetime) -> str:
    return at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def link_data(link: dict[str, Any]) -> dict[str, Any]:
    return link.get("data") or {}


def survey_keys(link: dict[str, Any]) -> list[str]:
    """The engine's ``surveys_for``: a feedback link opens one survey."""
    key = link_data(link).get("survey_key")
    return [key] if key in cfg.SURVEY_KEYS else []


async def entity_available(client: Any) -> bool:
    """True when the CRM has the Survey Response record type."""
    try:
        meta = await client.metadata(f"entityDefs.{cfg.ENTITY}.fields")
    except EspoError:
        return False
    return isinstance(meta, dict) and bool(meta)


async def _moment_options(client: Any) -> Optional[list[str]]:
    try:
        meta = await client.metadata(f"entityDefs.{cfg.ENTITY}.fields.moment")
    except EspoError:
        return None
    return list(meta.get("options") or []) if isinstance(meta, dict) else None


async def _existing(client: Any, survey_key: str, submitted: str,
                    data: dict[str, Any]) -> Optional[dict[str, Any]]:
    page = await client.list(cfg.ENTITY, where=[
        {"type": "equals", "attribute": "surveyKey", "value": survey_key},
        {"type": "equals", "attribute": "submittedAt", "value": submitted},
    ], select="id,contactId,engagementId,eventId,recommendScore,needsFollowUp", max_size=20)
    for row in page.get("list", []):
        if (row.get("contactId") or "") == (data.get("contact_id") or "") \
                and (row.get("engagementId") or "") == (data.get("engagement_id") or "") \
                and (row.get("eventId") or "") == (data.get("event_id") or ""):
            return row
    return None


def response_name(survey_key: str, data: dict[str, Any]) -> str:
    who = (data.get("name") or data.get("email") or "").strip()
    title = cfg.survey_title(survey_key)
    return f"{title} — {who}" if who else title


async def deliver(client: Any, link: dict[str, Any], row: dict[str, Any],
                  survey: Any) -> dict[str, Any]:
    """Write one submitted feedback survey to the CRM; returns the response
    (id plus what the alert needs). Raises ``EspoError`` on refusal."""
    data = link_data(link)
    answers = row.get("answers") or {}
    submitted = crm_stamp(row["submitted_at"])
    score = cfg.score_of(answers)
    reasons = cfg.follow_up_reasons(answers)
    existing = await _existing(client, survey.key, submitted, data)
    payload: dict[str, Any] = {
        "name": response_name(survey.key, data),
        "surveyKey": survey.key,
        "surveyVersion": survey.ref,
        "recommendScore": score,
        "answers": answers_json(survey, answers),
        "answersReadable": render_text(readable_html(survey, answers)),
        "needsFollowUp": bool(reasons),
        "submittedAt": submitted,
    }
    if link.get("consent_at"):
        payload["consentAt"] = crm_stamp(link["consent_at"])
    moment = data.get("moment") or ""
    options = await _moment_options(client)
    if moment and (options is None or moment in options):
        payload["moment"] = moment
    for field, key in (("contactId", "contact_id"), ("engagementId", "engagement_id"),
                       ("mentorProfileId", "mentor_profile_id"), ("eventId", "event_id"),
                       ("businessEvaluationId", "business_evaluation_id")):
        if data.get(key):
            payload[field] = data[key]
    if data.get("engagement_id"):
        eng = await client.get(cfg.ENGAGEMENT, data["engagement_id"], select="assignedUsersIds")
        payload["assignedUsersIds"] = list(eng.get("assignedUsersIds") or [])
    if existing:
        record_id = existing["id"]
    else:
        record_id = (await client.create(cfg.ENTITY, payload))["id"]
        log.info("feedback: %s response %s written (score %s%s)", survey.key, record_id,
                 score, ", needs follow-up" if reasons else "")
    return {"id": record_id, "surveyKey": survey.key, "recommendScore": score,
            "eventId": data.get("event_id") or "", "engagementId": data.get("engagement_id") or "",
            "mentorProfileId": data.get("mentor_profile_id") or "",
            "reasons": reasons, "about": link.get("display_name") or "",
            "who": data.get("name") or data.get("email") or ""}


async def submit(ctx: SubmitContext) -> None:
    """The engine's submit step: the CRM write, then the follow-up alert when
    one is needed (best-effort, never fails the submit)."""
    response = await deliver(ctx.client, ctx.link, ctx.row, ctx.survey)
    if not response["reasons"]:
        return
    try:
        from .alerts import alert_once
        from .runtime import feedback_store

        settings = get_settings()
        await alert_once(settings, ctx.client, feedback_store(settings), response,
                         about=response["about"], who=response["who"],
                         reasons=response["reasons"])
    except Exception as exc:  # noqa: BLE001 — the sweep retries a failed alert
        log.warning("feedback alert for %s not sent: %s", response["id"], exc)


def answers_of(raw: str) -> dict[str, Any]:
    """The answers from a response's JSON, or {}."""
    try:
        data = json.loads(raw or "")
    except ValueError:
        return {}
    return data.get("answers") if isinstance(data, dict) and isinstance(
        data.get("answers"), dict) else {}
