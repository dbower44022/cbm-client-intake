"""Backfill historical inbound email attachments into the Documents tabs.

The auto-filing pipeline (email-quality plan §3.1, v0.132.0) applies to newly
ingested messages go-forward. This one-shot sweep walks the ALREADY-STORED
inbound CCommunications, re-fetches each message's Gmail original (by
``sourceMailbox`` + ``gmailMessageId``, the same delegation as the sync), and
files any qualifying real attachments onto the records the message's
conversation links to — through the exact same engine (per-record SHA-256
dedup, ledger rows, size cap), so re-running it is idempotent.

Default is a read-only report of what WOULD be filed; ``--write`` applies.

Requirements: ESPO_BASE_URL / ESPO_API_KEY, GOOGLE_SERVICE_ACCOUNT_JSON,
DATABASE_URL, and the GDRIVE_* settings the worker carries
(GDRIVE_DOCS=true, GDRIVE_SHARED_DRIVE_ID, GDRIVE_IDENTITY=service,
GMAIL_SYNC=true) — run inside the deployed worker via ``doctl apps console``,
per environment.

    uv run python scripts/backfill_email_attachments.py            # report only
    uv run python scripts/backfill_email_attachments.py --write    # apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_settings  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402
from core.gmail import (  # noqa: E402
    GmailClient,
    GmailError,
    MessageGoneError,
    parse_message,
    resolve_gmail_service_account,
)

PAGE = 200
SELECT = "id,name,sentAt,direction,sourceMailbox,gmailMessageId,rfcMessageId,conversationId"


async def run(write: bool, limit: int) -> int:
    import comms.service  # noqa: F401 — resolves the comms.sync circular import
    from comms import attachments as att
    from comms.service import get_store

    settings = get_settings()
    if not settings.espo_base_url or not settings.espo_api_key:
        print("ESPO_BASE_URL / ESPO_API_KEY must be set (see the module docstring).")
        return 2
    sa_info = resolve_gmail_service_account(settings)
    if not sa_info:
        print("GOOGLE_SERVICE_ACCOUNT_JSON must be set (the Gmail delegation key).")
        return 2
    if write and not att.attachments_enabled(settings):
        print(
            "The attachment pipeline is not enabled here (needs GMAIL_SYNC, "
            "GDRIVE_DOCS, DATABASE_URL, GDRIVE_SHARED_DRIVE_ID, "
            "GDRIVE_IDENTITY=service)."
        )
        return 2
    store = get_store(settings)
    if write and store is None:
        print("DATABASE_URL must be set (the filing ledger lives in Postgres).")
        return 2

    espo = EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )
    clients: dict[str, GmailClient] = {}
    scanned = candidates = filed_msgs = errors = 0
    offset = 0
    try:
        while True:
            page = await espo.list(
                "CCommunication", select=SELECT, order_by="sentAt", order="asc",
                max_size=PAGE, offset=offset,
            )
            rows = page.get("list", [])
            if not rows:
                break
            offset += len(rows)
            for row in rows:
                scanned += 1
                if limit and candidates >= limit:
                    rows = []
                    break
                if (row.get("direction") or "") != "Inbound":
                    continue
                mailbox = (row.get("sourceMailbox") or "").strip().lower()
                gmail_id = row.get("gmailMessageId") or ""
                conv_id = row.get("conversationId") or ""
                if not mailbox or not gmail_id or not conv_id:
                    continue
                gmail = clients.get(mailbox)
                if gmail is None:
                    gmail = GmailClient(
                        sa_info, mailbox, settings.request_timeout_seconds
                    )
                    clients[mailbox] = gmail
                try:
                    parsed = parse_message(await gmail.get_message(gmail_id))
                except MessageGoneError:
                    continue
                except GmailError as exc:
                    errors += 1
                    print(f"  ! fetch failed {mailbox}/{gmail_id}: {exc}")
                    continue
                atts = parsed.real_attachments
                if not atts:
                    continue
                candidates += 1
                records = await att.conversation_parent_records(espo, conv_id)
                names = ", ".join(a.filename or "attachment" for a in atts)
                targets = ", ".join(f"{e}/{i}" for e, i, _ in records) or "(no records)"
                print(
                    f"- {row.get('sentAt')} {row.get('name')!r} [{mailbox}]: "
                    f"{len(atts)} attachment(s) ({names}) -> {targets}"
                )
                if write and records:
                    try:
                        await att.file_message_attachments(
                            settings, espo, store, gmail, parsed, records
                        )
                        filed_msgs += 1
                    except Exception as exc:  # noqa: BLE001
                        errors += 1
                        print(f"  ! filing failed: {exc}")
            if not rows:
                break
    except EspoError as exc:
        print(f"CRM read failed: {exc}")
        return 1
    finally:
        for gmail in clients.values():
            try:
                await gmail.aclose()
            except Exception:  # noqa: BLE001
                pass

    mode = "APPLIED" if write else "DRY-RUN (nothing written — use --write)"
    print(
        f"\n{mode}: scanned {scanned} stored messages; {candidates} carried real "
        f"attachments; {filed_msgs} filed this run; {errors} errors."
    )
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="apply (default: report only)")
    ap.add_argument(
        "--limit", type=int, default=0,
        help="stop after this many attachment-bearing messages (0 = no limit)",
    )
    args = ap.parse_args()
    sys.exit(asyncio.run(run(args.write, args.limit)))


if __name__ == "__main__":
    main()
