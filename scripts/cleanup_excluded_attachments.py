"""Archive email-attachment documents whose file type is on the never-file list.

From 0.208.0 inbound mail no longer files calendar invites, S/MIME signature
blobs or Outlook TNEF envelopes as documents
(``COMMS_ATTACHMENT_EXCLUDED_TYPES`` — see :func:`comms.attachments.
is_excluded_type`). This is the cleanup for everything filed *before* that:
one ``invite.ics`` per meeting, per reschedule, per acceptance, on every record
the thread touched, all with different bytes so the SHA-256 dedup never
collapsed them.

Scope, deliberately narrow:

* only documents whose ``doc_type`` is **Email attachment** — a file a human
  chose to upload is never touched, even if it is an ``.ics``;
* only ``active`` rows — an already-archived one is left alone;
* **archive, not delete**. This is exactly what a staff member clicking
  Archive does: the file moves to the record folder's ``_Archived`` subfolder
  and the row leaves the default Documents list. Nothing is destroyed, and
  Restore is one click away if a judgement call turns out wrong.

The ledger rows in ``comm_attachment`` are left as they are: those messages
*were* filed at the time, and the thread's attachment chip still opens the
archived copy. Only new arrivals get the ``excluded`` status.

Default is a READ-ONLY plan; ``--apply`` archives exactly what the plan listed.
The report is deterministic (no timestamps, stable ordering) because
``/setup``'s Operations tab fingerprints it: the dry-run is re-derived at apply
time and the run is refused if the world moved underneath.

Usage (from a deployed container — this needs the Drive service account and the
app database, so it is not a laptop script; the browser route is
``/setup`` → Operations → "Clean up excluded email attachments"):

    uv run python scripts/cleanup_excluded_attachments.py            # plan only
    uv run python scripts/cleanup_excluded_attachments.py --apply    # archive
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from comms import attachments as comms_attachments  # noqa: E402
from core.config import Settings, get_settings  # noqa: E402
from docs import service as docs_service  # noqa: E402
from docs.store import STATUS_ACTIVE  # noqa: E402

ATTRIBUTION = "attachment-cleanup"


async def collect(settings: Settings, store: Any) -> list[dict[str, Any]]:
    """The active email-attachment documents an excluded type would refuse
    today. Ordered by the store (uploaded_at, id) — stable across runs."""
    patterns = comms_attachments.excluded_types(settings)
    if not patterns:
        return []
    rows = await store.list_by_doc_type(
        docs_service.EMAIL_ATTACHMENT_DOC_TYPE, status=STATUS_ACTIVE
    )
    return [
        r
        for r in rows
        if comms_attachments.is_excluded_type(
            r.get("filename"), r.get("mimeType"), patterns
        )
    ]


def render_plan(settings: Settings, rows: list[dict[str, Any]]) -> str:
    """The reviewable plan. Deterministic — it is fingerprinted."""
    patterns = comms_attachments.excluded_types(settings)
    out: list[str] = []
    out.append("Never-file list: " + (", ".join(patterns) if patterns else "(empty)"))
    if not patterns:
        out.append(
            "\nNothing to plan — COMMS_ATTACHMENT_EXCLUDED_TYPES is empty, so no "
            "file type is excluded. Set it at /setup first."
        )
        return "\n".join(out)
    if not rows:
        out.append("\nNo filed email attachment matches it. Nothing to archive.")
        return "\n".join(out)
    by_record: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        by_record.setdefault((r["entityType"], r["recordId"]), []).append(r)
    out.append("")
    for (entity, record_id), docs in by_record.items():
        name = docs[0].get("recordName") or ""
        out.append(f"{entity} {record_id}" + (f' — "{name}"' if name else ""))
        for d in docs:
            uploaded = (d.get("uploadedAt") or "")[:10]
            out.append(
                "    {fn:<34} {mime:<28} {when}  doc {doc}".format(
                    fn=(d.get("filename") or "")[:34],
                    mime=(d.get("mimeType") or "")[:28],
                    when=uploaded,
                    doc=d["id"],
                )
            )
    out.append("")
    out.append(
        f"Plan: archive {len(rows)} document(s) across {len(by_record)} record(s). "
        "Each file moves to its record folder's _Archived subfolder; nothing is "
        "deleted and every one can be restored from the Documents tab."
    )
    return "\n".join(out)


async def run(apply: bool = False, settings: Optional[Settings] = None) -> int:
    """Print the plan, and with ``apply`` archive it. Returns a shell code:
    0 = clean/applied, 1 = documents found (plan only), 2 = not runnable."""
    settings = settings or get_settings()
    store = docs_service.get_store(settings)
    if store is None:
        print("No document store — DATABASE_URL and GDRIVE_DOCS must be set.")
        return 2
    rows = await collect(settings, store)
    print(render_plan(settings, rows))
    if not apply or not rows:
        return 1 if rows else 0

    drive = await comms_attachments._service_drive(settings, ATTRIBUTION)
    if drive is None:
        print(
            "\nCannot archive: no Drive service account is configured "
            "(GOOGLE_SERVICE_ACCOUNT_JSON + GDRIVE_IDENTITY=service)."
        )
        return 2
    archived = 0
    failures: list[str] = []
    print("")
    for r in rows:
        try:
            await docs_service.archive_document(
                store, drive, r["entityType"], r["recordId"], r["id"]
            )
            archived += 1
        except Exception as exc:  # noqa: BLE001 — one bad row never stops the sweep
            failures.append(f"    {r.get('filename')} (doc {r['id']}): {exc}")
    print(f"Archived {archived} of {len(rows)} document(s).")
    if failures:
        print(f"{len(failures)} could not be archived and were left active:")
        for line in failures:
            print(line)
        print("Re-run to retry them — archiving is idempotent per document.")
    return 0 if not failures else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--apply", action="store_true",
        help="archive the planned documents (default: print the plan only)",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run(apply=args.apply)))


if __name__ == "__main__":
    main()
