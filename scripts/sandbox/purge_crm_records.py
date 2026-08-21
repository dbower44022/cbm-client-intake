"""Empty the sandbox CRM of business records, keeping everything else.

This is the ONE-TIME clean slate before the training data is seeded — not the
nightly job.  The nightly reset (``reset_crm_sandbox.py``) restores a golden
baseline; this is how that baseline gets to be worth restoring.

Doug authorised this on 2026-08-21.  The reason is not tidiness: crm-test holds
what looks like real client data (real organisations, and individuals recorded
the way CBM records a client with no company yet), and the audience for the
instance is about to widen to every training group.  Session notes and
Communications are the sensitive part.  Pristine should mean entirely
fictional.

**Why deletes go through the API rather than truncating tables.**  A user's
email address lives in ``email_address`` / ``entity_email_address``, the same
tables a Contact's does.  Truncating "record" tables would silently strip every
login's address, and the same trap sits under attachments, stream notes and
every link table.  EspoCRM's own delete handles all of that, so this is slower
and correct rather than fast and destructive.

What is deliberately NOT touched: the schema (Entity Manager output lives in
files), roles, teams, users, email templates, portals, reports, workflows and
the Google/mailbox integration wiring.  Those are months of real configuration
work and the reason this is a record purge rather than a rebuild.

EspoCRM soft-deletes, so rows survive as ``deleted=1`` until the Cleanup job
runs.  Follow a purge with::

    ssh root@<droplet> 'docker exec espocrm php command.php run-job Cleanup'

...then capture the golden baseline.

Two entity groups need a decision rather than a default, so they are opt-in:

``--mentors``
    Deleting ``CMentorProfile`` unlinks every login from its manager profile,
    so the session tools go blind until the seed recreates them.  Right for a
    clean slate, wrong if you are only clearing client data.
``--events``
    ``CEvent`` doubles as CBM's org calendar on crm-test — most of its rows are
    internal team meetings, not workshops, and **something is still feeding it**
    (29 rows created in August 2026, the newest a real meeting from the day
    before this script was written).  Purging it is only durable once that sync
    is switched off; otherwise it refills with real calendar entries, which is
    both re-junking and a disclosure problem.

Read-only unless ``--apply``:

    uv run python scripts/sandbox/purge_crm_records.py
    uv run python scripts/sandbox/purge_crm_records.py --mentors --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.config import get_settings  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402

#: Child-before-parent. Deleting an Account first would strand its engagements
#: and leave the stream notes pointing at nothing.
PURGE_ORDER: tuple[str, ...] = (
    # activity and correspondence hanging off the records
    "CSession",
    "CCommunication",
    "CConversation",
    "CContribution",
    "CEventRegistration",
    "Meeting",
    "Call",
    "Task",
    "Document",
    "Email",
    # intake artefacts
    "CIntakeSubmission",
    "CInformationRequest",
    "CActionLog",
    # the record hubs
    "CEngagement",
    "CClientProfile",
    "CPartnerProfile",
    "CSponsorProfile",
    # people and companies last: everything above links to them
    "Contact",
    "Account",
)

OPTIONAL: dict[str, tuple[str, ...]] = {
    "mentors": ("CMentorProfile",),
    "events": ("CEvent",),
}

PAGE = 200  # EspoCRM's recordListMaxSizeLimit — more is a 403, not a truncation


async def purge_entity(client: EspoClient, entity: str, *, apply: bool) -> tuple[int, int]:
    """Delete every record of ``entity``. Returns (found, deleted)."""
    try:
        envelope = await client.list(entity, select="id", max_size=1)
    except EspoError as exc:
        print(f"  {entity:22} skipped — {exc}")
        return (0, 0)

    total = int(envelope.get("total") or 0)
    if not total or not apply:
        return (total, 0)

    deleted = 0
    while True:
        # Always read the first page: each delete shifts the window, so paging
        # with an offset would step over records.
        envelope = await client.list(entity, select="id", max_size=PAGE)
        rows = envelope.get("list", [])
        if not rows:
            break
        before = deleted
        for row in rows:
            try:
                await client.delete(entity, row["id"])
                deleted += 1
            except EspoError as exc:
                print(f"  {entity:22} {row['id']} not deleted — {exc}")
        if deleted == before:
            # A whole page refused: stop rather than loop on the same rows.
            print(f"  {entity:22} stopping — {len(rows)} record(s) could not be deleted")
            break
    return (total, deleted)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="actually delete")
    parser.add_argument("--mentors", action="store_true", help="also purge CMentorProfile")
    parser.add_argument("--events", action="store_true", help="also purge CEvent")
    args = parser.parse_args()

    settings = get_settings()
    base = settings.espo_base_url or ""
    if "crm-test" not in base.lower():
        print(f"REFUSING: ESPO_BASE_URL is {base!r}, not the crm-test sandbox.")
        return 2

    entities = list(PURGE_ORDER)
    for flag, extra in OPTIONAL.items():
        if getattr(args, flag):
            entities.extend(extra)

    print(f"\nPurging business records from {base}")
    print("APPLY — records will be deleted\n" if args.apply
          else "DRY RUN — nothing will be deleted\n")

    client = EspoClient(base, settings.espo_api_key, settings.request_timeout_seconds)
    found_total = deleted_total = 0
    for entity in entities:
        found, deleted = await purge_entity(client, entity, apply=args.apply)
        found_total += found
        deleted_total += deleted
        if found:
            suffix = f"  -> deleted {deleted}" if args.apply else ""
            print(f"  {entity:22} {found}{suffix}")

    print(f"\n{found_total} record(s) found, {deleted_total} deleted.")
    if not args.apply:
        print("\nRe-run with --apply to delete. Take a backup first:")
        print("  ssh root@104.131.45.208 '/var/www/espocrm/command.sh backup /root/espocrm-backup'")
    else:
        print("\nNow hard-delete the soft-deleted rows, then capture the baseline:")
        print("  ssh root@104.131.45.208 'docker exec espocrm php command.php run-job Cleanup'")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
