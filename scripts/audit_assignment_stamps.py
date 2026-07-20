"""Audit (and optionally heal) assignment stamps on engagement client records.

The Anthony Sacco incident (2026-07-20): an engagement's client contact was
never stamped with the assigned mentor's login User in ``assignedUsers``, so
the mentor's own-scope role couldn't attach the contact as a session attendee
(EspoCRM relate requires edit on the foreign record). Records drift out of
sync three ways: they predate the stamping machinery, they lost stamps when
Contact/Account switched to Multiple Assigned Users (the v0.82.0 mechanism),
or someone hand-edited assignments in the CRM UI.

This script walks every ASSIGNED engagement, derives who *should* hold access
— the assigned mentor's User plus every co-mentor's (``mentorProfile`` +
``additionalMentors``, the CRM's own links as the source of truth) — and
compares against the actual ``assignedUsers`` on:

  * the engagement itself,
  * every related contact (primary + ``engagementContacts``),
  * the client profile (``engagementClientId``),
  * the company (``clientOrganizationId``, with the client profile's
    ``linkedCompany`` fallback — the same resolution the apps use).

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
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_settings  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402
from assignments.service import assigned_user_id, is_assigned_to  # noqa: E402

ENGAGEMENT = "CEngagement"
CONTACT = "Contact"
CLIENT_PROFILE = "CClientProfile"
ACCOUNT = "Account"
MENTOR_PROFILE = "CMentorProfile"

SKIPPED_STATUSES = {
    "Completed", "Abandoned", "Inactive", "Declined", "Assignment Declined",
}

_PAGE = 200


async def _all_engagements(client: EspoClient) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = await client.list(
            ENGAGEMENT,
            select=(
                "id,name,engagementStatus,mentorProfileId,mentorProfileName,"
                "primaryEngagementContactId,engagementClientId,"
                "clientOrganizationId,assignedUsersIds,assignedUserId"
            ),
            max_size=_PAGE,
            offset=offset,
        )
        page = data.get("list", [])
        rows.extend(page)
        if len(page) < _PAGE:
            return rows
        offset += _PAGE


async def _entitled_user_ids(client: EspoClient, eng: dict[str, Any]) -> dict[str, str]:
    """{user_id: label} for the assigned mentor + co-mentors (skips profiles
    with no linked login User — nothing to stamp for them)."""
    entitled: dict[str, str] = {}
    if eng.get("mentorProfileId"):
        prof = await client.get(
            MENTOR_PROFILE, eng["mentorProfileId"],
            select="name,assignedUserId,assignedUsersIds",
        )
        uid = assigned_user_id(prof)
        if uid:
            entitled[uid] = prof.get("name") or "assigned mentor"
    co = await client.list_related(
        ENGAGEMENT, eng["id"], "additionalMentors",
        select="name,assignedUserId,assignedUsersIds", max_size=50,
    )
    for row in co.get("list", []):
        uid = assigned_user_id(row)
        if uid:
            entitled.setdefault(uid, row.get("name") or "co-mentor")
    return entitled


async def _related_records(
    client: EspoClient, eng: dict[str, Any]
) -> list[tuple[str, str, str]]:
    """(entity, id, label) for every client record that should carry the stamps."""
    records: list[tuple[str, str, str]] = [(ENGAGEMENT, eng["id"], "engagement")]
    contact_ids: set[str] = set()
    if eng.get("primaryEngagementContactId"):
        contact_ids.add(eng["primaryEngagementContactId"])
    related = await client.list_related(
        ENGAGEMENT, eng["id"], "engagementContacts", select="id", max_size=200
    )
    for row in related.get("list", []):
        contact_ids.add(row["id"])
    records += [(CONTACT, cid, "contact") for cid in sorted(contact_ids)]
    client_id = eng.get("engagementClientId")
    account_id = eng.get("clientOrganizationId")
    if client_id:
        records.append((CLIENT_PROFILE, client_id, "client profile"))
        if not account_id:
            prof = await client.get(CLIENT_PROFILE, client_id, select="linkedCompanyId")
            account_id = prof.get("linkedCompanyId")
    if account_id:
        records.append((ACCOUNT, account_id, "company"))
    return records


async def _missing_on(
    client: EspoClient, entity: str, record_id: str, entitled: dict[str, str]
) -> tuple[Optional[list[str]], list[str]]:
    """(current assignedUsersIds, entitled user ids missing from the record)."""
    rec = await client.get(entity, record_id, select="assignedUserId,assignedUsersIds")
    missing = [uid for uid in entitled if not is_assigned_to(rec, uid)]
    return rec.get("assignedUsersIds"), missing


async def run(heal: bool, all_statuses: bool) -> int:
    settings = get_settings()  # env vars first, .env fallback (the app's own rule)
    base, key = settings.espo_base_url, settings.espo_api_key
    if not base or not key:
        print("ESPO_BASE_URL / ESPO_API_KEY must be set (see the module docstring).")
        return 2
    client = EspoClient(base, key)
    engagements = await _all_engagements(client)
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
        if not all_statuses and status in SKIPPED_STATUSES:
            skipped_status += 1
            continue
        audited += 1
        try:
            entitled = await _entitled_user_ids(client, eng)
            if not entitled:
                findings.append(
                    f"⚠ {eng.get('name')!r} ({eng['id']}, {status}): mentor profile "
                    f"{eng.get('mentorProfileName')!r} has NO linked login User — "
                    f"nothing can be stamped (fix the profile in /mentoradmin)."
                )
                continue
            broken_here = False
            for entity, record_id, label in await _related_records(client, eng):
                current, missing = await _missing_on(client, entity, record_id, entitled)
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
                    merged = list(current or [])
                    merged += [u for u in missing if u not in merged]
                    await client.update(entity, record_id, {"assignedUsersIds": merged})
                    healed_records += 1
                    findings.append(f"  ✚ healed: {entity}/{record_id} -> {merged}")
            if broken_here:
                broken_engagements += 1
        except EspoError as exc:
            findings.append(f"⚠ {eng.get('name')!r} ({eng['id']}): audit failed: {exc}")

    for line in findings:
        print(line)
    print(
        f"\nSummary: {audited} audited, {broken_engagements} engagement(s) with "
        f"missing stamps, {skipped_unassigned} unassigned skipped, "
        f"{skipped_status} terminal-status skipped."
    )
    if heal:
        print(f"Healed {healed_records} record(s) (merge-only; nothing removed).")
    elif broken_engagements:
        print("Re-run with --heal to merge the missing users, or use Client "
              "Administration's right-click → Repair assignment per engagement.")
    return 1 if broken_engagements else 0


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
