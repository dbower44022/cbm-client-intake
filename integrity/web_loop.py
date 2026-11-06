"""The web component's daily loop for the CRM-use report (``crm_use.py``).

Checks every ten minutes whether the run is due: an hour before
``LOGIN_INTEGRITY_HOUR`` local time, so its faults are recorded before the
worker's check sends the integrity digest. The switch, the hour and the
timezone are read on every pass. Never raises.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

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


async def run_once(settings: Settings) -> bool:
    """True when the report ran to the end."""
    from core.admin_client import admin_client_factory
    from core.login_guard import reader

    from .crm_use import run_crm_use_report
    from .store import get_store

    factory = admin_client_factory(settings)
    key, store = reader(), get_store(settings)
    if factory is None or key is None or store is None:
        log.warning("integrity CRM-use report: needs the administrator account "
                    "(ESPO_PROVISION_*), the API key and a database — not run")
        return False
    return await run_crm_use_report(settings, await factory(), key, store) is not None


#: One retry, this long after a failed run; never more (an administrator
#: sign-in retried all day would lock the provisioning account out).
RETRY_AFTER = timedelta(minutes=30)


async def crm_use_loop() -> None:
    try:
        settings = get_settings()
        sched = (settings.login_integrity_hour, settings.login_integrity_tz)
        next_at = next_report_time(settings, datetime.now(timezone.utc))
    except Exception:  # noqa: BLE001 — say so rather than die unseen
        log.exception("integrity CRM-use report: could not schedule; the report is off "
                      "until the next restart")
        return
    was_on = False
    retried = False
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
                ok = False
                try:
                    ok = await run_once(settings)
                except Exception:  # noqa: BLE001 — e.g. the administrator sign-in
                    log.exception("integrity CRM-use report failed")
                finally:
                    if not ok and not retried:
                        retried = True
                        next_at = datetime.now(timezone.utc) + RETRY_AFTER
                        log.warning("integrity CRM-use report: one retry at %s UTC", next_at)
                    else:
                        retried = False
                        next_at = next_report_time(settings, datetime.now(timezone.utc))
        except Exception:  # noqa: BLE001 — the loop must survive
            log.exception("integrity CRM-use report loop error")
        await asyncio.sleep(TICK_SECONDS)
