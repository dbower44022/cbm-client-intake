"""One daily run of the login integrity check — plan § 4.2, steps 4a and 4b.

Called by the worker once a day (``LOGIN_INTEGRITY_CHECK``). Reads the CRM,
records the faults, writes one summary line to the worker log, and — only
with ``INTEGRITY_DIGEST`` on — sends the integrity digest. A failed read
changes nothing: the faults stay as the last complete run left them.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from core.config import Settings
from core.sandbox_reset import SANDBOX_URL_MARKER

from .check import CONDITIONS, find_faults, read_crm

log = logging.getLogger("cbm_intake.integrity")

#: On the sandbox the CRM is restored at 04:00 UTC and the app's database at
#: 05:00 UTC; between the two the data disagrees by design. A run that would
#: land in [04:00, 06:00) UTC there is moved to 06:00 UTC.
SANDBOX_QUIET_UTC = (4, 6)


def is_sandbox(settings: Settings) -> bool:
    return SANDBOX_URL_MARKER in (settings.espo_base_url or "").lower()


def next_run_time(settings: Settings, after: datetime, next_local_hour) -> datetime:
    """The next run, at ``LOGIN_INTEGRITY_HOUR`` local time, never inside the
    sandbox's restore window. ``next_local_hour`` is the worker's scheduler."""
    when = next_local_hour(settings.login_integrity_hour, settings.login_integrity_tz,
                           after, label="login integrity check")
    lo, hi = SANDBOX_QUIET_UTC
    if is_sandbox(settings) and lo <= when.hour < hi:
        moved = when.replace(hour=hi, minute=0, second=0, microsecond=0)
        log.warning("login integrity check: %s UTC falls in the sandbox restore window; "
                    "running at %s UTC instead", when.strftime("%H:%M"), moved.strftime("%H:%M"))
        when = moved
    return when


def summary_line(result: dict[str, Any], counts: dict[str, int], seconds: float) -> str:
    open_rows = result["open"]
    per = " ".join(
        f"c{c}={sum(1 for r in open_rows if r['condition'] == c)}" for c in sorted(CONDITIONS))
    return (f"login integrity check: {len(open_rows)} open ({per}), "
            f"{len(result['new'])} new, {len(result['closed'])} closed; read "
            f"{counts['profiles']} mentor profiles, {counts['users']} logins, "
            f"{counts['contacts']} mentor contacts in {seconds:.1f}s")


async def run_integrity_check(settings: Settings, client: Any, store: Any, *,
                              now: Optional[datetime] = None,
                              send: Any = None) -> Optional[dict[str, Any]]:
    """One complete run. Returns the store's result, or None when the CRM
    read failed (nothing changed)."""
    started = time.monotonic()
    try:
        snap = await read_crm(client, settings)
    except Exception as exc:  # noqa: BLE001 — a partial read must close nothing
        log.warning("login integrity check: the CRM read failed, nothing changed: %s", exc)
        return None
    found = find_faults(snap)
    from .signin import _day

    when = now or datetime.now(timezone.utc)
    result = await store.apply_run(found, now=now, today=_day(settings, when))
    counts = {"profiles": len(snap.profiles), "users": len(snap.users),
              "contacts": len(snap.contacts)}
    log.info(summary_line(result, counts, time.monotonic() - started))
    if settings.integrity_digest:
        from .digest import send_integrity_digest

        try:
            await send_integrity_digest(settings, store, result, send=send)
        except Exception as exc:  # noqa: BLE001 — the digest never fails the check
            log.warning("integrity digest failed: %s", exc)
    return result

