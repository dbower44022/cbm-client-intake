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
import signal
import traceback
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from core import monitoring, receipts
from core import store as store_mod
from core.config import Settings, get_settings
from core.espo import DryRunEspoClient, EspoApi, EspoClient, EspoError, EspoTransportError
from core.logging_setup import setup_logging
from core.resumable import ResumableClient
from core.store import Claimed, SubmissionStore, autoclose_reason
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


def _next_local_hour(hour: int, tz_name: str, after: datetime, *, label: str) -> datetime:
    """The next UTC instant at local ``hour`` in ``tz_name``, strictly after
    ``after`` — so a daily job lands at the same wall-clock time and a worker
    restart past today's hour schedules tomorrow (never an immediate re-fire).
    Falls back to a plain +24h if the timezone name is bad."""
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(tz_name)
    except Exception:  # noqa: BLE001 — bad tz name: degrade to a daily cadence
        log.warning("%s: bad timezone %r — using +24h cadence", label, tz_name)
        return after + timedelta(days=1)
    local = after.astimezone(tz)
    target = local.replace(
        hour=max(0, min(23, hour)), minute=0, second=0, microsecond=0
    )
    if target <= local:
        target = target + timedelta(days=1)
    return target.astimezone(timezone.utc)


def _next_digest_time(settings: Settings, after: datetime) -> datetime:
    """The next send time for the daily email digest."""
    return _next_local_hour(
        settings.comms_digest_hour, settings.comms_digest_tz, after, label="digest"
    )


def _next_sandbox_reset(settings: Settings, after: datetime) -> datetime:
    """The next run of the training-sandbox app-database reset."""
    return _next_local_hour(
        settings.sandbox_reset_hour, settings.sandbox_reset_tz, after, label="sandbox reset"
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
            log.warning(
                "retry %s (%s token=%s, attempt %s): %s",
                claimed.id, claimed.form_slug, claimed.submission_token, attempt, exc,
            )
        else:
            # Store the traceback tail alongside the message so a code bug
            # (e.g. KeyError) landing in needs_attention is diagnosable from
            # /ops, not just a four-character string.
            tail = traceback.format_exc()[-1000:]
            await store.mark_failed(
                claimed.id, status=store_mod.STATUS_NEEDS_ATTENTION,
                error=f"{str(exc)[:800]}\n--- traceback (tail) ---\n{tail}",
            )
            # The CRM receipt flips to Error with the full what-happened-and-
            # how-to-fix message (intake-receipt redesign 2026-07-27).
            await receipts.touch_safe(base, store, claimed.id)
            log.exception(
                "needs_attention %s (%s token=%s, attempt %s): %s",
                claimed.id, claimed.form_slug, claimed.submission_token, attempt, exc,
            )
        return

    # Record-creating forms (client-intake/volunteer/partner/sponsor) auto-close
    # on delivery — the downstream admin team owns them, /ops has no action.
    reason = autoclose_reason(claimed.form_slug)
    await store.mark_completed(claimed.id, ids, auto_close_reason=reason)
    # The CRM receipt reaches Completed (+ the Contact link). If the arrival-
    # time create never landed, this touch creates it (adopt-by-token first).
    await receipts.touch_safe(base, store, claimed.id)
    log.info(
        "delivered %s (%s token=%s) -> %s%s",
        claimed.id, claimed.form_slug, claimed.submission_token, ids,
        " [auto-closed: process completed]" if reason else "",
    )


async def run_once(
    store: SubmissionStore, settings: Settings,
    stop: Optional[asyncio.Event] = None,
) -> int:
    """Claim and deliver one batch. Returns how many were claimed.

    ``stop`` set mid-batch (SIGTERM during a deploy) finishes the CURRENT
    item and skips the rest — their leases were just taken, so the next
    worker reclaims them after lease expiry; stopping cleanly beats being
    SIGKILLed mid-CRM-write."""
    claimed = await store.claim_batch(
        settings.worker_batch_size, lease_seconds=settings.worker_lease_seconds
    )
    if claimed:
        log.info(
            "claimed %d: %s",
            len(claimed),
            "; ".join(
                f"{c.id} ({c.form_slug} token={c.submission_token})" for c in claimed
            ),
        )
    for i, item in enumerate(claimed):
        if stop is not None and stop.is_set() and i > 0:
            log.info(
                "stopping mid-batch (SIGTERM): %d of %d items delivered; the "
                "rest are reclaimed after their lease", i, len(claimed),
            )
            break
        await process_one(store, settings, item)
    return len(claimed)


async def run_cycle(
    store: SubmissionStore, settings: Settings,
    stop: Optional[asyncio.Event] = None,
) -> int:
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
        return await run_once(store, settings, stop)
    except Exception:  # noqa: BLE001 — nothing may crash the delivery loop
        log.exception("delivery cycle failed — continuing after the poll interval")
        return 0


async def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    store = store_mod.make_store(settings)
    if store is None:
        # No database configured (e.g. before Phase 1 is activated). Stay up but
        # idle rather than crash-loop, so the component can be deployed early.
        log.warning("worker idle: DATABASE_URL is not set")
        while True:
            await asyncio.sleep(60)

    # Graceful shutdown (Phase 6, reliability review 2026-07-17): every deploy
    # SIGTERMs the worker; finishing the in-flight item and stopping new
    # claims avoids rolling the duplicate-create dice on each push and the
    # up-to-15-minute lease delay on the killed row. (Schema note: tables come
    # from Alembic — the PRE_DEPLOY migrate job / `alembic upgrade head` —
    # never built at boot; see the create_app lifespan note.)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # non-unix (tests on odd platforms)
            pass

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

    # Meeting transcripts: Meet transcript retrieval into CSession (plan
    # prds/meet-transcript-integration.md §4). Inert unless MEET_TRANSCRIPTS is
    # on; also feature-gated per cycle on the CRM's sessionTranscription field.
    next_transcripts = datetime.now(timezone.utc)

    # Analytics: warm the seeded system dashboard's cached metrics on a cadence
    # (prds/analytics-app-plan.md). Inert unless ANALYTICS_ENABLED + a store.
    next_analytics = datetime.now(timezone.utc)

    # Assignment-stamp reconciliation (stamp-drift layer 3, 2026-07-20):
    # nightly merge-only self-heal of mentor/co-mentor assignedUsers stamps on
    # engagement client records. Inert in dry-run / without an API key.
    next_stamps = datetime.now(timezone.utc)

    # Intake-receipt reconciliation (Doug's 2026-07-27 redesign): converge
    # every row's CIntakeSubmission receipt — the guarantee behind "the CRM is
    # the single source of truth". Inert in dry-run (no real CRM to converge).
    next_receipts = datetime.now(timezone.utc)
    receipts_on = settings.receipt_reconcile_seconds > 0 and not settings.espo_dry_run
    if receipts_on:
        log.info(
            "intake-receipt reconciliation enabled (every %ss)",
            settings.receipt_reconcile_seconds,
        )

    # Inbound info@ poller (v0.110.0): captures new inbound threads on the
    # shared OPS_MAILBOX as held info-email submissions for /ops triage.
    # Inert unless GMAIL_SYNC + OPS_MAILBOX are set.
    next_inbound = datetime.now(timezone.utc)
    inbound_on = bool(
        settings.gmail_sync and settings.ops_mailbox and settings.ops_inbound_seconds > 0
    )
    if inbound_on:
        log.info(
            "inbound mailbox poll enabled (%s, every %ss)",
            settings.ops_mailbox, settings.ops_inbound_seconds,
        )

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
            if settings.gmail_resync:
                await comms_store.reset_all_sync_state()
                log.warning("GMAIL_RESYNC: sync cursors cleared — the next pass "
                            "re-runs the initial backfill; unset the flag after")
            log.info("gmail sync enabled (every %ss)", settings.gmail_sync_seconds)

    # Daily email digest (§4.2.4): anchored to comms_digest_hour in
    # comms_digest_tz so it lands each morning. Seeded to the NEXT future
    # occurrence, so a worker restart past the hour doesn't re-fire today.
    from comms.digest import digest_enabled

    digest_on = digest_enabled(settings) and comms_store is not None
    next_digest = _next_digest_time(settings, datetime.now(timezone.utc))
    if digest_on:
        log.info(
            "daily email digest enabled (%02d:00 %s; next %s UTC)",
            settings.comms_digest_hour, settings.comms_digest_tz, next_digest,
        )

    # Training-sandbox reset (crm-test only): empty the app's own record tables
    # so they match the CRM the droplet restored an hour earlier. Refuses on any
    # deployment whose CRM base URL is not crm-test, whatever the flag says.
    sandbox_on = False
    next_sandbox = _next_sandbox_reset(settings, datetime.now(timezone.utc))
    if settings.sandbox_nightly_reset:
        try:
            from core.sandbox_reset import guard as sandbox_guard

            sandbox_guard(settings)
            sandbox_on = True
            log.info(
                "training-sandbox reset enabled (%02d:00 %s; next %s UTC)",
                settings.sandbox_reset_hour, settings.sandbox_reset_tz, next_sandbox,
            )
        except Exception as exc:  # noqa: BLE001 — a refused guard must not boot-loop
            log.warning("training-sandbox reset NOT armed: %s", exc)

    # Events attendance (Phase 6a): pull the Zoom participant report for each
    # finished online event. Inert without Zoom, and bounded at both ends by the
    # grace / give-up windows so a webinar that was never held is not polled
    # forever.
    next_attendance = datetime.now(timezone.utc)
    attendance_on = (
        settings.events_active
        and settings.events_attendance_seconds > 0
        and not settings.espo_dry_run
    )
    if attendance_on:
        log.info(
            "events attendance pull enabled (every %ss, grace %smin, give up after %sh)",
            settings.events_attendance_seconds,
            settings.events_attendance_grace_minutes,
            settings.events_attendance_give_up_hours,
        )

    # Event reminders (Phase 6b). The only time-driven follow-up; the other
    # four are staff-triggered. Inert without Gmail + the shared mailbox.
    next_reminder = datetime.now(timezone.utc)
    reminders_on = settings.events_reminders and settings.events_reminder_seconds > 0
    if reminders_on:
        log.info(
            "event reminders enabled (every %ss, %sh before the event)",
            settings.events_reminder_seconds, settings.events_reminder_lead_hours,
        )

    # System Settings overrides. The worker is a separate container from web, so
    # it re-reads `app_setting` on its own timer — this is the lag between an
    # admin toggling a worker-side flag and the worker acting on it. Also the
    # review sweep for temporary overrides: reported, never auto-reverted
    # (ruling 5), because a flag flipping itself off unattended is its own
    # outage.
    from core.settings_store import make_settings_store, overdue_reviews
    from core.settings_store import refresh_into_config as _refresh_settings

    settings_store = make_settings_store(settings)
    next_settings = datetime.now(timezone.utc)
    next_review = datetime.now(timezone.utc) + timedelta(hours=1)
    if settings_store is not None and settings.settings_overrides:
        await _refresh_settings(settings_store, settings)
        log.info(
            "settings overrides enabled (refresh every %ss)",
            settings.setup_refresh_seconds,
        )

    while not stop.is_set():
        claimed = await run_cycle(store, settings, stop)

        now_cfg = datetime.now(timezone.utc)
        if settings_store is not None and now_cfg >= next_settings:
            try:
                await _refresh_settings(settings_store, get_settings())
            except Exception as exc:  # noqa: BLE001 — config refresh never crashes the worker
                log.warning("settings override refresh failed: %s", exc)
            settings = get_settings()
            next_settings = now_cfg + timedelta(
                seconds=max(5, settings.setup_refresh_seconds)
            )
        if attendance_on and now_cfg >= next_attendance:
            try:
                from events.attendance import run_attendance_cycle

                await run_attendance_cycle(settings)
            except Exception as exc:  # noqa: BLE001 — never crashes delivery
                log.warning("events attendance pull failed: %s", exc)
            next_attendance = now_cfg + timedelta(
                seconds=settings.events_attendance_seconds
            )
        if reminders_on and now_cfg >= next_reminder:
            try:
                from events.notify import run_reminder_cycle

                await run_reminder_cycle(settings)
            except Exception as exc:  # noqa: BLE001 — never crashes delivery
                log.warning("event reminder pass failed: %s", exc)
            next_reminder = now_cfg + timedelta(seconds=settings.events_reminder_seconds)
        if settings_store is not None and now_cfg >= next_review:
            try:
                overdue = await overdue_reviews(settings_store)
                if overdue:
                    log.warning(
                        "settings: %d temporary override(s) past review: %s "
                        "(nothing reverts automatically)",
                        len(overdue), ", ".join(o.key for o in overdue),
                    )
            except Exception as exc:  # noqa: BLE001
                log.debug("temporary-override review sweep failed: %s", exc)
            next_review = now_cfg + timedelta(hours=1)

        # Liveness heartbeat (P1-6): one upserted row per iteration; /healthz
        # reports its age so an external check can see a dead/wedged worker.
        try:
            await store.heartbeat()
        except Exception as exc:  # noqa: BLE001 — liveness must never crash the worker
            log.warning("heartbeat write failed: %s", exc)

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
        if (
            settings.meet_transcripts or settings.fathom_transcripts
        ) and now >= next_transcripts:
            try:
                from sessions.transcripts import run_transcript_cycle

                await run_transcript_cycle(settings, _client(settings))
            except Exception as exc:  # noqa: BLE001 — never crashes delivery
                log.warning("transcript retrieval cycle failed: %s", exc)
            next_transcripts = now + timedelta(
                seconds=settings.meet_transcripts_poll_seconds
            )
        if comms_store is not None and now >= next_gmail:
            try:
                await run_gmail_cycle(settings, comms_store)
            except Exception as exc:  # noqa: BLE001 — comms never crashes delivery
                log.warning("gmail sync cycle failed: %s", exc)
            next_gmail = now + timedelta(seconds=settings.gmail_sync_seconds)
        if receipts_on and now >= next_receipts:
            try:
                await receipts.run_receipt_sweep(
                    _client(settings), store, settings, alert_state
                )
            except Exception as exc:  # noqa: BLE001 — never crashes delivery
                log.warning("receipt reconciliation failed: %s", exc)
            next_receipts = now + timedelta(seconds=settings.receipt_reconcile_seconds)
        if inbound_on and now >= next_inbound:
            try:
                from ops.inbound import run_inbound_cycle

                await run_inbound_cycle(settings, store)
            except Exception as exc:  # noqa: BLE001 — never crashes delivery
                log.warning("inbound mailbox poll failed: %s", exc)
            next_inbound = now + timedelta(seconds=settings.ops_inbound_seconds)
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
        if (
            settings.analytics_enabled
            and settings.analytics_refresh_seconds > 0
            and now >= next_analytics
        ):
            try:
                from analytics.refresh import refresh_system_metrics

                await refresh_system_metrics(settings)
            except Exception as exc:  # noqa: BLE001 — never crashes delivery
                log.warning("analytics metric refresh failed: %s", exc)
            next_analytics = now + timedelta(seconds=settings.analytics_refresh_seconds)
        if settings.assignment_reconcile_seconds > 0 and now >= next_stamps:
            try:
                from assignments.stamps import run_stamp_reconciliation

                await run_stamp_reconciliation(settings)
            except Exception as exc:  # noqa: BLE001 — never crashes delivery
                log.warning("assignment stamp reconciliation failed: %s", exc)
            next_stamps = now + timedelta(seconds=settings.assignment_reconcile_seconds)
        if sandbox_on and now >= next_sandbox:
            try:
                from core.sandbox_reset import reset_app_tables

                result = await reset_app_tables(store._engine, settings, apply=True)
                log.info("training-sandbox reset cleared %s rows", result["total_rows"])
            except Exception as exc:  # noqa: BLE001 — never crashes delivery
                log.warning("training-sandbox reset failed: %s", exc)
            next_sandbox = _next_sandbox_reset(settings, datetime.now(timezone.utc))
        if digest_on and now >= next_digest:
            try:
                from comms.digest import run_digest_cycle

                await run_digest_cycle(settings, _client(settings), comms_store)
            except Exception as exc:  # noqa: BLE001 — never crashes delivery
                log.warning("daily digest cycle failed: %s", exc)
            next_digest = _next_digest_time(settings, datetime.now(timezone.utc))

        if claimed == 0 and not stop.is_set():
            # Sleep until the poll interval elapses OR SIGTERM arrives, so a
            # deploy never waits out a sleep.
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.worker_poll_seconds)
            except asyncio.TimeoutError:
                pass

    log.info("worker stopped cleanly (SIGTERM/SIGINT) — no in-flight delivery")


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
