"""Time one day's read of the CRM's sign-in log and Action History through the
programming interface — read-only (mentor login integrity plan, step 4c,
check C2).

The direct-use and shared-account reports would read these two lists once a
day as an administrator. Production's sign-in log was 6.6 GB before the
key-based account stopped being logged, so before deciding where the reports
run, this measures what one day's read costs. It writes nothing anywhere and
prints counts and timings only — never an address, a name or a row.

Run inside the deployed WEB container (the administrator account is on web
only), from the application folder:

    python scripts/measure_signin_log_read.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.admin_client import admin_client_factory  # noqa: E402
from core.config import get_settings  # noqa: E402

_PAGE = 200


async def _timed(label: str, coro):
    t = time.monotonic()
    try:
        out = await coro
        print(f"{label}: {time.monotonic() - t:.2f}s")
        return out
    except Exception as exc:  # noqa: BLE001
        print(f"{label}: FAILED after {time.monotonic() - t:.2f}s — {str(exc)[:200]}")
        return None


async def main() -> int:
    settings = get_settings()
    factory = admin_client_factory(settings)
    if factory is None:
        print("No administrator account here (ESPO_PROVISION_*). Run in the web container.")
        return 2
    admin = await factory()
    since = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    day = [{"type": "after", "attribute": "createdAt", "value": since}]
    people = day + [{"type": "isFalse", "attribute": "isDenied"}]
    print(f"CRM: {settings.espo_base_url}; window: the last 24 hours (since {since} UTC)\n")

    for entity, where, label in (
        ("AuthLogRecord", None, "sign-in log, all time"),
        ("AuthLogRecord", day, "sign-in log, last 24h"),
        ("AuthLogRecord", people, "sign-in log, last 24h, not denied"),
        ("ActionHistoryRecord", day, "Action History, last 24h"),
    ):
        env = await _timed(f"count — {label}",
                           admin.list(entity, where=where, select="id", max_size=1))
        if env is not None:
            print(f"   rows: {env.get('total')}")

    # One full day of Action History, page by page, as the report would read it.
    rows, offset, t = 0, 0, time.monotonic()
    while True:
        env = await _timed(f"page at offset {offset}", admin.list(
            "ActionHistoryRecord", where=day, max_size=_PAGE, offset=offset,
            select="id,userId,action,targetType,ipAddress,createdAt"))
        if env is None:
            break
        page = env.get("list", [])
        rows += len(page)
        if len(page) < _PAGE or offset >= 50 * _PAGE:
            break
        offset += _PAGE
    print(f"\nAction History, one day read in full: {rows} rows in "
          f"{time.monotonic() - t:.1f}s (stops after 50 pages)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
