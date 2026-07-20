"""Assignment-stamp derivation + merge-only reconciliation (one engine).

The drift class behind the 2026-07-20 Anthony Sacco incident: an engagement's
client records (contacts / client profile / company) missing the assigned
mentor's + co-mentors' login Users in ``assignedUsers``, so the mentors'
own-scope roles can't touch them (e.g. the session-attendee relate 403).
Records drift three ways — they predate the stamping machinery, they lost
stamps in the Contact/Account Multiple-Assigned-Users switch, or someone
hand-edited assignments in the CRM UI.

Consumers of this engine:

  * ``scripts/audit_assignment_stamps.py`` — the on-demand CLI report
    (+ ``--heal``);
  * :func:`run_stamp_reconciliation` — the worker's nightly self-heal
    (``ASSIGNMENT_RECONCILE_SECONDS``, the DOC-09 pattern), which makes the
    class converge no matter how the drift happened.

The contract (Doug's ruling 2026-07-20): the CRM's own links
(``mentorProfile`` + ``additionalMentors``) are the source of truth, and the
reconciliation is **merge-only** — it adds missing users, never removes
anyone (so it cannot revoke access; deliberate hand-REMOVALS get re-added
nightly, which is the accepted cost of self-healing).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from core.config import Settings
from core.espo import EspoClient, EspoError

from .service import assigned_user_id, is_assigned_to

log = logging.getLogger("cbm_intake.assignments.stamps")

ENGAGEMENT = "CEngagement"
CONTACT = "Contact"
CLIENT_PROFILE = "CClientProfile"
ACCOUNT = "Account"
MENTOR_PROFILE = "CMentorProfile"

# Engagements whose mentors no longer need access — skipped by default.
TERMINAL_STATUSES = frozenset(
    {"Completed", "Abandoned", "Inactive", "Declined", "Assignment Declined"}
)

_PAGE = 200

_ENGAGEMENT_SELECT = (
    "id,name,engagementStatus,mentorProfileId,mentorProfileName,"
    "primaryEngagementContactId,engagementClientId,"
    "clientOrganizationId,assignedUsersIds,assignedUserId"
)


async def all_engagements(client: Any) -> list[dict[str, Any]]:
    """Every engagement (paged), with the fields the audit needs."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = await client.list(
            ENGAGEMENT, select=_ENGAGEMENT_SELECT, max_size=_PAGE, offset=offset
        )
        page = data.get("list", [])
        rows.extend(page)
        if len(page) < _PAGE:
            return rows
        offset += _PAGE


async def entitled_user_ids(client: Any, eng: dict[str, Any]) -> dict[str, str]:
    """{user_id: label} for the assigned mentor + co-mentors (profiles with no
    linked login User contribute nothing — there is no user to stamp)."""
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


async def related_records(client: Any, eng: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(entity, id, label) for every record that should carry the stamps: the
    engagement itself, every related contact, the client profile, and the
    company (``clientOrganization`` with the profile's ``linkedCompany``
    fallback — the resolution the apps use)."""
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


async def missing_on(
    client: Any, entity: str, record_id: str, entitled: dict[str, str]
) -> tuple[Optional[list[str]], list[str]]:
    """(current assignedUsersIds, entitled user ids missing from the record)."""
    rec = await client.get(entity, record_id, select="assignedUserId,assignedUsersIds")
    missing = [uid for uid in entitled if not is_assigned_to(rec, uid)]
    return rec.get("assignedUsersIds"), missing


async def merge_missing(
    client: Any, entity: str, record_id: str,
    current: Optional[list[str]], missing: list[str],
) -> list[str]:
    """Merge ``missing`` into the record's ``assignedUsersIds`` (merge-only —
    existing users are always kept; the single ``assignedUserId`` is never
    touched). Returns the written list."""
    merged = list(current or [])
    merged += [u for u in missing if u not in merged]
    await client.update(entity, record_id, {"assignedUsersIds": merged})
    return merged


def system_client(settings: Settings) -> EspoClient:
    """The app's API-key client — entitlement derivation and healing must not
    vary with any staff user's ACL (the docs.grants pattern)."""
    return EspoClient(
        settings.espo_base_url, settings.espo_api_key, settings.request_timeout_seconds
    )


async def run_stamp_reconciliation(
    settings: Settings, *, client: Any = None
) -> Optional[dict[str, int]]:
    """One nightly self-heal pass (the worker's timer body).

    For every assigned, non-terminal engagement: derive the entitled users
    from the CRM's own links and MERGE any that are missing onto the
    engagement / contacts / client profile / company. Corrections and
    problems are logged (no alert — merges are the routine self-heal; the
    on-demand audit script is the reporting surface). Returns a summary, or
    None when there is no real CRM to run against."""
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    client = client or system_client(settings)
    summary = {
        "audited": 0, "engagementsHealed": 0, "recordsHealed": 0,
        "profilesWithoutUser": 0, "errors": 0,
    }
    for eng in await all_engagements(client):
        if not eng.get("mentorProfileId"):
            continue
        if (eng.get("engagementStatus") or "") in TERMINAL_STATUSES:
            continue
        summary["audited"] += 1
        try:
            entitled = await entitled_user_ids(client, eng)
            if not entitled:
                summary["profilesWithoutUser"] += 1
                log.warning(
                    "stamp reconciliation: %r (%s) — mentor profile %r has no "
                    "linked login User; nothing can be stamped",
                    eng.get("name"), eng["id"], eng.get("mentorProfileName"),
                )
                continue
            healed_here = False
            for entity, record_id, label in await related_records(client, eng):
                current, missing = await missing_on(client, entity, record_id, entitled)
                if not missing:
                    continue
                await merge_missing(client, entity, record_id, current, missing)
                summary["recordsHealed"] += 1
                healed_here = True
                log.info(
                    "stamp reconciliation: merged %s onto %s %s/%s (engagement %r)",
                    ", ".join(entitled[u] for u in missing),
                    label, entity, record_id, eng.get("name"),
                )
            if healed_here:
                summary["engagementsHealed"] += 1
        except EspoError as exc:
            summary["errors"] += 1
            log.warning(
                "stamp reconciliation: engagement %r (%s) failed: %s",
                eng.get("name"), eng["id"], exc,
            )
    log.info("assignment stamp reconciliation done: %s", summary)
    return summary
