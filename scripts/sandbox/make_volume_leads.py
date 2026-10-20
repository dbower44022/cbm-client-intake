"""Fill crm-test with a few thousand throwaway leads, for a volume live pass.

The Leads and Review grids were rebuilt for about 10,000 leads a year (build
plan § 7b). crm-test holds seventeen, which proves nothing about search speed,
paging or the 2,000-lead bulk cap. This makes N leads named ``Volume test
NNNNN`` — business and person leads, Unqualified and Qualified, a spread of
Cleveland ZIPs, two import batches, some with a phone — so every filter has
something to find.

Nothing here is kept: the nightly reset restores the baseline, which holds
none of them, so they are gone by the next morning. No campaign, touch,
Company or Contact is made.

Runs under the org-wide API key (it may create leads). Idempotent by name:
a lead that exists is skipped. Read-only unless ``--apply``. Refuses any CRM
but crm-test.

    uv run python scripts/sandbox/make_volume_leads.py --count 3000
    uv run python scripts/sandbox/make_volume_leads.py --count 3000 --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from campaigns import config as cfg  # noqa: E402
from core.config import get_settings  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402

PREFIX = "Volume test"
ZIPS = (("44102", "Cleveland"), ("44113", "Cleveland"), ("44107", "Lakewood"),
        ("44105", "Cleveland"), ("44111", "Cleveland"), ("44103", "Cleveland"))
STREETS = ("Lorain Ave", "Detroit Ave", "Clark Ave", "Fleet Ave", "Euclid Ave", "Madison Ave")
BATCHES = ("Volume test filings — A", "Volume test filings — B")


def lead(i: int) -> dict:
    zip_, city = ZIPS[i % len(ZIPS)]
    person = i % 7 == 0
    qualified = i % 5 == 0
    row = {
        "name": f"{PREFIX} {i:05d}",
        "mailingAddressStreet": f"{1000 + i} {STREETS[i % len(STREETS)]}",
        "mailingAddressCity": city, "mailingAddressState": "OH", "mailingAddressPostalCode": zip_,
        "mailingAddressCountry": "US", "addressStatus": cfg.ADDRESS_USABLE,
        "leadStatus": cfg.LEAD_QUALIFIED if qualified else cfg.LEAD_UNQUALIFIED,
        "leadSource": cfg.SOURCE_LIST if person else cfg.SOURCE_FILING,
        "importBatch": BATCHES[i % 2], "externalReference": f"VT-{i:05d}",
        "description": "Volume test lead — gone after the nightly reset.",
    }
    if person:
        row.update(firstName="Volume", lastName=f"Tester {i:05d}")
    else:
        row["businessName"] = row["name"]
    if i % 3 == 0:
        row["phone"] = f"+1216555{i % 10000:04d}"
    if qualified:
        row["website"] = f"https://volume-{i:05d}.example.com"
        row["qualifiedBy"] = "the volume script"
    return row


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--count", type=int, default=3000)
    parser.add_argument("--apply", action="store_true", help="actually write")
    args = parser.parse_args()
    settings = get_settings()
    base = settings.espo_base_url or ""
    if "crm-test" not in base.lower():
        print(f"REFUSING: ESPO_BASE_URL is {base!r}, not the crm-test sandbox.")
        return 2
    client = EspoClient(base, settings.espo_api_key, settings.request_timeout_seconds)
    have = await client.list(cfg.PROSPECT, select="id", max_size=1,
                             where=[{"type": "startsWith", "attribute": "name", "value": PREFIX}])
    existing = int(have.get("total") or 0)
    todo = max(0, args.count - existing)
    print(f"\n{base}: {existing} volume leads already there; {todo} to create.")
    if not args.apply:
        print("DRY RUN — nothing written. Re-run with --apply.")
        return 0
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    made = 0
    for i in range(existing, args.count):
        payload = lead(i)
        payload["leadStatusChangedAt"] = now
        try:
            await client.create(cfg.PROSPECT, payload)
        except EspoError as exc:
            print(f"\nSTOPPED at {i}: {exc}")
            return 1
        made += 1
        if made % 250 == 0:
            print(f"  {made} created…", flush=True)
    print(f"\nDone: {made} created, {existing + made} volume leads in all.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
