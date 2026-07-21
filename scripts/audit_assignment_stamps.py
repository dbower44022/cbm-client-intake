"""Audit (and optionally heal) assignment stamps on engagement client records.

The Anthony Sacco incident (2026-07-20): an engagement's client contact was
never stamped with the assigned mentor's login User in ``assignedUsers``, so
the mentor's own-scope role couldn't attach the contact as a session attendee
(EspoCRM relate requires edit on the foreign record).

This is the on-demand CLI over the shared engine in
:mod:`assignments.stamps` (the worker runs the same engine nightly as the
self-healing reconciliation). It walks every ASSIGNED engagement, derives who
*should* hold access — the assigned mentor's User plus every co-mentor's
(``mentorProfile`` + ``additionalMentors``, the CRM's own links as the source
of truth) — and compares against the actual ``assignedUsers`` on the
engagement, its contacts, the client profile, and the company.

Default is a READ-ONLY report. ``--heal`` merges the missing users into each
record's ``assignedUsersIds`` (merge-only — never removes anyone; the single
``assignedUserId`` is never touched), the exact write Client Administration's
"Repair assignment" performs per engagement.

Usage (reads ESPO_BASE_URL / ESPO_API_KEY from the env / .env — crm-test by
default; for prod use the overlay-key one-liner from CLAUDE.md's
"Form dropdown lists" section):

    uv run python scripts/audit_assignment_stamps.py            # report only
    uv run python scripts/audit_assignment_stamps.py --heal     # apply merges
    uv run python scripts/audit_assignment_stamps.py --all-statuses

By default terminal engagements (Completed / Abandoned / Inactive / Declined /
Assignment Declined) are skipped — their mentors no longer need access;
``--all-statuses`` includes them.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_settings  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402
from assignments import stamps  # noqa: E402


async def run(heal: bool, all_statuses: bool) -> int:
    settings = get_settings()  # env vars first, .env fallback (the app's own rule)
    base, key = settings.espo_base_url, settings.espo_api_key
    if not base or not key:
        print("ESPO_BASE_URL / ESPO_API_KEY must be set (see the module docstring).")
        return 2
    client = EspoClient(base, key)

    # Phase A — mentor personnel: each profile's linked Contact must carry the
    # profile's own User (the /mentorprofile own-save 403 class, 2026-07-20).
    profiles = await stamps.all_mentor_profiles(client)
    print(f"Auditing {len(profiles)} mentor profile(s) on {base}")
    broken_mentor_contacts = healed_mentor_contacts = 0
    for prof in profiles:
        uid = stamps.assigned_user_id(prof)
        contact_id = prof.get("contactRecordId")
        if not uid or not contact_id:
            continue
        try:
            current, missing = await stamps.missing_on(
                client, stamps.CONTACT, contact_id, {uid: prof.get("name") or "mentor"}
            )
            if not missing:
                continue
            broken_mentor_contacts += 1
            print(
                f"✗ mentor {prof.get('name')!r} ({prof.get('mentorStatus')}): own "
                f"Contact/{contact_id} is missing their User "
                f"(assignedUsers={current or []})"
            )
            if heal:
                merged = await stamps.merge_missing(
                    client, stamps.CONTACT, contact_id, current, missing
                )
                healed_mentor_contacts += 1
                print(f"  ✚ healed: Contact/{contact_id} -> {merged}")
        except EspoError as exc:
            print(f"⚠ mentor {prof.get('name')!r}: contact audit failed: {exc}")
    if not broken_mentor_contacts:
        print("All mentor own-Contacts carry their User. ✔")
    print()

    engagements = await stamps.all_engagements(client)
    print(f"Auditing {len(engagements)} engagement(s) on {base}\n")

    audited = skipped_unassigned = skipped_status = 0
    broken_engagements = 0
    healed_records = 0
    findings: list[str] = []

    for eng in engagements:
        status = eng.get("engagementStatus") or "?"
        if not eng.get("mentorProfileId"):
            skipped_unassigned += 1
            continue
        if not all_statuses and status in stamps.TERMINAL_STATUSES:
            skipped_status += 1
            continue
        audited += 1
        try:
            entitled = await stamps.entitled_user_ids(client, eng)
            if not entitled:
                findings.append(
                    f"⚠ {eng.get('name')!r} ({eng['id']}, {status}): mentor profile "
                    f"{eng.get('mentorProfileName')!r} has NO linked login User — "
                    f"nothing can be stamped (fix the profile in /mentoradmin)."
                )
                continue
            broken_here = False
            for entity, record_id, label in await stamps.related_records(client, eng):
                current, missing = await stamps.missing_on(
                    client, entity, record_id, entitled
                )
                if not missing:
                    continue
                broken_here = True
                names = ", ".join(entitled[u] for u in missing)
                findings.append(
                    f"✗ {eng.get('name')!r} ({eng['id']}, {status}): {label} "
                    f"{entity}/{record_id} is missing {names} "
                    f"(assignedUsers={current or []})"
                )
                if heal:
                    merged = await stamps.merge_missing(
                        client, entity, record_id, current, missing
                    )
                    healed_records += 1
                    findings.append(f"  ✚ healed: {entity}/{record_id} -> {merged}")
            if broken_here:
                broken_engagements += 1
        except EspoError as exc:
            findings.append(f"⚠ {eng.get('name')!r} ({eng['id']}): audit failed: {exc}")

    for line in findings:
        print(line)
    print(
        f"\nSummary: {audited} engagement(s) audited, {broken_engagements} with "
        f"missing stamps, {skipped_unassigned} unassigned skipped, "
        f"{skipped_status} terminal-status skipped; "
        f"{broken_mentor_contacts} mentor own-Contact(s) missing their User."
    )
    if heal:
        print(
            f"Healed {healed_records} engagement record(s) + "
            f"{healed_mentor_contacts} mentor Contact(s) (merge-only; nothing removed)."
        )
    elif broken_engagements or broken_mentor_contacts:
        print("Re-run with --heal to merge the missing users (mentor own-Contacts "
              "can also be healed by /mentoradmin's Update Mentor Status; "
              "engagements by right-click → Repair assignment).")
    return 1 if (broken_engagements or broken_mentor_contacts) else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--heal", action="store_true",
                        help="merge missing users into assignedUsers (default: report only)")
    parser.add_argument("--all-statuses", action="store_true",
                        help="include Completed/Abandoned/etc engagements")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(heal=args.heal, all_statuses=args.all_statuses)))


if __name__ == "__main__":
    main()
