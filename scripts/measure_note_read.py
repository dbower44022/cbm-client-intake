"""Time the activity page's read of the CRM's own record notes — read-only
(mentor login integrity plan, step 6: "Before step 6 — one read-only check").

The activity page lists the CRM's Create, Update and Assign notes across
every record by author and date, under the application's key-based account,
and gives up after 12 seconds (``activity.service.NOTE_READ_SECONDS``). This
times that read — every page, the page's own filters and budget — for 7
and 30 days with no author, for the busiest person, and for System. It writes nothing and prints counts and timings only —
never a name or a row.

Run inside a deployed container, from the application folder (/app):

    .venv/bin/python scripts/measure_note_read.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from activity.service import NOTE_READ_SECONDS, SYSTEM_PERSON, _note_rows, key_client  # noqa: E402
from core.history import _key_user_id  # noqa: E402
from core.config import get_settings  # noqa: E402

def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


async def _timed(label: str, key, uid: str, key_user: str, since: str):
    """The page's own read: every page, its filters, its 12-second budget."""
    t = time.monotonic()
    try:
        rows, truncated, slow = await _note_rows(key, uid, key_user, since, "")
        took = time.monotonic() - t
        verdict = ("TOO SLOW — the page would stop early" if slow
                   else "OK" + (" (stopped at the row cap)" if truncated else ""))
        print(f"{label}: {took:.2f}s, {len(rows)} rows — {verdict}")
        return rows
    except Exception as exc:  # noqa: BLE001
        print(f"{label}: FAILED after {time.monotonic() - t:.2f}s — {str(exc)[:200]}")
        return []


async def main() -> int:
    settings = get_settings()
    key = key_client(settings)
    if key is None:
        print("No CRM key on this server.")
        return 2
    key_user = await _key_user_id(key, settings)
    print(f"CRM: {settings.espo_base_url}; the page gives up after {NOTE_READ_SECONDS:.0f}s\n")
    week = await _timed("7 days, anyone", key, "", key_user, _since(7))
    await _timed("30 days, anyone", key, "", key_user, _since(30))
    authors = Counter(r.get("createdById") for r in week if r.get("createdById") != key_user)
    if authors:
        await _timed("30 days, the busiest person", key, authors.most_common(1)[0][0],
                     key_user, _since(30))
    if key_user:
        await _timed("30 days, System", key, SYSTEM_PERSON, key_user, _since(30))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
