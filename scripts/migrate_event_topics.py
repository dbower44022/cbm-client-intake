"""Copy each event's single ``topic`` into the multiple-choice ``topics`` (F1).

One-time, per CRM, after ``scripts/plans/cevent-topics.json`` has created the
field (``prds/events/CBM_Events_Topics_Design.md`` § 7). For every ``CEvent``
whose ``topic`` is set and whose ``topics`` is empty, write
``topics = [topic]``. An event whose ``topics`` is already set is skipped, so
a re-run changes nothing; an event with no topic is skipped. The retired
``topic`` is never written.

**Idempotent, dry-run by default, additive only.** Runs as the org-wide API
key — its role holds ``CEvent`` edit on every CRM — and refuses to start when
the CRM has no ``topics`` field (apply the plan first). Ships in the image so
production's copy runs from inside the deployed web container, where the
address and key are the process's own::

    cd /app && PYTHONPATH=/app .venv/bin/python scripts/migrate_event_topics.py           # dry run
    cd /app && PYTHONPATH=/app .venv/bin/python scripts/migrate_event_topics.py --apply   # apply

From the repository against crm-test the same two commands read ``.env``
through the application's settings. ``--url`` / ``--key`` override both.

Exit codes: 0 done (or nothing to do), 1 a write or read-back failed, 2 the
CRM lacks the field or no credential, 3 the CRM could not be reached.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.config import get_settings  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402

EVENT = "CEvent"
OLD, NEW = "topic", "topics"
PAGE = 200


async def plan(client: Any) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Which events need the copy, and why the others do not."""
    to_copy: list[dict[str, Any]] = []
    skipped: list[str] = []
    offset = 0
    while True:
        data = await client.list(
            EVENT, select=f"id,name,{OLD},{NEW}", max_size=PAGE, offset=offset,
            order_by="dateStart", order="desc",
        )
        rows = data.get("list", [])
        for row in rows:
            single = (row.get(OLD) or "").strip()
            current = row.get(NEW) or []
            if current:
                skipped.append(f"{row.get('name')!r}: topics already {current}")
            elif not single:
                skipped.append(f"{row.get('name')!r}: no topic to copy")
            else:
                to_copy.append(row)
        offset += len(rows)
        if len(rows) < PAGE or offset >= int(data.get("total") or 0):
            break
    return to_copy, skipped, []


async def run(client: Any, *, apply: bool) -> int:
    options = await client.metadata_enum_options(EVENT, NEW)
    if options is None:
        print(f"{EVENT}.{NEW} does not exist on this CRM - apply "
              "scripts/plans/cevent-topics.json first.", file=sys.stderr)
        return 2
    to_copy, skipped, failed = await plan(client)
    done: list[str] = []
    for row in to_copy:
        single = (row.get(OLD) or "").strip()
        label = f"{row.get('name')!r}: {NEW} <- [{single}]"
        if single not in options:
            # The CRM would refuse the whole write; the value stays where it is
            # and the row is named so a human can decide.
            failed.append(f"{label} - {single!r} is not an option of {EVENT}.{NEW}")
            continue
        if not apply:
            done.append(f"WOULD set {label}")
            continue
        try:
            await client.update(EVENT, row["id"], {NEW: [single]})
            back = await client.get(EVENT, row["id"], select=f"id,{NEW}")
            if (back.get(NEW) or []) == [single]:
                done.append(f"set {label} - read back OK")
            else:
                failed.append(f"{label} - read-back is {back.get(NEW)!r}")
        except EspoError as exc:
            failed.append(f"{label} - {exc}")

    for title, rows in (("CHANGES", done), ("SKIPPED (already correct)", skipped),
                        ("FAILED", failed)):
        if rows:
            print(f"{title}:")
            for line in rows:
                print(f"  {'!' if title == 'FAILED' else '-'} {line}")
            print()
    if not done and not failed:
        print("Nothing to do - every event already matches.")
    if not apply:
        print(f"Dry run only. {len(done)} event(s) would change. "
              "Re-run with --apply to make these changes.")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Copy CEvent.topic into CEvent.topics, once.")
    ap.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    ap.add_argument("--url", default=os.environ.get("ESPO_BASE_URL"))
    ap.add_argument("--key", default=os.environ.get("ESPO_API_KEY"))
    args = ap.parse_args()
    url, key = args.url, args.key
    if not (url and key):
        s = get_settings()
        url, key = url or s.espo_base_url, key or s.espo_api_key
    if not (url and key):
        print("No CRM address or key (ESPO_BASE_URL / ESPO_API_KEY).", file=sys.stderr)
        return 2
    print(f"CRM:  {url}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN - nothing will change'}\n")
    client = EspoClient(url, key, 30)
    try:
        return asyncio.run(run(client, apply=args.apply))
    except EspoError as exc:
        print(f"Could not complete: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
