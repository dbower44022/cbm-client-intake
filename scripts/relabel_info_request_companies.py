"""Relabel the companies the information request door created before ruling 34.

Until 10-17-26 the information request door created a new company typed
``Client`` with ``cClientStatus = Prospect`` — a nearest fit from before the
``Prospect`` type existed on Companies. Ruling 34 (prds/prospect-marketing/
rulings.md) types a new one ``Prospect`` with the client status untouched, so
the relabel at conversion (ruling 21, build plan § 1.9) is one rule for every
door. This one-time script brings the companies created under the old shape
into line, once per CRM.

**What it changes.** A Company whose ``cCompanyType`` is EXACTLY ``["Client"]``,
whose ``cClientStatus`` is ``Prospect`` and which has NO ``CClientProfile``
(matched on ``linkedCompanyId`` — a client profile means a real client
relationship, whatever the status field says) has ``Client`` replaced by
``Prospect``. Nothing else on the record changes; ``cClientStatus`` is left as
it is. A company carrying any other type, or a client profile, is reported and
left alone.

**Idempotent, dry-run by default.** Runs as the org-wide API key and refuses
to start when the CRM has no ``Prospect`` option on ``cCompanyType`` (apply
the Phase 1 plan first). Ships in the image so production's run happens from
inside the deployed web container, where the address and key are the
process's own::

    cd /app && PYTHONPATH=/app .venv/bin/python scripts/relabel_info_request_companies.py           # dry run
    cd /app && PYTHONPATH=/app .venv/bin/python scripts/relabel_info_request_companies.py --apply   # apply

From the repository against crm-test the same two commands read ``.env``
through the application's settings. ``--url`` / ``--key`` override both.

Exit codes: 0 done (or nothing to do), 1 a write failed, 2 the CRM lacks the
option or no credential, 3 the CRM could not be reached.
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

ACCOUNT = "Account"
CLIENT_PROFILE = "CClientProfile"
TYPE_FIELD = "cCompanyType"
STATUS_FIELD = "cClientStatus"
CLIENT = "Client"
PROSPECT = "Prospect"
PAGE = 200


async def _page_all(client: Any, entity: str, *, select: str, where: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = await client.list(entity, select=select, where=where, max_size=PAGE, offset=offset,
                                 order_by="createdAt", order="asc")
        batch = page.get("list", [])
        rows.extend(batch)
        if len(batch) < PAGE:
            return rows
        offset += PAGE


async def plan(client: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """The companies to relabel and the reasons others were left alone."""
    candidates = await _page_all(
        client, ACCOUNT, select=f"id,name,{TYPE_FIELD},{STATUS_FIELD}",
        where=[{"type": "equals", "attribute": STATUS_FIELD, "value": PROSPECT}],
    )
    to_change: list[dict[str, Any]] = []
    skipped: list[str] = []
    for row in candidates:
        types = [t for t in (row.get(TYPE_FIELD) or []) if t]
        label = f"{row.get('name')!r} (Account/{row['id']})"
        if types != [CLIENT]:
            skipped.append(f"{label}: type is {types or 'empty'}, not exactly [Client] — left alone")
            continue
        profile = await client.find_one(CLIENT_PROFILE, "linkedCompanyId", row["id"], select="id")
        if profile:
            skipped.append(f"{label}: has a client profile ({CLIENT_PROFILE}/{profile['id']}) — a real client, left alone")
            continue
        to_change.append(row)
    return to_change, skipped


async def run(client: Any, *, apply: bool) -> int:
    options = await client.metadata_enum_options(ACCOUNT, TYPE_FIELD)
    if not options or PROSPECT not in options:
        print(f"This CRM has no {PROSPECT!r} option on {ACCOUNT}.{TYPE_FIELD} — apply "
              "scripts/plans/coutreach-entities.json first.", file=sys.stderr)
        return 2
    to_change, skipped = await plan(client)
    failed: list[str] = []
    done: list[str] = []
    for row in to_change:
        label = f"{row.get('name')!r} (Account/{row['id']})"
        if apply:
            try:
                await client.update(ACCOUNT, row["id"], {TYPE_FIELD: [PROSPECT]})
                done.append(f"{label}: [Client] -> [Prospect]")
            except EspoError as exc:
                failed.append(f"{label}: {exc}")
        else:
            done.append(f"{label}: [Client] -> [Prospect]")
    for title, rows in (("CHANGES" if apply else "WOULD CHANGE", done), ("LEFT ALONE", skipped), ("FAILED", failed)):
        if rows:
            print(f"{title} ({len(rows)}):")
            for line in rows:
                print(f"  {'!' if title == 'FAILED' else '-'} {line}")
            print()
    if not done and not failed:
        print("Nothing to do — no company carries the old shape.")
    if not apply:
        print(f"Dry run only. {len(done)} compan{'y' if len(done) == 1 else 'ies'} would change. "
              "Re-run with --apply to make these changes.")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Relabel information-request companies from Client to Prospect (ruling 34), once.")
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
