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
import traceback
from datetime import datetime, timedelta, timezone

import httpx

from core import monitoring
from core import store as store_mod
from core.config import Settings, get_settings
from core.espo import DryRunEspoClient, EspoApi, EspoClient, EspoError, EspoTransportError
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
    if isinstance(exc, EspoTransportError):
        # EspoClient wraps transport failures (P0-3); always retryable.
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

    base = _client(settings)

    async def _save(progress: dict) -> None:
        await store.save_progress(claimed.id, progress)

    client = ResumableClient(base, claimed.progress, _save)

    submission = None
    try:
        # Validation runs INSIDE the classify-and-route net (P0-1): a payload
        # the current schema rejects (e.g. a form schema tightened after
        # capture) is a permanent failure routed to needs_attention — it must
        # never escape and kill the worker process.
        submission = spec.submission_model.model_validate(claimed.payload)
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
            # Store the traceback tail alongside the message so a code bug
            # (e.g. KeyError) landing in needs_attention is diagnosable from
            # /ops, not just a four-character string.
            tail = traceback.format_exc()[-1000:]
            await store.mark_failed(
                claimed.id, status=store_mod.STATUS_NEEDS_ATTENTION,
                error=f"{str(exc)[:800]}\n--- traceback (tail) ---\n{tail}",
            )
            if submission is not None:
                await log_submission(
                    base, spec.slug, submission,
                    reason=REASON_ORCHESTRATOR_ERROR, status=STATUS_NEW,
                )
            log.exception("needs_attention %s (attempt %s): %s", claimed.id, attempt, exc)
        return

    await log_submission(
        base, spec.slug, submission,
        reason=REASON_NORMAL, status=STATUS_PROCESSED, contact_id=ids.get("contactId"),
    )
    await store.mark_completed(claimed.id, ids)
    log.info("delivered %s -> %s", claimed.id, ids)


async def run_once(store: SubmissionStore, settings: Settings) -> int:
    """Claim and deliver one batch. Returns how many were claimed."""
    claimed = await store.claim_batch(
        settings.worker_batch_size, lease_seconds=settings.worker_lease_seconds
    )
    for item in claimed:
        await process_one(store, settings, item)
    return len(claimed)


async def run_cycle(store: SubmissionStore, settings: Settings) -> int:
    """One guarded delivery cycle — what the main loop actually runs.

    Two hardenings from the 2026-07-17 reliability review:

    - **P0-2**: with ``ASYNC_DELIVERY`` off (the documented rollback), the web
      tier delivers synchronously — the worker must NOT also claim the same
      ``pending`` rows or every submission is delivered twice. Flag off ⇒ no
      claiming (the monitoring/comms timers in ``main`` keep running).
    - **P0-1 (loop guard)**: no exception — store failure, claim error,
      anything ``process_one``'s own net misses — may kill the loop. Log it
      with the traceback and report an empty batch so the loop sleeps and
      tries again.
    """
    if not settings.async_delivery:
        return 0
    try:
        return await run_once(store, settings)
    except Exception:  # noqa: BLE001 — nothing may crash the delivery loop
        log.exception("delivery cycle failed — continuing after the poll interval")
        return 0


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
    if not settings.async_delivery:
        log.warning(
            "ASYNC_DELIVERY is off — claim loop disabled; the web tier delivers "
            "synchronously (P0-2 double-delivery guard). Monitoring/comms timers "
            "keep running."
        )

    # Phase 3: alert + schema-drift checks run here on their own cadence.
    alert_state: dict = {}
    next_alert = datetime.now(timezone.utc)
    next_schema = datetime.now(timezone.utc)

    # Documents (DOC-MGMT): the nightly Drive-grant reconciliation (DOC-09) +
    # documentsFolderUrl re-check (DOC-08). Inert unless GDRIVE_DOCS is on and
    # the service-identity access model is active (docs.grants.grants_enabled).
    next_docs = datetime.now(timezone.utc)

    # Communications: Gmail conversation sync (+ optional AI summaries), on its
    # own timer. Inert unless GMAIL_SYNC is on and the pieces are configured.
    comms_store = None
    next_gmail = datetime.now(timezone.utc)
    if settings.gmail_sync:
        from comms.store import make_comms_store

        comms_store = make_comms_store(settings)
        if comms_store is None:
            log.warning("GMAIL_SYNC is on but DATABASE_URL is not set — sync disabled")
        else:
            await comms_store.create_all()
            if settings.gmail_resync:
                await comms_store.reset_all_sync_state()
                log.warning("GMAIL_RESYNC: sync cursors cleared — the next pass "
                            "re-runs the initial backfill; unset the flag after")
            log.info("gmail sync enabled (every %ss)", settings.gmail_sync_seconds)

    while True:
        claimed = await run_cycle(store, settings)

        now = datetime.now(timezone.utc)
        if now >= next_alert:
            try:
                await monitoring.run_alert_check(store, settings, alert_state)
            except Exception as exc:  # noqa: BLE001 — monitoring never crashes the worker
                log.warning("alert check failed: %s", exc)
            next_alert = now + timedelta(seconds=settings.alert_check_seconds)
        if settings.schema_check_seconds > 0 and now >= next_schema:
            try:
                await monitoring.run_schema_drift_check(settings, alert_state)
            except Exception as exc:  # noqa: BLE001
                log.warning("schema-drift check failed: %s", exc)
            next_schema = now + timedelta(seconds=settings.schema_check_seconds)
        if comms_store is not None and now >= next_gmail:
            try:
                await run_gmail_cycle(settings, comms_store)
            except Exception as exc:  # noqa: BLE001 — comms never crashes delivery
                log.warning("gmail sync cycle failed: %s", exc)
            next_gmail = now + timedelta(seconds=settings.gmail_sync_seconds)
        if (
            settings.gdrive_docs
            and settings.gdrive_reconcile_seconds > 0
            and now >= next_docs
        ):
            try:
                from docs.reconcile import run_docs_reconciliation

                await run_docs_reconciliation(settings)
            except Exception as exc:  # noqa: BLE001 — never crashes delivery
                log.warning("docs grant reconciliation failed: %s", exc)
            next_docs = now + timedelta(seconds=settings.gdrive_reconcile_seconds)

        if claimed == 0:
            await asyncio.sleep(settings.worker_poll_seconds)


async def run_gmail_cycle(settings: Settings, comms_store) -> None:
    """One Communications cycle: sync every manager mailbox, then the optional
    summary pass. Credentials resolve like the mailbox check does — the in-app
    Email-Setup config first, else the GOOGLE_* env vars."""
    from comms.summarize import run_summary_pass
    from comms.sync import run_gmail_sync
    from core.app_config import make_app_config_store
    from core.gmail import resolve_gmail_service_account

    google_cfg = None
    cfg_store = make_app_config_store(settings)
    if cfg_store is not None:
        try:
            google_cfg = await cfg_store.get_google_config()
        finally:
            await cfg_store.dispose()
    sa_info = resolve_gmail_service_account(settings, google_cfg)
    if sa_info is None:
        log.warning("gmail sync: no Google service-account credentials configured")
        return
    espo = _client(settings)
    await run_gmail_sync(settings, comms_store, espo, sa_info)
    await run_summary_pass(settings, espo)


if __name__ == "__main__":
    asyncio.run(main())
