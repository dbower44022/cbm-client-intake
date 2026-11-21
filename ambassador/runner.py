"""Running deliveries: the web's one try, and the worker's retries (PRD § 4.1).

:func:`deliver_one` wraps the organization-wide client in a
``ResumableClient`` over the row's saved progress, runs the chain, and marks
the row delivered or records the failed attempt (backoff 1 minute to 6 hours,
then left failed and logged). :func:`run_cycle` is the worker's pass over the
rows that are due.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from core.resumable import ResumableClient

from . import delivery
from .store import FAILED, ReportStore

log = logging.getLogger("cbm_intake.ambassador")

#: Rows the worker delivers per pass.
BATCH = 10
#: How long the worker holds a row it claimed.
WORKER_LEASE_SECONDS = 600


async def deliver_one(settings: Any, store: ReportStore, client: Any,
                      report: dict[str, Any]) -> Optional[str]:
    """Deliver one captured report. Returns the activity id, or None when
    this attempt failed (the row is left for the next one). Never raises."""

    async def _save(progress: dict[str, Any]) -> None:
        await store.save_progress(report["id"], progress)

    resumable = ResumableClient(client, report.get("progress") or {}, _save)
    try:
        activity_id = await delivery.deliver(resumable, settings, report)
    except Exception as exc:  # noqa: BLE001 — recorded and retried
        status = await store.failed_attempt(report["id"], str(exc))
        level = log.error if status == FAILED else log.warning
        level("ambassador report %s not recorded (%s): %s", report.get("reference"), status, exc)
        return None
    await store.delivered(report["id"], activity_id)
    return activity_id


async def run_cycle(settings: Any, store: ReportStore, client: Any) -> int:
    """Deliver every report that is due; returns how many were recorded."""
    done = 0
    for report in await store.claim_due(BATCH, WORKER_LEASE_SECONDS):
        if await deliver_one(settings, store, client, report):
            done += 1
    if done:
        log.info("ambassador delivery: %d report(s) recorded", done)
    return done
