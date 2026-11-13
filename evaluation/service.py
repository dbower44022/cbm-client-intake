"""The Business Evaluation's client side (plan § 3 step 3; rulings BE8, BE11,
BE12, BE13): link checks, answer checks, the readable text, and the CRM write
on submit.

Rules kept here:

* **A link that is unknown, expired or replaced is one answer**: not valid.
  Nothing tells the caller which, and checking never calls the CRM.
* **Answers save in the application database as the client goes** and reach
  the CRM only on submit. A submitted survey never changes.
* **Nothing is submitted without consent** (BE11); the consent time goes on
  every Business Evaluation record the link submits.
* **The CRM write runs under the org-wide key.** A refusal keeps the answers,
  tells the client they are safe, and the worker retries
  (``run_retry_cycle``) with backoff.
* **The business profile goes to the client profile**, area answers to the
  area's Business Evaluation record.
"""

from __future__ import annotations

import html
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from core.espo import EspoError

from .surveys import PROFILE_KEY, Question, Survey

log = logging.getLogger("cbm_intake.evaluation")

ENTITY = "CBusinessEvaluation"
CLIENT_PROFILE = "CClientProfile"

STATUS_IN_PROGRESS = "In Progress"
STATUS_SUBMITTED = "Submitted"

# What the page shows for a survey.
NOT_STARTED, IN_PROGRESS, SUBMITTED = "not_started", "in_progress", "submitted"

#: Backoff after a refused CRM write: 1m, 5m, 30m, 2h, then every 6h.
RETRY_STEPS = (60, 300, 1800, 7200, 21600)

SHORT_MAX = 500
LONG_MAX = 5000
NUMBER_MAX = 1e12


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def crm_stamp(at: datetime) -> str:
    """EspoCRM stores datetimes as UTC with no offset."""
    return at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def link_is_open(link: Optional[dict[str, Any]], now: Optional[datetime] = None) -> bool:
    if not link or link.get("replaced_at"):
        return False
    return (now or utcnow()) < link["expires_at"]


def survey_keys(link: dict[str, Any]) -> list[str]:
    """The surveys a link opens, in the order the client answers them: the
    business profile first when the engagement does not have one yet (BE8)."""
    keys = [PROFILE_KEY] if link.get("profile_needed") else []
    return keys + [k for k in link.get("area_keys") or [] if k != PROFILE_KEY]


def state_of(row: Optional[dict[str, Any]]) -> str:
    if not row:
        return NOT_STARTED
    if row.get("submitted_at"):
        return SUBMITTED
    return IN_PROGRESS if row.get("answers") else NOT_STARTED


# --- answers -----------------------------------------------------------------

def _blank(value: Any) -> bool:
    return value is None or value == "" or value == []


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip().replace(",", "").replace("$", "")
        try:
            number = float(text)
        except ValueError:
            return None
    else:
        return None
    if math.isnan(number) or math.isinf(number) or abs(number) > NUMBER_MAX:
        return None
    return int(number) if number.is_integer() else number


def check_value(q: Question, value: Any) -> tuple[Any, Optional[str]]:
    """A value in its stored form, or the reason it cannot be accepted."""
    if q.type in ("short_text", "long_text"):
        if not isinstance(value, str):
            return None, "Please type an answer."
        limit = SHORT_MAX if q.type == "short_text" else LONG_MAX
        text = value.strip()
        if len(text) > limit:
            return None, f"Please keep this under {limit} characters."
        return text, None
    if q.type == "single_choice":
        if value not in q.options:
            return None, "Please choose one of the answers."
        return value, None
    if q.type == "multiple_choice":
        if not isinstance(value, list) or not all(v in q.options for v in value):
            return None, "Please choose from the answers."
        picked = [o for o in q.options if o in value]
        if q.max and len(picked) > q.max:
            return None, f"Please choose no more than {q.max}."
        return picked, None
    if q.type == "yes_no":
        if value not in ("Yes", "No"):
            return None, "Please choose yes or no."
        return value, None
    if q.type == "scale":
        number = _number(value)
        if number is None or number not in (1, 2, 3, 4, 5):
            return None, "Please choose a number from 1 to 5."
        return int(number), None
    number = _number(value)
    if number is None:
        return None, "Please enter a number."
    if q.type == "currency" and number < 0:
        return None, "Please enter an amount of zero or more."
    return number, None


def clean_answers(survey: Survey, raw: Any) -> tuple[dict[str, Any], dict[str, str]]:
    """The answers this survey can store, and a message per question whose
    value cannot be. Unknown question ids are dropped; blanks are left out."""
    if not isinstance(raw, dict):
        return {}, {}
    kept: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for qid, value in raw.items():
        question = survey.questions.get(qid)
        if question is None or _blank(value):
            continue
        stored, error = check_value(question, value)
        if error:
            errors[qid] = error
        elif not _blank(stored):
            kept[qid] = stored
    return kept, errors


def missing_required(survey: Survey, answers: dict[str, Any]) -> dict[str, str]:
    return {q.id: "This question needs an answer." for q in survey.questions.values()
            if q.required and _blank(answers.get(q.id))}


def _shown(q: Question, value: Any) -> str:
    if _blank(value):
        return "Not answered"
    if isinstance(value, list):
        return "; ".join(value)
    if q.type == "currency":
        return f"${value:,}" if isinstance(value, int) else f"${value:,.2f}"
    if q.type == "scale":
        ends = f" ({q.low} to {q.high})" if q.low and q.high else ""
        return f"{value} out of 5{ends}"
    return str(value)


def readable_html(survey: Survey, answers: dict[str, Any]) -> str:
    """The answers as question-and-answer text for reviewers (answersReadable)."""
    parts = [f"<p><em>{html.escape(survey.title)} survey, version {survey.version}</em></p>"]
    for section in survey.sections:
        parts.append(f"<h3>{html.escape(section.title)}</h3>")
        for q in section.questions:
            shown = html.escape(_shown(q, answers.get(q.id))).replace("\n", "<br>")
            parts.append(f"<p><strong>{html.escape(q.label)}</strong><br>{shown}</p>")
    return "\n".join(parts)


def answers_json(survey: Survey, answers: dict[str, Any]) -> str:
    """The answers as JSON for the analysis: version-stamped, in question order."""
    ordered = {q.id: answers[q.id] for s in survey.sections for q in s.questions if q.id in answers}
    return json.dumps({"survey": survey.ref, "answers": ordered}, ensure_ascii=False)


# --- the CRM -------------------------------------------------------------------

async def mark_in_progress(client: Any, record_id: str) -> None:
    """Best-effort: the area's record moves from Sent to In Progress on the
    client's first save. Never fails the save."""
    try:
        await client.update(ENTITY, record_id, {"status": STATUS_IN_PROGRESS})
    except EspoError as exc:
        log.warning("evaluation %s: In Progress not written: %s", record_id, exc)


async def deliver(client: Any, link: dict[str, Any], row: dict[str, Any],
                  survey: Survey) -> None:
    """Write one submitted survey to the CRM. Raises ``EspoError`` on refusal."""
    answers = row.get("answers") or {}
    submitted = row["submitted_at"]
    if survey.key == PROFILE_KEY:
        await client.update(CLIENT_PROFILE, link["client_profile_id"], {
            "evaluationProfile": answers_json(survey, answers),
            "evaluationProfileAt": crm_stamp(submitted),
        })
        return
    if not row.get("crm_record_id"):
        raise EspoError(f"no Business Evaluation record for {survey.key} on this link")
    payload: dict[str, Any] = {
        "answers": answers_json(survey, answers),
        "answersReadable": readable_html(survey, answers),
        "surveyVersion": survey.ref,
        "submittedAt": crm_stamp(submitted),
        "status": STATUS_SUBMITTED,
    }
    if link.get("consent_at"):
        payload["consentAt"] = crm_stamp(link["consent_at"])
    await client.update(ENTITY, row["crm_record_id"], payload)


def next_retry(attempts: int, now: datetime) -> datetime:
    step = RETRY_STEPS[min(attempts, len(RETRY_STEPS) - 1)]
    return now + timedelta(seconds=step)


async def deliver_row(store: Any, client: Any, link: dict[str, Any], row: dict[str, Any],
                      surveys: dict[str, Survey]) -> bool:
    """Deliver and record the outcome. True when the CRM has it."""
    survey = surveys.get(row["survey_version"])
    now = utcnow()
    if survey is None:
        await store.mark_failed(row["id"], f"survey {row['survey_version']} is not on this build",
                                next_retry(row.get("attempts") or 0, now))
        return False
    try:
        await deliver(client, link, row, survey)
    except EspoError as exc:
        log.warning("evaluation %s %s not written to the CRM (attempt %s): %s",
                    row["id"], row["survey_version"], (row.get("attempts") or 0) + 1, exc)
        await store.mark_failed(row["id"], str(exc), next_retry(row.get("attempts") or 0, now))
        return False
    await store.mark_delivered(row["id"], now)
    log.info("evaluation %s %s written to the CRM", row["id"], row["survey_version"])
    return True


async def run_retry_cycle(store: Any, client: Any, surveys: dict[str, Survey]) -> dict[str, int]:
    """The worker's pass: every submitted survey the CRM has not taken yet."""
    done = failed = 0
    for row in await store.due(utcnow()):
        link = await store.link_by_id(row["link_id"])
        if link is None:
            continue
        if await deliver_row(store, client, link, row, surveys):
            done += 1
        else:
            failed += 1
    if done or failed:
        log.info("evaluation retry: %s written, %s still refused", done, failed)
    return {"written": done, "refused": failed}
