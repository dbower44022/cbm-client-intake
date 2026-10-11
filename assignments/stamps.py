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


async def ensure_user_on_record(
    client: Any, entity: str, record_id: str, user_id: str
) -> bool:
    """Merge ONE user onto ONE record's ``assignedUsers`` if missing (the
    heal-on-access primitive). Returns True when a write happened."""
    rec = await client.get(entity, record_id, select="assignedUserId,assignedUsersIds")
    if is_assigned_to(rec, user_id):
        return False
    await merge_missing(client, entity, record_id, rec.get("assignedUsersIds"), [user_id])
    return True


# --- mentor personnel records (the SECOND drift class, found 2026-07-20) -------
# A mentor's own linked Contact (``CMentorProfile.contactRecord``) missing the
# mentor's own User: /mentorprofile routes contact-field saves to that Contact,
# and the Mentor Role edits Contacts at own scope — an unstamped own-Contact
# 403s the mentor's own profile save. Same drift causes as the engagement
# class; healed by the same merge-only rule (profile links = truth).

_PROFILE_SELECT = "id,name,mentorStatus,contactRecordId,assignedUserId,assignedUsersIds"


async def all_mentor_profiles(client: Any) -> list[dict[str, Any]]:
    """Every mentor profile (paged), with the mentor-contact audit fields."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = await client.list(
            MENTOR_PROFILE, select=_PROFILE_SELECT, max_size=_PAGE, offset=offset
        )
        page = data.get("list", [])
        rows.extend(page)
        if len(page) < _PAGE:
            return rows
        offset += _PAGE


# --- partner / funder records: the domain TEAM (the THIRD drift class) --------
# ``OPEN-ITEMS.md`` #40, Doug's ruling 2026-10-11 (option B): the Partner
# Manager and Sponsor Manager roles read their records, companies and contacts
# at *team* (the sponsor one today, the partner one the day the standard
# tightens it), and a record that belongs to no team is invisible to every
# non-administrator on that team — three of production's four funders were,
# and the training sandbox's six are again every morning, because the nightly
# reset restores a snapshot taken before they were put in the team by hand.
# Same contract as the user stamps: merge-only (a team is added, never
# removed), best-effort per record, the CRM's own links decide which company
# and contacts belong to the record. The quick-add stamps new records at
# source (v0.249.1); this pass converges everything that predates it or was
# un-teamed by hand.

#: (profile entity, the Settings attribute naming its team, the company FK,
#: the contacts link) — the sessions ``DomainConfig`` facts, repeated here so
#: the worker never imports the sessions package.
TEAM_DOMAINS: tuple[tuple[str, str, str, str], ...] = (
    ("CPartnerProfile", "partner_team_name", "partnerCompanyId", "contacts"),
    ("CSponsorProfile", "sponsor_team_name", "sponsorCompanyId", "sponsorContacts"),
)
ACCOUNT = "Account"


async def team_id_by_name(client: Any, name: str) -> Optional[str]:
    """The Team id for ``name``, or None when it does not exist / is unreadable."""
    if not (name or "").strip():
        return None
    team = await client.find_one("Team", "name", name.strip(), select="id")
    return team["id"] if team else None


async def ensure_team_on_record(
    client: Any, entity: str, record_id: str, team_id: str,
    current: Optional[list[str]] = None,
) -> bool:
    """Merge ONE team onto ONE record's ``teamsIds`` if missing. ``current`` is
    the record's teams when the caller already read them (a list row); None
    reads the record first. Returns True when a write happened."""
    if current is None:
        rec = await client.get(entity, record_id, select="teamsIds")
        current = rec.get("teamsIds") or []
    if team_id in current:
        return False
    await client.update(entity, record_id, {"teamsIds": list(current) + [team_id]})
    return True


async def all_domain_records(client: Any, entity: str, company_fk: str) -> list[dict[str, Any]]:
    """Every partner / funder record (paged) with its teams and company id."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = await client.list(
            entity, select=f"id,name,teamsIds,{company_fk}", max_size=_PAGE, offset=offset
        )
        page = data.get("list", [])
        rows.extend(page)
        if len(page) < _PAGE:
            return rows
        offset += _PAGE


async def run_team_reconciliation(
    settings: Settings, client: Any, summary: dict[str, int]
) -> None:
    """One pass of the domain-team heal, adding to ``summary``: for every
    partner / funder record, the record itself, its company and its contacts
    carry the domain's team. A team the CRM does not have is logged once and
    that domain skipped (nothing can be stamped); a record that fails is
    counted and the pass goes on."""
    for entity, team_attr, company_fk, contacts_link in TEAM_DOMAINS:
        team_name = getattr(settings, team_attr, "") or ""
        try:
            team_id = await team_id_by_name(client, team_name)
        except EspoError as exc:
            summary["errors"] += 1
            log.warning("team reconciliation: Team %r lookup failed: %s", team_name, exc)
            continue
        if not team_id:
            log.warning(
                "team reconciliation: Team %r not found — %s records cannot be "
                "stamped on this CRM", team_name, entity,
            )
            continue
        try:
            records = await all_domain_records(client, entity, company_fk)
        except EspoError as exc:
            summary["errors"] += 1
            log.warning("team reconciliation: %s listing failed: %s", entity, exc)
            continue
        for rec in records:
            summary["teamRecords"] += 1
            healed_here = False
            try:
                if await ensure_team_on_record(client, entity, rec["id"], team_id, rec.get("teamsIds") or []):
                    healed_here = True
                    log.info("team reconciliation: %s/%s %r joined %r",
                             entity, rec["id"], rec.get("name"), team_name)
                company_id = rec.get(company_fk)
                if company_id and await ensure_team_on_record(client, ACCOUNT, company_id, team_id):
                    healed_here = True
                    log.info("team reconciliation: company Account/%s of %r joined %r",
                             company_id, rec.get("name"), team_name)
                contacts = await client.list_related(
                    entity, rec["id"], contacts_link, select="id,teamsIds", max_size=_PAGE,
                )
                for ct in contacts.get("list", []):
                    if await ensure_team_on_record(client, CONTACT, ct["id"], team_id, ct.get("teamsIds") or []):
                        healed_here = True
                        log.info("team reconciliation: Contact/%s of %r joined %r",
                                 ct["id"], rec.get("name"), team_name)
            except EspoError as exc:
                summary["errors"] += 1
                log.warning("team reconciliation: %s %r (%s) failed: %s",
                            entity, rec.get("name"), rec["id"], exc)
                continue
            if healed_here:
                summary["teamHealed"] += 1


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
    engagement / contacts / client profile / company. Then (phase C) every
    partner / funder record, its company and its contacts carry the domain
    team. Corrections and
    problems are logged (no alert — merges are the routine self-heal; the
    on-demand audit script is the reporting surface). Returns a summary, or
    None when there is no real CRM to run against."""
    if settings.espo_dry_run or not settings.espo_api_key:
        return None
    client = client or system_client(settings)
    summary = {
        "audited": 0, "engagementsHealed": 0, "recordsHealed": 0,
        "profilesWithoutUser": 0, "errors": 0,
        "mentorProfiles": 0, "mentorContactsHealed": 0,
        "teamRecords": 0, "teamHealed": 0,
    }

    # Phase A — mentor personnel: every profile's linked Contact must carry the
    # profile's own User (the /mentorprofile own-save class, 2026-07-20).
    try:
        for prof in await all_mentor_profiles(client):
            uid = assigned_user_id(prof)
            contact_id = prof.get("contactRecordId")
            if not uid or not contact_id:
                continue
            summary["mentorProfiles"] += 1
            try:
                if await ensure_user_on_record(client, CONTACT, contact_id, uid):
                    summary["mentorContactsHealed"] += 1
                    log.info(
                        "stamp reconciliation: merged %r's User onto their own "
                        "Contact/%s", prof.get("name"), contact_id,
                    )
            except EspoError as exc:
                summary["errors"] += 1
                log.warning(
                    "stamp reconciliation: mentor contact heal failed for %r "
                    "(Contact/%s): %s", prof.get("name"), contact_id, exc,
                )
    except EspoError as exc:
        summary["errors"] += 1
        log.warning("stamp reconciliation: mentor profile listing failed: %s", exc)
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
    # Phase C — partner / funder records, their companies and contacts carry
    # the domain team (#40, Doug's ruling 2026-10-11). Same timer, same
    # summary line, so one log entry a night says what every pass found.
    try:
        await run_team_reconciliation(settings, client, summary)
    except Exception as exc:  # noqa: BLE001 — never takes the user phases down with it
        summary["errors"] += 1
        log.warning("team reconciliation failed: %s", exc)
    log.info("assignment stamp reconciliation done: %s", summary)
    return summary
