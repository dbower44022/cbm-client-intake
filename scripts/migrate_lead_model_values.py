"""Move stored values to the lead model's words (ruling 45), once per CRM.

Runs after ``scripts/plans/coutreach-lead-model.json`` has added the new
fields and options (``coutreach-lead-model-crm-handoff.md`` § 4). It moves
what is stored today onto the words of rulings 41-50:

**On each lead (``CProspect``)**

* ``leadStatus`` — *Converted* when the lead has a converted Company or
  Contact (``promotedCompany`` / ``promotedContact``); *Disqualified* when it
  left by the old *Unqualified* reason; else from ``funnelStage``:
  Unverified → *Unqualified*, Qualified → *Qualified* **only when the lead
  holds a website or an email** (ruling 42: without one it can never be
  Qualified; ruling 53 lets a filing with one enter Qualified), else
  *Unqualified*. A lead at Lead, Warm
  Lead or Opportunity with no converted record has no rule (ruling 42: contact
  without a website or email converts nothing), so it is **reported, never
  written** — a human decides. The status is only ever raised from the default
  (empty or *Unqualified*), so a re-run after the code release never undoes a
  status the application set.
* ``sideExit`` — *Already known* → *Duplicate*; the old *Unqualified* reason is
  cleared (it became the *Disqualified* status above).
* ``leadSource`` — copied from ``entryDoor`` when empty (the three values are
  the same words).

**On Contact and Account** (``cFunnelStage``, ``cEntryStage``)

* Unverified, Qualified, Lead → *Prospect*; Warm Lead → *Engaged*;
  Opportunity stays. A Company or Contact carries a stage only because a lead
  was converted into it or a public form created it, so every old early stage
  means first contact happened (ruling 43).

**On each touch** (``COutreachTouch.stageAtTouch``, the position the target
held when touched — needs ``scripts/plans/coutreach-touch-positions.json``)

* A touch on a lead: Unverified → *Unqualified*; Qualified stays. Lead, Warm
  Lead or Opportunity on a lead has no rule and is **reported, never written**.
* A touch on a Company or Contact: the same moves as their stages above.

**Idempotent, dry-run by default, never removes an option or a field.** Runs as
the org-wide API key (its role edits ``CProspect``, Contact and Account) and
refuses to start when ``CProspect.leadStatus`` is missing. Ships in the image,
so production's copy runs from inside the deployed web container::

    cd /app && PYTHONPATH=/app .venv/bin/python scripts/migrate_lead_model_values.py           # dry run
    cd /app && PYTHONPATH=/app .venv/bin/python scripts/migrate_lead_model_values.py --apply   # apply

From the repository against crm-test the same commands read ``.env`` through
the application's settings. ``--url`` / ``--key`` override both. The dry run is
also the record count ruling 45 asks for before a CRM's script runs.

Exit codes: 0 done (or nothing to do), 1 a write or read-back failed or a lead
needs a decision, 2 the CRM lacks the fields or no credential, 3 the CRM could
not be reached.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.config import get_settings  # noqa: E402
from core.espo import EspoClient, EspoError  # noqa: E402

LEAD = "CProspect"
PAGE = 200

STATUS_FROM_STAGE = {"Unverified": "Unqualified", "Qualified": "Qualified"}
TOUCH = "COutreachTouch"
LEAD_TOUCH_MOVES = {"Unverified": "Unqualified"}
#: Old values a touch on a lead may hold that no rule maps (reported only).
LEAD_TOUCH_UNMAPPED = ("Lead", "Warm Lead", "Opportunity")
EXIT_MOVES = {"Already known": "Duplicate", "Unqualified": ""}
STAGE_MOVES = {"Unverified": "Prospect", "Qualified": "Prospect", "Lead": "Prospect",
               "Warm Lead": "Engaged"}
#: (entity, stored field) pairs whose stage values move.
STAGE_FIELDS = (("Contact", "cFunnelStage"), ("Contact", "cEntryStage"),
                ("Account", "cFunnelStage"), ("Account", "cEntryStage"))


async def read_all(client: Any, entity: str, select: str, where: list | None = None) -> list[dict[str, Any]]:
    """Every matching row, read before any write so paging cannot skip rows."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = await client.list(entity, select=select, max_size=PAGE, offset=offset,
                                 where=where or [], order_by="createdAt", order="asc")
        page = data.get("list", [])
        rows.extend(page)
        offset += len(page)
        if len(page) < PAGE or offset >= int(data.get("total") or 0):
            return rows


def lead_changes(row: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """The writes one lead needs, and a reason when it needs a human instead."""
    out: dict[str, Any] = {}
    note = None
    current = row.get("leadStatus") or ""
    exit_now = row.get("sideExit") or ""
    if row.get("promotedCompanyId") or row.get("promotedContactId"):
        target = "Converted"
    elif exit_now == "Unqualified":
        target = "Disqualified"
    else:
        target = STATUS_FROM_STAGE.get(row.get("funnelStage") or "")
        if target == "Qualified" and not (row.get("website") or row.get("email")):
            target = "Unqualified"   # ruling 42: no website or email, never Qualified
        if target is None and row.get("funnelStage"):
            note = (f"stage {row.get('funnelStage')!r} with no converted record — "
                    "no rule (ruling 42); decide its status by hand")
    if target and current in ("", "Unqualified") and target != current:
        out["leadStatus"] = target
    if exit_now in EXIT_MOVES:
        out["sideExit"] = EXIT_MOVES[exit_now]
    if not row.get("leadSource") and row.get("entryDoor"):
        out["leadSource"] = row["entryDoor"]
    return out, note


async def run(client: Any, *, apply: bool) -> int:
    if await client.metadata_enum_options(LEAD, "leadStatus") is None:
        print(f"{LEAD}.leadStatus does not exist on this CRM - apply "
              "scripts/plans/coutreach-lead-model.json first.", file=sys.stderr)
        return 2
    done: list[str] = []
    decide: list[str] = []
    failed: list[str] = []

    leads = await read_all(client, LEAD, "id,name,funnelStage,sideExit,entryDoor,leadStatus,"
                                         "leadSource,promotedCompanyId,promotedContactId,website,email")
    print(f"{LEAD}: {len(leads)} record(s)")
    for row in leads:
        changes, note = lead_changes(row)
        label = f"{LEAD} {row.get('name')!r}"
        if note:
            decide.append(f"{label}: {note}")
        if changes:
            await write(client, LEAD, row["id"], changes, label, apply, done, failed)

    for entity, field in STAGE_FIELDS:
        rows = await read_all(client, entity, f"id,name,{field}",
                              [{"type": "in", "attribute": field, "value": list(STAGE_MOVES)}])
        print(f"{entity}.{field}: {len(rows)} record(s) on an old stage")
        for row in rows:
            await write(client, entity, row["id"], {field: STAGE_MOVES[row[field]]},
                        f"{entity} {row.get('name')!r}", apply, done, failed)

    await move_touches(client, apply=apply, done=done, decide=decide, failed=failed)

    print()
    for title, rows in (("CHANGES", done), ("NEEDS A DECISION (not written)", decide), ("FAILED", failed)):
        if rows:
            print(f"{title}:")
            for line in rows:
                print(f"  {'!' if title != 'CHANGES' else '-'} {line}")
            print()
    if not done and not decide and not failed:
        print("Nothing to do - every record already carries the lead model's words.")
    if not apply:
        print(f"Dry run only. {len(done)} record(s) would change. Re-run with --apply to make these changes.")
    return 1 if (failed or decide) else 0


def touch_change(row: dict[str, Any]) -> tuple[str | None, str | None]:
    """The new ``stageAtTouch`` for one touch, and a note when no rule maps it."""
    value = row.get("stageAtTouch") or ""
    if row.get("prospectId"):
        if value in LEAD_TOUCH_MOVES:
            return LEAD_TOUCH_MOVES[value], None
        if value in LEAD_TOUCH_UNMAPPED:
            return None, f"a touch on a lead recorded {value!r} — no rule maps it; decide by hand"
        return None, None
    return STAGE_MOVES.get(value), None


async def move_touches(client: Any, *, apply: bool, done: list[str], decide: list[str],
                       failed: list[str]) -> None:
    old = sorted(set(STAGE_MOVES) | set(LEAD_TOUCH_MOVES) | set(LEAD_TOUCH_UNMAPPED))
    rows = await read_all(client, TOUCH, "id,name,stageAtTouch,prospectId",
                          [{"type": "in", "attribute": "stageAtTouch", "value": old}])
    print(f"{TOUCH}.stageAtTouch: {len(rows)} record(s) on an old value")
    if not rows:
        return
    options = await client.metadata_enum_options(TOUCH, "stageAtTouch") or []
    missing = [o for o in ("Unqualified", "Prospect", "Engaged") if o not in options]
    if missing:
        decide.append(f"{TOUCH}.stageAtTouch lacks {', '.join(missing)} - apply "
                      "scripts/plans/coutreach-touch-positions.json first; no touch written")
        return
    for row in rows:
        new, note = touch_change(row)
        label = f"{TOUCH} {row.get('name')!r}"
        if note:
            decide.append(f"{label}: {note}")
        if new and new != row.get("stageAtTouch"):
            await write(client, TOUCH, row["id"], {"stageAtTouch": new}, label, apply, done, failed)


async def write(client: Any, entity: str, rid: str, changes: dict[str, Any], label: str,
                apply: bool, done: list[str], failed: list[str]) -> None:
    shown = ", ".join(f"{k} <- {v!r}" for k, v in changes.items())
    if not apply:
        done.append(f"WOULD set {label}: {shown}")
        return
    try:
        await client.update(entity, rid, changes)
        back = await client.get(entity, rid, select="id," + ",".join(changes))
        wrong = {k: back.get(k) for k, v in changes.items() if (back.get(k) or "") != (v or "")}
        if wrong:
            failed.append(f"{label}: read-back is {wrong!r}")
        else:
            done.append(f"set {label}: {shown} - read back OK")
    except EspoError as exc:
        failed.append(f"{label}: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Move stored values to the lead model's words, once.")
    ap.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    ap.add_argument("--url", default=os.environ.get("ESPO_BASE_URL"))
    ap.add_argument("--key", default=os.environ.get("ESPO_API_KEY"))
    args = ap.parse_args()
    url, key = args.url, args.key
    if not (url and key):
        s = get_settings()
        url, key = url or s.espo_base_url, key or s.espo_api_key
    if not (url and key):
        print("No CRM address or key (ESPO_BASE_URL / ESPO_API_KEY).", file=sys.stderr)
        return 2
    print(f"CRM:  {url}")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN - nothing will change'}\n")
    client = EspoClient(url, key, 30)
    try:
        return asyncio.run(run(client, apply=args.apply))
    except EspoError as exc:
        print(f"Could not complete: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
