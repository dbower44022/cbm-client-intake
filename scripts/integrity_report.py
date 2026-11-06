"""Print the login integrity faults — read-only (mentor login integrity plan
§ 4.2, step 4a).

This is how the backlog on an instance is read before anyone is emailed.
It never writes to the CRM or to the application's database.

Two modes:

* default — the OPEN faults the daily check has recorded in the application's
  database (needs ``DATABASE_URL``).
* ``--live`` — run the six conditions against the CRM now and print what they
  find, without recording anything (needs ``ESPO_BASE_URL`` / ``ESPO_API_KEY``).
  Useful before ``LOGIN_INTEGRITY_CHECK`` is switched on.

Run inside the deployed web or worker container (the do-app-console-scripting
memory), from the application folder:

    python scripts/integrity_report.py
    python scripts/integrity_report.py --live
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_settings  # noqa: E402
from core.espo import EspoClient  # noqa: E402
from integrity.check import CONDITIONS, find_faults, read_crm  # noqa: E402


def _print(faults: list[dict], *, stored: bool) -> None:
    if not faults:
        print("No login faults.")
        return
    by_cond: dict[int, int] = {}
    for f in faults:
        by_cond[f["condition"]] = by_cond.get(f["condition"], 0) + 1
    print(f"{len(faults)} login fault(s):")
    for c, n in sorted(by_cond.items()):
        print(f"  condition {c} — {CONDITIONS.get(c, '?')}: {n}")
    print()
    current = None
    for f in sorted(faults, key=lambda x: (x["condition"], x["summary"])):
        if f["condition"] != current:
            current = f["condition"]
            print(f"== {current}. {CONDITIONS.get(current, '?')}")
        print(f"- {f['summary']}")
        if stored:
            line = f"    first found {f['first_seen']:%Y-%m-%d %H:%M} UTC"
            if f.get("ack_at"):
                line += (f"; acknowledged by {f.get('ack_by') or '?'} "
                         f"{f['ack_at']:%Y-%m-%d}: {f.get('ack_note') or ''}")
            print(line)


async def run(live: bool) -> int:
    settings = get_settings()
    if live:
        if not settings.espo_base_url or not settings.espo_api_key:
            print("ESPO_BASE_URL / ESPO_API_KEY must be set.")
            return 2
        client = EspoClient(settings.espo_base_url, settings.espo_api_key,
                            settings.request_timeout_seconds)
        snap = await read_crm(client, settings)
        print(f"Read {len(snap.profiles)} mentor profiles, {len(snap.users)} logins, "
              f"{len(snap.contacts)} mentor contacts on {settings.espo_base_url}. "
              f"Nothing recorded.\n")
        _print(find_faults(snap), stored=False)
        return 0
    from integrity.store import get_store

    store = get_store(settings)
    if store is None:
        print("DATABASE_URL must be set (or use --live).")
        return 2
    try:
        _print(await store.open_faults(), stored=True)
    finally:
        await store.dispose()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true",
                    help="run the conditions against the CRM now; record nothing")
    sys.exit(asyncio.run(run(ap.parse_args().live)))
