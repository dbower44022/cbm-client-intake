"""V2 Phase 1 delivery worker — see prds/v2/CBM_Intake_V2_Technical_Design.md §5.3.

Claims captured submissions from the durable store and delivers them into
EspoCRM, retrying transient failures with backoff. Delivery is resumable
(``core.resumable``), so a retry after a partial failure completes the missing
records without duplicating the ones already created.

Run as its own App Platform component:  python -m worker
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx

from core import store as store_mod
from core.config import Settings, get_settings
from core.espo import DryRunEspoClient, EspoApi, EspoClient, EspoError
from core.resumable import ResumableClient
from core.store import Claimed, SubmissionStore
from core.submission_log import (
    REASON_NORMAL,
    REASON_ORCHESTRATOR_ERROR,
    STATUS_NEW,
    STATUS_PROCESSED,
    log_submission,
)
from forms import SPECS_BY_SLUG

log = logging.getLogger("cbm_intake.worker")

# Backoff schedule (seconds) indexed by attempt number: 1m, 5m, 30m, 2h, 6h.
_BACKOFF = [60, 300, 1800, 7200, 21600]


def _client(settings: Settings) -> EspoApi:
    if settings.espo_dry_run:
        return DryRunEspoClient()
    return EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )


def _is_transient(exc: Exception) -> bool:
    """Retry network blips and CRM 5xx/408/429; treat 4xx (bad data) as permanent."""
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, EspoError):
        match = re.search(r"HTTP (\d{3})", str(exc))
        if match:
            code = int(match.group(1))
            return code >= 500 or code in (408, 429)
        return True  # an EspoError without a clear code — give it the benefit of the doubt
    return False  # unexpected exception types are not retried


def _backoff_seconds(attempt: int) -> int:
    return _BACKOFF[min(attempt, len(_BACKOFF)) - 1]


async def process_one(store: SubmissionStore, settings: Settings, claimed: Claimed) -> None:
    spec = SPECS_BY_SLUG.get(claimed.form_slug)
    if spec is None:
        await store.mark_failed(
            claimed.id, status=store_mod.STATUS_NEEDS_ATTENTION,
            error=f"unknown form '{claimed.form_slug}'",
        )
        return

    submission = spec.submission_model.model_validate(claimed.payload)
    base = _client(settings)

    async def _save(progress: dict) -> None:
        await store.save_progress(claimed.id, progress)

    client = ResumableClient(base, claimed.progress, _save)

    try:
        ids = await spec.orchestrator(submission, client)
    except Exception as exc:  # noqa: BLE001 — classify + route, never crash the loop
        attempt = (claimed.attempt_count or 0) + 1
        if _is_transient(exc) and attempt < settings.max_delivery_attempts:
            next_at = datetime.now(timezone.utc) + timedelta(seconds=_backoff_seconds(attempt))
            await store.mark_retry(
                claimed.id, attempt_count=attempt, next_attempt_at=next_at, error=str(exc)
            )
            log.warning("retry %s (attempt %s): %s", claimed.id, attempt, exc)
        else:
            await store.mark_failed(
                claimed.id, status=store_mod.STATUS_NEEDS_ATTENTION, error=str(exc)
            )
            await log_submission(
                base, spec.slug, submission,
                reason=REASON_ORCHESTRATOR_ERROR, status=STATUS_NEW,
            )
            log.error("needs_attention %s (attempt %s): %s", claimed.id, attempt, exc)
        return

    await log_submission(
        base, spec.slug, submission,
        reason=REASON_NORMAL, status=STATUS_PROCESSED, contact_id=ids.get("contactId"),
    )
    await store.mark_completed(claimed.id, ids)
    log.info("delivered %s -> %s", claimed.id, ids)


async def run_once(store: SubmissionStore, settings: Settings) -> int:
    """Claim and deliver one batch. Returns how many were claimed."""
    claimed = await store.claim_batch(settings.worker_batch_size)
    for item in claimed:
        await process_one(store, settings, item)
    return len(claimed)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    store = store_mod.make_store(settings)
    if store is None:
        # No database configured (e.g. before Phase 1 is activated). Stay up but
        # idle rather than crash-loop, so the component can be deployed early.
        log.warning("worker idle: DATABASE_URL is not set")
        while True:
            await asyncio.sleep(60)

    await store.create_all()
    log.info(
        "worker started (async_delivery=%s, dry_run=%s, batch=%s)",
        settings.async_delivery, settings.espo_dry_run, settings.worker_batch_size,
    )
    while True:
        claimed = await run_once(store, settings)
        if claimed == 0:
            await asyncio.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    asyncio.run(main())
