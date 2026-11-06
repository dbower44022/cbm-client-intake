"""The web component's daily loop for the CRM-use report (``crm_use.py``).

Checks every ten minutes whether the run is due: an hour before
``LOGIN_INTEGRITY_HOUR`` local time, so its faults are recorded before the
worker's check sends the integrity digest. The switch, the hour and the
timezone are read on every pass. Never raises.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from core.config import Settings, get_settings

log = logging.getLogger("cbm_intake.integrity")

TICK_SECONDS = 600


def next_report_time(settings: Settings, after: datetime) -> datetime:
    from worker import _next_local_hour

    from .run import SANDBOX_QUIET_UTC, is_sandbox

    when = _next_local_hour((settings.login_integrity_hour - 1) % 24,
                            settings.login_integrity_tz, after, label="CRM-use report")
    lo, hi = SANDBOX_QUIET_UTC
    if is_sandbox(settings) and lo <= when.hour < hi:
        when = when.replace(hour=hi, minute=0, second=0, microsecond=0)
    return when


async def run_once(settings: Settings) -> None:
    from core.admin_client import admin_client_factory
    from core.login_guard import reader

    from .crm_use import run_crm_use_report
    from .store import get_store

    factory = admin_client_factory(settings)
    key, store = reader(), get_store(settings)
    if factory is None or key is None or store is None:
        log.warning("integrity CRM-use report: needs the administrator account "
                    "(ESPO_PROVISION_*), the API key and a database — not run")
        return
    await run_crm_use_report(settings, await factory(), key, store)


async def crm_use_loop() -> None:
    settings = get_settings()
    sched = (settings.login_integrity_hour, settings.login_integrity_tz)
    next_at = next_report_time(settings, datetime.now(timezone.utc))
    was_on = False
    while True:
        try:
            settings = get_settings()
            now = datetime.now(timezone.utc)
            on = bool(settings.integrity_crm_use_report)
            if (settings.login_integrity_hour, settings.login_integrity_tz) != sched or on != was_on:
                sched = (settings.login_integrity_hour, settings.login_integrity_tz)
                next_at = next_report_time(settings, now)
                if on != was_on:
                    log.info("integrity CRM-use report %s (next %s UTC)",
                             "enabled" if on else "disabled", next_at)
                was_on = on
            if on and now >= next_at:
                await run_once(settings)
                next_at = next_report_time(settings, datetime.now(timezone.utc))
        except Exception:  # noqa: BLE001 — the loop must survive
            log.exception("integrity CRM-use report failed")
        await asyncio.sleep(TICK_SECONDS)
