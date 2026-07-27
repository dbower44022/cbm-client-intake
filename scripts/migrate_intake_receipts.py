"""One-off migration for the intake-receipt redesign (2026-07-27).

Converts every existing CIntakeSubmission record from the old
``reason``/``status`` model to the new single-vocabulary model, and back-links
each receipt to its app-store submission row so the reconciliation sweep never
creates duplicates for pre-redesign submissions.

What it does, per CRM record that has no ``intakeStatus`` yet:

  1. ``intakeStatus`` from ``reason``:  Normal -> Completed,
     Honeypot -> Held-Spam, OrchestratorError -> Error.
  2. ``intakeMessage`` per the design (spam-trap wording / "All emails need
     review" / the old description's error header for Error records).
  3. ``payload`` = the JSON block copied out of the old ``description``.
  4. Back-link: the submission token inside that JSON is matched to the
     app-store row (DATABASE_URL required) and stored as ``crm_receipt_id``.

Rows whose app-store state has since moved on (e.g. discarded) are then
converged by the normal sweep — run "Sync receipts" in Submission Admin (or
wait for the hourly pass) after this script.

DRY-RUN by default (prints what it would do); ``--write`` applies.

Run it where both the CRM key and the database are available — the deployed
web/worker console (`doctl apps console`) per environment:

    python -m scripts.migrate_intake_receipts            # dry-run
    python -m scripts.migrate_intake_receipts --write
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys

from core import receipts
from core.config import get_settings
from core.espo import EspoClient
from core.store import make_store

PAGE = 100

_STATUS_FROM_REASON = {
    "Normal": receipts.R_COMPLETED,
    "Honeypot": receipts.R_HELD_SPAM,
    "OrchestratorError": receipts.R_ERROR,
}

# Reverse of the app's form-value mapping (receipt "form" enum -> app slug).
_SLUG_FROM_FORM = {"Partner": "partner", "Sponsor": "sponsor", "Email": "info-email"}

_TOKEN_RE = re.compile(r'"submission_token"\s*:\s*"([^"]+)"')
_PAYLOAD_MARK = "----- submission payload -----"


def _payload_block(description: str) -> str:
    """The raw JSON block the old writer appended to ``description``."""
    if not description:
        return ""
    if _PAYLOAD_MARK in description:
        return description.split(_PAYLOAD_MARK, 1)[1].strip()
    return ""


def _message_for(status: str, form_value: str, description: str) -> str:
    slug = _SLUG_FROM_FORM.get(form_value, form_value)
    if status == receipts.R_HELD_SPAM:
        title = receipts._form_title(slug)  # noqa: SLF001 — same package family
        return f"The {title} spam trap was triggered"
    if status == receipts.R_ERROR:
        # The old description's header (above the payload block) is the best
        # available what-happened text for a historical failure.
        head = (description or "").split(_PAYLOAD_MARK, 1)[0].strip()
        return head or (
            "This submission failed to process before the receipt redesign; "
            "see Submission Admin for its stored error."
        )
    return ""


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="apply changes")
    args = parser.parse_args()

    settings = get_settings()
    if settings.espo_dry_run or not settings.espo_api_key:
        print("ERROR: needs a real CRM (ESPO_DRY_RUN=false + ESPO_API_KEY).")
        return 2
    client = EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )
    store = make_store(settings)
    if store is None:
        print("WARNING: DATABASE_URL not set — fields will migrate but receipts "
              "cannot be back-linked to app rows (run in the deployed console "
              "for the full migration).")

    print(f"CRM: {settings.espo_base_url}  mode: {'WRITE' if args.write else 'DRY-RUN'}")

    migrated = linked = skipped = failed = 0
    offset = 0
    while True:
        env = await client.list(
            receipts.RECEIPT_ENTITY,
            select="id,name,reason,status,intakeStatus,description,payload",
            max_size=PAGE, offset=offset, order_by="createdAt", order="asc",
        )
        rows = env.get("list") or []
        if not rows:
            break
        for rec in rows:
            rid = rec.get("id")
            token_source = (rec.get("payload") or "") + (rec.get("description") or "")
            token_match = _TOKEN_RE.search(token_source)
            token = token_match.group(1) if token_match else None

            changes: dict = {}
            if not rec.get("intakeStatus"):
                reason = rec.get("reason") or ""
                status = _STATUS_FROM_REASON.get(reason)
                if status is None:
                    print(f"  SKIP {rid} ({rec.get('name')}): unknown reason {reason!r}")
                    skipped += 1
                else:
                    changes["intakeStatus"] = status
                    msg = _message_for(status, rec.get("form") or "", rec.get("description") or "")
                    if msg:
                        changes["intakeMessage"] = msg
                    block = _payload_block(rec.get("description") or "")
                    if block and not rec.get("payload"):
                        changes["payload"] = block

            link_info = None
            if store is not None and token:
                found = await store.find_ids_by_tokens([token])
                link_info = found.get(token)

            if changes or (link_info and not link_info.get("crm_receipt_id")):
                verb = []
                if changes:
                    verb.append(f"set {sorted(changes)} (-> {changes.get('intakeStatus', '?')})")
                if link_info and not link_info.get("crm_receipt_id"):
                    verb.append(f"link app row {link_info['id'][:8]}")
                print(f"  {rid} ({rec.get('name')}): " + "; ".join(verb))
                if args.write:
                    try:
                        if changes:
                            await client.update(receipts.RECEIPT_ENTITY, rid, changes)
                            migrated += 1
                        if link_info and not link_info.get("crm_receipt_id"):
                            await store.set_receipt_id(link_info["id"], rid)
                            linked += 1
                    except Exception as exc:  # noqa: BLE001 — report + continue
                        failed += 1
                        print(f"    FAILED: {exc}")
                else:
                    migrated += 1 if changes else 0
                    linked += 1 if link_info and not link_info.get("crm_receipt_id") else 0
            else:
                skipped += 1
        if len(rows) < PAGE:
            break
        offset += PAGE

    print(
        f"\n{'Applied' if args.write else 'Would apply'}: {migrated} record(s) "
        f"migrated, {linked} back-linked, {skipped} already current/skipped, "
        f"{failed} failed."
    )
    if args.write:
        print("Next: run 'Sync receipts' in Submission Admin (or wait for the "
              "hourly sweep) to converge discarded/held rows, then delete the "
              "old reason/status fields in Entity Manager per "
              "cintake-submission-redesign.md §6.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
