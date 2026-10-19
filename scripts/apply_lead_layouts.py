"""The lead's CRM screens on the lead model's fields
(``coutreach-lead-model-crm-handoff.md`` § 7), once per CRM, with the code release.

The lead's (``CProspect``) list and detail layouts were built on the fields the
lead model retires. At the code release they move to the fields it writes:

* **List**: ``funnelStage`` → ``leadStatus``, ``entryDoor`` → ``leadSource``
  (the columns become name, Lead status, Lead Source, the reason, website).
* **Detail**: ``funnelStage`` → ``leadStatus``, ``entryStage`` →
  ``leadStatusChangedAt``, ``entryDoor`` → ``leadSource``; ``stageChangedAt``
  is taken off (its cell left empty) — the status carries its own stamp.

Each retired field is replaced where it stands, so staff find the new field in
the old one's place; a layout that already carries the new field is left alone
(idempotent). Nothing else on either layout changes. Dry run by default; needs
an Admin-type login (``ESPO_ADMIN_BASE`` / ``_USER`` / ``_PASS``; inside a
container they are exported from the provisioning admin). Refuses to start when
``CProspect.leadStatus`` is missing — apply ``scripts/plans/coutreach-lead-model.json``
first.

    PYTHONPATH=. uv run python scripts/run_with_admin.py scripts/apply_lead_layouts.py          # dry run
    ... scripts/apply_lead_layouts.py --apply

Exit codes: 0 done (or nothing to do), 1 a write or read-back failed, 2 the CRM
lacks the fields or no admin credential.

Revision 1.0 · 10-19-26 · Claude (Claude Code), for D. Bower — first version,
written with the lead-model code release (build plan § 7a.5 step 2).
"""
from __future__ import annotations

import asyncio
import copy
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

LEAD = "CProspect"
#: retired field -> its replacement (None: the cell is emptied).
DETAIL_MOVES: dict[str, str | None] = {
    "funnelStage": "leadStatus",
    "entryStage": "leadStatusChangedAt",
    "entryDoor": "leadSource",
    "stageChangedAt": None,
}
LIST_MOVES: dict[str, str] = {"funnelStage": "leadStatus", "entryDoor": "leadSource"}
NEW_FIELDS = ("leadStatus", "leadStatusChangedAt", "leadSource")


def detail_fields(layout: Any) -> set[str]:
    out: set[str] = set()
    for panel in layout or []:
        for row in (panel or {}).get("rows") or []:
            for cell in row or []:
                if isinstance(cell, dict) and cell.get("name"):
                    out.add(cell["name"])
    return out


def rewrite_detail(layout: Any) -> tuple[list[Any], list[str]]:
    """The detail layout with each retired field replaced in place, and what
    changed. A replacement the layout already carries is not added twice: the
    retired cell is emptied instead."""
    new = copy.deepcopy(list(layout or []))
    have = detail_fields(new)
    changes: list[str] = []
    for panel in new:
        for row in (panel or {}).get("rows") or []:
            for i, cell in enumerate(row or []):
                if not (isinstance(cell, dict) and cell.get("name") in DETAIL_MOVES):
                    continue
                old = cell["name"]
                repl = DETAIL_MOVES[old]
                if repl and repl not in have:
                    row[i] = {"name": repl}
                    have.add(repl)
                    changes.append(f"detail: {old} -> {repl}")
                else:
                    row[i] = False
                    changes.append(f"detail: {old} removed")
    missing = [f for f in NEW_FIELDS if f not in have]
    if missing:
        rows, pair = [], []
        for f in missing:
            pair.append({"name": f})
            if len(pair) == 2:
                rows.append(pair)
                pair = []
        if pair:
            rows.append(pair + [False])
        new.append({"label": "Lead", "rows": rows})
        changes.append(f"detail: add {', '.join(missing)} in a Lead panel")
    return new, changes


def rewrite_list(cols: Any) -> tuple[list[Any], list[str]]:
    """The list layout with each retired column replaced in place."""
    new = copy.deepcopy([c for c in (cols or []) if isinstance(c, dict)])
    names = {c.get("name") for c in new}
    out: list[Any] = []
    changes: list[str] = []
    for c in new:
        old = c.get("name")
        if old in LIST_MOVES:
            repl = LIST_MOVES[old]
            if repl in names:
                changes.append(f"list: {old} removed")
                continue
            out.append({**c, "name": repl})
            names.add(repl)
            changes.append(f"list: {old} -> {repl}")
        else:
            out.append(c)
    for repl in LIST_MOVES.values():
        if repl not in {c.get("name") for c in out}:
            out.append({"name": repl})
            changes.append(f"list: add {repl}")
    return out, changes


async def run(apply: bool) -> int:
    from espo_admin import connect, load_env  # noqa: E402  (scripts/ on sys.path)

    client, profile = await connect(load_env())
    if profile.get("type") != "admin":
        print(f"{profile.get('userName')} is type={profile.get('type')}; this needs an Admin-type account.")
        return 2
    base = client._base
    print(f"CRM:  {base}\nUser: {profile.get('userName')} (type=admin)\n"
          f"Mode: {'APPLY' if apply else 'DRY RUN - nothing will change'}\n")
    fields = await client._request("GET", f"{base}/Metadata", op="m",
                                   params={"key": f"entityDefs.{LEAD}.fields"})
    have = fields.json() if fields.status_code == 200 and fields.content else {}
    if not isinstance(have, dict) or any(f not in have for f in NEW_FIELDS):
        print(f"{LEAD} lacks {', '.join(NEW_FIELDS)} - apply scripts/plans/coutreach-lead-model.json first.")
        return 2

    changes: list[str] = []
    failed: list[str] = []
    r = await client._request("GET", f"{base}/{LEAD}/layout/detail", op="layout")
    detail = r.json() if r.status_code == 200 else []
    new_detail, dchanges = rewrite_detail(detail)
    changes += dchanges
    if dchanges and apply:
        w = await client._request("PUT", f"{base}/{LEAD}/layout/detail", op="layout", json_body=new_detail)
        back = await client._request("GET", f"{base}/{LEAD}/layout/detail", op="layout")
        got = detail_fields(back.json() if back.status_code == 200 else [])
        if w.status_code >= 300 or any(f not in got for f in NEW_FIELDS) or got & {"funnelStage", "entryStage", "entryDoor"}:
            failed.append(f"{LEAD} detail layout -> HTTP {w.status_code}; read-back holds {sorted(got)}")

    r = await client._request("GET", f"{base}/{LEAD}/layout/list", op="layout")
    cols = r.json() if r.status_code == 200 and isinstance(r.json(), list) else []
    new_cols, lchanges = rewrite_list(cols)
    changes += lchanges
    if lchanges and apply:
        w = await client._request("PUT", f"{base}/{LEAD}/layout/list", op="layout", json_body=new_cols)
        back = await client._request("GET", f"{base}/{LEAD}/layout/list", op="layout")
        names = {c.get("name") for c in (back.json() if back.status_code == 200 else []) if isinstance(c, dict)}
        if w.status_code >= 300 or not {"leadStatus", "leadSource"} <= names or names & set(LIST_MOVES):
            failed.append(f"{LEAD} list layout -> HTTP {w.status_code}; read-back holds {sorted(n for n in names if n)}")

    if apply and changes:
        await client._request("POST", f"{base}/Admin/clearCache", op="cache", json_body={})
    if changes:
        print(f"{'CHANGED' if apply else 'WOULD CHANGE'}:")
        for c in changes:
            print(f"  - {c}")
    else:
        print("Nothing to do - the lead's layouts already carry the lead model's fields.")
    if failed:
        print("FAILED:")
        for f in failed:
            print(f"  ! {f}")
    if not apply and changes:
        print("\nDry run only. Re-run with --apply to make these changes.")
    return 1 if failed else 0


def main() -> int:
    sys.path.insert(0, str(REPO / "scripts"))
    return asyncio.run(run("--apply" in sys.argv))


if __name__ == "__main__":
    raise SystemExit(main())
