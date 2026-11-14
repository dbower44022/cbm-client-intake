"""Business Evaluation's client side (plan § 3 step 3; rulings BE8, BE11, BE13):
the surveys a link opens, the CRM write on submit, and the In Progress step
on a survey's first save. The page, the link checks, the answer checks and
the retry are the survey engine's (``surveys/``, ruling BE23).

Rules kept here:

* **The business profile goes to the client profile**, area answers to the
  area's Business Evaluation record.
* **The consent time goes on every Business Evaluation record the link
  submits** (BE11).
* **The CRM write runs under the org-wide key.** A refusal (``EspoError``)
  keeps the answers and the engine's worker pass retries.

A Business Evaluation link's ``data`` holds ``client_profile_id``, ``round``,
``area_keys`` and ``profile_needed``; its ``record_id`` is the engagement and
its ``display_name`` the company name.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core.espo import EspoError
from surveys.answers import answers_json, readable_html
from surveys.registry import SubmitContext

from .surveys import PROFILE_KEY

log = logging.getLogger("cbm_intake.evaluation")

#: The survey purpose key, stored on every Business Evaluation link.
PURPOSE = "business-evaluation"

ENGAGEMENT = "CEngagement"
ENTITY = "CBusinessEvaluation"
CLIENT_PROFILE = "CClientProfile"

STATUS_IN_PROGRESS = "In Progress"
STATUS_SUBMITTED = "Submitted"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def crm_stamp(at: datetime) -> str:
    """EspoCRM stores datetimes as UTC with no offset."""
    return at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def link_data(link: dict[str, Any]) -> dict[str, Any]:
    return link.get("data") or {}


def survey_keys(link: dict[str, Any]) -> list[str]:
    """The surveys a link opens, in the order the client answers them: the
    business profile first when the engagement does not have one yet (BE8)."""
    data = link_data(link)
    keys = [PROFILE_KEY] if data.get("profile_needed") else []
    return keys + [k for k in data.get("area_keys") or [] if k != PROFILE_KEY]


async def mark_in_progress(client: Any, record_id: str) -> None:
    """Best-effort: the area's record moves from Sent to In Progress on the
    client's first save. Never fails the save."""
    try:
        await client.update(ENTITY, record_id, {"status": STATUS_IN_PROGRESS})
    except EspoError as exc:
        log.warning("evaluation %s: In Progress not written: %s", record_id, exc)


async def first_save(ctx: SubmitContext) -> None:
    """The engine's first-save step: In Progress on an area's record. The
    business profile has no record of its own, so nothing happens for it."""
    if ctx.row.get("crm_record_id"):
        await mark_in_progress(ctx.client, ctx.row["crm_record_id"])


async def deliver(client: Any, link: dict[str, Any], row: dict[str, Any], survey) -> None:
    """Write one submitted survey to the CRM. Raises ``EspoError`` on refusal."""
    answers = row.get("answers") or {}
    submitted = row["submitted_at"]
    if survey.key == PROFILE_KEY:
        await client.update(CLIENT_PROFILE, link_data(link)["client_profile_id"], {
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


async def submit(ctx: SubmitContext) -> None:
    """The engine's submit step."""
    await deliver(ctx.client, ctx.link, ctx.row, ctx.survey)
