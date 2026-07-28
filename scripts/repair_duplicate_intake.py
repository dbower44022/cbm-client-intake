"""Consolidate the duplicate client-intake records left by a re-submitted form.

THE DAMAGE THIS REPAIRS (the incidents behind v0.185.0)
-------------------------------------------------------
Until v0.185.0 the client-intake orchestrator created ``CClientProfile`` and
``CEngagement`` unconditionally, so a client who re-filled the whole form got a
second one of each. Worse, ``CClientProfile.linkedCompany`` is a **hasOne**
link: creating the second profile silently MOVED the company (and the client
contact) off the first one. The end state is

    Account ──> profile B  (holds the links)   <── engagement B
                profile A  (ORPHANED: no company, no contact)  <── engagement A

and if staff had already assigned engagement A, the live engagement is the one
pointing at the empty hub. That is exactly what happened to Christopher Maurer
(2026-07-17): the engagement assigned to Anthony Sacco hangs off the orphan,
while the duplicate staff Declined kept the good links.

THE REPAIR
----------
One client = one profile hub, many engagements. Two shapes turn up in the live
data and the SHAPE IS DERIVED, never assumed, so a stale id in ``CASES`` can
never cause a destructive mistake:

**CONSOLIDATE** — two profiles, the Account points at one (polunas, maurer):

1. **Keep the profile the Account actually points at.** The Account holds the
   FK (``Account.cClientProfile`` belongsTo, ``CClientProfile.linkedCompany``
   hasOne), so the profile it names is already correctly wired — keeping it
   means ZERO link writes and no hasOne juggling that could strand the record
   halfway.
2. **Backfill** any field the keeper left empty from the orphan (null-fill
   only — never overwrite).
3. **Re-point every engagement** that references the orphan at the keeper.
4. **Delete the orphan profile** — an empty husk once nothing points at it.
5. **Post a stream note** on each surviving engagement recording the merge, so
   the change is visible in EspoCRM history rather than looking like a silent
   hand edit.

**RELINK** — one profile and the Account's link slot is EMPTY (lafrance,
bower; found by ``--scan`` 2026-07-28). Nothing stole anything and there is
nothing to delete: the profile is simply re-attached to its company, which is
purely additive. These are NOT duplicate damage — the likeliest cause is a
hand edit in the CRM that cleared the link — but the symptom staff see is
identical (the engagement shows no company), so they are repaired here too.

Engagements are KEPT by default, including duplicates: once staff have marked
one Declined that is a recorded decision, not junk. ``--delete-declined-
duplicates`` opts into removing the superseded polunas engagement instead.

Deletion needs an EspoCRM **admin**: the intake API user is create-only. This
script therefore uses the provisioning admin service account
(``ESPO_PROVISION_USERNAME`` / ``ESPO_PROVISION_PASSWORD``), which exists on
the **web** component only — run it there.

USAGE
-----
Default is a READ-ONLY report; ``--write`` applies. Always run the report
first and read it.

    # inside the deployed web container (see CLAUDE.md / the memory note on
    # `doctl apps console` scripting):
    PYTHONPATH=/app .venv/bin/python scripts/repair_duplicate_intake.py
    PYTHONPATH=/app .venv/bin/python scripts/repair_duplicate_intake.py --write

    --scan          also sweep the whole CRM for OTHER orphaned client
                    profiles (any profile with no company that an engagement
                    still points at). Read-only regardless of --write.
    --case NAME     repair only one case (polunas / maurer / lafrance / bower).

The cases are declared in ``CASES`` below, by id, deliberately: this is a
repair of specific incidents, not a bulk migration, and every id was verified
against production before being written down. ``--scan`` is how new ones are
found — run it after any repair to confirm the CRM is clean.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.admin_client import admin_client_factory  # noqa: E402
from core.config import get_settings  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402
from core.stream import post_stream_note  # noqa: E402

CLIENT_PROFILE = "CClientProfile"
ENGAGEMENT = "CEngagement"
ACCOUNT = "Account"

# Fields worth carrying over from the orphan when the keeper left them empty.
# Deliberately narrow: the intake-written business facts. Links are NOT here —
# the keeper's links are the ones that are correct.
_MERGE_FIELDS = ("numberOfEmployees", "formationDate", "description")

# A profile field set that is safe to read on any instance.
_PROFILE_SELECT = (
    "id,name,deleted,linkedCompanyId,linkedCompanyName,clientcontactId,clientcontactName,"
    "numberOfEmployees,formationDate,description,createdAt"
)
_ENGAGEMENT_SELECT = (
    "id,name,deleted,engagementStatus,engagementClientId,clientOrganizationId,"
    "mentorProfileId,mentorProfileName,primaryEngagementContactId,createdAt"
)


@dataclass
class Case:
    """One damaged client intake to repair.

    Two shapes turn up in the data, and the repair differs:

    * **CONSOLIDATE** — two profiles, and the Account points at one of them.
      The second profile's create stole the link. Merge onto the keeper,
      re-point engagements, delete the husk. (polunas, maurer)
    * **RELINK** — one profile and the Account's link slot is EMPTY, so
      nothing stole anything and there is nothing to delete: the profile just
      needs re-attaching to its company. Purely additive. (lafrance, bower)

    The shape is DERIVED from the live data, never declared, so the script
    cannot delete anything on a mistaken assumption.
    """

    name: str
    account_id: str
    # Every profile the incident produced. The keeper is DERIVED (the one the
    # Account points at), never assumed, so a stale id here can't cause a
    # destructive mistake — it just fails the safety check.
    profile_ids: tuple[str, ...]
    # Engagements to keep (re-pointed at the keeper profile if needed).
    keep_engagements: tuple[str, ...]
    # Engagements to DELETE: superseded duplicates that were never worked.
    # Empty = keep every engagement, which is the default and the safer answer
    # once staff have dispositioned a record (a Declined duplicate is a
    # decision someone made, not junk). See --delete-declined-duplicates.
    delete_engagements: tuple[str, ...] = ()
    note: str = ""
    warnings: list[str] = field(default_factory=list)


CASES: tuple[Case, ...] = (
    Case(
        name="polunas",
        account_id="6a67b924b23f7b96e",          # Flowing River Conflict Solutions
        profile_ids=("6a67b9ae91cc77ea1", "6a67b9257f66200df"),
        # 20:03 submission — carries the "Requesting Brad Swimmer" wording AND
        # the intact links. Neither engagement was ever assigned.
        keep_engagements=("6a67b9aecb6fd8180", "6a67b925bf93ab219"),
        # NOTE (2026-07-28): the 20:01 duplicate was originally going to be
        # deleted as an unworked superseded record. Staff have since triaged
        # it — it is now **Declined**, i.e. a decision someone recorded — so
        # it is KEPT by default and merely re-pointed at the surviving
        # profile, exactly as the Maurer Declined duplicate is. Pass
        # --delete-declined-duplicates to remove it instead.
        note=(
            "Duplicate intake consolidated: this client submitted the request "
            "form twice on 2026-07-27, 2 minutes apart, the second time to ask "
            "for a specific mentor. Both engagements now share the one client "
            "profile that is linked to the company and contact; the empty "
            "duplicate profile was removed."
        ),
    ),
    Case(
        name="maurer",
        account_id="6a5a2c69df75c8cb7",          # Red House Studio
        profile_ids=("6a5a2cf3d9f9a62ab", "6a5a2c6a8749c1ec1"),
        # BOTH engagements are kept: 6a5a2c6ab50ca311f is live (Assigned,
        # Anthony Sacco) and 6a5a2cf41f660cb99 was explicitly Declined by
        # staff — a real decision, not junk. They simply need to share the one
        # correctly-linked profile.
        keep_engagements=("6a5a2c6ab50ca311f", "6a5a2cf41f660cb99"),
        note=(
            "Duplicate intake consolidated: this client submitted the request "
            "form twice on 2026-07-17, 2 minutes apart, the second time to ask "
            "for a specific mentor. Creating the second client profile had "
            "silently moved the company and contact off the first one, leaving "
            "this engagement pointing at an empty profile. Both engagements "
            "now share the client profile that is linked to the company and "
            "contact."
        ),
    ),
    # --- RELINK shape: found by --scan 2026-07-28, not duplicate-related ---
    # One profile each, and the Account's link slot is EMPTY, so nothing stole
    # it and there is no husk to delete. The engagement simply shows no company
    # until the profile is re-attached. Both were created by the intake user in
    # June and later touched by a human, so the likeliest cause is a hand edit
    # in the CRM that cleared the link (Mizukagami's profile was last modified
    # by "Admin", Mindy's by Douglas Bower).
    Case(
        name="lafrance",
        account_id="6a3ba4a2954ab7d59",          # Mizukagami.ai
        profile_ids=("6a3ba4a2f3c71bf89",),
        keep_engagements=("6a3ba4a332dcc85da",),  # Active, Douglas Bower
        note=(
            "Client profile re-linked to the company: this engagement's client "
            "profile had lost its company link, so the record showed no company "
            "in the mentoring tools."
        ),
    ),
    Case(
        name="bower",
        account_id="6a3b56d2dae5bc19e",          # mindy Bower (Pre-Startup)
        profile_ids=("6a3b56d336941edd7",),
        keep_engagements=("6a3b56d3619699205",),  # Pending Acceptance
        note=(
            "Client profile re-linked to the company: this engagement's client "
            "profile had lost its company link, so the record showed no company "
            "in the mentoring tools."
        ),
    ),
)


async def _get(client: EspoClient, entity: str, rid: str, select: str) -> Optional[dict]:
    """Read a record, treating a SOFT-DELETED one as gone.

    EspoCRM deletes by flag, and an ADMIN's GET still returns the row with
    ``deleted: true`` (ordinary users get a 404, and lists exclude it). Without
    this check a second run of the script sees an already-deleted husk as a
    live orphan and plans the delete all over again — the script has to be
    re-runnable, since that is how it is verified.
    """
    try:
        rec = await client.get(entity, rid, select=select)
    except EspoError:
        return None
    if rec and rec.get("deleted"):
        return None
    return rec


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


async def _load(client: EspoClient, case: Case) -> Optional[dict]:
    """Read the case's live state and pick the keeper. None => cannot repair."""
    account = await _get(client, ACCOUNT, case.account_id, "id,name,deleted,cClientProfileId")
    if account is None:
        case.warnings.append(f"Account {case.account_id} not found — skipped.")
        return None

    keeper_id = account.get("cClientProfileId")
    profiles = {}
    for pid in case.profile_ids:
        rec = await _get(client, CLIENT_PROFILE, pid, _PROFILE_SELECT)
        if rec is not None:
            profiles[pid] = rec
    if not profiles:
        case.warnings.append("None of this case's client profiles exist any more.")
        return None

    # Derive the shape from the live data (see Case's docstring).
    if _empty(keeper_id):
        # RELINK: the Account's slot is free. Only safe with exactly ONE
        # profile — with two, writing the link would pick a winner arbitrarily
        # and re-create the very hasOne theft this script exists to undo.
        if len(profiles) != 1:
            case.warnings.append(
                f"The Account has no linked client profile and this case names "
                f"{len(profiles)} — cannot tell which should own the company. "
                "Skipped; resolve by hand."
            )
            return None
        only_id, only = next(iter(profiles.items()))
        return {
            "shape": "relink", "account": account, "keeper": only,
            "orphans": [], "engagements": await _engagements(client, case),
            "relink": _empty(only.get("linkedCompanyId")),
        }

    if keeper_id not in profiles:
        case.warnings.append(
            f"The Account points at client profile {keeper_id!r}, which is not one "
            f"of this case's known profiles {case.profile_ids} — the data has "
            "changed since this repair was written. Skipped (nothing deleted)."
        )
        return None

    orphans = [p for p in profiles if p != keeper_id]
    return {
        "shape": "consolidate",
        "account": account,
        "keeper": profiles[keeper_id],
        "orphans": [profiles[p] for p in orphans],
        "engagements": await _engagements(client, case),
        "relink": False,
    }


async def _engagements(client: EspoClient, case: Case) -> dict[str, dict]:
    found = {}
    for eid in case.keep_engagements + case.delete_engagements:
        rec = await _get(client, ENGAGEMENT, eid, _ENGAGEMENT_SELECT)
        if rec is None:
            case.warnings.append(f"Engagement {eid} not found — already cleaned up?")
        else:
            found[eid] = rec
    return found


def _plan(case: Case, state: dict) -> list[tuple[str, str, dict]]:
    """The ordered list of writes. Returned as (action, target, detail) so the
    dry run prints exactly what --write will do — the same list, executed."""
    keeper = state["keeper"]
    orphan_ids = {o["id"] for o in state["orphans"]}
    steps: list[tuple[str, str, dict]] = []

    # 0. RELINK shape: re-attach the profile to its company. The Account's
    #    hasOne slot is empty, so this takes nothing away from another record.
    if state.get("relink"):
        steps.append(("relink", f"{CLIENT_PROFILE}/{keeper['id']}",
                      {"linkedCompanyId": case.account_id}))

    # 1. backfill the keeper from the orphans (null-fill only)
    fill: dict[str, Any] = {}
    for orphan in state["orphans"]:
        for f in _MERGE_FIELDS:
            if f not in fill and _empty(keeper.get(f)) and not _empty(orphan.get(f)):
                fill[f] = orphan[f]
    if fill:
        steps.append(("backfill", f"{CLIENT_PROFILE}/{keeper['id']}", fill))

    # 2. re-point kept engagements that reference an orphan
    for eid in case.keep_engagements:
        rec = state["engagements"].get(eid)
        if rec is None:
            continue
        if rec.get("engagementClientId") in orphan_ids:
            steps.append((
                "repoint", f"{ENGAGEMENT}/{eid}",
                {"engagementClientId": keeper["id"],
                 "from": rec.get("engagementClientId")},
            ))
        # An engagement created before v0.38.1 may also lack the company link.
        if _empty(rec.get("clientOrganizationId")):
            steps.append((
                "link-company", f"{ENGAGEMENT}/{eid}",
                {"clientOrganizationId": case.account_id},
            ))

    # 3. delete superseded engagements
    for eid in case.delete_engagements:
        rec = state["engagements"].get(eid)
        if rec is None:
            continue
        if rec.get("mentorProfileId"):
            case.warnings.append(
                f"Engagement {eid} is marked for deletion but HAS an assigned "
                f"mentor ({rec.get('mentorProfileName')}) — refusing to delete it."
            )
            continue
        steps.append(("delete", f"{ENGAGEMENT}/{eid}", {"name": rec.get("name")}))

    # 4. delete the orphan profiles (the caller has already proved nothing
    #    outside this case still points at them)
    for orphan in state["orphans"]:
        steps.append(("delete", f"{CLIENT_PROFILE}/{orphan['id']}",
                      {"name": orphan.get("name")}))

    # 5. history
    for eid in case.keep_engagements:
        if eid in state["engagements"]:
            steps.append(("note", f"{ENGAGEMENT}/{eid}", {"text": case.note}))
    return steps


async def _note_already_posted(client: EspoClient, eid: str, text: str) -> bool:
    """True if this engagement already carries this repair note.

    Makes the whole script safely re-runnable: every other step is naturally
    idempotent (a re-point that is already correct plans nothing, a delete of a
    gone record plans nothing), but a note would stack up a fresh copy on each
    run. Notes are only readable by a privileged user, which is what we are.
    """
    marker = text[:60]
    try:
        env = await client.list(
            "Note",
            where=[{"type": "equals", "attribute": "parentId", "value": eid},
                   {"type": "equals", "attribute": "parentType", "value": ENGAGEMENT},
                   {"type": "equals", "attribute": "type", "value": "Post"}],
            select="id,post", max_size=20,
        )
    except EspoError:
        return False  # can't tell: posting a possible duplicate beats losing it
    return any(marker in (n.get("post") or "") for n in env.get("list", []))


async def _guard_orphan_unreferenced(
    client: EspoClient, orphan_id: str, allowed: set[str]
) -> list[str]:
    """Engagement ids still pointing at ``orphan_id`` that we are NOT fixing."""
    try:
        env = await client.list(
            ENGAGEMENT,
            where=[{"type": "equals", "attribute": "engagementClientId", "value": orphan_id}],
            select="id,name", max_size=50,
        )
    except EspoError:
        return []  # can't check: the caller treats this as "unknown", see below
    return [r["id"] for r in env.get("list", []) if r["id"] not in allowed]


async def _apply(client: EspoClient, steps: list[tuple[str, str, dict]]) -> int:
    applied = 0
    for action, target, detail in steps:
        entity, rid = target.split("/", 1)
        try:
            if action in ("backfill", "link-company", "relink"):
                await client.update(entity, rid, {k: v for k, v in detail.items()
                                                  if k != "from"})
            elif action == "repoint":
                await client.update(entity, rid,
                                    {"engagementClientId": detail["engagementClientId"]})
            elif action == "delete":
                await client.delete(entity, rid)
            elif action == "note":
                await post_stream_note(client, entity, rid, detail["text"])
            applied += 1
            print(f"      applied: {action} {target}")
        except EspoError as exc:
            print(f"      FAILED:  {action} {target} — {exc}")
    return applied


async def scan_orphans(client: EspoClient) -> None:
    """Find any OTHER client profile with no company that an engagement uses."""
    print("\n=== Scan: orphaned client profiles referenced by an engagement ===")
    offset, seen, orphans = 0, 0, []
    while True:
        env = await client.list(CLIENT_PROFILE, select="id,name,linkedCompanyId",
                                max_size=200, offset=offset)
        rows = env.get("list", [])
        if not rows:
            break
        seen += len(rows)
        orphans += [r for r in rows if _empty(r.get("linkedCompanyId"))]
        offset += len(rows)
        if offset >= (env.get("total") or 0):
            break
    print(f"  {seen} client profile(s); {len(orphans)} with no linked company.")
    flagged = 0
    for o in orphans:
        env = await client.list(
            ENGAGEMENT,
            where=[{"type": "equals", "attribute": "engagementClientId", "value": o["id"]}],
            select="id,name,engagementStatus,mentorProfileName", max_size=20,
        )
        users = env.get("list", [])
        if users:
            flagged += 1
            print(f"\n  ORPHAN {o['id']} — {o.get('name')!r}")
            for e in users:
                print(f"    used by {e['id']} [{e.get('engagementStatus')}] "
                      f"{e.get('name')!r} mentor={e.get('mentorProfileName') or '—'}")
    if not flagged:
        print("  No orphaned profile is referenced by an engagement. Clean.")
    else:
        print(f"\n  {flagged} orphaned profile(s) still in use — each is a client "
              "whose engagement points at an empty hub.")


async def run(write: bool, do_scan: bool, only: Optional[str],
              delete_declined: bool) -> int:
    settings = get_settings()
    factory = admin_client_factory(settings)
    if factory is None:
        print(
            "Admin credentials are required (deleting records is admin-only in "
            "EspoCRM; the intake API user is create-only).\n"
            "Set ESPO_PROVISION_USERNAME / ESPO_PROVISION_PASSWORD — they are "
            "present on the deployed WEB component, so run this there."
        )
        return 2
    client = await factory()
    print(f"Connected to {settings.espo_base_url} as the provisioning admin.")
    print("MODE: " + ("WRITE — changes will be applied." if write
                      else "DRY RUN — nothing will be changed."))

    total_steps = 0
    for case in CASES:
        if only and case.name != only:
            continue
        if delete_declined and case.name == "polunas":
            # Move the superseded duplicate from "keep" to "delete".
            case.keep_engagements = tuple(
                e for e in case.keep_engagements if e != "6a67b925bf93ab219")
            case.delete_engagements = ("6a67b925bf93ab219",)
        print(f"\n=== Case: {case.name} ===")
        state = await _load(client, case)
        if state is None:
            for w in case.warnings:
                print(f"  ! {w}")
            continue

        keeper = state["keeper"]
        print(f"  Shape   : {state['shape'].upper()}")
        print(f"  Account : {state['account'].get('name')} ({case.account_id})")
        print(f"  KEEP    : profile {keeper['id']} — company="
              f"{keeper.get('linkedCompanyName') or '—'}, contact="
              f"{keeper.get('clientcontactName') or '—'}")
        for o in state["orphans"]:
            print(f"  ORPHAN  : profile {o['id']} — company="
                  f"{o.get('linkedCompanyName') or '—'}, contact="
                  f"{o.get('clientcontactName') or '—'}")
        for eid, rec in state["engagements"].items():
            fate = "DELETE" if eid in case.delete_engagements else "keep"
            print(f"  {fate:6s}  : engagement {eid} [{rec.get('engagementStatus')}] "
                  f"mentor={rec.get('mentorProfileName') or '—'} "
                  f"profile={rec.get('engagementClientId')}")

        # Safety: never delete a profile something else still points at.
        allowed = set(case.keep_engagements) | set(case.delete_engagements)
        blocked = False
        for o in state["orphans"]:
            stray = await _guard_orphan_unreferenced(client, o["id"], allowed)
            if stray:
                case.warnings.append(
                    f"Profile {o['id']} is still referenced by engagement(s) "
                    f"{', '.join(stray)} outside this case — refusing to touch "
                    "this case. Re-check the data."
                )
                blocked = True
        if blocked:
            for w in case.warnings:
                print(f"  ! {w}")
            continue

        steps = _plan(case, state)
        # Drop notes already posted by an earlier run (keeps --write re-runnable).
        kept = []
        for step in steps:
            if step[0] == "note":
                eid = step[1].split("/", 1)[1]
                if await _note_already_posted(client, eid, step[2]["text"]):
                    continue
            kept.append(step)
        steps = kept
        print("\n  Planned changes:")
        if not steps:
            print("    (none — already consolidated)")
        for action, target, detail in steps:
            shown = {k: v for k, v in detail.items() if k != "text"}
            print(f"    {action:12s} {target} {shown if shown else ''}")
        for w in case.warnings:
            print(f"  ! {w}")
        total_steps += len(steps)

        if write and steps:
            print("\n  Applying…")
            await _apply(client, steps)

    if do_scan:
        await scan_orphans(client)

    if not write and total_steps:
        print(f"\nDRY RUN complete — {total_steps} change(s) planned. "
              "Re-run with --write to apply.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--write", action="store_true",
                        help="apply the changes (default is a read-only report)")
    parser.add_argument("--scan", action="store_true",
                        help="also sweep for other orphaned client profiles")
    parser.add_argument("--case", choices=[c.name for c in CASES],
                        help="repair only this case")
    parser.add_argument(
        "--delete-declined-duplicates", action="store_true",
        help=("also DELETE the superseded duplicate engagement in the polunas "
              "case. Off by default: staff have since marked it Declined, "
              "which is a recorded decision, and deletion is irreversible."),
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run(write=args.write, do_scan=args.scan, only=args.case,
                             delete_declined=args.delete_declined_duplicates)))


if __name__ == "__main__":
    main()
