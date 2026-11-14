"""The survey engine's rules about links and submits.

* **A link that is unknown, expired, replaced, or whose purpose is switched
  off is one answer**: not valid. Nothing tells the caller which, and
  checking never calls the CRM.
* **A submitted survey is handed to its purpose's submit step.** A refusal
  keeps the answers and the worker retries (``run_retry_cycle``) with backoff:
  1 minute, 5 minutes, 30 minutes, 2 hours, then every 6 hours.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from . import registry
from .definitions import Survey
from .registry import SubmitContext, SurveyPurpose

log = logging.getLogger("cbm_intake.surveys")

#: Backoff after a refused submit: 1m, 5m, 30m, 2h, then every 6h.
RETRY_STEPS = (60, 300, 1800, 7200, 21600)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def link_is_open(link: Optional[dict[str, Any]], now: Optional[datetime] = None) -> bool:
    if not link or link.get("replaced_at"):
        return False
    return (now or utcnow()) < link["expires_at"]


def next_retry(attempts: int, now: datetime) -> datetime:
    step = RETRY_STEPS[min(attempts, len(RETRY_STEPS) - 1)]
    return now + timedelta(seconds=step)


async def deliver_row(store: Any, purpose: SurveyPurpose, client: Any, link: dict[str, Any],
                      row: dict[str, Any], surveys: dict[str, Survey]) -> bool:
    """Hand one submitted survey to its purpose and record the outcome. True
    when the purpose has taken it."""
    survey = surveys.get(row["survey_version"])
    now = utcnow()
    if survey is None:
        await store.mark_failed(row["id"], f"survey {row['survey_version']} is not on this build",
                                next_retry(row.get("attempts") or 0, now))
        return False
    try:
        await purpose.submit(SubmitContext(link=link, row=row, survey=survey, client=client))
    except purpose.retryable as exc:
        log.warning("survey %s %s %s not handed on (attempt %s): %s", purpose.key, row["id"],
                    row["survey_version"], (row.get("attempts") or 0) + 1, exc)
        await store.mark_failed(row["id"], str(exc), next_retry(row.get("attempts") or 0, now))
        return False
    await store.mark_delivered(row["id"], now)
    log.info("survey %s %s %s handed on", purpose.key, row["id"], row["survey_version"])
    return True


async def first_save(purpose: SurveyPurpose, client: Any, link: dict[str, Any],
                     row: dict[str, Any], survey: Survey) -> None:
    """The purpose's first-save step, best-effort: it never fails the save."""
    if purpose.first_save is None:
        return
    try:
        await purpose.first_save(SubmitContext(link=link, row=row, survey=survey, client=client))
    except Exception as exc:  # noqa: BLE001 — best-effort by contract
        log.warning("survey %s %s: first-save step failed: %s", purpose.key, row.get("id"), exc)


async def run_retry_cycle(store: Any, purpose: SurveyPurpose, client: Any,
                          surveys: Optional[dict[str, Survey]] = None) -> dict[str, int]:
    """The worker's pass for one purpose: every submitted survey on its links
    that has not been handed on yet. ``surveys`` defaults to the purpose's
    registered definitions."""
    surveys = surveys if surveys is not None else registry.definitions(purpose.key)
    if surveys is None:
        return {"written": 0, "refused": 0}
    done = failed = 0
    for row in await store.due(utcnow()):
        link = await store.link_by_id(row["link_id"])
        if link is None or link.get("purpose") != purpose.key:
            continue
        if await deliver_row(store, purpose, client, link, row, surveys):
            done += 1
        else:
            failed += 1
    if done or failed:
        log.info("survey retry %s: %s written, %s still refused", purpose.key, done, failed)
    return {"written": done, "refused": failed}
