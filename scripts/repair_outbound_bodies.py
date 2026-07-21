"""Repair truncated OUTBOUND message bodies in the CRM (CCommunication).

Before the outbound-clean fix (2026-07-21), messages our users SENT were run
through the full inbound signature-stripping heuristics at ingest — an early
"Thanks," / "Best," line or a "Jane Smith / Marketing Consultant" style
introduction deleted every paragraph after it, and even a normal sign-off +
signature was removed, so sent mail read as cut off in the Communications
tab (the mindy@mindybower.com report). The viewer renders the stored
``bodyCleaned`` verbatim, and the sync's dedup never re-stores an existing
message, so old rows don't heal on their own.

This script re-fetches each Outbound CCommunication's raw message from Gmail
(by ``sourceMailbox`` + ``gmailMessageId``, same delegation as the sync),
re-cleans it with ``outbound=True`` (quoted history removed, authored content
kept), and — with ``--write`` — updates ``bodyCleaned`` + ``snippet`` where
the result differs. Default is a read-only report.

Requirements: ESPO_BASE_URL / ESPO_API_KEY (env / .env; the API key already
reads+edits CCommunication for the sync) and GOOGLE_SERVICE_ACCOUNT_JSON
(the Gmail delegation key — on the deployed workers; locally, copy it from
the overlay or run where the env has it).

    uv run python scripts/repair_outbound_bodies.py            # report only
    uv run python scripts/repair_outbound_bodies.py --write    # apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_settings  # noqa: E402
from core.email_clean import clean_email  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402
from core.gmail import (  # noqa: E402
    GmailClient,
    GmailError,
    MessageGoneError,
    parse_message,
    resolve_gmail_service_account,
)

COMMUNICATION = "CCommunication"
PAGE = 200
SELECT = "id,name,sentAt,sourceMailbox,gmailMessageId,toAddresses,snippet,bodyCleaned"


async def run(write: bool) -> int:
    settings = get_settings()
    if not settings.espo_base_url or not settings.espo_api_key:
        print("ESPO_BASE_URL / ESPO_API_KEY must be set (see the module docstring).")
        return 2
    sa_info = resolve_gmail_service_account(settings)
    if not sa_info:
        print("GOOGLE_SERVICE_ACCOUNT_JSON must be set (the Gmail delegation key).")
        return 2
    espo = EspoClient(settings.espo_base_url, settings.espo_api_key)

    rows: list[dict] = []
    offset = 0
    while True:
        try:
            page = await espo.list(
                COMMUNICATION,
                where=[{"type": "equals", "attribute": "direction", "value": "Outbound"}],
                select=SELECT,
                max_size=PAGE,
                offset=offset,
            )
        except EspoError as exc:
            print(f"CRM read failed: {exc}")
            return 2
        batch = page.get("list", [])
        rows.extend(batch)
        offset += PAGE
        if len(batch) < PAGE:
            break
    print(f"{len(rows)} outbound messages stored in the CRM.")

    gmail_by_mailbox: dict[str, GmailClient] = {}
    changed = unchanged = gone = errors = repaired = 0
    try:
        for row in rows:
            mailbox = (row.get("sourceMailbox") or "").strip()
            gmail_id = (row.get("gmailMessageId") or "").strip()
            label = f"{row['id']} {row.get('sentAt') or ''} → {row.get('toAddresses') or ''}"
            if not mailbox or not gmail_id:
                errors += 1
                print(f"  SKIP (no mailbox/gmail id): {label}")
                continue
            gmail = gmail_by_mailbox.get(mailbox)
            if gmail is None:
                gmail = GmailClient(sa_info, mailbox)
                gmail_by_mailbox[mailbox] = gmail
            try:
                parsed = parse_message(await gmail.get_message(gmail_id))
            except MessageGoneError:
                gone += 1
                print(f"  GONE from Gmail (kept as stored): {label}")
                continue
            except GmailError as exc:
                errors += 1
                print(f"  GMAIL ERROR ({exc}): {label}")
                continue
            cleaned = clean_email(parsed.body_text, parsed.body_html, outbound=True)
            if cleaned.html == (row.get("bodyCleaned") or ""):
                unchanged += 1
                continue
            changed += 1
            old_len = len(row.get("bodyCleaned") or "")
            print(f"  TRUNCATED ({old_len} → {len(cleaned.html)} chars): {label}")
            if write:
                try:
                    await espo.update(
                        COMMUNICATION,
                        row["id"],
                        {"bodyCleaned": cleaned.html, "snippet": cleaned.snippet[:100]},
                    )
                    repaired += 1
                except EspoError as exc:
                    errors += 1
                    print(f"    WRITE FAILED ({exc}): {label}")
    finally:
        for gmail in gmail_by_mailbox.values():
            await gmail.aclose()

    print(
        f"\nDone: {changed} differ, {unchanged} already correct, "
        f"{gone} gone from Gmail, {errors} errors."
        + (f" {repaired} repaired." if write else " Re-run with --write to repair.")
    )
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="apply the repairs")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(run(args.write)))


if __name__ == "__main__":
    main()
