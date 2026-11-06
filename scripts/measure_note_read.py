"""Time the activity page's read of the CRM's own record notes — read-only
(mentor login integrity plan, step 6: "Before step 6 — one read-only check").

The activity page lists the CRM's Create, Update and Assign notes across
every record by author and date, under the application's key-based account,
and gives up after 12 seconds (``activity.service.NOTE_READ_SECONDS``). This
times that read for the busiest author of the last 30 days and for a 7-day
range with no author. It writes nothing and prints counts and timings only —
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

from activity.service import NOTE_READ_SECONDS, key_client  # noqa: E402
from core.config import get_settings  # noqa: E402

TYPES = {"type": "in", "attribute": "type", "value": ["Create", "Update", "Assign"]}


def _since(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


async def _timed(label: str, key, where):
    t = time.monotonic()
    try:
        page = await key.list("Note", where=where, max_size=200, order_by="createdAt",
                              order="desc", select="id,createdById")
        took = time.monotonic() - t
        verdict = "OK" if took < NOTE_READ_SECONDS else "TOO SLOW for the page"
        print(f"{label}: {took:.2f}s, total {page.get('total')} — {verdict}")
        return page
    except Exception as exc:  # noqa: BLE001
        print(f"{label}: FAILED after {time.monotonic() - t:.2f}s — {str(exc)[:200]}")
        return None


async def main() -> int:
    settings = get_settings()
    key = key_client(settings)
    if key is None:
        print("No CRM key on this server.")
        return 2
    print(f"CRM: {settings.espo_base_url}; the page gives up after {NOTE_READ_SECONDS:.0f}s\n")
    month = await _timed("30 days, any author, first page", key,
                         [TYPES, {"type": "after", "attribute": "createdAt", "value": _since(30)}])
    await _timed("7 days, any author, first page", key,
                 [TYPES, {"type": "after", "attribute": "createdAt", "value": _since(7)}])
    authors = Counter(r.get("createdById") for r in (month or {}).get("list") or [])
    if authors:
        busiest = authors.most_common(1)[0][0]
        await _timed("one author, no date range", key,
                     [TYPES, {"type": "equals", "attribute": "createdById", "value": busiest}])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
